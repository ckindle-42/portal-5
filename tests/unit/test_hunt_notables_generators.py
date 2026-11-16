from __future__ import annotations

import json
from typing import Any

from portal.modules.security.core.hunt.executor import Read
from portal.modules.security.core.hunt.notables.behaviours import Behaviour
from portal.modules.security.core.hunt.notables.cards import SourceCard
from portal.modules.security.core.hunt.notables.generators import (
    _alert_query,
    _behaviour_deviations,
    _robust_z,
    _series_by_source,
    _source_deviations,
    alerts,
    exact_counts,
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
    source: str,
    actor: str,
    hosts: int,
    actors: int,
    events: int,
    first: float,
    object_value: str = "shape",
) -> Behaviour:
    return Behaviour(
        source,
        "user",
        actor,
        "image",
        "cmd.exe",
        "path",
        object_value,
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


def test_alert_query_drops_star_adjacent_role_values() -> None:
    query = _alert_query(_alert_facts(), "alpha*medium*verylongsegment", "***")

    assert "verylongsegment" not in query
    assert "medium" not in query
    assert "*" not in query
    assert 'index="ix"' in query


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
    assert '"scan"' in str(notables[0].evidence[0]["query"])
    assert "TERM(" not in str(notables[0].evidence[0]["query"])
    again, _ = alerts(_Executor(rows), [_alert_card()], {"ix:alerts": _alert_facts()})
    assert [item.notable_id for item in again] == [item.notable_id for item in notables]


def test_alerts_route_the_alert_part_of_a_mixed_source():
    activity = SourceCard(
        index="ix",
        sourcetype="eve.json",
        kind="activity",
        roles={"actor": ("src",), "action": ("proto",)},
        understood=True,
        reason=None,
        fmt="json",
        coverage=1.0,
        fields=(),
        sample={},
        facts={},
        model={},
        cache_key="activity",
        part_field="event_type",
        part_value="flow",
    )
    alert = SourceCard(
        index="ix",
        sourcetype="eve.json",
        kind="alert",
        roles={"actor": ("src",), "action": ("sig",)},
        understood=True,
        reason=None,
        fmt="json",
        coverage=1.0,
        fields=(),
        sample={},
        facts={},
        model={},
        cache_key="alert",
        part_field="event_type",
        part_value="alert",
    )
    facts = SourceFacts("ix", "eve.json", 2, 0.0, 60.0, ("h1",), 1, ("s1",), 1)
    rows = [
        {
            "_raw": json.dumps({"event_type": "flow", "src": "a", "proto": "TCP"}),
            "_time": 10.0,
            "host": "h1",
        },
        {
            "_raw": json.dumps({"event_type": "alert", "src": "a", "sig": "ET scan"}),
            "_time": 20.0,
            "host": "h1",
        },
    ]

    notables, receipt = alerts(_Executor(rows), [activity, alert], {"ix:eve.json": facts})

    assert [item.what for item in notables] == ["alert ET scan on a"]
    assert receipt["sources"][0]["card_id"] == alert.card_id


def test_peer_rare_orders_by_share_of_possible_hosts_and_actors():
    behaviours = [
        _behaviour("ix:st", "common", hosts=4, actors=4, events=10, first=1.0),
        _behaviour("ix:st", "lonely", hosts=1, actors=1, events=1, first=5.0),
        _behaviour("ix:st", "middle", hosts=2, actors=1, events=5, first=3.0),
    ]
    stats = {"ix:st": {"hosts_possible": 4, "actors_possible": 4}}
    notables, receipt = peer_rare(behaviours, stats)
    assert (receipt["existed"], receipt["kept"], receipt["tied_at_cut"]) == (3, 3, 0)
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
    assert (receipt["existed"], receipt["kept"], receipt["tied_at_cut"]) == (2, 2, 0)
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


def test_equal_rarity_prefers_the_more_specific_and_better_evidenced_behaviour():
    behaviours = [
        _behaviour("ix:st", "bob", hosts=1, actors=1, events=1, first=1.0),
        _behaviour("ix:st", "amy", hosts=1, actors=1, events=5, first=2.0),
    ]
    stats = {"ix:st": {"hosts_possible": 4, "actors_possible": 4}}
    notables, receipt = peer_rare(behaviours, stats)
    assert notables[0].counts["events"] == 5
    assert receipt["tie_break"] == ["measure", "specificity", "events", "lexical"]


def test_the_receipt_reports_how_many_candidates_tied_at_the_cut():
    behaviours = [
        _behaviour("ix:st", f"actor{index}", hosts=1, actors=1, events=1, first=1.0)
        for index in range(301)
    ]
    stats = {"ix:st": {"hosts_possible": 4, "actors_possible": 400}}
    notables, receipt = peer_rare(behaviours, stats)
    assert len(notables) == 300
    assert receipt["tied_at_cut"] == 301


class _CountExecutor:
    def __init__(self, count: object = "42") -> None:
        self.count = count
        self.queries: list[str] = []

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> Read:
        del start, end, kind, row_cap
        self.queries.append(query)
        return Read([{"count": self.count}], False, None)


def test_exact_counts_replace_sampled_events_where_the_terms_are_indexed():
    behaviours = [_behaviour("ix:st", "bob", hosts=1, actors=1, events=5, first=1.0)]
    notables, _receipt = peer_rare(
        behaviours, {"ix:st": {"hosts_possible": 4, "actors_possible": 4}}
    )
    executor = _CountExecutor("42")
    updated, receipt = exact_counts(executor, "ix", 0.0, 100.0, notables)
    assert receipt["counted"] == 1
    assert receipt["queries"] == 1
    assert receipt["by_source"] == {"ix:st": 1}
    assert updated[0].counts["events"] == 42
    assert updated[0].counts["sampled_events"] == 5
    assert updated[0].counts["counted_from"] == "index_terms"
    assert '"bob"' not in executor.queries[0]
    assert '"shape"' in executor.queries[0]
    assert "TERM(" not in executor.queries[0]


def test_a_non_term_or_below_sample_count_is_declared_not_used():
    behaviours = [
        _behaviour(
            "ix:st", "bob smith", hosts=1, actors=1, events=1, first=1.0, object_value="two words"
        ),
        _behaviour("ix:st", "bob", hosts=1, actors=1, events=5, first=2.0),
    ]
    notables, _receipt = peer_rare(
        behaviours, {"ix:st": {"hosts_possible": 4, "actors_possible": 4}}
    )
    _updated, receipt = exact_counts(_CountExecutor("1"), "ix", 0.0, 100.0, notables)
    assert receipt["counted"] == 0
    assert receipt["reasons"] == {"no_index_terms": 1, "below_sample": 1}


def test_generate_reports_exact_counts_for_peer_rare():
    behaviours = [_behaviour("ix:st", "bob", hosts=1, actors=1, events=5, first=1.0)]
    notables, receipt = generate(
        _CountExecutor("42"),
        "ix",
        0.0,
        100.0,
        [],
        {},
        behaviours,
        {"ix:st": {"hosts_possible": 4, "actors_possible": 4}},
        ["peer_rare"],
    )
    assert notables[0].counts["events"] == 42
    assert receipt["peer_rare"]["exact_counts"]["counted"] == 1


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
