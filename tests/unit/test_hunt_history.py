"""Novelty weight comes from the stream's prior history in hours, not from bucket counts."""

from __future__ import annotations

import math
from typing import Any

import pytest

from portal.modules.security.core.hunt.engine import HOUR, host_hour_novelty

DAY = 86400
T0 = 100 * DAY + 45 * 60  # a stream starting mid-hour, so the hour zoom has a prior bucket


def _rows(*moments: tuple[float, str]) -> list[dict[str, Any]]:
    return [
        {"_time": float(t), "host": "h", "source": "s", "punct": p, "count": 1} for t, p in moments
    ]


def test_weight_is_the_history_in_hours_not_the_bucket_count() -> None:
    early = host_hour_novelty(_rows((T0, "."), (T0 + 1800, "!")), span=60)
    late = host_hour_novelty(_rows((T0, "."), (T0 + 3 * DAY, "!")), span=60)

    # one prior bucket each, so the old bucket-count weight would be log1p(1) for both
    assert early[(T0 + 1800, "h")][0] == pytest.approx(math.log1p(0.5))
    assert late[(T0 + 3 * DAY, "h")][0] == pytest.approx(math.log1p(72))
    assert early[(T0 + 1800, "h")][0] < late[(T0 + 3 * DAY, "h")][0]


def test_first_day_scores_below_seasoned_history_at_both_zooms() -> None:
    early_min = host_hour_novelty(_rows((T0, "."), (T0 + 1800, "!")), span=60)[(T0 + 1800, "h")][0]
    late_min = host_hour_novelty(_rows((T0, "."), (T0 + 3 * DAY, "!")), span=60)[
        (T0 + 3 * DAY, "h")
    ][0]
    early_hour = host_hour_novelty(_rows((T0, "."), (T0 + 1800, "!")), span=HOUR)[
        (100 * DAY + HOUR, "h")
    ][0]
    late_hour = host_hour_novelty(_rows((T0, "."), (T0 + 3 * DAY, "!")), span=HOUR)[
        (103 * DAY, "h")
    ][0]

    assert early_min < late_min
    assert early_hour < late_hour


def test_the_same_time_gap_weighs_the_same_at_every_zoom() -> None:
    rows = _rows((T0, "."), (T0 + 3 * DAY, "!"))
    by_minute = host_hour_novelty(rows, span=60)[(T0 + 3 * DAY, "h")][0]
    by_hour = host_hour_novelty(rows, span=HOUR)[(103 * DAY, "h")][0]

    assert by_minute == pytest.approx(by_hour)


def test_no_history_is_no_surprise() -> None:
    assert host_hour_novelty(_rows((T0, "!")), span=60) == {}
