"""Case focus: seed hygiene, entity timelines, the merge rule and the focused core.

The Search protocol is mocked with a miniature Splunk over a fixed event list -- no network.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

import pytest

from portal.modules.security.core.hunt import jobs
from portal.modules.security.core.hunt.engine import HOUR, Burst, Lead
from portal.modules.security.core.hunt.investigate import (
    Case,
    Investigator,
    Pivot,
    merge_cases,
)

DAY = 86400


class FakeSearch:
    """Only the query shapes the investigator issues, over a fixed event list."""

    def __init__(self, events: list[dict[str, Any]], fail_on: str = "") -> None:
        self.events = events
        self.fail_on = fail_on
        self.queries: list[str] = []

    def iter_post(self, q: str, start: float, end: float) -> list[dict[str, Any]]:
        self.queries.append(q)
        if self.fail_on and self.fail_on in q:
            raise RuntimeError("search failed")
        rows = [e for e in self.events if start <= float(e["_time"]) < end]
        if q.startswith("| tstats count where index="):
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
        selected = [
            e
            for e in rows
            if (host is None or e["host"] == host)
            and (source is None or e["source"] == source)
            and (token is None or token in e["_raw"])
        ]
        if tail.startswith(" table _raw punct"):
            return [{"_raw": e["_raw"], "punct": e.get("punct", "")} for e in selected]
        if tail.startswith(" head "):
            n = int(re.search(r"head (\d+)", tail).group(1))
            selected = selected[:n]
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
    head = re.sub(r'\b(?:host|source)="[^"]+"', "", q.split("|", 1)[0])
    m = re.search(r'"([^"]+)"', head)
    return m.group(1) if m else None


def _term(q: str) -> str | None:
    m = re.search(r'TERM\("([^"]+)"\)', q)
    return m.group(1) if m else None


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


def test_environment_wide_lead_is_not_investigated() -> None:
    leads = [_lead(i, v) for i, v in enumerate([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])]
    search = FakeSearch([FILLER[0]])
    investigator = Investigator(search, "idx", 0.0, 10**9)

    cases = investigator.investigate_all(leads, dig=20)

    seeds = {c.seed for c in cases}
    assert "h9@1009" not in seeds
    assert "h8@1008" in seeds
    assert not any("tok9x" in q for q in search.queries)
    assert any("tok8x" in q for q in search.queries)


def test_environment_wide_is_relative_to_its_own_zoom_level() -> None:
    # The same hosts-novel count is the rarest band of one level and the whole of another.
    hour_level = [_lead(i, v) for i, v in enumerate([10, 1, 1, 1, 1, 1, 1, 1, 1, 1])]
    minute_level = [_lead(100 + i, 10, span=60) for i in range(10)]
    search = FakeSearch([FILLER[0]])
    investigator = Investigator(search, "idx", 0.0, 10**9)

    seeds = {c.seed for c in investigator.investigate_all(hour_level + minute_level, dig=40)}

    assert "h0@1000" not in seeds
    assert "h100@1100" in seeds


def test_level_maximum_is_skipped_even_without_a_clean_decile() -> None:
    leads = [_lead(0, 10, host="boot"), _lead(1, 1, host="quiet")]
    investigator = Investigator(FakeSearch([FILLER[0]]), "idx", 0.0, 10**9)

    seeds = {c.seed for c in investigator.investigate_all(leads, dig=10)}

    assert "boot@1000" not in seeds
    assert "quiet@1001" in seeds


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


def test_failed_lookups_degrade_only_their_case() -> None:
    search = FakeSearch(ENTITIES + FILLER, fail_on="dedup 2 host source punct")
    investigator = Investigator(search, "idx", 0.0, 10**9)

    case = investigator.investigate(_entity_lead(), depth=1)

    assert case.degraded == investigator.degraded
    assert any(d.startswith("kinds 10.9.0.10") for d in case.degraded)


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
