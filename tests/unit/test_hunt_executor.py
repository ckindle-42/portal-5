"""The one budgeted executor: deadline hard stop, one classification, per-kind cost."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from portal.modules.security.core.hunt import jobs as hunt_jobs
from portal.modules.security.core.hunt.executor import (
    HuntBudget,
    HuntBudgetExceededError,
    HuntExecutor,
    Read,
)
from portal.modules.security.core.review.window import SplunkWindowSource, WindowFetchError


def test_the_transport_read_path_accepts_the_cancel_handle() -> None:
    parameters = inspect.signature(SplunkWindowSource.iter_post_bounded).parameters
    assert "cancel" in parameters


def test_a_slow_model_stage_does_not_consume_the_read_clock() -> None:
    """A stage that issues no read still spends the wall clock: behaviours starts its own."""
    from portal.modules.security.core.hunt.executor import (
        DEFAULT_BUDGETS,
        HuntBudget,
        HuntExecutor,
    )

    class _OneRow:
        def iter_post_bounded(
            self,
            query: str,
            start: float,
            end: float,
            timeout_seconds: float = 0,
            max_results: int | None = None,
        ) -> list[dict[str, Any]]:
            del query, end, timeout_seconds, max_results
            return [{"_time": start, "host": "h1"}]

    budget = HuntBudget(dict(DEFAULT_BUDGETS) | {"job_seconds": 60.0})
    budget.started -= 600.0  # the model-bound cards stage spent the shared clock
    budget.exhausted = "job_deadline_exceeded"
    budget.queries = 17
    executor = HuntExecutor(_OneRow(), budget)

    budget.restart_clock()

    assert budget.expired_reason() is None
    assert budget.job_remaining() > 59.0
    read = executor.read("search index=ix", 0.0, 1.0, kind="discovery")
    assert read.rows and read.reason is None
    assert budget.queries == 18  # the ceiling stays global: one more request, never a reset


def test_one_capped_evidence_read_does_not_end_the_job(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wheeler shape: a single read cut by its row cap is that query's coverage, not the job."""
    from tests.unit.test_hunt_wire import END, INDEX, START, JobSearch, _plant

    class _CapOnce(JobSearch):
        def __init__(self, events: list[dict[str, Any]]) -> None:
            super().__init__(events)
            self.capped = False

        def iter_post_bounded(
            self,
            query: str,
            start: float,
            end: float,
            timeout_seconds: float = 0,
            max_results: int | None = None,
        ) -> Any:
            if "table _time host source punct _raw" in query and not self.capped:
                self.capped = True
                raise WindowFetchError(
                    f"Splunk search job sid-wheeler result budget exceeded "
                    f"({max_results + 1} > {max_results})",
                    sid="sid-wheeler",
                    censored=True,
                    coverage={"sid": "sid-wheeler", "censored": True},
                    reason="row_cap",
                )
            return super().iter_post_bounded(query, start, end, timeout_seconds, max_results)

    monkeypatch.setattr(hunt_jobs, "_ROOT", tmp_path)
    hunt_jobs._run(
        "hunt-capped-read",
        _CapOnce(_plant()),
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

    job = hunt_jobs.load("hunt-capped-read")
    assert job is not None
    assert job["status"] != "FAILED"
    assert "result budget exceeded" not in str(job.get("error"))
    assert any(slot.get("censored") for slot in job["progress"]["request_kinds"].values()), job[
        "progress"
    ]["request_kinds"]


class _EmptySearch:
    """A transport whose reads would answer if the shared budget ever let one through."""

    def iter_post_bounded(
        self,
        query: str,
        start: float,
        end: float,
        *,
        timeout_seconds: float = 0,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        del query, start, end, timeout_seconds, max_results
        return []


def test_the_observer_sees_a_request_budget_refusal() -> None:
    budget = HuntBudget(
        {"query_seconds": 30.0, "job_seconds": 60.0, "requests": 0, "cells": 10, "events": 10}
    )
    executor = HuntExecutor(_EmptySearch(), budget)
    seen: list[Read] = []
    executor.read_observer = lambda query, start, end, read, source_id, part: seen.append(read)

    with pytest.raises(HuntBudgetExceededError):
        executor.read("search index=ix | head 1", 0.0, 1.0, kind="discovery")

    assert [read.reason for read in seen] == ["request_budget_exhausted"]
    assert seen[0].rows == [] and seen[0].censored


def test_relate_runs_after_a_behaviours_stage_whose_clock_expired(tmp_path: Path) -> None:
    """relate starts its own stage clock: a behaviours deadline expiry never aborts its reads."""
    from portal.modules.security.core.hunt.executor import DEFAULT_BUDGETS
    from portal.modules.security.core.hunt.notables.relate import relate_stage

    class _AnsweringSearch:
        def iter_post_bounded(
            self,
            query: str,
            start: float,
            end: float,
            *,
            timeout_seconds: float = 0,
            max_results: int | None = None,
        ) -> list[dict[str, Any]]:
            del query, start, end, timeout_seconds, max_results
            return [{"_time": 15.0, "host": "h1", "source": "/a.log", "_raw": "uid=33"}]

    budget = HuntBudget(dict(DEFAULT_BUDGETS) | {"job_seconds": 60.0})
    budget.started -= 600.0  # behaviours spent the shared wall clock; the expiry is sticky
    budget.exhausted = "job_deadline_exceeded"
    budget.queries = 17
    search: Any = _AnsweringSearch()
    search.executor = HuntExecutor(search, budget)
    cards = [
        {
            "index": "ix",
            "sourcetype": "st",
            "source_id": "ix:st",
            "structure": "kv",
            "role_overrides": {"actor": {"field": "uid"}},
            "facts": {"sources": ["/a.log"]},
        }
    ]
    (tmp_path / "sources.json").write_text(
        json.dumps({"index": "ix", "start": 0.0, "end": 100.0, "cards": cards}),
        encoding="utf-8",
    )
    notables = [
        {
            "source_id": "ix:st",
            "notable_id": "n1",
            "generator": "alerts",
            "host": "h1",
            "first_seen": 10.0,
            "last_seen": 20.0,
            "entities": [{"role": "actor", "value": "33"}],
        }
    ]
    (tmp_path / "notables.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in notables), encoding="utf-8"
    )

    receipt = relate_stage(out=tmp_path, search=search)

    assert (receipt["seeds"], receipt["requests"]) == (1, 1)  # relate issued its own read
    assert budget.expired_reason() is None
    assert budget.job_remaining() > 59.0
    assert budget.queries == 18  # the request ceiling stays global across the clock restart
