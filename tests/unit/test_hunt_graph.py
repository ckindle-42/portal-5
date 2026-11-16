"""Entity graph: major-value segmentation, co-occurrence, deviation and accumulation."""

from __future__ import annotations

from typing import Any

from portal.modules.security.core.hunt.engine import HOUR
from portal.modules.security.core.hunt.graph import (
    MAX_EDGES_PER_EVENT,
    MAX_VALUES_PER_EVENT,
    Cell,
    build,
    deviations,
    is_term,
    notables,
    values,
)
from portal.modules.security.core.hunt.observations import Observation

START = 1_700_000_000 // HOUR * HOUR
H0 = START
H1 = START + HOUR
H2 = START + 2 * HOUR


def _event(hour: int, raw: str, host: str = "h1", source: str = "s1") -> dict[str, Any]:
    return {"_time": float(hour), "host": host, "source": source, "_raw": raw}


def _graph(
    rows: list[tuple[int, str, str, str, int]],
    history: dict[str, dict[int, int]] | None = None,
    missing: dict[str, str] | None = None,
) -> Any:
    cells: dict[Cell, list[dict[str, Any]]] = {}
    for hour, host, source, raw, count in rows:
        cells.setdefault((host, source, hour), [])
        for _ in range(count):
            cells[(host, source, hour)].append(_event(hour, raw, host, source))
    return build(cells, history, missing)


def _series(hour: int, count: int, prior: int, back: int = 24) -> dict[int, int]:
    series = {hour - step * HOUR: prior for step in range(1, back + 1)}
    series[hour] = count
    return series


def test_values_are_the_major_segments_in_appearance_order() -> None:
    assert values('a b,c\t"d" -- e%20f') == ["a", "b", "c", "d", "e", "f"]
    assert values("a a b") == ["a", "a", "b"]
    assert values("") == []
    # '=' and ':' are minor breakers, so a field pair and a clock stay one major value.
    assert values("user=admin ip=10.0.0.1 10:00:00") == [
        "user=admin",
        "ip=10.0.0.1",
        "10:00:00",
    ]
    # The longest encoded breaker wins before its prefix.
    assert values("a%2526b%26c%3Dd") == ["a", "b", "c", "d"]


def test_nodes_and_edges_keep_counts_per_hour_and_per_host() -> None:
    graph = _graph(
        [
            (H0, "h1", "s1", "a b", 1),
            (H0, "h1", "s1", "a c", 1),
            (H1, "h1", "s1", "a b d", 1),
        ]
    )

    assert graph.truncations == {}
    assert graph.nodes["a"].hours == {H0: 2, H1: 1}
    assert graph.nodes["a"].hosts == {"h1": 3}
    assert graph.nodes["a"].degree == {H0: 2, H1: 2}
    assert graph.edges[("a", "b")].hours == {H0: 1, H1: 1}
    assert graph.edges[("a", "b")].hosts == {"h1": 2}
    assert graph.neighbours("a") == {"b", "c", "d"}
    assert graph.edge_weight("a", "b") == 2


def test_effort_budgets_are_recorded_as_truncation() -> None:
    wide = " ".join(f"w{index}" for index in range(MAX_VALUES_PER_EVENT + 5))
    graph = _graph([(H0, "h1", "s1", wide, 1)])
    assert graph.truncations["values"].events == 1
    assert graph.truncations["values"].dropped == 5
    assert len(graph.nodes) == MAX_VALUES_PER_EVENT

    dense = " ".join(f"d{index}" for index in range(40))
    graph = _graph([(H0, "h1", "s1", dense, 1)])
    possible = 40 * 39 // 2
    assert graph.truncations["edges"].events == 1
    assert graph.truncations["edges"].dropped == possible - MAX_EDGES_PER_EVENT
    assert len(graph.edges) == MAX_EDGES_PER_EVENT
    assert sum(node.degree[H0] for node in graph.nodes.values()) == 2 * MAX_EDGES_PER_EVENT


def test_a_first_hour_is_first_seen_at_retention_start_and_not_a_notable() -> None:
    graph = _graph(
        [
            (H0, "h1", "s1", "a b", 1),
            (H1, "h1", "s1", "a b", 1),
            (H1, "h1", "s1", "late z", 1),
        ]
    )
    recorded = {(dev.entity, dev.hour): dev for dev in deviations(graph)}

    assert recorded[("a", H0)].first_seen is True
    assert recorded[("a", H0)].volume_z is None
    assert recorded[("a", H0)].signals == ()
    assert recorded[("a", H1)].first_seen is False
    assert recorded[("a", H1)].signals == ()
    assert recorded[("late", H1)].first_seen is True
    assert notables(graph, []) == []


