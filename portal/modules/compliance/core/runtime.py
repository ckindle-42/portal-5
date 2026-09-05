"""Process-local call counters used only to prove routed V3 wiring."""

from __future__ import annotations

from collections import Counter

CALL_COUNTS: Counter[str] = Counter()


def bump(component: str) -> None:
    CALL_COUNTS[component] += 1


def snapshot() -> dict[str, int]:
    return dict(CALL_COUNTS)
