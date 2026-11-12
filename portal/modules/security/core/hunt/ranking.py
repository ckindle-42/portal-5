"""Progress labels for one issued hunt search, plus exact where-literals."""

from __future__ import annotations

import re

_KIND_SPAN = re.compile(r"span=(\d+)s")


def where_literal(value: str) -> str:
    """Exact ``where`` string. Search-clause quotes still treat ``*`` as a wildcard."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def query_progress_shape(query: str, start: float, end: float) -> str:
    """Decide whether one issued search is a packed parent, a narrow standalone screen,
    or other. Packed parents carry every token as an append subsearch. Single-bucket
    tstats TERM scans are standalone because live-measured at ~0.37 s each while a
    packed window parent is ~15.2 s."""
    if "eval _ht=" in query:
        return "packed"
    span_match = _KIND_SPAN.search(query)
    if span_match is not None:
        narrow = end - start <= int(span_match.group(1)) + 1e-6
        if (
            narrow
            and query.startswith("| tstats")
            and "TERM(" in query
            and " by _time span=" in query
        ):
            return "standalone"
    return "other"


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
