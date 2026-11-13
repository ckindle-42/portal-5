from __future__ import annotations

import json
from typing import Any

from portal.modules.security.core.hunt.executor import Read
from portal.modules.security.core.hunt.notables.behaviours import Behaviour
from portal.modules.security.core.hunt.notables.cards import SourceCard
from portal.modules.security.core.hunt.notables.generators import (
    _behaviour_deviations,
    _robust_z,
    _series_by_source,
    _source_deviations,
    alerts,
    generate,
    peer_rare,
)
from portal.modules.security.core.hunt.notables.sample import SourceFacts


class _Executor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> Read:
        del query, kind, row_cap
        return Read(
            [dict(row) for row in self.rows if start <= float(row["_time"]) < end],
            False,
            None,
        )


def _behaviour(
    source: str, actor: str, hosts: int, actors: int, events: int, first: float
) -> Behaviour:
    return Behaviour(
        source,
        "user",
        actor,
        "image",
        "cmd.exe",
        "path",
        "shape",
        "literal",
        "literal",
        "shape",
        events,
        first,
        first + 10.0,
        hosts,
        actors,
        10.0,
        "q",
        "raw",
        0.0,
        20.0,
    )


def _alert_card() -> SourceCard:
    return SourceCard(
        index="ix",
        sourcetype="alerts",
        kind="alert",
        roles={"actor": ("user",), "action": ("alert",)},
        understood=True,
        reason=None,
        fmt="json",
        coverage=1.0,
        fields=(),
        sample={},
        facts={},
        model={},
        cache_key="k",
    )


def _alert_facts() -> SourceFacts:
    return SourceFacts("ix", "alerts", 100, 0.0, 3600.0, ("h1", "h2"), 2, ("s1",), 1)


def test_alerts_raise_one_notable_per_distinct_alert_and_entity():
    rows = [
        {"_raw": json.dumps({"alert": "scan", "user": "bob"}), "_time": 10.0, "host": "h1"},
        {"_raw": json.dumps({"alert": "scan", "user": "bob"}), "_time": 20.0, "host": "h2"},
        {"_raw": json.dumps({"alert": "scan", "user": "amy"}), "_time": 30.0, "host": "h1"},
    ]
    notables, receipt = alerts(_Executor(rows), [_alert_card()], {"ix:alerts": _alert_facts()})
    assert receipt["existed"] == 2
    assert [item.what for item in notables] == ["alert scan on bob", "alert scan on amy"]
    assert notables[0].counts["occurrences"] == 2
    assert notables[0].counts["hosts"] == 2
    assert 'TERM("scan")' in str(notables[0].evidence[0]["query"])
    again, _ = alerts(_Executor(rows), [_alert_card()], {"ix:alerts": _alert_facts()})
    assert [item.notable_id for item in again] == [item.notable_id for item in notables]


def test_peer_rare_orders_by_share_of_possible_hosts_and_actors():
    behaviours = [
        _behaviour("ix:st", "common", hosts=4, actors=4, events=10, first=1.0),
        _behaviour("ix:st", "lonely", hosts=1, actors=1, events=1, first=5.0),
        _behaviour("ix:st", "middle", hosts=2, actors=1, events=5, first=3.0),
    ]
    stats = {"ix:st": {"hosts_possible": 4, "actors_possible": 4}}
    notables, receipt = peer_rare(behaviours, stats)
    assert receipt == {"existed": 3, "kept": 3}
    assert [item.entities[0][1] for item in notables] == ["lonely", "middle", "common"]
    assert notables[0].measure_value == 0.0625
    assert notables[-1].measure_value == 1.0


def test_a_missing_actor_is_unknown_not_rare_and_sorts_last():
    behaviours = [
        _behaviour("ix:st", "", hosts=7, actors=0, events=100, first=1.0),
        _behaviour("ix:st", "bob", hosts=1, actors=1, events=1, first=2.0),
    ]
    stats = {"ix:st": {"hosts_possible": 7, "actors_possible": 150}}
    notables, receipt = peer_rare(behaviours, stats)
    assert receipt == {"existed": 2, "kept": 2}
    assert notables[0].measure_value == round(1 / 7 * 1 / 150, 10)
    assert notables[1].measure_value == 1.0
    assert "actor not present in this behaviour" in notables[1].why
    assert "0/150" not in notables[1].why


def test_a_behaviour_without_a_host_is_not_rare_by_zero_hosts():
    behaviours = [_behaviour("ix:st", "bob", hosts=0, actors=1, events=2, first=1.0)]
    stats = {"ix:st": {"hosts_possible": 7, "actors_possible": 150}}
    notables, _receipt = peer_rare(behaviours, stats)
    assert notables[0].measure_value == round(1 / 150, 10)
    assert "host not present in this behaviour" in notables[0].why
    assert "0/7" not in notables[0].why


def test_robust_z_and_source_deviations_rank_a_burst_first():
    steady = [10, 11, 9, 10, 12]
    spike = [10, 10, 10, 10, 900]
    assert _robust_z(steady)[0] < 0.5
    assert _robust_z(spike)[0] > 1.0
    grouped = {
        "quiet": [(float(hour), 10) for hour in range(5)],
        "loud": [(float(hour), 10) for hour in range(4)] + [(4.0, 900)],
    }
    bursts, firsts, detail = _source_deviations(grouped, "ix", 0.0)
    assert detail["sources"] == 2
    assert bursts[0].what.startswith("source loud burst")
    assert firsts[0].measure_value == 0.0


def test_behaviour_deviation_order_is_latest_first_and_stable():
    behaviours = [
        _behaviour("ix:st", "early", 1, 1, 1, 100.0),
        _behaviour("ix:st", "late", 1, 1, 1, 900.0),
    ]
    found, detail = _behaviour_deviations(behaviours, 0.0)
    assert detail == {"existed": 2, "kept": 2}
    assert found[0].measure_value == 900.0
    assert found[1].measure_value == 100.0


def test_series_grouping_ignores_rows_without_a_source():
    grouped = _series_by_source(
        [
            {"sourcetype": "a", "count": "2", "_time": "60"},
            {"sourcetype": "a", "count": "1", "_time": "0"},
            {"sourcetype": "", "count": "9", "_time": "0"},
        ]
    )
    assert grouped == {"a": [(0.0, 1), (60.0, 2)]}


def test_generate_keeps_generators_separately_switchable():
    behaviours = [_behaviour("ix:st", "bob", hosts=1, actors=1, events=1, first=5.0)]
    stats = {"ix:st": {"hosts_possible": 2, "actors_possible": 2}}
    notables, receipt = generate(
        _Executor([]),
        "ix",
        0.0,
        3600.0,
        [],
        {"ix:st": _alert_facts()},
        behaviours,
        stats,
        ["peer_rare"],
    )
    assert [item.generator for item in notables] == ["peer_rare"]
    assert receipt["enabled"] == ["peer_rare"]
    assert "alerts" not in receipt
    empty, _ = generate(_Executor([]), "ix", 0.0, 3600.0, [], {}, behaviours, stats, [])
    assert empty == []
