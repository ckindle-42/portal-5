"""Probe: wiki_search, the Rule-13 discovery index (consumer ``wiki_search``).

Two fixtures. (1) Key-independent self-retrieval, always available: each
canonical unit is queried by its own TITLE and must come back in the top-k;
the document side is the body without the title, so neither path can win by
echoing the query. (2) Natural-language questions with expected unit ids from
``tests/data/embedding_consumers/wiki_queries.json`` (authored in Phase 3 under
the content-word-overlap rule); absent -> reported, not faked. Incumbent is the
real ``portal_wiki.mcp.wiki_search``.
"""

from __future__ import annotations

import json
import re
from typing import Any

from portal.platform.embedding.contract import Role, Task

from ..framework import (
    MEASURED,
    REPO_ROOT,
    ProbeContext,
    ProbeResult,
    compare,
    fixture_digest,
    mrr,
    probe,
    recall_at_k,
    top_k_by_cosine,
)

QUERIES = REPO_ROOT / "tests" / "data" / "embedding_consumers" / "wiki_queries.json"
_MD = re.compile(r"[#*`>\[\]_|-]+")


def _clean(body: str, limit: int = 1800) -> str:
    return _MD.sub(" ", body)[:limit]


def _incumbent(query: str, k: int) -> list[str]:
    from portal_wiki.mcp import wiki_search

    res = wiki_search(query, top_k=k)
    rows = res.get("results", []) if isinstance(res, dict) else []
    return [r["unit_id"] for r in rows]


async def _score(
    ctx: ProbeContext, queries: list[str], gold: list[list[str]], docs: dict[str, Any], dim: int
) -> dict[str, Any]:
    inc = [_incumbent(q, 10) for q in queries]
    qv = await ctx.client.embed_texts(queries, task=Task.SEARCH, role=Role.QUERY, dim=dim)
    cand = [top_k_by_cosine(v, docs, 10) for v in qv]
    return {
        "incumbent": {
            "recall@5": round(recall_at_k(inc, gold, 5), 4),
            "mrr": round(mrr(inc, gold), 4),
        },
        "candidate": {
            "recall@5": round(recall_at_k(cand, gold, 5), 4),
            "mrr": round(mrr(cand, gold), 4),
        },
    }


@probe("wiki_search")
async def run(ctx: ProbeContext) -> ProbeResult:
    from portal.platform.wiki.store import load_all

    units = [u for u in load_all() if u.title and u.body]
    dim = int(ctx.opt("wiki_dim", 768))
    vecs = await ctx.client.embed_texts(
        [_clean(u.body) for u in units], task=Task.SEARCH, role=Role.DOCUMENT, dim=dim
    )
    docs = {u.id: v for u, v in zip(units, vecs, strict=True)}
    # Self-retrieval queries: a deterministic stride sample (the incumbent
    # re-reads every unit per call, so the full set is slow but allowed: wiki_sample=0).
    n = int(ctx.opt("wiki_sample", 250))
    pool = sorted(units, key=lambda u: u.id)
    sample = pool if n <= 0 or n >= len(pool) else pool[:: max(1, len(pool) // n)][:n]
    self_ret = await _score(ctx, [u.title for u in sample], [[u.id] for u in sample], docs, dim)
    result: dict[str, Any] = {"self_retrieval_by_title": self_ret}
    notes = []
    if QUERIES.is_file():
        qs = json.loads(QUERIES.read_text())
        result["natural_language"] = await _score(
            ctx, [q["query"] for q in qs], [q["expected_unit_ids"] for q in qs], docs, dim
        )
    else:
        notes.append(
            f"{QUERIES.relative_to(REPO_ROOT)} absent — natural-language fixture not measured"
        )
    primary_block = result.get("natural_language", self_ret)
    inc_p = primary_block["incumbent"]["recall@5"]
    cand_p = primary_block["candidate"]["recall@5"]
    return ProbeResult(
        consumer="wiki_search",
        status=MEASURED,
        incumbent={"primary": inc_p, **{k: v["incumbent"] for k, v in result.items()}},
        candidate={"primary": cand_p, **{k: v["candidate"] for k, v in result.items()}},
        hint=compare(inc_p, cand_p),
        fixture={
            "units": len(units),
            "self_retrieval_sample": len(sample),
            "units_sha": fixture_digest(sorted(docs)),
        },
        identity=await ctx.client.version_tag(dim),
        notes=notes,
    )
