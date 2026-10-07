"""Compliance probes: crosswalk candidates and key-independent findability."""

from __future__ import annotations

import importlib.util
import json
import random
import re
import sys
from typing import Any

from portal.platform.embedding.contract import Role, Task

from ..framework import (
    MEASURED,
    REPO_ROOT,
    REPORTS_DIR,
    ProbeContext,
    ProbeResult,
    blocked,
    compare,
    fixture_digest,
    mrr,
    probe,
    recall_at_k,
    top_k_by_cosine,
)

DATA = REPO_ROOT / "portal" / "modules" / "compliance" / "data"
_PARAM = re.compile(r"\{\{[^}]*\}\}")


def _clean(t: str) -> str:
    return " ".join(_PARAM.sub(" ", t).split())


@probe("compliance_crosswalk")
async def crosswalk(ctx: ProbeContext) -> ProbeResult:
    cw = json.loads((DATA / "crosswalk.json").read_text())["mappings"]
    csf = json.loads((DATA / "csf_2_0.json").read_text())["controls"]
    nist = json.loads((DATA / "nist_800_53_rev5.json").read_text())["controls"]
    ids = list(nist)
    texts = [
        f"{k} {nist[k].get('title', '')} {nist[k].get('family', '')}: {_clean(nist[k].get('statement', ''))}"[
            :1500
        ]
        for k in ids
    ]
    dv = await ctx.client.embed_texts(texts, task=Task.SEARCH, role=Role.DOCUMENT, dim=768)
    docs = dict(zip(ids, dv, strict=True))
    seeded = [
        (k.split(":", 1)[1], v["nist_800_53"]) for k, v in cw.items() if k.split(":", 1)[1] in csf
    ]
    q = [f"{csf[c].get('title', '')}: {csf[c].get('statement', '')}" for c, _ in seeded]
    qv = await ctx.client.embed_texts(q, task=Task.SEARCH, role=Role.QUERY, dim=768)
    ranked = [top_k_by_cosine(v, docs, 10) for v in qv]
    gold = [[g for g in tg if g in nist] for _, tg in seeded]

    # a seeded target may be a control enhancement/parent: also credit family-parent matches
    def parent(c: str) -> str:
        return c.split("(", 1)[0]

    ranked_parent = [[parent(x) for x in r] for r in ranked]
    gold_parent = [[parent(g) for g in gs] for gs in gold]
    r5 = round(recall_at_k(ranked, gold, 5), 4)
    r5p = round(recall_at_k(ranked_parent, gold_parent, 5), 4)
    # proposals for CSF subcategories the seed does not cover (never written to crosswalk.json)
    seeded_ids = {c for c, _ in seeded}
    todo = [c for c, v in csf.items() if c not in seeded_ids and "." in c and v.get("statement")][
        :400
    ]
    pq = await ctx.client.embed_texts(
        [f"{csf[c].get('title', '')}: {csf[c]['statement']}" for c in todo],
        task=Task.SEARCH,
        role=Role.QUERY,
        dim=768,
    )
    proposals = {
        c: [{"nist_800_53": t, "rank": i + 1} for i, t in enumerate(top_k_by_cosine(v, docs, 5))]
        for c, v in zip(todo, pq, strict=True)
    }
    out = REPORTS_DIR / "crosswalk_proposals.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "_note": "PROPOSALS ONLY - never merged into crosswalk.json; EG2 SEARCH top-5 per unmapped CSF 2.0 subcategory",
                "proposals": proposals,
            },
            indent=1,
        )
    )
    return ProbeResult(
        "compliance_crosswalk",
        MEASURED,
        {
            "primary": 1.0,
            "note": "the hand-curated 35-row seed is the reference (recall 1.0 by definition); it covers a small part of CSF 2.0",
        },
        {
            "primary": r5,
            "recall@5_parent_credit": r5p,
            "mrr": round(mrr(ranked, gold), 4),
            "recall@1": round(recall_at_k(ranked, gold, 1), 4),
            "proposals_written": len(proposals),
            "proposals_path": str(out.relative_to(REPO_ROOT)),
        },
        "INCONCLUSIVE",
        fixture={"seed_rows": len(seeded), "targets": len(ids), "sha": fixture_digest(seeded)},
        identity=await ctx.client.version_tag(768),
        notes=[
            "seed recall@5 measures whether EG2 would have found the curated mappings; proposals are for human review"
        ],
    )


