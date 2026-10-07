"""rag_first_stage and owui_attachment_rag.

rag_first_stage drives scripts/rag_retrieval_eval.py twice on the synthetic control set (9 two-page
PDFs whose answers exist ONLY on the figure): once against the incumbent VL server (:8942, 2048d)
and once with the retrieval seam pointed at EG2 by env alone (VL_RETRIEVAL_URL=:8946/vl,
VL_EMBEDDING_DIM=768; the rerank still forwards to the VL reranker). Pass
``--opt rag_inc=PATH --opt rag_cand=PATH`` to reuse stored eval JSONs.
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
    top_k_by_cosine,
)
from ._common import DATA, legacy_embed

SCRATCH = Path("/Volumes/data01/portal5_scratch_eg2")
FIX = REPO_ROOT / "tests" / "fixtures" / "rag_eval_corpus"


def _build_corpus(dest: Path) -> list[str]:
    readme = (FIX / "README.md").read_text()
    code = re.search(r"```python\n(.*?)```", readme[readme.index("## Synthetic builder") :], re.S)
    if not code:
        raise RuntimeError("synthetic builder not found in the fixture README")
    script = dest.parent / "build_synthetic.py"
    script.write_text(code.group(1))
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(REPO_ROOT / ".venv" / "bin" / "python"), str(script), str(dest)],
        check=True,
        capture_output=True,
    )
    return sorted(p.name for p in dest.glob("*.pdf"))


def _eval(
    corpus: Path, queries: Path, lance: Path, out: Path, env_extra: dict[str, str]
) -> dict[str, Any]:
    if lance.exists():
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
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=3600,
        check=False,
    )
    if r.returncode or not out.is_file():
        raise RuntimeError(f"rag_retrieval_eval failed: {r.stderr[-300:]}")
    return json.loads(out.read_text())


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
    if inc_p and cand_p:
        inc_rep, cand_rep = (
            json.loads(Path(inc_p).read_text()),
            json.loads(Path(cand_p).read_text()),
        )
    else:
        if not ctx.live:
            return blocked("rag_first_stage", "needs --live (VL server :8942 + EG2 :8946, ~20 min)")
        work = SCRATCH / "rag_first_stage"
        work.mkdir(parents=True, exist_ok=True)
        files = _build_corpus(work / "corpus")
        q = yaml.safe_load((FIX / "queries.yaml").read_text())
        q["queries"] = [x for x in q["queries"] if x["target_file"] in files]
        qf = work / "queries_synthetic.yaml"
        qf.write_text(yaml.safe_dump(q))
        inc_rep = _eval(work / "corpus", qf, work / "lance_inc", work / "inc.json", {})
        cand_rep = _eval(
            work / "corpus",
            qf,
            work / "lance_cand",
            work / "cand.json",
            {"VL_RETRIEVAL_URL": "http://localhost:8946/vl", "VL_EMBEDDING_DIM": "768"},
        )
    if "error" in cand_rep.get("ingest", {}) or "error" in inc_rep.get("ingest", {}):
        return blocked(
            "rag_first_stage",
            f"ingest error: {cand_rep.get('ingest') if 'error' in cand_rep.get('ingest', {}) else inc_rep.get('ingest')}",
        )
    inc, cand = _flat(inc_rep), _flat(cand_rep)
    return ProbeResult(
        "rag_first_stage",
        MEASURED,
        {"primary": inc["recall@1"], **inc},
        {"primary": cand["recall@1"], **cand},
        compare(inc["recall@1"], cand["recall@1"]),
        fixture={
            "docs": inc_rep["n_docs"],
            "queries": inc["queries"],
            "corpus": "9 synthetic figure-only PDFs (the public NERC/NIST PDFs and the operator procedures are not on this host)",
            "sha": fixture_digest(inc["by_category"]),
        },
        identity=await ctx.client.version_tag(768),
        notes=[
            "primary = recall@1 over diagram-only+mixed synthetic queries, the category the fusion/text-gate work was built for; final ranking is after the VL rerank in both arms (the reranker is unchanged)",
            "ingest wall time is reported per arm",
        ],
    )


# ── owui_attachment_rag ─────────────────────────────────────────────────────

_BGE = """
import json, sys
from sentence_transformers import CrossEncoder
m = CrossEncoder("BAAI/bge-reranker-v2-m3")
rows = json.load(open("/tmp/bge_in.json"))
out = []
for r in rows:
    out.append([float(s) for s in m.predict([[r["q"], d] for d in r["docs"]])])
