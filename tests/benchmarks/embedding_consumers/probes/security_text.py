"""Security text-retrieval probes: spl_library and field_journal."""

from __future__ import annotations

import glob
from pathlib import Path

from portal.platform.embedding.contract import Task

from ..framework import (
    MEASURED,
    REPO_ROOT,
    ProbeContext,
    ProbeResult,
    blocked,
    compare,
    fixture_digest,
    probe,
)
from ._common import auc_roc, cos, load_fixture, retrieval_ab

JOURNAL = REPO_ROOT / "portal" / "modules" / "security" / "core" / "field_journal"


def _ref() -> dict[str, str]:
    from portal.modules.security.core.siem.spl_detections import technique_reference

    return dict(technique_reference())


def _search_library(ref: dict[str, str], query: str, k: int = 10) -> list[str]:
    """spl_search_library's matching rule (detections_mcp.py): id-or-substring over descriptions."""
    q = query.strip()
    return [t for t, d in ref.items() if q.upper() in t.upper() or q.lower() in d.lower()][:k]


def _overlap_ratio(expected: str, observed: str) -> float:
    """spl_diff_hypothesis's score: matched keywords / expected keywords (word sets)."""
    e, o = set(expected.lower().split()), set(observed.lower().split())
    return len(e & o) / max(len(e), 1)


@probe("spl_library")
async def spl_library(ctx: ProbeContext) -> ProbeResult:
    ref = _ref()
    fx = load_fixture("spl_library.json")["rows"]
    rows = [r for r in fx if any(t in ref for t in r["technique_ids"])]
    gold = [[t for t in r["technique_ids"] if t in ref] for r in rows]
    res = await retrieval_ab(
        ctx,
        [r["query"] for r in rows],
        gold,
        list(ref),
        list(ref.values()),
        incumbent_rank=lambda i: _search_library(ref, rows[i]["query"]),
    )
    pairs = load_fixture("spl_hypothesis_pairs.json")["pairs"]
    ex = await ctx.client.embed_texts(
        [p["expected"] for p in pairs], task=Task.SENTENCE_SIMILARITY, dim=768
    )
    ob = await ctx.client.embed_texts(
        [p["observed"] for p in pairs], task=Task.SENTENCE_SIMILARITY, dim=768
    )
    cs = [cos(a, b) for a, b in zip(ex, ob, strict=True)]
    ws = [_overlap_ratio(p["expected"], p["observed"]) for p in pairs]
    m = [p["match"] for p in pairs]

    def split(v: list[float]) -> tuple[list[float], list[float]]:
        return [x for x, g in zip(v, m, strict=True) if g], [
            x for x, g in zip(v, m, strict=True) if not g
        ]

    inc = {
        "primary": res["incumbent"]["recall@5"],
        **res["incumbent"],
        "diff_auc_word_overlap": auc_roc(*split(ws)),
    }
    cand = {
        "primary": res["candidate"]["recall@5"],
        **res["candidate"],
        "diff_auc_cosine": auc_roc(*split(cs)),
    }
    return ProbeResult(
        "spl_library",
        MEASURED,
        inc,
        cand,
        compare(inc["primary"], cand["primary"]),
        fixture={
            "queries": len(rows),
            "library": len(ref),
            "pairs": len(pairs),
            "sha": fixture_digest(fx),
        },
        identity=await ctx.client.version_tag(768),
        notes=[
            "queries are analyst phrasings; incumbent = spl_search_library substring/ID rule; diff = AUC matched vs unmatched"
        ],
    )


@probe("field_journal")
async def field_journal(ctx: ProbeContext) -> ProbeResult:
    """Measured on the LIVE journal, which is degenerate by size.

    The incumbent is ``field_journal.recall(category, keywords, limit=5)``: a keyword-occurrence
    count over each entry's whole JSON blob, returning the top ``limit``. With fewer entries than
    ``limit`` every query returns every entry, so the ranking function — keyword count or cosine —
    cannot change the result set. That is measured here rather than asserted: both arms are run and
    their returned sets compared.
    """
    import json as _json

    from portal.modules.security.core import field_journal as fj

    paths = [q for q in sorted(glob.glob(str(JOURNAL / "*.json"))) if not q.endswith("_index.json")]
    entries = []
    for path in paths:
        try:
            entries.append(_json.loads(Path(path).read_text()))
        except ValueError:
            continue
    if not entries:
        return blocked("field_journal", "no journal entries exist", fixture={"entries": 0})
    limit = 5
    # Content actually available to retrieve from (the recall-relevant fields).
    content = {
        "execution_chain": sum(len(e.get("execution_chain") or []) for e in entries),
        "pitfalls": sum(len(e.get("pitfalls") or []) for e in entries),
        "reusable": sum(len(e.get("reusable") or []) for e in entries),
        "verified_findings": sum(len(e.get("verified_findings") or []) for e in entries),
    }
    categories = sorted({e.get("scenario_category", "other") for e in entries})
    queries = [
        "which prior engagement hit a tooling pitfall and how was it resolved",
        "reusable pattern for enumerating a host",
        "what did a failed engagement establish",
    ]
    ids = [e.get("engagement_id", f"entry-{i}") for i, e in enumerate(entries)]
    texts = [_json.dumps(e) for e in entries]
    # incumbent arm: the real production call
    inc_sets = [
        [h.get("engagement_id") for h in fj.recall("all", keywords=q.split(), limit=limit)]
        for q in queries
    ]
    # candidate arm: EG2 over the same entry texts
    dv = await ctx.client.embed_texts(texts, task=Task.SEARCH, dim=768)
    qv = await ctx.client.embed_texts(queries, task=Task.SEARCH, dim=768)
    docs = dict(zip(ids, dv, strict=True))
    from ..framework import top_k_by_cosine

    cand_sets = [top_k_by_cosine(v, docs, limit) for v in qv]
    identical = all(set(a) == set(b) for a, b in zip(inc_sets, cand_sets, strict=True))
    degenerate = len(entries) <= limit
    return ProbeResult(
        "field_journal",
        MEASURED,
        {
            "primary": 1.0 if degenerate else None,
            "arm": "field_journal.recall keyword-occurrence count over the entry JSON blob",
            "returned_sets": inc_sets,
        },
        {
            "primary": 1.0 if degenerate else None,
            "arm": "EG2 SEARCH 768d cosine over the same entry JSON",
            "returned_sets": cand_sets,
            "result_sets_identical_to_incumbent": identical,
        },
        "PARITY" if degenerate and identical else "INCONCLUSIVE",
        fixture={
            "entries": len(entries),
            "limit": limit,
            "categories": categories,
            "retrievable_content_items": content,
            "sha": fixture_digest(ids),
        },
        identity=await ctx.client.version_tag(768),
        notes=[
            f"DEGENERATE BY SIZE: {len(entries)} entries <= limit {limit}, so every query returns every entry under both arms (verified identical: {identical}). Recall@5 is 1.0 for both by construction, and discrimination is undefined",
            f"the entries also carry no retrievable content: {content} — the write-back path has recorded only failed engagements with empty chains",
            "consequence for the Phase 4 decision: this consumer can neither support nor block the swap. The transformation it would adopt (substring/keyword -> embedding retrieval over short security text records) is measured under spl_library and attack_mapping on real corpora",
            "re-measure once the journal exceeds the recall limit with non-empty execution_chain/pitfalls entries",
        ],
    )
