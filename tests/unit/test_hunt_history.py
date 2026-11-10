"""History in time, not buckets, and concentration across zoom levels.

Novelty weight comes from the stream's prior history in hours (a first-day startup is not
well-evidenced), and a minute lead inherits the boot hour's hosts-novel count. Rows go
straight to the engine, or through hunt() over a miniature Splunk -- no network.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

import pytest

from portal.modules.security.core.hunt.engine import HOUR, host_hour_novelty, hunt

DAY = 86400
T0 = 100 * DAY + 45 * 60  # a stream starting mid-hour, so the hour zoom has a prior bucket
BASE = 100 * DAY
H1 = BASE + HOUR
H2 = BASE + 2 * HOUR
ENV = [f"e{i}" for i in range(13)]


def _rows(*moments: tuple[float, str]) -> list[dict[str, Any]]:
    return [
        {"_time": float(t), "host": "h", "source": "s", "punct": p, "count": 1} for t, p in moments
    ]


def _boot_rows() -> list[dict[str, Any]]:
    """13 hosts boot together one minute into H1; hb boots alone 30 minutes in; hq is alone in H2."""
    rows = [{"_time": float(BASE), "host": h, "source": "s", "punct": ".", "count": 1} for h in ENV]
    rows += [
        {"_time": float(H1 + 60), "host": h, "source": "s", "punct": "!", "count": 1} for h in ENV
    ]
    rows += [
        {"_time": float(BASE), "host": "hb", "source": "s", "punct": ".", "count": 1},
        {"_time": float(H1 + 1800), "host": "hb", "source": "s", "punct": "!", "count": 1},
        {"_time": float(BASE), "host": "hq", "source": "s", "punct": ".", "count": 1},
        {"_time": float(H2), "host": "hq", "source": "s", "punct": "@", "count": 1},
    ]
    return rows


class LadderSearch:
    """Answers the ladder and template queries hunt() issues; digging finds no events."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def iter_post(self, q: str, start: float, end: float) -> list[dict[str, Any]]:
        rows = [r for r in self.rows if start <= float(r["_time"]) < end]
        if q.startswith("| tstats min(_time)"):
            times = [float(r["_time"]) for r in rows]
            return [{"lo": min(times), "hi": max(times)}]
        if q.startswith("| tstats count where index="):
            span = int(re.search(r"span=(\d+)s", q).group(1))
            counts = Counter(
                (
                    r["host"],
                    r["source"],
                    r.get("punct", ""),
                    int(float(r["_time"])) // span * span,
                )
                for r in rows
            )
            return [
                {"host": h, "source": s, "punct": p, "_time": t, "count": n}
                for (h, s, p, t), n in counts.items()
            ]
        return []


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
        (BASE + HOUR, "h")
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


def test_minute_lead_inherits_the_boot_hour_concentration() -> None:
    out = hunt(LadderSearch(_boot_rows()), "idx", float(BASE), float(H2 + 60))

    hb_minute = next(lead for lead in out if lead.span == 60 and lead.host == "hb")
    assert hb_minute.hosts_novel_that_hour == 14
    expected = round(math.log1p((H1 + 1800 - BASE) / HOUR) / 14, 2)
    assert hb_minute.novelty == expected
    quiet_hour = next(lead for lead in out if lead.span == HOUR and lead.host == "hq")
    assert quiet_hour.hosts_novel_that_hour == 1
