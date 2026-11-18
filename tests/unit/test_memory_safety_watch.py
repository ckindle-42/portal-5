from __future__ import annotations

from scripts.memory_safety_watch import (
    _trip,
)


def test_watch_ignores_low_swap_while_memory_is_plentiful():
    # The 2026-10-07 W2 false trip: macOS grows swap in 1 GiB files on demand,
    # so low free swap with 87% free memory is not a hazard.
    assert (
        _trip({"swap_free_mb": 791.3, "memory_free_pct": 87, "pressure_critical": False}, 1024, 20)
        is None
    )
    assert (
        _trip({"swap_free_mb": 2048, "memory_free_pct": 10, "pressure_critical": False}, 1024, 20)
        is None
    )
    assert _trip({"swap_free_mb": None, "memory_free_pct": None}, 1024, 20) is None
