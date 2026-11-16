"""Cross-generator merge: one final ranking from per-generator ranked lists."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .generators import Notable, _interleave

MERGE_METHODS = ("blocks", "interleave", "rrf")
DEFAULT_MERGE = "interleave"  # leave-one-family-out winner; docs/hunt/MERGE_REPORT.md
RRF_K = 60  # reciprocal-rank fusion constant (Cormack et al. 2009); never per-corpus


def group_by_generator(notables: Sequence[Notable], priority: Sequence[str]) -> list[list[Notable]]:
    """Per-generator lists in within-generator order, groups in priority order."""
    groups: dict[str, list[Notable]] = {}
    for notable in notables:
        groups.setdefault(notable.generator, []).append(notable)

    def order(name: str) -> tuple[int, str]:
        return (priority.index(name) if name in priority else len(priority), name)

    return [groups[name] for name in sorted(groups, key=order)]


def duplicate_key(notable: Notable) -> tuple[str, str] | None:
    """What two generators must both name for their notables to be one finding."""
    if not notable.evidence:
        return None
    line = str(notable.evidence[0].get("line") or "")
    return (notable.source_id, line) if line else None


def _rrf(groups: Sequence[Sequence[Notable]]) -> tuple[list[Notable], int]:
    """Reciprocal-rank fusion; one finding raised by several generators fuses into one entry."""
    entries: list[tuple[int, int, Notable]] = [
        (group_position, rank, notable)
        for group_position, group in enumerate(groups)
        for rank, notable in enumerate(group)
    ]
    by_key: dict[tuple[str, str] | int, list[int]] = {}
    for position, (_group_position, _rank, notable) in enumerate(entries):
        duplicate = duplicate_key(notable)
        by_key.setdefault(duplicate if duplicate is not None else position, []).append(position)
    scored: list[tuple[float, int, int, Notable]] = []
    fused = 0
    for group_key, positions in by_key.items():
        if isinstance(group_key, tuple) and len(positions) > 1:
            fused += 1
        score = sum(1.0 / (RRF_K + entries[position][1] + 1) for position in positions)
        group_position, rank, notable = min(entries[position] for position in positions)
        scored.append((-score, group_position, rank, notable))
    scored.sort(key=lambda item: item[:3])
    return [notable for _score, _group_position, _rank, notable in scored], fused


def merge_notables(
    notables: Sequence[Notable], priority: Sequence[str], method: str
) -> tuple[list[Notable], dict[str, Any]]:
    """Merge every generator's ranked list into one final ranking, declaring how."""
    groups = group_by_generator(notables, priority)
    fused = 0
    if method == "blocks":
        merged = [notable for group in groups for notable in group]
    elif method == "interleave":
        merged = _interleave(groups, sum(len(group) for group in groups))
    elif method == "rrf":
        merged, fused = _rrf(groups)
    else:
        raise ValueError(f"unknown merge method: {method!r} (known: {', '.join(MERGE_METHODS)})")
    receipt = {
        "method": method,
        "priority": list(priority),
        "groups": {group[0].generator: len(group) for group in groups if group},
        "merged": len(merged),
        "fused": fused,
    }
    return merged, receipt