def _load_findability() -> Any:
    p = REPO_ROOT / "scripts" / "compliance" / "truth" / "findability.py"
    spec = importlib.util.spec_from_file_location("p5_findability", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    sys.modules["p5_findability"] = m
    spec.loader.exec_module(m)
    return m


def _rank_of(target: str, ids: list[str], sims: Any) -> int:
    import numpy as np

    order = np.argsort(-sims)
    for pos, i in enumerate(order, start=1):
        if ids[int(i)] == target:
            return pos
    return 10**6


@probe("compliance_retrieval")
async def retrieval(ctx: ProbeContext) -> ProbeResult:  # noqa: C901, PLR0912, PLR0915
    if not ctx.live:
        return blocked("compliance_retrieval", "needs --live (incumbent VL server :8942)")
    import numpy as np

    from portal.platform.retrieval import embedding as vl

    fnd = _load_findability()
    try:
        from portal.modules.compliance.core.repository import Repository

        repo = Repository()
    except Exception as e:  # noqa: BLE001
        return blocked(
            "compliance_retrieval", f"compliance store unavailable: {type(e).__name__}: {e}"
        )
    n_req = int(ctx.opt("compliance_req_sample", 250))
    n_op = int(ctx.opt("compliance_op_sample", 250))
    try:
        reqs = [
            r
            for r in fnd.requirement_parts(repo, fnd.GOVERNING_STANDARDS)
            if r["query"] and r["text"]
        ]
        ops = fnd.operator_headings(repo, None)
        spans = repo._conn.execute(
            "select s.section_id, s.revision_id, s.char_start, s.char_end from source_sections s"
        ).fetchall()
        doc_text: dict[str, str] = {}
        op_text: dict[str, str] = {}
        want = {o["section_id"] for o in ops}
        for row in spans:
            if row["section_id"] in want:
                rid = str(row["revision_id"])
                if rid not in doc_text:
                    doc_text[rid] = repo.get_document_text(rid) or ""
                full = doc_text[rid]
                a, b = int(row["char_start"] or 0), int(row["char_end"] or 0)
                if 0 <= a < b <= len(full):
                    op_text[str(row["section_id"])] = full[a:b]
    finally:
        repo.close()
    rng = random.Random(20261007)
    out: dict[str, Any] = {}
    inc_rates, cand_rates = {}, {}
    for name, pop, text_of, top in (
        ("requirements", reqs, lambda x: x["text"], 3),
        (
            "operator",
            [o for o in ops if o["section_id"] in op_text],
            lambda x: op_text[x["section_id"]],
            5,
        ),
    ):
        if not pop:
            return blocked("compliance_retrieval", f"no {name} population in the store")
        pop = [c for c in pop if text_of(c).strip() and c["query"].strip()]
        rng.shuffle(pop)
        targets = pop[: (n_req if name == "requirements" else n_op)]
        extra = pop[len(targets) : len(targets) + (350 if name == "requirements" else 400)]
        corpus = targets + extra
        ids = [c["section_id"] for c in corpus]
        ctext = [text_of(c)[:1500] for c in corpus]
        qtext = [t["query"] for t in targets]
        # candidate (EG2)
        cd = np.asarray(
            await ctx.client.embed_texts(ctext, task=Task.SEARCH, role=Role.DOCUMENT, dim=768),
            dtype=np.float32,
        )
        cq = np.asarray(
            await ctx.client.embed_texts(qtext, task=Task.SEARCH, role=Role.QUERY, dim=768),
            dtype=np.float32,
        )
        cand_ranks = [_rank_of(t["section_id"], ids, cd @ cq[i]) for i, t in enumerate(targets)]
        # incumbent (live Qwen3-VL embedder on :8942)
        vd_list: list[list[float]] = []
        for s in range(0, len(ctext), 12):
            vd_list += await vl.vl_embed_batch([{"text": t} for t in ctext[s : s + 12]])
        vq_list: list[list[float]] = []
        for s in range(0, len(qtext), 12):
            vq_list += await vl.vl_embed_batch(
                [{"text": t, "is_query": True} for t in qtext[s : s + 12]]
            )
        vd = np.asarray(vd_list, dtype=np.float32)
        vd /= np.linalg.norm(vd, axis=1, keepdims=True) + 1e-9
        vq = np.asarray(vq_list, dtype=np.float32)
        vq /= np.linalg.norm(vq, axis=1, keepdims=True) + 1e-9
        inc_ranks = [_rank_of(t["section_id"], ids, vd @ vq[i]) for i, t in enumerate(targets)]
        inc_rates[name] = round(sum(r <= top for r in inc_ranks) / len(targets), 4)
        cand_rates[name] = round(sum(r <= top for r in cand_ranks) / len(targets), 4)
        out[name] = {
            "targets": len(targets),
            "corpus": len(corpus),
            f"incumbent_top{top}": inc_rates[name],
            f"candidate_top{top}": cand_rates[name],
            "incumbent_mrr": round(sum(1 / r for r in inc_ranks) / len(inc_ranks), 4),
            "candidate_mrr": round(sum(1 / r for r in cand_ranks) / len(cand_ranks), 4),
        }
        if name == "requirements":
            # candidate_links pool overlap: dense top-40 pool (RERANK_POOL) of each embedder, per requirement query
            ov = []
            for i in range(len(targets)):
                a = set(np.argsort(-(vd @ vq[i]))[:40].tolist())
                b = set(np.argsort(-(cd @ cq[i]))[:40].tolist())
                ov.append(len(a & b) / 40)
            out[name]["dense_pool40_overlap_mean"] = round(sum(ov) / len(ov), 4)
    inc_p = round(sum(inc_rates.values()) / len(inc_rates), 4)
    cand_p = round(sum(cand_rates.values()) / len(cand_rates), 4)
    return ProbeResult(
        "compliance_retrieval",
        MEASURED,
        {
            "primary": inc_p,
            **out,
            "metric_note": "mean of requirement top-3 and operator top-5 findability",
        },
        {
            "primary": cand_p,
            **{
                k: {kk: vv for kk, vv in v.items() if kk.startswith("candidate")}
                for k, v in out.items()
            },
        },
        compare(inc_p, cand_p),
        fixture={"requirements_sample": n_req, "operator_sample": n_op, "sha": fixture_digest(out)},
        identity=await ctx.client.version_tag(768),
        notes=[
            "A/B on a scratch corpus built from the compliance store's own section text (both embedders index identical text; the production lance tables compliance_nerc_corpus / compliance_operator_corpus are not built on this host)",
            "candidate_links.DEFAULT_THRESHOLD (0.5) is a VL RERANK-score threshold; the reranker stays on :8942, so the threshold does not move with the embedder. Only the dense pool changes: see dense_pool40_overlap_mean",
        ],
    )
