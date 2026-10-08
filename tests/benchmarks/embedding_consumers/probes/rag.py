"""rag_first_stage and owui_attachment_rag.

rag_first_stage drives scripts/rag_retrieval_eval.py on the full labelled corpus from
``tests/fixtures/rag_eval_corpus/manifest.yaml`` (13 public NERC CIP standards, the NIST SP 800-82r3
architecture slice and the 9 synthetic figure-only PDFs; the operator ``internal`` distractors are
not on this host) with every query in ``queries.yaml`` (prose_only, diagram_only, mixed). Incumbent:
the VL server (:8942, 2048d) with the shipped fusion. Candidate: the retrieval seam pointed at EG2
by env (VL_RETRIEVAL_URL=:8946/vl, VL_EMBEDDING_DIM=768; rerank still forwards to the VL reranker).

``VL_TEXT_GATE`` (0.72) is an ABSOLUTE cosine threshold calibrated on Qwen3-VL's similarity scale.
EG2's text cosines sit higher, so reusing 0.72 suppresses the visual boost for most diagram queries
(the 2026-10-07 0.391 result). The candidate therefore gets its own gate, derived label-free by
quantile matching: the incumbent's top-text-sim distribution over the query set says what share of
queries 0.72 gates; the EG2 gate is the cut that gates the same share of EG2's distribution. The
run at the incumbent's 0.72 is kept as a diagnostic. First-stage recall (target file in the top-5
text or visual rows, before fusion/rerank) is reported separately from the fused result.
Pass ``--opt rag_inc=PATH --opt rag_cand=PATH`` to reuse stored eval JSONs.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx
import yaml

from portal.platform.embedding.contract import Role, Task

from ..framework import (
    MEASURED,
    REPO_ROOT,
    ProbeContext,
    ProbeResult,
    blocked,
    compare,
    fixture_digest,
    probe,
    recall_at_k,
)
from ._common import DATA, historical_incumbent

SCRATCH = Path("/Volumes/data01/portal5_scratch_eg2")
FIX = REPO_ROOT / "tests" / "fixtures" / "rag_eval_corpus"
CIP_PDFS = REPO_ROOT / "portal" / "modules" / "compliance" / "data" / "cip_pdfs"
INCUMBENT_GATE = 0.72
INC_EMBED = "http://localhost:8942/embed"
CAND_EMBED = "http://localhost:8946/vl/embed"


def _build_synthetic(dest: Path) -> None:
    readme = (FIX / "README.md").read_text()
    code = re.search(r"```python\n(.*?)```", readme[readme.index("## Synthetic builder") :], re.S)
    if not code:
        raise RuntimeError("synthetic builder not found in the fixture README")
    script = dest.parent / "build_synthetic.py"
    script.write_text(code.group(1))
    subprocess.run(
        [str(REPO_ROOT / ".venv" / "bin" / "python"), str(script), str(dest)],
        check=True,
        capture_output=True,
    )


def _assemble_corpus(dest: Path) -> list[str]:
    """Manifest ``public`` entries (local compliance copy first, else the manifest URL) plus the
    synthetic builder."""
    import pymupdf

    dest.mkdir(parents=True, exist_ok=True)
    manifest = yaml.safe_load((FIX / "manifest.yaml").read_text())
    for ent in manifest["public"]:
        out = dest / ent["file"]
        if out.is_file():
            continue
        local = CIP_PDFS / ent["file"]
        if local.is_file() and "slice" not in ent:
            shutil.copy2(local, out)
            continue
        raw = dest.parent / "dl" / Path(ent["url"]).name
        if not raw.is_file():
            raw.parent.mkdir(parents=True, exist_ok=True)
            r = httpx.get(ent["url"], follow_redirects=True, timeout=300)
            r.raise_for_status()
            raw.write_bytes(r.content)
        if "slice" in ent:
            a, b = (int(x) for x in ent["slice"].split("-"))
            src, sl = pymupdf.open(raw), pymupdf.open()
            sl.insert_pdf(src, from_page=a, to_page=b)
            sl.save(out)
        else:
            shutil.copy2(raw, out)
    _build_synthetic(dest)
    return sorted(p.name for p in dest.glob("*.pdf"))


def _eval(
    corpus: Path,
    queries: Path,
    lance: Path,
    out: Path,
    env_extra: dict[str, str],
    *,
    reuse: bool = False,
    fusion: str = "rrf",
    cached: bool = False,
) -> dict[str, Any]:
    if cached and out.is_file():
        return json.loads(out.read_text())
    if lance.exists() and not reuse:
        shutil.rmtree(lance)
    env = {**os.environ, **env_extra}
    r = subprocess.run(
        [
            str(REPO_ROOT / ".venv" / "bin" / "python"),
            "scripts/rag_retrieval_eval.py",
            str(corpus),
            str(queries),
            "--lance-dir",
            str(lance),
            "--out",
            str(out),
            "--fusion",
            fusion,
            *(["--reuse"] if reuse else []),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=4 * 3600,
        check=False,
    )
    if r.returncode or not out.is_file():
        raise RuntimeError(f"rag_retrieval_eval failed: {r.stderr[-300:]}")
    return json.loads(out.read_text())


def _first_stage(lance: Path, embed_url: str, queries: list[dict[str, Any]]) -> dict[str, Any]:
    """Per query: top text cosine (the gate's input) and whether an accepted target file is in the
    top-5 text or visual rows of the raw dense search (before fusion and rerank)."""
    import lancedb

    db = lancedb.connect(str(lance / "rag"))
    ttbl, vtbl = db.open_table("kb_ragEval"), db.open_table("kb_ragEval_visual")
    sims: list[float] = []
    hits: dict[str, list[bool]] = {}
    with httpx.Client(timeout=300) as c:
        for q in queries:
            r = c.post(embed_url, json={"text": q["query"], "is_query": True})
            r.raise_for_status()
            v = r.json()["embedding"]
            trows = ttbl.search(v).limit(5).to_list()
            vrows = vtbl.search(v).limit(5).to_list()
            sims.append(max(0.0, 1.0 - trows[0]["_distance"] / 2.0) if trows else 0.0)
            ok = {q["target_file"], *q.get("also_accept", [])}
            rows = [*trows, *vrows]
            hits.setdefault(q["category"], []).append(
                any(Path(x["source_file"]).name in ok for x in rows)
            )
    return {
        "top_text_sims": [round(s, 4) for s in sims],
        "recall@5_by_category": {k: round(sum(v) / len(v), 4) for k, v in hits.items()},
    }


def _matched_gate(inc_sims: list[float], cand_sims: list[float], tau: float) -> float:
    """The cut on ``cand_sims`` that gates the same number of queries ``tau`` gates on
    ``inc_sims`` (label-free; the gate fires when sim < tau)."""
    n_fire = sum(s < tau for s in inc_sims)
    c = sorted(cand_sims)
    if n_fire <= 0:
        return round(c[0] - 1e-4, 4)
    if n_fire >= len(c):
        return round(c[-1] + 1e-4, 4)
    return round((c[n_fire - 1] + c[n_fire]) / 2, 4)


def _flat(rep: dict[str, Any]) -> dict[str, Any]:
    s = rep["summary"]
    n = sum(v["n"] for v in s.values())
    return {
        "recall@1": round(sum(v["recall@1"] * v["n"] for v in s.values()) / n, 4),
        "recall@5": round(sum(v["recall@5"] * v["n"] for v in s.values()) / n, 4),
        "mrr": round(sum(v["mrr"] * v["n"] for v in s.values()) / n, 4),
        "by_category": s,
        "ingest_s": rep["ingest"].get("_ingest_s"),
        "chunks": rep["ingest"].get("chunks_added"),
        "pages": rep["ingest"].get("pages_added"),
        "queries": n,
    }


@probe("rag_first_stage")
async def rag_first_stage(ctx: ProbeContext) -> ProbeResult:
    inc_p, cand_p = ctx.opt("rag_inc"), ctx.opt("rag_cand")
    extra: dict[str, Any] = {}
    if inc_p and cand_p:
        inc_rep, cand_rep = (
            json.loads(Path(inc_p).read_text()),
            json.loads(Path(cand_p).read_text()),
        )
    else:
        if not ctx.live:
            return blocked("rag_first_stage", "needs --live (VL server :8942 + EG2 :8946, ~2 h)")
        work = SCRATCH / "rag_full"
        files = _assemble_corpus(work / "corpus")
        q = yaml.safe_load((FIX / "queries.yaml").read_text())
        q["queries"] = [x for x in q["queries"] if x["target_file"] in files]
        qf = work / "queries.yaml"
        qf.write_text(yaml.safe_dump(q))
        cand_env = {"VL_RETRIEVAL_URL": "http://localhost:8946/vl", "VL_EMBEDDING_DIM": "768"}
        # rag_reuse=1: keep existing lance dirs and eval JSONs (re-scores only what is missing)
        keep = ctx.opt("rag_reuse") == "1"
        inc_rep = _eval(
            work / "corpus", qf, work / "lance_inc", work / "inc.json", {}, reuse=keep, cached=keep
        )
        # ingest once at the incumbent gate (diagnostic run), then re-score at EG2's own gate
        cand_rep_0 = _eval(
            work / "corpus",
            qf,
            work / "lance_cand",
            work / "cand_g072.json",
            cand_env,
            reuse=keep,
            cached=keep,
        )
        fs_inc = _first_stage(work / "lance_inc", INC_EMBED, q["queries"])
        fs_cand = _first_stage(work / "lance_cand", CAND_EMBED, q["queries"])
        gate = _matched_gate(fs_inc["top_text_sims"], fs_cand["top_text_sims"], INCUMBENT_GATE)
        cand_rep = _eval(
            work / "corpus",
            qf,
            work / "lance_cand",
            work / "cand.json",
            {**cand_env, "VL_TEXT_GATE": str(gate)},
            reuse=True,
            cached=keep,
        )
        # no-reranker arms: can the VL reranker be retired too? (eval's embed_sim strategy orders
        # the visual arm by embedding cosine and never calls the reranker)
        inc_norr = _eval(
            work / "corpus",
            qf,
            work / "lance_inc",
            work / "inc_embed_sim.json",
            {},
            reuse=True,
            fusion="embed_sim",
            cached=keep,
        )
        cand_norr = _eval(
            work / "corpus",
            qf,
            work / "lance_cand",
            work / "cand_embed_sim.json",
            cand_env,
            reuse=True,
            fusion="embed_sim",
            cached=keep,
        )
        extra = {
            "inc_first_stage": fs_inc,
            "cand_first_stage": fs_cand,
            "cand_gate": gate,
            "cand_at_incumbent_gate": _flat(cand_rep_0),
            "inc_no_reranker": _flat(inc_norr),
            "cand_no_reranker": _flat(cand_norr),
        }
    if "error" in cand_rep.get("ingest", {}) or "error" in inc_rep.get("ingest", {}):
        return blocked(
            "rag_first_stage",
            f"ingest error: {cand_rep.get('ingest') if 'error' in cand_rep.get('ingest', {}) else inc_rep.get('ingest')}",
        )
    inc, cand = _flat(inc_rep), _flat(cand_rep)
    return ProbeResult(
        "rag_first_stage",
        MEASURED,
        {
            "primary": inc["recall@1"],
            **inc,
            "gate": INCUMBENT_GATE,
            **(
                {"first_stage": extra["inc_first_stage"], "no_reranker": extra["inc_no_reranker"]}
                if extra
                else {}
            ),
        },
        {
            "primary": cand["recall@1"],
            **cand,
            **(
                {
                    "gate": extra["cand_gate"],
                    "first_stage": extra["cand_first_stage"],
                    "at_incumbent_gate_0.72": extra["cand_at_incumbent_gate"],
                    "no_reranker": extra["cand_no_reranker"],
                }
                if extra
                else {}
            ),
        },
        compare(inc["recall@1"], cand["recall@1"]),
        fixture={
            "docs": inc_rep["n_docs"],
            "queries": inc["queries"],
            "corpus": "manifest public (13 NERC CIP + NIST 800-82r3 arch slice) + 9 synthetic figure-only PDFs; operator internal distractors not on this host",
            "sha": fixture_digest(inc["by_category"]),
        },
        identity=await ctx.client.version_tag(768),
        notes=[
            "primary = fused recall@1 over all categories; final ranking is after the VL rerank in both arms (the reranker is unchanged)",
            "candidate gate = label-free quantile match of the incumbent's 0.72 onto EG2's top-text-sim distribution; the 0.72 run is kept as a diagnostic",
            "first_stage = target file in the raw top-5 text or visual rows, before fusion/rerank",
            "no_reranker = eval --fusion embed_sim (visual arm by embedding cosine, no VL rerank call); answers whether the Qwen3-VL reranker can be retired with the embedder",
        ],
    )


# ── owui_attachment_rag ─────────────────────────────────────────────────────

#: Live Open WebUI retrieval settings (webui.db ``rag.*`` keys, read 2026-10-07): markdown-header
#: splitter then 1500/100 character chunks, hybrid search (BM25 + dense, ensemble weight 0.5),
#: top_k 3 per retriever, reranked to top_k_reranker 3 by bge-reranker-v2-m3.
OWUI_CHUNK, OWUI_OVERLAP, OWUI_TOP_K, OWUI_TOP_K_RERANK, OWUI_BM25_W = 1500, 100, 3, 3, 0.5
EG2_OWUI = "http://localhost:8946/v1/embeddings"
HF_CACHE = "/Volumes/data01/hf-cache"
EG2_PY = Path.home() / ".portal5" / "eg2-venv" / "bin" / "python3"

_BGE = """
import json, sys
from sentence_transformers import CrossEncoder
m = CrossEncoder("BAAI/bge-reranker-v2-m3")
rows = json.load(open(sys.argv[1]))
json.dump([[float(s) for s in m.predict([[r["q"], d] for d in r["docs"]])] for r in rows],
          open(sys.argv[2], "w"))
"""


def _owui_chunks(body: str) -> list[str]:
    """Markdown-header split, then fixed 1500-char windows with 100 overlap (OWUI's
    RecursiveCharacterTextSplitter on prose this size reduces to the same windows)."""
    parts = re.split(r"(?m)^(?=#{1,6} )", body)
    out: list[str] = []
    step = OWUI_CHUNK - OWUI_OVERLAP
    for part in parts:
        part = part.strip()
        for i in range(0, max(1, len(part)), step):
            c = part[i : i + OWUI_CHUNK]
            if c.strip():
                out.append(c)
            if i + OWUI_CHUNK >= len(part):
                break
    return out


class _BM25:
    """Okapi BM25 (k1 1.5, b 0.75, whitespace tokens): rank_bm25's defaults, which is what
    langchain's BM25Retriever (OWUI's hybrid arm) uses."""

    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        import math as _m

        self.toks = [d.split() for d in docs]
        self.k1, self.b = k1, b
        self.avg = sum(map(len, self.toks)) / len(self.toks)
        df: dict[str, int] = {}
        for t in self.toks:
            for w in set(t):
                df[w] = df.get(w, 0) + 1
        n = len(docs)
        self.idf = {w: _m.log((n - f + 0.5) / (f + 0.5) + 1) for w, f in df.items()}
        self.tf = [{w: t.count(w) for w in set(t)} for t in self.toks]

    def top(self, q: str, k: int) -> list[int]:
        qs = q.split()
        sc = []
        for i, tf in enumerate(self.tf):
            ln = len(self.toks[i])
            s = 0.0
            for w in qs:
                f = tf.get(w, 0)
                if f:
                    s += (
                        self.idf[w]
                        * f
                        * (self.k1 + 1)
                        / (f + self.k1 * (1 - self.b + self.b * ln / self.avg))
                    )
            sc.append(s)
        return sorted(range(len(sc)), key=lambda i: -sc[i])[:k]


def _ensemble(bm25: list[int], dense: list[int], w_bm25: float) -> list[int]:
    """langchain EnsembleRetriever: weighted reciprocal rank fusion, c = 60."""
    score: dict[int, float] = {}
    for w, lst in ((w_bm25, bm25), (1 - w_bm25, dense)):
        for r, i in enumerate(lst):
            score[i] = score.get(i, 0.0) + w / (r + 60)
    return sorted(score, key=lambda i: -score[i])


async def _eg2_owui_embed(texts: list[str], role: Role) -> list[list[float]]:
    """EG2 behind OWUI's openai engine with the contract prefixes configured in OWUI
    (RAG_EMBEDDING_QUERY_PREFIX / RAG_EMBEDDING_CONTENT_PREFIX): what a repoint would serve."""
    import httpx as _h

    from portal.platform.embedding.contract import format_text

    out: list[list[float]] = []
    async with _h.AsyncClient(timeout=600) as c:
        for i in range(0, len(texts), 32):
            batch = [format_text(t, Task.SEARCH, role) for t in texts[i : i + 32]]
            r = await c.post(EG2_OWUI, json={"input": batch})
            r.raise_for_status()
            out += [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]
    return out


def _bge_scores(pairs: list[dict[str, Any]]) -> list[list[float]]:
    with tempfile.TemporaryDirectory() as td:
        i, o, sc = Path(td) / "in.json", Path(td) / "out.json", Path(td) / "bge.py"
        i.write_text(json.dumps(pairs))
        sc.write_text(_BGE)
        r = subprocess.run(
            [str(EG2_PY), str(sc), str(i), str(o)],
            capture_output=True,
            text=True,
            env={"HF_HUB_CACHE": HF_CACHE, "PATH": "/usr/bin:/bin", "HOME": str(Path.home())},
            timeout=7200,
        )
        if r.returncode:
            raise RuntimeError(r.stderr[-300:])
        return json.loads(o.read_text())


@probe("owui_attachment_rag")
async def owui_attachment_rag(ctx: ProbeContext) -> ProbeResult:  # noqa: C901, PLR0915
    import httpx

    from portal.platform.wiki.store import load_all

    qs = json.loads((DATA / "wiki_queries.json").read_text())["rows"]
    units = [u for u in load_all() if u.body]
    owner, texts = [], []
    for u in units:
        for c in _owui_chunks(f"# {u.title}\n{u.body}"):
            owner.append(u.id)
            texts.append(c)
    gold = [q["expected_unit_ids"] for q in qs]
    queries = [q["query"] for q in qs]
    bm25 = _BM25(texts)
    bm_top = [bm25.top(q, OWUI_TOP_K) for q in queries]

    import numpy as np

    dense = None
    dv = await _eg2_owui_embed(texts, Role.DOCUMENT)
    qv = await _eg2_owui_embed(queries, Role.QUERY)
    d = np.asarray(dv, dtype=np.float32)
    d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-9
    qm = np.asarray(qv, dtype=np.float32)
    qm /= np.linalg.norm(qm, axis=1, keepdims=True) + 1e-9
    dense = [np.argsort(-(d @ qm[i]))[:OWUI_TOP_K].tolist() for i in range(len(queries))]
    pool = [_ensemble(b, dd, OWUI_BM25_W) for b, dd in zip(bm_top, dense, strict=True)]

    def units_of(idx: list[int]) -> list[str]:
        seen: list[str] = []
        for i in idx:
            if owner[i] not in seen:
                seen.append(owner[i])
        return seen

    def score(ranked: list[list[int]]) -> dict[str, float]:
        u = [units_of(r[:OWUI_TOP_K_RERANK]) for r in ranked]
        return {"recall@3": round(recall_at_k(u, gold, OWUI_TOP_K_RERANK), 4)}

    notes: list[str] = []
    r: dict[str, Any] = {
        "dense_only": score(dense),
        "hybrid_no_rerank": score(pool),
    }
    bge = ctx.live and ctx.opt("owui_bge", "1") == "1"
    if bge:
        try:
            sc = _bge_scores(
                [
                    {"q": q, "docs": [texts[i] for i in p]}
                    for q, p in zip(queries, pool, strict=True)
                ]
            )
            r["hybrid_bge"] = score(
                [[p[j] for j in np.argsort(-np.asarray(s))] for p, s in zip(pool, sc, strict=True)]
            )
        except Exception as e:  # noqa: BLE001
            notes.append(f"bge arm failed: {type(e).__name__}: {str(e)[:200]}")
    if ctx.live:
        rer = []
        async with httpx.AsyncClient(timeout=600) as c:
            for q, p in zip(queries, pool, strict=True):
                rr = await c.post(
                    "http://localhost:8946/v1/rerank",
                    json={
                        "model": "x",
                        "query": q,
                        "documents": [texts[i] for i in p],
                        "top_n": len(p),
                    },
                )
                rr.raise_for_status()
                order = sorted(rr.json()["results"], key=lambda x: -x["relevance_score"])
                rer.append([p[x["index"]] for x in order])
        r["hybrid_vl_rerank"] = score(rer)
    # the :8917 arm is retired; its committed scorecard block is the incumbent
    hist = {
        k: v for k, v in historical_incumbent("owui_attachment_rag").items() if k != "provenance"
    }
    key = "hybrid_bge" if "hybrid_bge" in r else "hybrid_no_rerank"
    inc_primary = hist[key]["recall@3"]
    cand_primary = r[key]["recall@3"]
    return ProbeResult(
        "owui_attachment_rag",
        MEASURED,
        {"primary": inc_primary, **hist},
        {"primary": cand_primary, **r},
        compare(inc_primary, cand_primary),
        fixture={"queries": len(qs), "chunks": len(texts), "units": len(units)},
        identity=await ctx.client.version_tag(768),
        notes=[
            f"primary = {key} recall@3 in both arms (OWUI production pipeline: header split, 1500/100 chunks, BM25+dense ensemble w=0.5, top_k 3, rerank to 3)",
            "incumbent = FIXED historical :8917 arm (reports/embedding_consumers/20261008T021720Z, service retired at the EG2 cutover) — same-fixture comparison, not a fresh paired run",
            "corpus = wiki canonical units with the 47 authored wiki queries (no operator attachments on this host); bge-reranker-v2-m3 runs on the host (same model OWUI loads in-container)",
            "EG2 arm = :8946 OpenAI endpoint with contract prefixes applied as OWUI's RAG_EMBEDDING_*_PREFIX settings would",
            *notes,
        ],
    )
