"""Security text-retrieval probes: spl_library and field_journal."""

from __future__ import annotations

import glob

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
    entries = [
        p for p in sorted(glob.glob(str(JOURNAL / "*.json"))) if not p.endswith("_index.json")
    ]
    if len(entries) < 20:
        return blocked(
            "field_journal",
            f"only {len(entries)} journal entries exist (floor is 20); revisit once the journal has grown",
            fixture={"entries": len(entries)},
        )
    return blocked(
        "field_journal",
        "entries present but no technique-labelled gold; author gold before measuring",
        fixture={"entries": len(entries)},
    )
