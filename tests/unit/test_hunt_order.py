"""Host-hour order is shared by the bench script and the hunt job."""

from __future__ import annotations

from portal.modules.security.core.hunt.observations import (
    Observation,
    literal_query,
)
from portal.modules.security.core.hunt.order import (
    best_host_hour,
    order_group_indexes,
    positive_seeds,
)


def _shape(host: str, hour: int, entity: str, score: float) -> Observation:
    return Observation(
        "shape",
        host,
        entity,
        hour,
        score,
        {"signal": "burst", "literal": literal_query("shape", "events", host, entity)},
    )


def test_positive_seeds_follow_the_host_hour_sum() -> None:
    busy = [_shape("busy", 0, f"e{i}", 2) for i in range(3)]
    idle = _shape("idle", 0, "zero", 0)
    rows = [_shape("solo", 0, "once", 5), *busy, idle]
    from portal.modules.security.core.hunt.order import accumulated_rows

    ordered = accumulated_rows(rows, "judge_not_configured")

    assert [row["host"] for row in ordered[:2]] == ["busy", "solo"]
    assert ordered[-1]["host"] == "idle"
    assert all(row["p_yes"] is None for row in ordered)
    assert all(row["reason"] == "judge_not_configured" for row in ordered)
    assert {item.host for item in positive_seeds(rows, ordered, 1, 12)} == {"busy"}
    assert idle not in positive_seeds(rows, ordered, 3, 12)


def test_group_order_uses_best_host_hour_and_keeps_ties() -> None:
    rows = [{"host": "a", "hour": 1}, {"host": "b", "hour": 2}]

    assert order_group_indexes([[("b", 2)], [("a", 1), ("b", 2)]], rows) == [1, 0]
    assert order_group_indexes([[("a", 1)], [("a", 1)]], rows) == [0, 1]
    assert best_host_hour([("b", 2), ("a", 1)], rows) == ("a", 1)
