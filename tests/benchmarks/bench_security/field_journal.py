"""Security field-journal — evidence-based engagement memory (Gap 2).

After each engagement, records the observed execution chain, pitfalls, and
reusable patterns (only observed facts, mirroring proven_coverage). The loop
recalls relevant prior engagements before acting and writes back after.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

JOURNAL_DIR = Path(__file__).resolve().parent / "field_journal"
JOURNAL_DIR.mkdir(parents=True, exist_ok=True)


def _sorted_entries() -> list[Path]:
    """All journal entry files sorted by name (newest last)."""
    if not JOURNAL_DIR.exists():
        return []
    return sorted(
        [p for p in JOURNAL_DIR.glob("*.json") if p.name != "_index.json"],
        key=lambda p: p.name,
    )


def write_entry(entry: dict) -> Path:
    """Write an engagement journal entry.

    Entry schema (record only observed facts):
      { engagement_id, ts, scenario_category, goal,
        execution_chain: [{step, tool, args_snip, observed, oracle, verified}],
        pitfalls: [{problem, cause, resolution}],
        reusable: [{pattern, snippet}],
        outcome: 'goal_met'|'partial'|'failed',
        proven_coverage, verified_findings }

    Filename: YYYY-MM-DD_<category>_<engagement_id>.json.
    Stamped via stamp_result_meta if available.
    """
    try:
        from tests.benchmarks.capability_lib import stamp_result_meta

        entry = stamp_result_meta(entry)
    except ImportError:
        pass

    ts_str = entry.get("ts", datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ"))
    date_part = ts_str[:10]
    category = entry.get("scenario_category", "unknown")
    eng_id = entry.get("engagement_id", ts_str[11:])
    filename = f"{date_part}_{category}_{eng_id}.json"
    out_path = JOURNAL_DIR / filename
    out_path.write_text(json.dumps(entry, indent=2))
    return out_path


def rebuild_index() -> Path:
    """Regenerate field_journal/_index.json: by category, top pitfalls, cumulative stats."""
    entries = _sorted_entries()
    by_category: dict[str, list[str]] = {}
    all_pitfalls: list[dict] = []
    outcomes = {"goal_met": 0, "partial": 0, "failed": 0}

    for p in entries:
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        cat = data.get("scenario_category", "other")
        by_category.setdefault(cat, []).append(p.name)
        for pit in data.get("pitfalls", []):
            all_pitfalls.append({"file": p.name, **pit})
        outcomes[data.get("outcome", "partial")] = (
            outcomes.get(data.get("outcome", "partial"), 0) + 1
        )

    top_pitfalls = sorted(all_pitfalls, key=lambda x: len(x.get("problem", "")), reverse=True)[:20]

    index = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "total_entries": len(entries),
        "by_category": {k: len(v) for k, v in by_category.items()},
        "outcomes": outcomes,
        "top_pitfalls": top_pitfalls,
    }
    out_path = JOURNAL_DIR / "_index.json"
    out_path.write_text(json.dumps(index, indent=2))
    return out_path


def recall(scenario_category: str, keywords: list[str] | None = None, limit: int = 5) -> list[dict]:
    """Return prior entries matching category/keywords, most-relevant first.

    Relevance = number of keyword matches across the entry.
    """
    if keywords is None:
        keywords = []
    scored: list[tuple[int, dict]] = []
    for p in _sorted_entries():
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        cat = data.get("scenario_category", "other")
        if scenario_category and scenario_category != "all" and cat != scenario_category:
            continue
        text_blob = json.dumps(data).lower()
        score = sum(1 for kw in keywords if kw.lower() in text_blob)
        scored.append((score, data))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [data for _, data in scored[:limit]]


def record_engagement(
    chain_result: dict,
    scenario: dict | None = None,
    engagement_id: str = "",
) -> Path | None:
    """Map a completed exec-chain/loop result into the entry schema and write it.

    Non-fatal: a journal write failure logs a warning, never aborts the engagement.
    """
    try:
        category = (scenario or {}).get("category", "general")
        goal = (scenario or {}).get("goal", chain_result.get("scenario", "unknown"))

        entry: dict[str, Any] = {
            "engagement_id": engagement_id or datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ"),
            "ts": datetime.now(tz=UTC).isoformat(),
            "scenario_category": category,
            "goal": goal,
            "execution_chain": _extract_exec_chain(chain_result),
            "pitfalls": _extract_pitfalls(chain_result),
            "reusable": _extract_reusable(chain_result),
            "outcome": _derive_outcome(chain_result),
            "proven_coverage": chain_result.get("proven_coverage", {}),
            "verified_findings": chain_result.get("verified_findings", []),
        }
        write_entry(entry)
        rebuild_index()
        return JOURNAL_DIR
    except Exception as e:
        import sys

        print(f"  [journal] WARNING: write-back failed: {e}", file=sys.stderr)
        return None


def _extract_exec_chain(chain_result: dict) -> list[dict]:
    """Extract tool-call + observation pairs from a chain result."""
    chain: list[dict] = []
    for tc in chain_result.get("tools_called", []):
        if isinstance(tc, str):
            chain.append({"step": tc, "tool": tc})
        elif isinstance(tc, dict):
            chain.append(
                {
                    "step": tc.get("tool", tc.get("step", "")),
                    "tool": tc.get("tool", ""),
                    "args_snip": str(tc.get("arguments", {}))[:200],
                    "observed": str(tc.get("output", ""))[:500],
                }
            )
    return chain


def _extract_pitfalls(chain_result: dict) -> list[dict]:
    """Extract failure/pitfall patterns from a chain result."""
    pitfalls: list[dict] = []
    errors = chain_result.get("errors", [])
    for err in errors:
        pitfalls.append(
            {
                "problem": str(err)[:200],
                "cause": "chain execution",
                "resolution": "see error trace",
            }
        )
    return pitfalls


def _extract_reusable(chain_result: dict) -> list[dict]:
    """Extract reusable patterns from successful steps."""
    reusable: list[dict] = []
    for tc in chain_result.get("successful_tools", chain_result.get("tools_called", [])):
        snippet = ""
        if isinstance(tc, dict):
            snippet = str(tc.get("output", ""))[:300]
        if snippet:
            reusable.append(
                {
                    "pattern": tc.get("tool", "step") if isinstance(tc, dict) else str(tc),
                    "snippet": snippet,
                }
            )
    return reusable[:10]


def _derive_outcome(chain_result: dict) -> str:
    """Derive outcome from chain result signals."""
    if chain_result.get("compromise_confirmed") or chain_result.get("verified"):
        return "goal_met"
    if chain_result.get("chain_depth", 0) > 0:
        return "partial"
    return "failed"
