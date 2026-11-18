"""Case focus: seed hygiene, entity timelines, the merge rule and the focused core.

The Search protocol is mocked with a miniature Splunk over a fixed event list -- no network.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from portal.modules.security.core.hunt.engine import HOUR, Lead
from portal.modules.security.core.hunt.investigate import (
    SEED_SAMPLE,
    Case,
    Investigator,
    Pivot,
    RetrievalPlan,
    _slot_variability,
    _tokens,
    merge_cases,
)


def test_shape_slot_variability_discounts_constant_values_and_dates() -> None:
    events = [
        {"source": "a", "punct": "shape", "_raw": "fixed action target"},
        {"source": "a", "punct": "shape", "_raw": "fixed action-2 target-2"},
        {"source": "b", "punct": "other", "_raw": "fixed event-1"},
        {"source": "b", "punct": "other", "_raw": "fixed event-2"},
    ]

    variability = _slot_variability(events)

    assert variability["fixed"] < variability["action"]
    assert variability["fixed"] < variability["target"]
    assert "2026-11-10" not in _tokens("observed 2026-11-10 fixed")


def test_seed_punct_where_is_exact_before_head_for_star_and_quote() -> None:
    star = 'user=* "admin"'
    quoted = 'say "hi" *'
    neighbor = "user= admin"
    events = [
        {"_time": 1000.0, "host": "h", "source": "svc", "punct": star, "_raw": "user admin login"},
        {
            "_time": 1001.0,
            "host": "h",
            "source": "svc",
            "punct": neighbor,
            "_raw": "user other login",
        },
        {"_time": 1002.0, "host": "h", "source": "svc", "punct": quoted, "_raw": "say hi there"},
    ]

    class _SeedSearch:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def iter_post(self, q: str, start: float, end: float) -> list[dict[str, Any]]:
            self.queries.append(q)
            if " by host source punct" in q:
                return [{"host": "h", "source": "svc", "punct": star, "count": 1}]
            if " by _time span=1h" in q:
                return [{"count": 1}]
            if q.startswith("| tstats"):
                return [{"count": 1, "host": "h", "source": "svc", "_time": 1000.0}]
            if q.startswith("search "):
                # Every event comes back, including one a punct=* search would have admitted.
                return [
                    {
                        "_time": event["_time"],
                        "host": event["host"],
                        "source": event["source"],
                        "punct": event["punct"],
                        "_raw": event["_raw"],
                    }
                    for event in events
                    if start <= float(event["_time"]) < end
                ]
            raise AssertionError(q)

    search = _SeedSearch()
    investigator = Investigator(search, "idx", 0.0, 10**9)
    lead = Lead(
        hour=1000,
        host="h",
        novelty=1.0,
        hosts_novel_that_hour=1,
        novel_templates=[("svc", star, 1), ("svc", quoted, 1)],
        span=HOUR,
    )

    investigator.seed_tokens(lead, examine=20)

    seed_queries = [q for q in search.queries if q.startswith("search ")]
    assert len(seed_queries) == 2
    expected = (
        '| where punct="user=* \\"admin\\""',
        '| where punct="say \\"hi\\" *"',
    )
    for query, where in zip(seed_queries, expected, strict=True):
        head, rest = query.split("|", 1)
        assert "punct" not in head
        assert 'host="h"' in head and 'source="svc"' in head
        assert where in query
        assert query.index("| where punct=") < query.index("| head ")
        assert f"| head {SEED_SAMPLE + 1} " in query
        assert rest.strip().startswith("where punct=")
    shapes = {row["shape"][1] for rows in investigator._provenance.values() for row in rows}
    assert shapes == {star, quoted}
    assert "other" not in investigator._provenance


def test_pivot_checkpoint_carries_prior_cases_and_the_current_one() -> None:
    recorded: list[list[Case]] = []

    class _CheckpointSearch:
        def iter_post(self, q: str, start: float, end: float) -> list[dict[str, Any]]:
            if " by _time span=1h" in q:
                return [{"count": 1}]
            if " by host source punct" in q:
                return []
            if q.startswith("| tstats"):
                return [{"count": 1}]
            raise AssertionError(q)

        def checkpoint(self, phase: str, **values: Any) -> None:
            assert phase == "investigating"
            recorded.append(list(values["cases"]))

    investigator = Investigator(_CheckpointSearch(), "idx", 0.0, 10.0)
    prior = Case(seed="prior", seed_hour=0, partial=False)
    investigator.completed_cases = [prior]
    plan = RetrievalPlan(token="tok1", cells=(), indexed_count=1, coverage_complete=True)
    investigator.seed_tokens = lambda _lead, examine: ["tok1"]  # type: ignore[method-assign]
    investigator.footprint = lambda _token, exact=False: (1, 1, 1)  # type: ignore[method-assign]
    investigator.pivot_weight = lambda _token, exact=False: 1.0  # type: ignore[method-assign]
    investigator._plan = lambda _token: plan  # type: ignore[method-assign]
    investigator._token_evidence = lambda *_a, **_k: (Counter(), [], [])  # type: ignore[method-assign]
    current = Case(seed="h@0", seed_hour=0, partial=True)
    lead = Lead(
        hour=0,
        host="h",
        novelty=1.0,
        hosts_novel_that_hour=1,
        novel_templates=[],
    )

    investigator._investigate_into(current, lead, depth=1, breadth=1, examine=1, minutes=1)

    assert recorded
    assert recorded[0] == [prior, current]
    assert current in recorded[0]


def _case(seed: str, pivots: list[Pivot]) -> Case:
    return Case(seed=seed, seed_hour=0, pivots=list(pivots))


def test_deep_common_pivot_does_not_merge() -> None:
    a = _case(
        "a",
        [
            Pivot("bg", 500, 9, 4, 2, 0.5),
            Pivot("a1", 4, 2, 2, 0, 3.0),
            Pivot("a2", 5, 2, 2, 1, 2.9),
        ],
    )
    b = _case(
        "b",
        [
            Pivot("bg", 500, 9, 4, 2, 0.5),
            Pivot("b1", 4, 2, 2, 2, 3.0),
            Pivot("b2", 5, 2, 2, 2, 2.9),
        ],
    )

    assert len(merge_cases([a, b])) == 2


def test_merge_cases_preserves_coverage_from_both_seeds() -> None:
    left = _case("left", [Pivot("shared", 1, 1, 1, 0, 1.0)])
    right = _case("right", [Pivot("shared", 1, 1, 1, 0, 1.0)])
    left.coverage.append({"token": "left-token", "coverage_complete": False})
    right.coverage.append({"token": "right-token", "coverage_complete": False})

    merged = merge_cases([left, right])

    assert len(merged) == 1
    assert [row["token"] for row in merged[0].coverage] == ["left-token", "right-token"]


def test_deep_pivot_never_merges_even_when_specific() -> None:
    a = _case(
        "a",
        [Pivot("bg", 3, 2, 2, 2, 3.0), Pivot("a1", 4, 2, 2, 0, 3.0), Pivot("a2", 5, 2, 2, 1, 2.9)],
    )
    b = _case(
        "b",
        [Pivot("bg", 3, 2, 2, 2, 3.0), Pivot("b1", 4, 2, 2, 2, 3.0), Pivot("b2", 5, 2, 2, 2, 2.9)],
    )

    assert len(merge_cases([a, b])) == 2


def test_specific_shared_pivot_near_a_seed_merges() -> None:
    a = _case(
        "a",
        [Pivot("bg", 3, 2, 2, 0, 3.0), Pivot("a1", 4, 2, 2, 0, 3.0), Pivot("a2", 5, 2, 2, 1, 2.9)],
    )
    b = _case(
        "b",
        [Pivot("bg", 3, 2, 2, 2, 3.0), Pivot("b1", 4, 2, 2, 2, 3.0), Pivot("b2", 5, 2, 2, 2, 2.9)],
    )

    merged = merge_cases([a, b])

    assert len(merged) == 1
    assert merged[0].merged_from == ["a", "b"]


def _weighted_case(n: int) -> Case:
    case = Case(seed="s", seed_hour=0)
    case.pivots = [
        Pivot("p", 2, 2, 2, 0, 1.0),
        Pivot("q", 3, 2, 2, 0, 1.0),
        Pivot("r", 4, 2, 2, 1, 1.0),
    ]
    case.events = {
        f"e{i}": {
            "host": f"h{i % 3}",
            "source": "s",
            "time": float(i),
            "raw": f"e{i}",
            "via": "p",
            "weight": float(i),
        }
        for i in range(n)
    }
    return case


def test_core_is_median_weighted_capped_and_in_time_order() -> None:
    case = _weighted_case(600)

    core = case.core()

    assert len(core) == 200
    assert [e["time"] for e in core] == sorted(e["time"] for e in core)
    assert min(e["weight"] for e in core) == 400.0
    summary = case.summary()
    assert summary["events"] == 600
    assert summary["core_events"] == 200
    assert summary["core_hosts"] == 3
    assert summary["pivot_depths"] == {0: 2, 1: 1}
    assert len(summary["picture"]) == 25
    assert {e["time"] for e in summary["picture"]} <= {e["time"] for e in core}


def test_core_is_fair_across_normalized_via_routes() -> None:
    case = Case(seed="s", seed_hour=0)
    url = "https://example.test/a:b"
    case.pivots = [
        Pivot(token, 2, 2, 2, 0, 1.0)
        for token in ("dominant", "route-a", "route-b", "route-c", url)
    ]
    next_event = 0

    def add(route: str, via: str, count: int) -> None:
        nonlocal next_event
        for _ in range(count):
            case.events[f"e{next_event}"] = {
                "host": "h",
                "source": "s",
                "time": float(next_event),
                "raw": f"event {next_event}",
                "via": via,
                "weight": 1.0,
                "kind": f"{route}-{next_event}",
                "kind_count": 1,
            }
            next_event += 1

    add("dominant", "dominant", 240)
    add("route-a", "route-a", 80)
    add("route-a", "timeline:route-a", 80)
    add("route-a", "near:timeline:route-a", 80)
    add("route-b", "near:route-b", 120)
    add("route-c", "near:timeline:route-c", 120)
    add("url", url, 40)
    add("url", f"near:{url}", 40)

    core = case.core()
    counts: dict[str, int] = {}
    for event in core:
        via = event["via"]
        route = (
            "route-a"
            if via in {"route-a", "timeline:route-a", "near:timeline:route-a"}
            else "route-b"
            if via == "near:route-b"
            else "route-c"
            if via == "near:timeline:route-c"
            else "url"
            if via in {url, f"near:{url}"}
            else "dominant"
        )
        counts[route] = counts.get(route, 0) + 1

    assert len(core) == 200
    assert counts == {"dominant": 40, "route-a": 40, "route-b": 40, "route-c": 40, "url": 40}
    assert any(event["via"] == url for event in core)
    assert [event["time"] for event in core] == sorted(event["time"] for event in core)


def test_core_keeps_seed_priority_kind_budget_and_zero_cap() -> None:
    case = Case(seed="s", seed_hour=0, seed_windows=[("seed", 100, 110)])
    case.pivots = [Pivot(token, 2, 2, 2, 0, 1.0) for token in ("a", "b", "c", "d", "out")]
    for route in ("a", "b", "c", "d"):
        case.events[f"seed-{route}"] = {
            "host": "seed",
            "source": "s",
            "time": 100.0 + ord(route) - ord("a"),
            "raw": f"seed {route}",
            "via": route,
            "weight": 1.0,
            "kind": "shared",
            "kind_count": 1,
        }
        case.events[f"unique-{route}"] = {
            "host": "seed",
            "source": "s",
            "time": 104.0 + ord(route) - ord("a"),
            "raw": f"unique {route}",
            "via": route,
            "weight": 1.0,
            "kind": f"unique-{route}",
            "kind_count": 1,
        }
    case.events["outward"] = {
        "host": "other",
        "source": "s",
        "time": 200.0,
        "raw": "outward high weight",
        "via": "out",
        "weight": 1000.0,
        "kind": "outward",
        "kind_count": 1,
    }

    core = case.core(cap=4)

    assert len(core) == 4
    assert sum(event["host"] == "seed" for event in core) == 3
    assert sum(event["host"] == "other" for event in core) == 1
    assert sum(event["kind"] == "shared" for event in core) == 3
    assert [event["time"] for event in core] == sorted(event["time"] for event in core)
    assert case.core(cap=0) == []


def test_core_keeps_outward_relations_when_seed_routes_are_many() -> None:
    case = Case(seed="s", seed_hour=0, seed_windows=[("seed", 0, 1000)])
    case.pivots = [Pivot(f"p{i}", 2, 2, 2, 0, 1.0) for i in range(20)]
    for i in range(20):
        case.events[f"seed-{i}"] = {
            "host": "seed",
            "source": "s",
            "time": float(i),
            "raw": f"seed event {i}",
            "via": f"p{i}",
            "kind": f"seed-kind-{i}",
        }
        case.events[f"out-{i}"] = {
            "host": f"other-{i}",
            "source": "s",
            "time": float(1000 + i),
            "raw": f"outward event {i}",
            "via": f"timeline:p{i}",
            "kind": f"out-kind-{i}",
        }

    core = case.core(cap=10)

    assert len(core) == 10
    assert sum(event["host"] == "seed" for event in core) == 5
    assert sum(event["host"].startswith("other-") for event in core) == 5
    assert any(event["via"].startswith("timeline:") for event in core)