json.dump(out, open("/tmp/bge_out.json", "w"))
"""


def _chunks(body: str, size: int = 900) -> list[str]:
    body = re.sub(r"[#*`>\[\]_|-]+", " ", body)
    return [
        body[i : i + size]
        for i in range(0, min(len(body), 5400), size)
        if body[i : i + size].strip()
    ]


@probe("owui_attachment_rag")
async def owui_attachment_rag(ctx: ProbeContext) -> ProbeResult:  # noqa: C901, PLR0912, PLR0915
    import httpx

    from portal.platform.wiki.store import load_all

    qs = json.loads((DATA / "wiki_queries.json").read_text())["rows"]
    units = [u for u in load_all() if u.body]
    ids, texts = [], []
    for u in units:
        for c in _chunks(f"{u.title}\n{u.body}"):
            ids.append(u.id)
            texts.append(c)
    gold = [q["expected_unit_ids"] for q in qs]
    dv = await ctx.client.embed_texts(texts, task=Task.SEARCH, role=Role.DOCUMENT, dim=768)
    qv = await ctx.client.embed_texts(
        [q["query"] for q in qs], task=Task.SEARCH, role=Role.QUERY, dim=768
    )
    keys = [f"{i}#{n}" for n, i in enumerate(ids)]
    dd = dict(zip(keys, dv, strict=True))

    def unit_rank(chunk_keys: list[str]) -> list[str]:
        seen: list[str] = []
        for k in chunk_keys:
            u = k.split("#")[0]
            if u not in seen:
                seen.append(u)
        return seen

    cand_dense = [unit_rank(top_k_by_cosine(v, dd, 20)) for v in qv]
    ld = await legacy_embed(texts)
    lq = await legacy_embed([q["query"] for q in qs])
    ldd = dict(zip(keys, ld, strict=True))
    inc_pool = [top_k_by_cosine(v, ldd, 20) for v in lq]
    inc_dense = [unit_rank(p) for p in inc_pool]
    out: dict[str, Any] = {
        "dense": {
            "incumbent": {
                "recall@1": round(recall_at_k(inc_dense, gold, 1), 4),
                "recall@5": round(recall_at_k(inc_dense, gold, 5), 4),
            },
            "candidate": {
                "recall@1": round(recall_at_k(cand_dense, gold, 1), 4),
                "recall@5": round(recall_at_k(cand_dense, gold, 5), 4),
            },
        }
    }
    notes = []
    # incumbent rerank: OWUI's in-container bge-reranker-v2-m3 over the :8917 top-20 chunks
    bge: dict[str, Any] = {}
    try:
        if ctx.live and ctx.opt("owui_bge") == "1":
            payload = [
                {"q": q["query"], "docs": [texts[int(k.split("#")[1])] for k in pool]}
                for q, pool in zip(qs, inc_pool, strict=True)
            ]
            Path(tempfile.gettempdir(), "bge_in.json").write_text(json.dumps(payload))
            subprocess.run(
                [
                    "docker",
                    "cp",
                    str(Path(tempfile.gettempdir(), "bge_in.json")),
                    "portal5-open-webui:/tmp/bge_in.json",
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["docker", "exec", "portal5-open-webui", "python", "-c", _BGE],
                check=True,
                capture_output=True,
                timeout=3000,
            )
            subprocess.run(
                [
                    "docker",
                    "cp",
                    "portal5-open-webui:/tmp/bge_out.json",
                    str(Path(tempfile.gettempdir(), "bge_out.json")),
                ],
                check=True,
                capture_output=True,
            )
            scores = json.loads(Path(tempfile.gettempdir(), "bge_out.json").read_text())
            rer = [
                unit_rank([k for _, k in sorted(zip(sc, pool, strict=True), reverse=True)])
                for sc, pool in zip(scores, inc_pool, strict=True)
            ]
            bge = {
                "recall@1": round(recall_at_k(rer, gold, 1), 4),
                "recall@5": round(recall_at_k(rer, gold, 5), 4),
            }
            mem = subprocess.run(
                [
                    "docker",
                    "stats",
                    "--no-stream",
                    "--format",
                    "{{.MemUsage}}",
                    "portal5-open-webui",
                ],
                capture_output=True,
                text=True,
            ).stdout.strip()
            size = subprocess.run(
                [
                    "docker",
                    "exec",
                    "portal5-open-webui",
                    "sh",
                    "-c",
                    "du -sh ~/.cache/huggingface 2>/dev/null | cut -f1",
                ],
                capture_output=True,
                text=True,
            ).stdout.strip()
            bge["owui_container_mem_now"] = mem
            bge["bge_cache_in_container"] = size
    except Exception as e:  # noqa: BLE001
        notes.append(f"bge rerank arm not run: {type(e).__name__}: {str(e)[:160]}")
    if not bge:
        notes.append(
            "bge arm not run: the OWUI container is capped at 2 GiB and bge-reranker-v2-m3 needs ~2.3 GB, so loading it there risks OOM-killing Open WebUI; enable with --opt owui_bge=1"
        )
    # candidate rerank: EG2 pool through /v1/rerank (forwards to the VL reranker)
    vl: dict[str, Any] = {}
    try:
        if ctx.live:
            rer = []
            async with httpx.AsyncClient(timeout=600) as c:
                for q, v in zip(qs, qv, strict=True):
                    pool = top_k_by_cosine(v, dd, 20)
                    r = await c.post(
                        "http://localhost:8946/v1/rerank",
                        json={
                            "model": "x",
                            "query": q["query"],
                            "documents": [texts[int(k.split("#")[1])] for k in pool],
                            "top_n": 20,
                        },
                    )
                    r.raise_for_status()
                    res = sorted(r.json()["results"], key=lambda x: -x["relevance_score"])
                    rer.append(unit_rank([pool[x["index"]] for x in res]))
            vl = {
                "recall@1": round(recall_at_k(rer, gold, 1), 4),
                "recall@5": round(recall_at_k(rer, gold, 5), 4),
            }
    except Exception as e:  # noqa: BLE001
        notes.append(f"VL rerank arm not run: {type(e).__name__}: {str(e)[:160]}")
    inc_primary = bge.get("recall@5", out["dense"]["incumbent"]["recall@5"])
    cand_primary = vl.get("recall@5", out["dense"]["candidate"]["recall@5"])
    return ProbeResult(
        "owui_attachment_rag",
        MEASURED,
        {
            "primary": inc_primary,
            "dense_8917": out["dense"]["incumbent"],
            "dense_plus_bge_reranker": bge,
        },
        {
            "primary": cand_primary,
            "dense_eg2": out["dense"]["candidate"],
            "dense_plus_vl_rerank": vl,
        },
        compare(inc_primary, cand_primary),
        fixture={"queries": len(qs), "chunks": len(texts), "units": len(units)},
        identity=await ctx.client.version_tag(768),
        notes=[
            "PROXY, not a scratch-Open-WebUI A/B: the retrieval pipeline OWUI runs (chunk 900 chars -> embed -> top-20 -> rerank) is re-run in-process on the wiki corpus with the 47 authored wiki queries; the incumbent bge reranker runs inside the portal5-open-webui container, the candidate reranker is the VL reranker behind :8946/v1/rerank. A scratch OWUI container on :8081 would add only OWUI's own prompt assembly",
            *notes,
        ],
    )
