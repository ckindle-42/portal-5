"""Observation seeds become episodes and then the existing investigation."""

from __future__ import annotations

import re
from typing import Any

from portal.modules.security.core.hunt import jobs
from portal.modules.security.core.hunt.engine import HOUR, hunt
from portal.modules.security.core.hunt.observations import literal_matches, observe
from portal.modules.security.core.review.window import WindowFetchError
from tests.unit.test_hunt_observations import END, INDEX, START, GridSearch, _event, _keyed


def _quoted(query: str, name: str) -> str | None:
    found = re.search(rf'\b{name}="([^"]*)"', query)
    return found.group(1) if found else None


def _raw_rows(query: str, window: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Events a seed or evidence read would return: host, optional source, literal punct."""
    host = _quoted(query, "host")
    source = _quoted(query, "source")
    punct = re.search(r'where punct="((?:\\.|[^"\\])*)"', query)
    punct_value = punct.group(1).replace('\\"', '"') if punct else None
    scopes = [
        (item_host, item_source, int(lo), int(hi))
        for item_host, item_source, lo, hi in re.findall(
            r'\(host="([^"]*)" source="([^"]*)" _time>=(\d+) _time<(\d+)\)', query
        )
    ]
    term = re.search(r'TERM\("([^"]*)"\)', query)
    selected = []
    for row in window:
        if host is not None and row["host"] != host:
            continue
        if source is not None and row["source"] != source:
            continue
        if punct_value is not None and row["punct"] != punct_value:
            continue
        if term is not None and term.group(1) not in str(row.get("_raw", "")):
            continue
        if scopes and not any(
            row["host"] == item_host
            and row["source"] == item_source
            and lo <= float(row["_time"]) < hi
            for item_host, item_source, lo, hi in scopes
        ):
            continue
        selected.append(row)
    head = re.search(r"head (\d+)", query)
    if head:
        selected = selected[: int(head.group(1))]
    return [
        {
            "_time": row["_time"],
            "host": row["host"],
            "source": row["source"],
            "punct": row["punct"],
            "_raw": row["_raw"],
        }
        for row in selected
    ]


def _plant() -> list[dict[str, Any]]:
    """h1 runs for two adjacent hours; h2 shares uid=alpha in the second; h1 returns later."""
    early, mid, late = START, START + HOUR, START + 3 * HOUR
    rows: list[dict[str, Any]] = []
    rows += _event(early, "h1", "uid=alpha", n=2)
    rows += _event(mid, "h1", "uid=alpha", n=8, punct="!!")
    rows += _event(mid, "h2", "uid=alpha", n=4, punct="!!")
    rows += _event(late, "h1", "uid=later", n=1, punct="late")
    return rows


class JobSearch(GridSearch):
    """Observation grids plus the template inventory investigation reads at startup."""

    def iter_post(self, query: str, start: float, end: float) -> list[dict[str, Any]]:
        if "table _time host source punct _raw" in query:
            return _raw_rows(query, self._window(start, end))
        if "by host source punct" in query and "sourcetype" not in query and "span=" not in query:
            counts: dict[tuple[str, str, str], int] = {}
            for row in self._window(start, end):
                key = (str(row["host"]), str(row["source"]), str(row["punct"]))
                counts[key] = counts.get(key, 0) + 1
            return [
                {"host": host, "source": source, "punct": punct, "count": count}
                for (host, source, punct), count in sorted(counts.items())
            ]
        return super().iter_post(query, start, end)

    def iter_post_bounded(
        self,
        query: str,
        start: float,
        end: float,
        timeout_seconds: float = 0,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        return self.iter_post(query, start, end)


def _hosts(lead_obs: list[dict[str, Any]]) -> set[str]:
    return {str(row["host"]) for row in lead_obs}


def _hours(lead_obs: list[dict[str, Any]]) -> set[int]:
    return {int(row["hour"]) for row in lead_obs}


def test_two_runs_return_the_same_seeds_episodes_and_lead_order() -> None:
    rows = _plant()
    first = hunt(GridSearch(rows), INDEX, float(START), float(END), candidates=50)
    second = hunt(GridSearch(rows), INDEX, float(START), float(END), candidates=50)

    assert [lead.as_dict() for lead in first] == [lead.as_dict() for lead in second]
    assert first


def test_episode_order_matches_the_brute_force_grouping() -> None:
    """Leads follow host-hour position. Ties would keep the episode order."""
    from portal.modules.security.core.hunt.evidence import accumulated_host_hours

    rows = _plant()
    run = observe(GridSearch(rows), INDEX, float(START), float(END))
    leads = hunt(GridSearch(rows), INDEX, float(START), float(END), candidates=50)
    investigated = [
        (row["kind"], row["host"], row["entity"], row["hour"])
        for lead in leads
        for row in lead.observations
    ]
    scored = {
        (obs.kind, obs.host, obs.entity, obs.hour): obs.score
        for obs in run.observations
        if obs.score is not None and obs.score > 0
    }

    assert investigated
    assert set(investigated) <= set(scored)
    linked = next(lead for lead in leads if _hosts(lead.observations) == {"h1", "h2"})
    assert _hours(linked.observations) == {START + HOUR}
    assert START + 3 * HOUR not in _hours(linked.observations)
    later = next(lead for lead in leads if START + 3 * HOUR in _hours(lead.observations))
    assert _hosts(later.observations) == {"h1"}
    assert START not in {hour for lead in leads for hour in _hours(lead.observations)}
    position = {
        (cell.host, cell.hour): index
        for index, cell in enumerate(accumulated_host_hours(run.observations))
    }

    def _best(lead: Any) -> int:
        return min(position[(row["host"], int(row["hour"]))] for row in lead.observations)

    assert [_best(lead) for lead in leads] == sorted(_best(lead) for lead in leads)
    assert all(lead.p_yes is None for lead in leads)
    assert all(lead.acc_rank >= 1 for lead in leads)


def test_ranking_requests_stay_constant_as_tokens_grow() -> None:
    small = GridSearch(_keyed(6, ["uid"], tokens=1))
    large = GridSearch(_keyed(40, ["uid"], tokens=12))
    hunt(small, INDEX, float(START), float(END), candidates=15)
    hunt(large, INDEX, float(START), float(END), candidates=15)

    assert len(small.calls) == len(large.calls)
    assert len(small.calls) > 0


def test_literals_match_only_the_observed_value() -> None:
    rows = _plant()
    leads = hunt(GridSearch(rows), INDEX, float(START), float(END), candidates=50)
    shape = next(
        row
        for lead in leads
        for row in lead.observations
        if row["kind"] == "shape" and row["entity"] == "!!"
    )
    other = next(row for row in rows if row["punct"] == "late")
    same = next(row for row in rows if row["punct"] == "!!")

    assert "where punct=" in str(shape["literal"])
    assert literal_matches(same, str(shape["literal"]))
    assert not literal_matches(other, str(shape["literal"]))


def test_a_spent_observation_budget_ends_partial(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(jobs, "_ROOT", tmp_path)
    jobs._run(
        "hunt-wire-budget",
        JobSearch(_plant()),
        INDEX,
        float(START),
        float(END),
        5,
        budgets={
            "query_seconds": 30,
            "job_seconds": 60,
            "requests": 2,
            "cells": 1000,
            "events": 1000,
        },
    )
    job = jobs.load("hunt-wire-budget")

    assert job is not None
    assert job["status"] == "PARTIAL"
    assert job["coverage_complete"] is False
    assert "budget" in str(job["coverage_reason"])
    assert job["status"] != "COMPLETE"


def test_a_spent_investigation_budget_ends_partial(tmp_path: Any, monkeypatch: Any) -> None:
    """Observation fits exactly. The first investigation search spends the request budget."""
    monkeypatch.setattr(jobs, "_ROOT", tmp_path)
    probe = JobSearch(_plant())
    hunt(probe, INDEX, float(START), float(END), candidates=20)
    jobs._run(
        "hunt-wire-invest-budget",
        JobSearch(_plant()),
        INDEX,
        float(START),
        float(END),
        20,
        budgets={
            "query_seconds": 30,
            "job_seconds": 60,
            "requests": len(probe.calls),
            "cells": 1000,
            "events": 1000,
        },
    )
    job = jobs.load("hunt-wire-invest-budget")

    assert job is not None
    assert probe.calls
    assert job["status"] == "PARTIAL"
    assert job["coverage_complete"] is False
    assert job["status"] != "COMPLETE"
    assert "exhausted" in str(job["coverage_reason"])
    assert job["progress"]["observation_request_kinds"]
    assert "volume" in job["progress"]["observation_request_kinds"]


def test_censored_observations_are_not_a_complete_job(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(jobs, "_ROOT", tmp_path)
    jobs._run(
        "hunt-wire-censor",
        JobSearch(_plant(), censored=" punct "),
        INDEX,
        float(START),
        float(END),
        5,
        budgets={
            "query_seconds": 30,
            "job_seconds": 60,
            "requests": 200,
            "cells": 1000,
            "events": 1000,
        },
    )
    job = jobs.load("hunt-wire-censor")

    assert job is not None
    assert job["status"] == "PARTIAL"
    assert job["coverage_complete"] is False
    reasons = job["progress"]["ranking_coverage_reasons"]
    assert any("censored" in reason for reason in reasons)
    assert "volume" in job["progress"]["observation_request_kinds"]
    assert "volume" not in job["progress"]["request_kinds"]
    assert job["progress"]["observation_request_kinds"]["shape"]["censored"] == 1


def test_a_shared_value_becomes_a_case(tmp_path: Any, monkeypatch: Any) -> None:
    """Shape seeds carry no source, the same shape the live grids give investigation."""
    monkeypatch.setattr(jobs, "_ROOT", tmp_path)
    jobs._run(
        "hunt-wire-case",
        JobSearch(_plant(), censored="source sourcetype"),
        INDEX,
        float(START),
        float(END),
        20,
        budgets={
            "query_seconds": 30,
            "job_seconds": 60,
            "requests": 200,
            "cells": 1000,
            "events": 1000,
        },
    )
    job = jobs.load("hunt-wire-case")

    assert job is not None
    assert job["status"] != "FAILED"
    assert job.get("error") is None
    templates = [item for lead in job["leads"] for item in lead.get("novel_templates", [])]
    assert templates
    assert all(item[0] == "" for item in templates)
    assert job["cases"][0]["evidence"]
    hosts = {
        row["host"]
        for lead in job["leads"]
        for row in lead["observations"]
        if row["entity"] == "uid=alpha"
    }
    assert hosts == {"h1", "h2"}
    assert job["cases"]
    assert job["cases"][0]["seed"].split("@", 1)[0] in {"h1", "h2"}
    assert any(row["investigated"] for row in job["observations"])
    assert (
        any(not row["investigated"] for row in job["observations"])
        or len(job["observations"]) <= 20
    )


class _SlowVolume(JobSearch):
    """The whole-index volume grid overruns one query bound. Narrower slices answer."""

    def __init__(self, events: list[dict[str, Any]], *, always: bool) -> None:
        super().__init__(events)
        self.always = always

    def iter_post_bounded(
        self,
        query: str,
        start: float,
        end: float,
        timeout_seconds: float = 0,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        wide = "by host _time span=1h" in query and (self.always or end - start > HOUR)
        if wide:
            raise WindowFetchError(
                f"Splunk search job sid-slow exceeded {timeout_seconds}s",
                sid="sid-slow",
                censored=True,
                coverage={"sid": "sid-slow", "censored": True, "doneProgress": None},
                reason="query_bound",
            )
        return super().iter_post_bounded(
            query, start, end, timeout_seconds=timeout_seconds, max_results=max_results
        )


def _run_slow(tmp_path: Any, monkeypatch: Any, *, always: bool, job_id: str) -> dict[str, Any]:
    monkeypatch.setattr(jobs, "_ROOT", tmp_path)
    jobs._run(
        job_id,
        _SlowVolume(_plant(), always=always),
        INDEX,
        float(START),
        float(END),
        5,
        budgets={
            "query_seconds": 30,
            "job_seconds": 60,
            "requests": 200,
            "cells": 1000,
            "events": 1000,
        },
    )
    job = jobs.load(job_id)
    assert job is not None
    return job


def test_a_slow_volume_grid_is_split_and_the_job_continues(tmp_path: Any, monkeypatch: Any) -> None:
    job = _run_slow(tmp_path, monkeypatch, always=False, job_id="hunt-wire-split")

    assert job["status"] != "FAILED"
    assert "HuntSearchFailedError" not in str(job.get("error"))
    assert "volume" in job["progress"]["observation_request_kinds"]
    reasons = job["progress"]["ranking_coverage_reasons"]
    assert not any(reason.startswith("volume:") for reason in reasons)


def test_a_grid_that_still_overruns_is_partial_not_failed(tmp_path: Any, monkeypatch: Any) -> None:
    job = _run_slow(tmp_path, monkeypatch, always=True, job_id="hunt-wire-bound")

    assert job["status"] == "PARTIAL"
    assert job["status"] != "FAILED"
    assert job["coverage_complete"] is False
    reasons = job["progress"]["ranking_coverage_reasons"]
    assert any(reason == "volume:query_bound" for reason in reasons)
    assert "HuntSearchFailedError" not in str(job.get("error"))
