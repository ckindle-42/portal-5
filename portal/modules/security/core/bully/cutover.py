"""P7 authoritative-feed cutover helpers.

The six compounding feeds share one three-state contract. ``off`` and
``shadow`` preserve the baseline consumer result; shadow additionally exposes
the replacement result for disagreement evidence. ``authoritative`` consumes
the replacement. Rollback is therefore a mode change that retains records.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FEEDS: tuple[str, ...] = (
    "semantic_hunt_memory",
    "known_state",
    "roi_target_intelligence",
    "training_pair_harvest",
    "fleet_local_fine_tune",
    "playbook_memory",
)
MODES = ("off", "shadow", "authoritative")


@dataclass(frozen=True)
class CutoverResult:
    feed: str
    mode: str
    effective: Any
    baseline: Any
    replacement: Any
    disagreed: bool


def feed_mode(config: dict[str, Any], feed: str) -> str:
    if feed not in FEEDS:
        raise ValueError(f"unknown compounding feed: {feed!r}")
    mode = ((config.get("feeds") or {}).get(feed) or "off").lower()
    if mode not in MODES:
        raise ValueError(f"invalid mode {mode!r} for feed {feed!r}; expected {MODES}")
    return mode


def consume(feed: str, mode: str, *, baseline: Any, replacement: Any) -> CutoverResult:
    if feed not in FEEDS:
        raise ValueError(f"unknown compounding feed: {feed!r}")
    if mode not in MODES:
        raise ValueError(f"invalid mode {mode!r} for feed {feed!r}")
    return CutoverResult(
        feed=feed,
        mode=mode,
        effective=replacement if mode == "authoritative" else baseline,
        baseline=baseline,
        replacement=replacement,
        disagreed=baseline != replacement,
    )


def rollback_drill(feed: str, replacement: Any, baseline: Any) -> dict[str, Any]:
    """Prove authoritative→off restores the baseline byte-for-byte."""
    authoritative = consume(feed, "authoritative", baseline=baseline, replacement=replacement)
    rolled_back = consume(feed, "off", baseline=baseline, replacement=replacement)
    return {
        "feed": feed,
        "authoritative_used_replacement": authoritative.effective == replacement,
        "rollback_restored_baseline": rolled_back.effective == baseline,
        "records_retained": rolled_back.replacement == replacement,
    }