def test_volume_above_its_own_prior_hours_is_a_deviation() -> None:
    graph = _graph(
        [
            (H0, "h1", "s1", "a x", 1),
            (H1, "h1", "s1", "a x", 1),
            (H2, "h1", "s1", "a x", 10),
        ]
    )
    ranked = notables(graph, [])

    assert [notable.entity for notable in ranked] == ["a", "x"]
    top = ranked[0]
    assert top.signals == ("volume",)
    assert top.host_hours == (("h1", H2, HOUR),)
    assert top.strength > 0
    assert top.deviations[-1].volume_z is not None and top.deviations[-1].volume_z > 0
    assert top.deviations[-1].prior_hours_active == 2
    lead = top.as_lead()
    assert (lead["host"], lead["hour"], lead["span"]) == ("h1", H2, HOUR)
    assert lead["score"] == top.strength
    assert lead["entity"] == "a"


def test_an_edge_never_seen_in_prior_hours_is_new() -> None:
    graph = _graph(
        [
            (H0, "h1", "s1", "a x", 1),
            (H1, "h1", "s1", "a y", 1),
            (H2, "h1", "s1", "a x", 1),
        ]
    )
    ranked = notables(graph, [])

    assert [notable.entity for notable in ranked] == ["a"]
    assert ranked[0].signals == ("new_edge",)
    assert ranked[0].deviations[0].new_edges == ("y",)
    assert ranked[0].host_hours == (("h1", H1, HOUR),)


def test_peers_are_entities_whose_neighbourhoods_overlap() -> None:
    graph = _graph(
        [
            (H0, "h1", "s1", "a hub", 1),
            (H0, "h1", "s1", "b hub", 1),
            (H1, "h1", "s1", "a hub", 3),
            (H1, "h1", "s1", "b hub", 1),
        ]
    )
    recorded = {(dev.entity, dev.hour): dev for dev in deviations(graph)}

    assert recorded[("a", H1)].peer_volume == 1.0
    assert recorded[("b", H1)].peer_volume == 0.0
    assert recorded[("a", H1)].peer_degree is not None


def test_convergence_across_cells_outranks_one_strong_cell() -> None:
    graph = _graph(
        [
            (H0, "h1", "s1", "wide base", 1),
            (H1, "h2", "s2", "wide three", 3),
            (H2, "h1", "s1", "wide base", 3),
            (H0, "h1", "s1", "deep base", 1),
            (H1, "h1", "s1", "deep base", 20),
            (H2, "h1", "s1", "deep base", 1),
        ]
    )
    names = [notable.entity for notable in notables(graph, [])]

    assert names.index("wide") < names.index("deep")
    wide = next(notable for notable in notables(graph, []) if notable.entity == "wide")
    assert wide.cells == 2
    assert wide.hosts == 2
    assert wide.hours == 2


def test_total_order_breaks_ties_by_entity() -> None:
    graph = _graph(
        [
            (H0, "h1", "s1", "alpha a0", 1),
            (H1, "h1", "s1", "alpha a0", 3),
            (H0, "h1", "s1", "beta b0", 1),
            (H1, "h1", "s1", "beta b0", 3),
        ]
    )
    names = [notable.entity for notable in notables(graph, [])]

    assert names.index("alpha") < names.index("beta")
    plain = {(dev.entity, dev.hour): dev for dev in deviations(graph)}
    twin = (plain[("alpha", H1)], plain[("beta", H1)])
    assert twin[0].volume_z == twin[1].volume_z
    assert twin[0].peer_volume == twin[1].peer_volume


def test_notables_are_the_same_whatever_the_input_order() -> None:
    rows = [
        (H0, "h1", "s1", "a x", 1),
        (H1, "h2", "s2", "a y", 2),
        (H2, "h1", "s1", "a x", 5),
    ]
    forward = _graph(rows)
    backward = _graph(list(reversed(rows)))

    assert [dev.as_dict() for dev in deviations(forward)] == [
        dev.as_dict() for dev in deviations(backward)
    ]
    assert [notable.as_lead() for notable in notables(forward, [])] == [
        notable.as_lead() for notable in notables(backward, [])
    ]


