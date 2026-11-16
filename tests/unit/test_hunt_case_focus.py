"""Case focus: seed hygiene, entity timelines, the merge rule and the focused core.

The Search protocol is mocked with a miniature Splunk over a fixed event list -- no network.
"""

from __future__ import annotations

import re
import threading
import time
from collections import Counter
from typing import Any

import pytest

from portal.modules.security.core.hunt import jobs
from portal.modules.security.core.hunt.engine import HOUR, Burst, Lead
from portal.modules.security.core.hunt.executor import DEFAULT_BUDGETS, HuntBudget
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

DAY = 86400


class FakeSearch:
    """Only the query shapes the investigator issues, over a fixed event list."""

    def __init__(
        self,
        events: list[dict[str, Any]],
        fail_on: str = "",
        force_term_miss: bool = False,
    ) -> None:
        self.events = events
        self.fail_on = fail_on
        self.force_term_miss = force_term_miss
        self.queries: list[str] = []

    def iter_post(self, q: str, start: float, end: float) -> list[dict[str, Any]]:
        self.queries.append(q)
        if self.fail_on and self.fail_on in q:
            raise RuntimeError("search failed")
        rows = [e for e in self.events if start <= float(e["_time"]) < end]
        if q.startswith("| tstats count where index="):
            if " by host source _time span=3600s" in q:
                term = _term(q)
                source = _clause(q, "source")
                host = _clause(q, "host")
                selected = [
                    e
                    for e in rows
                    if (term is None or (not self.force_term_miss and term in e["_raw"]))
                    and (source is None or source == e["source"])
                    and (host is None or host == e["host"])
                ]
                counts = Counter(
                    (
                        e["host"],
                        e["source"],
                        int(float(e["_time"])) // HOUR * HOUR,
                    )
                    for e in selected
                )
                return [
                    {"host": h, "source": s, "_time": t, "count": n}
                    for (h, s, t), n in counts.items()
                ]
            if " by _time span=1h | stats count" in q:  # populated hours
                return [{"count": len({int(float(e["_time"])) // 3600 for e in rows})}]
            if " by host source punct" in q:
                counts = Counter((e["host"], e["source"], e.get("punct", "")) for e in rows)
                return [
                    {"host": h, "source": s, "punct": p, "count": n}
                    for (h, s, p), n in counts.items()
                ]
            if " by host source" in q:
                term = _term(q)
                counts = Counter(
                    (e["host"], e["source"]) for e in rows if term is None or term in e["_raw"]
                )
                return [{"host": h, "source": s, "count": n} for (h, s), n in counts.items()]
            return [{"count": len(rows)}]
        if q.startswith("| tstats min(_time)"):
            times = [float(e["_time"]) for e in rows]
            return [{"lo": min(times), "hi": max(times)}] if times else [{"lo": 0.0, "hi": 0.0}]
        if q.startswith("search index="):
            return self._search(q, rows)
        raise AssertionError(f"FakeSearch: unhandled query {q!r}")

    def _search(self, q: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        host = _clause(q, "host")
        source = _clause(q, "source")
        token = _quoted_token(q)
        tail = q.split("|", 1)[1]
        scopes = [
            (h, s, int(lo), int(hi))
            for h, s, lo, hi in re.findall(
                r'\(host="([^"]+)" source="([^"]+)" _time>=(\d+) _time<(\d+)\)', q
            )
        ]
        selected = [
            e
            for e in rows
            if (scopes or host is None or e["host"] == host)
            and (scopes or source is None or e["source"] == source)
            and (token is None or token in e["_raw"])
            and (
                not scopes
                or any(
                    e["host"] == h and e["source"] == s and lo <= float(e["_time"]) < hi
                    for h, s, lo, hi in scopes
                )
            )
        ]
        if tail.startswith(" table _raw punct"):
            return [{"_raw": e["_raw"], "punct": e.get("punct", "")} for e in selected]
        if tail.startswith(" head "):
            n = int(re.search(r"head (\d+)", tail).group(1))
            selected = selected[:n]
            if "table _time host source punct _raw" in tail:
                return [
                    {
                        "_time": e["_time"],
                        "host": e["host"],
                        "source": e["source"],
                        "punct": e.get("punct", ""),
                        "_raw": e["_raw"],
                    }
                    for e in selected
                ]
            if "bin _time" in tail:
                counts = Counter(
                    (int(float(e["_time"])) // HOUR * HOUR, e["host"], e["source"])
                    for e in selected
                )
                return [
                    {"_time": t, "host": h, "source": s, "count": c}
                    for (t, h, s), c in counts.items()
                ]
            if "stats count by host source" in tail:
                counts = Counter((e["host"], e["source"]) for e in selected)
                return [{"host": h, "source": s, "count": c} for (h, s), c in counts.items()]
        if "dedup 2 host source punct" in tail:
            return _dedup(selected, ("host", "source", "punct"))
        if "dedup 2 source punct" in tail:
            return _dedup(selected, ("source", "punct"))
        raise AssertionError(f"FakeSearch: unhandled search {q!r}")


def _clause(q: str, name: str) -> str | None:
    m = re.search(rf'\b{name}="([^"]+)"', q)
    return m.group(1) if m else None


def _quoted_token(q: str) -> str | None:
    head = re.sub(r'\b(?:index|host|source)="[^"]+"', "", q.split("|", 1)[0])
    matches = re.findall(r'"([^"]+)"', head)
    return matches[-1] if matches else None


def _term(q: str) -> str | None:
    m = re.search(r'TERM\("([^"]+)"\)', q)
    if m:
        return m.group(1)
    m = re.search(r'index="[^\"]+"\s+"((?:\\.|[^"\\])*)"', q)
    return re.sub(r"\\(.)", r"\1", m.group(1)) if m else None


def _dedup(events: list[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: Counter[tuple[Any, ...]] = Counter()
    out = []
    for e in events:
        key = tuple(e.get(f, "") for f in fields)
        if seen[key] < 2:
            seen[key] += 1
            out.append(
                {
                    "_time": e["_time"],
                    "host": e["host"],
                    "source": e["source"],
                    "punct": e.get("punct", ""),
                    "_raw": e["_raw"],
                }
            )
    return out


def _lead(i: int, hosts_novel: int, *, span: int = HOUR, host: str | None = None) -> Lead:
    return Lead(
        hour=1000 + i,
        host=host or f"h{i}",
        novelty=1.0,
        hosts_novel_that_hour=hosts_novel,
        novel_templates=[],
        bursts=[Burst(f"tok{i}x", 2, 0.0, 1, 3.0)],
        span=span,
    )


FIRST_DAY = 10 * DAY + 23 * HOUR
SECOND_DAY = 11 * DAY + HOUR
ENTITIES = [
    {
        "_time": float(FIRST_DAY),
        "host": "web01",
        "source": "auth",
        "punct": ":::: ",
        "_raw": "session from 10.9.0.10 opened",
    },
    {
        "_time": float(FIRST_DAY + 60),
        "host": "web01",
        "source": "auth",
        "punct": ":::: ",
        "_raw": "session from 10.9.0.10 closed",
    },
    {
        "_time": float(FIRST_DAY + 120),
        "host": "db01",
        "source": "net",
        "punct": "..",
        "_raw": "10.9.0.10 connected",
    },
    {
        "_time": float(SECOND_DAY),
        "host": "web01",
        "source": "auth",
        "punct": ":::: ",
        "_raw": "session from 10.9.0.10 again",
    },
]
FILLER = [
    {
        "_time": float(FIRST_DAY + i * 20),
        "host": "fill",
        "source": "beat",
        "punct": ".",
        "_raw": f"heartbeat {i} ok",
    }
    for i in range(100)
]


def _entity_lead() -> Lead:
    return Lead(
        hour=FIRST_DAY,
        host="web01",
        novelty=1.0,
        hosts_novel_that_hour=1,
        novel_templates=[],
        bursts=[Burst("10.9.0.10", 2, 0.0, 1, 3.0)],
    )


def test_investigation_effort_limit_uses_rank_order() -> None:
    leads = [_lead(i, v) for i, v in enumerate([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])]
    search = FakeSearch([FILLER[0]])
    investigator = Investigator(search, "idx", 0.0, 10**9)

    cases = investigator.investigate_all(leads, dig=9)

    seeds = {c.seed for c in cases}
    assert "h9@1009" not in seeds
    assert "h8@1008" in seeds
    assert not any("tok9x" in q for q in search.queries)
    assert any("tok8x" in q for q in search.queries)


def test_term_cells_use_whole_minor_phrases_and_skip_unclean_handles() -> None:
    search = FakeSearch([FILLER[0]])
    investigator = Investigator(search, "idx", 0.0, 10**9)

    _cells, scans = investigator._term_cells("pivot", {"alpha=medium=verylongsegment", "foo^bar"})

    query = next(q for q in search.queries if "by host source _time span=3600s" in q)
    assert scans == 1
    assert '"alpha=medium=verylongsegment" "verylongsegment"' in query
    assert "*" not in query


def test_independent_investigation_reads_are_concurrent_and_ordered() -> None:
    class ConcurrentSearch:
        def __init__(self) -> None:
            self.lock = threading.Lock()
            self.active = 0
            self.peak = 0

        def iter_post(self, query: str, _start: float, _end: float) -> list[dict[str, str]]:
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            time.sleep(0.02)
            with self.lock:
                self.active -= 1
            return [{"query": query}]

    source = ConcurrentSearch()
    budget = HuntBudget(dict(DEFAULT_BUDGETS), concurrency=3)
    investigator = Investigator.__new__(Investigator)
    investigator.search = jobs.BudgetedSearch(source, budget)
    requests = [(f"query-{index}", 0.0, 1.0) for index in range(12)]

    rows = investigator._rows_many(requests)

    assert source.peak == 3
    assert [group[0]["query"] for group in rows] == [query for query, _s, _e in requests]


def test_investigation_does_not_filter_by_zoom_level_population() -> None:
    # The same hosts-novel count is the rarest band of one level and the whole of another.
    hour_level = [_lead(i, v) for i, v in enumerate([10, 1, 1, 1, 1, 1, 1, 1, 1, 1])]
    minute_level = [_lead(100 + i, 10, span=60) for i in range(10)]
    search = FakeSearch([FILLER[0]])
    investigator = Investigator(search, "idx", 0.0, 10**9)

    seeds = {c.seed for c in investigator.investigate_all(hour_level + minute_level, dig=40)}

    assert "h0@1000" in seeds
    assert "h100@1100" in seeds


def test_high_spread_lead_remains_in_the_ranked_effort_budget() -> None:
    leads = [_lead(0, 10, host="boot"), _lead(1, 1, host="quiet")]
    investigator = Investigator(FakeSearch([FILLER[0]]), "idx", 0.0, 10**9)

    seeds = {c.seed for c in investigator.investigate_all(leads, dig=10)}

    assert "boot@1000" in seeds
    assert "quiet@1001" in seeds


def test_investigation_budget_does_not_apply_a_decile_filter() -> None:
    leads = [_lead(0, 10, host="wide"), _lead(1, 1, host="quiet")]
    investigator = Investigator(FakeSearch([FILLER[0]]), "idx", 0.0, 10**9)

    cases = investigator.investigate_all(leads, dig=2)

    assert {case.seed for case in cases} == {"wide@1000", "quiet@1001"}


def test_pivot_seen_on_two_days_pulls_the_other_days_kinds() -> None:
    investigator = Investigator(FakeSearch(ENTITIES + FILLER), "idx", 0.0, 10**9)

    case = investigator.investigate(_entity_lead(), depth=1)

    timeline = [e for e in case.events.values() if e["via"] == "timeline:10.9.0.10"]
    assert [e["raw"] for e in timeline] == ["session from 10.9.0.10 again"]
    pivot = next(p for p in case.pivots if p.token == "10.9.0.10")
    assert timeline[0]["weight"] == pivot.weight
    assert not any(
        e["raw"] == "session from 10.9.0.10 again" and e["via"] == "10.9.0.10"
        for e in case.events.values()
    )


def test_compound_term_miss_uses_observed_and_expanded_cells() -> None:
    events = [
        {
            "_time": float(FIRST_DAY),
            "host": "web01",
            "source": "access",
            "punct": "::::",
            "_raw": "GET /1.1 status",
        },
        {
            "_time": float(SECOND_DAY),
            "host": "web02",
            "source": "access",
            "punct": "::::",
            "_raw": "GET /1.1 again",
        },
    ]
    lead = Lead(
        hour=FIRST_DAY,
        host="web01",
        novelty=1.0,
        hosts_novel_that_hour=1,
        novel_templates=[],
        bursts=[Burst("/1.1", 2, 0.0, 1, 3.0)],
    )
    search = FakeSearch(events, force_term_miss=True)
    investigator = Investigator(search, "idx", 0.0, 10**9)

    case = investigator.investigate(lead, depth=1)

    pivot = next(p for p in case.pivots if p.token == "/1.1")
    assert pivot.indexed_count is None
    assert pivot.verified_count == 2
    assert pivot.count_semantics == "verified_local_sample_global_unknown"
    assert pivot.weight == 0.0
    assert {event["host"] for event in case.events.values()} == {"web01", "web02"}
    assert any(event["time"] == SECOND_DAY for event in case.events.values())
    assert case.coverage[0]["reason"] == "term_miss_seeded_from_observation"
    assert all(
        "host=" in query and "source=" in query and "_time>=" in query
        for query in search.queries
        if query.startswith("search index=") and "head 501" in query
    )


def test_no_index_or_observation_has_no_raw_whole_index_fallback() -> None:
    search = FakeSearch([FILLER[0]])
    investigator = Investigator(search, "idx", 0.0, 10**9)

    assert investigator.kinds("unobserved") == []

    assert not any(query.startswith("search index=") for query in search.queries)


def test_indexed_plan_cache_respects_environment_window_and_query_semantics() -> None:
    search = FakeSearch(ENTITIES + FILLER)
    investigator = Investigator(search, "idx", 0.0, 10**9)

    plan = investigator._plan("10.9.0.10")
    query_count = len(search.queries)

    assert investigator._plan("10.9.0.10") is plan
    assert len(search.queries) == query_count
    assert next(iter(investigator._plans)) == (
        "idx",
        0.0,
        10**9,
        "10.9.0.10",
        "term-host-source-hour-v1",
    )
    assert investigator.pivot_weight("missing") == 0.0


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


def test_quoted_token_is_escaped_as_a_literal() -> None:
    search = FakeSearch([])
    investigator = Investigator(search, "idx", 0.0, 10**9)
    token = 'value" OR index=*'

    investigator._plan(token)

    term_query = next(
        query
        for query in search.queries
        if query.startswith("| tstats") and "by host source _time span=3600s" in query
    )
    assert '"value" "index"' in term_query
    assert "*" not in term_query
    assert ' "value" OR index=* ' not in term_query


def test_raw_verification_checks_token_boundaries_after_search() -> None:
    events = [
        {
            "_time": float(FIRST_DAY),
            "host": "web01",
            "source": "access",
            "punct": "shape",
            "_raw": "agent connected",
        },
        {
            "_time": float(FIRST_DAY),
            "host": "web01",
            "source": "access",
            "punct": "shape",
            "_raw": "xagent123 connected",
        },
    ]
    search = FakeSearch(events)
    investigator = Investigator(search, "idx", 0.0, 10**9)
    investigator._remember("agent", events[0], "agent", ("access", "shape"), 0)

    rows = investigator.kinds("agent")

    assert [row["_raw"] for row in rows] == ["agent connected"]


def test_censored_local_sample_never_becomes_a_rare_global_count() -> None:
    events = [
        {
            "_time": float(FIRST_DAY),
            "host": f"web{i % 2}",
            "source": "access",
            "punct": "::::",
            "_raw": f"token-unique event {i}",
        }
        for i in range(501)
    ] + [
        {
            "_time": float(FIRST_DAY),
            "host": "filler",
            "source": "metrics",
            "punct": ".",
            "_raw": f"ordinary event {i}",
        }
        for i in range(100)
    ]
    search = FakeSearch(events)
    investigator = Investigator(search, "idx", 0.0, 10**9)

    assert investigator.pivot_weight("token-unique", exact=True) == 0.0

    plan = investigator._plan("token-unique")
    assert plan.indexed_count == 501
    assert plan.verified_count == 500
    assert plan.count_semantics == "indexed_estimate_and_verified_sample"
    assert plan.censored is True
    assert plan.coverage_complete is False


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


def test_failed_lookups_degrade_only_their_case() -> None:
    search = FakeSearch(ENTITIES + FILLER, fail_on="table _time host source punct _raw")
    investigator = Investigator(search, "idx", 0.0, 10**9)

    case = investigator.investigate(_entity_lead(), depth=1)

    assert case.degraded == investigator.degraded
    assert any(d.startswith("evidence 10.9.0.10") for d in case.degraded)


def test_case_view_shows_the_core_not_every_event(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jobs, "_ROOT", tmp_path)
    case = _weighted_case(40)
    payload = {**case.summary(), "evidence": list(case.events.values())}
    jobs._write("hunt-test", {"job_id": "hunt-test", "cases": [payload]})

    view = jobs.case_view(job_id="hunt-test", case_no=1, n=10)

    assert "events" not in view
    assert "hosts" not in view
    assert view["core_events"] == len(case.core())
    assert len(view["core"]) == 10
    assert len(view["picture"]) == 10
    assert view["core"][0].split(": ", 1)[1] == case.core()[0]["raw"][:180]
