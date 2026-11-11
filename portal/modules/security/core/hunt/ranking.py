"""Ranking reads: deterministic samples, conservative burst bounds, progress kinds.

A token's burst z cannot exceed ``z_upper(now)`` when every prior active hour counted 1.
Tokens below the kept bursts' z are not given a full-history series. Narrow hour counts
and coarser spans rolled up from a finer exact series are exact, not approximations.
"""

from __future__ import annotations

import math
import re

_KIND_SPAN = re.compile(r"span=(\d+)s")


def where_literal(value: str) -> str:
    """Exact ``where`` string. Search-clause quotes still treat ``*`` as a wildcard."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def z_upper(now: int) -> float:
    """Max rounded-input z: prior median at least log1p(1), MAD at least 0."""
    return (math.log1p(max(int(now), 0)) - math.log1p(1)) / 0.5


def census_query(index_literal: str, host_literal: str, sample: int) -> str:
    """Lead-bucket sample in md5(_raw) order. ``head`` is the row effort budget."""
    return (
        f"search index={index_literal} host={host_literal} "
        f"| eval _k=md5(_raw) | sort {sample} _k _time _raw | head {sample} "
        f"| table _raw punct"
    )


def slot_query(index_literal: str, host_literal: str, term_literal: str, sample: int) -> str:
    return (
        f"search index={index_literal} host={host_literal} TERM({term_literal}) "
        f"| eval _k=md5(_raw) | sort {sample} _k _time _raw | head {sample} "
        f"| table _raw punct"
    )


def peer_history_query(index_literal: str, host_literal: str, punct: str, sample: int) -> str:
    return (
        f"search index={index_literal} host={host_literal} "
        f"| where punct={where_literal(punct)} "
        f"| eval _k=md5(_raw) | sort {sample} _k _time _raw | head {sample} "
        f"| table _raw punct"
    )


def rollup_series(series: dict[int, int], coarse: int) -> dict[int, int]:
    """Sum an exact finer series into ``coarse`` buckets. Missing hours are zeros."""
    rolled: dict[int, int] = {}
    for bucket, count in series.items():
        slot = int(bucket) // coarse * coarse
        rolled[slot] = rolled.get(slot, 0) + int(count)
    return rolled


def note_ranking(search: object, reason: str) -> None:
    budget = getattr(search, "budget", None)
    notes = getattr(budget, "ranking_notes", None)
    if isinstance(notes, set):
        notes.add(reason)


def query_progress_kind(query: str, start: float, end: float) -> str:
    """Stable hunt-progress kind for one issued search."""
    if "where punct=" in query:
        return "peer_history"
    if "md5(_raw)" in query:
        return "burst_sample"
    if "TERM(" in query and "table _raw punct" in query:
        return "peer_slot"
    span_match = _KIND_SPAN.search(query)
    narrow = span_match is not None and end - start <= int(span_match.group(1)) + 1e-6
    packed = 'eval _ht="' in query or "eval _ht=" in query
    if packed:
        return "hour_screen" if narrow else "packed_series"
    if query.startswith("| tstats") and "TERM(" in query and " by _time span=" in query:
        return "hour_screen" if narrow else "token_series"
    if "dedup host source punct" in query:
        return "template"
    if (
        query.startswith("| tstats")
        and "TERM(" in query
        and query.rstrip().endswith("by host source")
    ):
        return "term_tstats"
    if "min(_time)" in query:
        return "ladder"
    by_clause = query.split(" by ", 1)[-1] if " by " in query else ""
    if query.startswith("| tstats") and by_clause.startswith("host") and "source" not in by_clause:
        return "host_inventory"
    if query.startswith("search "):
        return "evidence"
    return "other"