def test_observations_back_the_deviating_host_hour() -> None:
    graph = _graph(
        [
            (H0, "h1", "s1", "user=admin x", 1),
            (H1, "h1", "s1", "user=admin x", 2),
        ]
    )
    backing = Observation("value", "h1", "user=admin", H1, 9.0, {"signal": "burst", "now": 2})
    peer = Observation("value", "h1", "other=thing", H1, 9.0, {"signal": "burst"})
    other_hour = Observation("value", "h1", "user=admin", H0, 9.0, {"signal": "novelty"})

    notable = next(
        item for item in notables(graph, [backing, peer, other_hour]) if item.entity == "user=admin"
    )

    assert [row["entity"] for row in notable.observations] == ["other=thing", "user=admin"]
    assert {row["hour"] for row in notable.observations} == {H1}


def test_a_value_is_a_single_indexed_term_only_when_it_segments_back_to_itself() -> None:
    assert is_term("uid=alpha")
    assert is_term("10.0.0.1")
    assert is_term(":")
    assert is_term("--")
    assert not is_term("a,b")
    assert not is_term("a\tb")
    assert not is_term("__::_[]:__..__<>")
    assert not is_term("")


def test_retention_history_decides_a_steady_value_is_not_a_deviation() -> None:
    graph = _graph(
        [
            (H0, "h1", "s1", "steady burst", 1),
            (H1, "h1", "s1", "steady burst", 1),
            (H2, "h1", "s1", "steady burst", 10),
        ],
        {
            "steady": _series(H2, 3, 3),
            "burst": _series(H2, 9, 1),
        },
    )
    recorded = {(dev.entity, dev.hour): dev for dev in deviations(graph)}

    steady = recorded[("steady", H2)]
    assert steady.history is True
    assert steady.volume == 3  # the index's count, not the 10 sampled events
    assert steady.sampled == 10
    assert steady.volume_z == 0.0
    assert steady.signals == ()
    assert [notable.entity for notable in notables(graph, [])] == ["burst"]


def test_an_entity_without_history_is_scored_and_says_why() -> None:
    graph = _graph(
        [
            (H0, "h1", "s1", "loose x", 1),
            (H1, "h1", "s1", "loose y", 1),
        ],
        missing={"loose": "not_a_term"},
    )
    recorded = {(dev.entity, dev.hour): dev for dev in deviations(graph)}[("loose", H1)]

    assert recorded.history is False
    assert recorded.history_reason == "not_a_term"
    assert recorded.volume == recorded.sampled == 1
    assert recorded.signals == ("new_edge",)
    assert notables(graph, [])[0].entity == "loose"
    assert notables(graph, [])[0].checked is False


def test_a_checked_deviation_outranks_an_unchecked_one() -> None:
    graph = _graph(
        [
            (H0, "h1", "s1", "ana off", 1),
            (H1, "h1", "s1", "ana off", 5),
            (H0, "h1", "s1", "bob p", 1),
            (H1, "h1", "s1", "bob q r s", 1),
        ],
        {"ana": _series(H1, 5, 1)},
        {"bob": "budget"},
    )
    ranked = notables(graph, [])
    names = [notable.entity for notable in ranked]

    assert names[0] == "ana"
    assert ranked[0].checked is True
    assert ranked[names.index("bob")].checked is False


def test_the_strongest_backing_observation_orders_the_notables() -> None:
    graph = _graph(
        [
            (H0, "h1", "s1", "low x", 1),
            (H1, "h1", "s1", "low x", 2),
            (H0, "h2", "s2", "high y", 1),
            (H1, "h2", "s2", "high y", 2),
        ]
    )
    weak = Observation("volume", "h1", "", H1, 1.0, {"signal": "burst"})
    strong = Observation("volume", "h2", "", H1, 9.0, {"signal": "burst"})
    names = [notable.entity for notable in notables(graph, [weak, strong])]

    assert names.index("high") < names.index("low")
    assert names.index("y") < names.index("low")
    lead = next(item.as_lead() for item in notables(graph, [weak, strong]) if item.entity == "high")
    assert lead["trigger_score"] == 9.0
    assert [row["host"] for row in lead["observations"]] == ["h2"]


def test_first_seen_without_prior_history_is_kept_out_of_the_notables() -> None:
    graph = _graph([(H2, "h1", "s1", "new only", 3)], {"new": {H2: 3}})
    recorded = {(dev.entity, dev.hour): dev for dev in deviations(graph)}

    assert recorded[("new", H2)].first_seen is True
    assert recorded[("new", H2)].signals == ()
    assert notables(graph, []) == []
