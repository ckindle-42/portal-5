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
    ProbeContext,
    ProbeResult,
    blocked,
    compare,
    fixture_digest,
    probe,
    top_k_by_cosine,
)

DATA = REPO_ROOT / "portal" / "modules" / "compliance" / "data"
TEST_DATA = REPO_ROOT / "tests" / "data" / "embedding_consumers"
_PARAM = re.compile(r"\{\{[^}]*\}\}")


def _clean(t: str) -> str:
    return " ".join(_PARAM.sub(" ", t).split())


@probe("compliance_crosswalk")
async def crosswalk(ctx: ProbeContext) -> ProbeResult:
    """Both arms scored against NIST's official CSF 2.0 -> SP 800-53 Rev 5 informative references
    (tests/data/embedding_consumers/csf2_to_80053r5_official.json): the incumbent is the hand seed in
    crosswalk.json, the candidate is EG2 SEARCH top-k over the 800-53 catalog."""
    cw = json.loads((DATA / "crosswalk.json").read_text())["mappings"]
    csf = json.loads((DATA / "csf_2_0.json").read_text())["controls"]
    nist = json.loads((DATA / "nist_800_53_rev5.json").read_text())["controls"]
    official = json.loads((TEST_DATA / "csf2_to_80053r5_official.json").read_text())["mappings"]
    subs = [c for c in sorted(official) if c in csf and csf[c].get("statement")]
    gold = [set(official[c]) for c in subs]
    seed = {k.split(":", 1)[1]: set(v["nist_800_53"]) for k, v in cw.items()}
    ids = list(nist)
    texts = [
        f"{k} {nist[k].get('title', '')} {nist[k].get('family', '')}: {_clean(nist[k].get('statement', ''))}"[
            :1500
        ]
        for k in ids
    ]
    dv = await ctx.client.embed_texts(texts, task=Task.SEARCH, role=Role.DOCUMENT, dim=768)
    docs = dict(zip(ids, dv, strict=True))
    qv = await ctx.client.embed_texts(
        [f"{c}: {csf[c]['statement']}" for c in subs], task=Task.SEARCH, role=Role.QUERY, dim=768
    )
    ranked = [top_k_by_cosine(v, docs, 10) for v in qv]

    def arm(pred: list[set[str]]) -> dict[str, float]:
        n = len(subs)
        hit = sum(bool(p & g) for p, g in zip(pred, gold, strict=True)) / n
        offered = [p for p in pred if p]
        prec = (
            sum(len(p & g) / len(p) for p, g in zip(pred, gold, strict=True) if p) / len(offered)
            if offered
            else 0.0
        )
        rec = sum(len(p & g) / len(g) for p, g in zip(pred, gold, strict=True)) / n
        return {
            "subcategory_hit_rate": round(hit, 4),
            "coverage": round(len(offered) / n, 4),
            "precision": round(prec, 4),
            "pair_recall": round(rec, 4),
        }

    inc = arm([seed.get(c, set()) for c in subs])
    cand5 = arm([set(r[:5]) for r in ranked])
    cand10 = arm([set(r[:10]) for r in ranked])
    return ProbeResult(
        "compliance_crosswalk",
        MEASURED,
        {"primary": inc["subcategory_hit_rate"], **inc, "seed_rows": len(seed)},
        {"primary": cand5["subcategory_hit_rate"], "top5": cand5, "top10": cand10},
        compare(inc["subcategory_hit_rate"], cand5["subcategory_hit_rate"]),
        fixture={
            "subcategories": len(subs),
            "official_pairs": sum(map(len, gold)),
            "catalog": len(ids),
            "sha": fixture_digest(official),
        },
        identity=await ctx.client.version_tag(768),
        notes=[
            "primary = share of CSF 2.0 subcategories (with official 800-53 references) for which the arm offers at least one officially mapped control: seed rows vs EG2 top-5",
            "precision = share of offered controls that NIST maps; EG2 proposals stay review-only (never merged into crosswalk.json)",
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
        # reranker retirement: EG2 dense top-20 re-ordered by the VL reranker vs EG2 dense alone,
        # on a sample (the rerank is ~seconds per query)
        n_rr = min(len(targets), int(ctx.opt("compliance_rerank_sample", 100)))
        rr_dense, rr_rerank = [], []
        for i in range(n_rr):
            pool = np.argsort(-(cd @ cq[i]))[:20].tolist()
            order = await vl.vl_rerank(qtext[i], [{"text": ctext[j]} for j in pool], len(pool))
            reranked = [ids[pool[o["index"]]] for o in order]
            rr_rerank.append(targets[i]["section_id"] in reranked[:top])
            rr_dense.append(targets[i]["section_id"] in [ids[j] for j in pool[:top]])
        out[name]["eg2_dense_vs_dense_plus_vl_rerank"] = {
            "queries": n_rr,
            f"dense_top{top}": round(sum(rr_dense) / n_rr, 4),
            f"dense_plus_rerank_top{top}": round(sum(rr_rerank) / n_rr, 4),
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
                k: {
                    kk: vv
                    for kk, vv in v.items()
                    if kk.startswith("candidate") or kk.startswith("eg2_")
                }
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
