"""The one budgeted executor: deadline hard stop, one classification, per-kind cost."""

from __future__ import annotations

import inspect
import threading
import time
from typing import Any

import httpx
import pytest

from portal.modules.security.core.hunt import jobs as hunt_jobs
from portal.modules.security.core.hunt.executor import (
    HuntBudget,
    HuntBudgetExceededError,
    HuntDeadlineExceededError,
    HuntExecutor,
    Read,
)
from portal.modules.security.core.review.window import SplunkWindowSource, WindowFetchError


class _CappedSource:
    """Serves its rows, then reports the query cut by the cap it was given."""

    def __init__(self, rows: list[dict[str, Any]], *, reason: str = "row_cap") -> None:
        self.rows = rows
        self.reason = reason
        self.caps: list[int | None] = []

    def iter_post_bounded(
        self,
        _query: str,
        _start: float,
        _end: float,
        *,
        timeout_seconds: float,
        max_results: int | None,
        cancel: Any = None,
    ) -> Any:
        self.caps.append(max_results)
        for index, row in enumerate(self.rows):
            if max_results is not None and index >= max_results:
                break
            yield row
        if max_results is not None and len(self.rows) > max_results:
            raise WindowFetchError(
                f"Splunk search job sid-cap result budget exceeded ({len(self.rows)} > {max_results})",
                sid="sid-cap",
                censored=True,
                coverage={"sid": "sid-cap", "censored": True, "cap": max_results},
                reason=self.reason,
            )


def _budget(**limits: float) -> HuntBudget:
    base = {"query_seconds": 1.0, "job_seconds": 10.0, "requests": 100, "cells": 100, "events": 100}
    base.update(limits)
    return HuntBudget(base)


def test_a_row_cap_cut_censors_the_query_and_keeps_what_it_read() -> None:
    source = _CappedSource([{"i": str(index)} for index in range(9)])
    budget = _budget()
    read = HuntExecutor(source, budget).read(
        '| tstats count where index="i" by host _time span=1h',
        0.0,
        1.0,
        kind="volume",
        row_cap=4,
    )

    assert isinstance(read, Read)
    assert read.censored is True
    assert read.reason == "row_cap"
    assert [row["i"] for row in read.rows] == ["0", "1", "2", "3"]  # the cap kept its rows
    assert source.caps == [4]
    assert budget.exhausted is None  # a query's own cap does not spend the shared work
    assert budget.snapshot()["request_kinds"]["volume"] == {
        "requests": 1,
        "seconds": budget.snapshot()["request_kinds"]["volume"]["seconds"],
        "censored": 1,
        "shape": "other",
    }


def test_a_time_bound_cut_censors_that_query_and_the_work_continues() -> None:
    class _SlowOnce(_CappedSource):
        def __init__(self, rows: list[dict[str, Any]]) -> None:
            super().__init__(rows)
            self.slow = True

        def iter_post_bounded(self, *args: Any, **kwargs: Any) -> Any:
            if self.slow:
                self.slow = False
                time.sleep(0.5)
                yield from self.rows
                return
            yield from super().iter_post_bounded(*args, **kwargs)

    source = _SlowOnce([{"i": "0"}])
    budget = _budget(query_seconds=0.05, job_seconds=5.0)
    executor = HuntExecutor(source, budget)

    cut = executor.read(
        '| tstats count where index="i" by host _time span=1h', 0.0, 1.0, kind="volume"
    )
    assert cut.censored is True
    assert cut.reason == "query_bound"

    again = executor.read(
        '| tstats count where index="i" by host _time span=1h', 0.0, 1.0, kind="volume"
    )
    assert again.rows == [{"i": "0"}]
    assert again.censored is False
    assert budget.queries == 2
    assert budget.exhausted is None


def test_the_job_deadline_stops_a_blocking_query() -> None:
    blocked = threading.Event()

    class _Blocked:
        def iter_post_bounded(self, *_args: Any, **_kwargs: Any) -> Any:
            blocked.wait()
            yield {"i": "0"}

    budget = _budget(query_seconds=0.05, job_seconds=0.05)
    began = time.monotonic()
    try:
        with pytest.raises(HuntDeadlineExceededError, match="job_deadline_exceeded"):
            HuntExecutor(_Blocked(), budget).read(
                '| tstats count where index="i"', 0.0, 1.0, kind="x"
            )
    finally:
        blocked.set()

    assert time.monotonic() - began < 2.0
    assert budget.exhausted == "job_deadline_exceeded"


def test_the_job_deadline_cancels_the_transport_job() -> None:
    class _Endless:
        def __init__(self) -> None:
            self.cancelled = threading.Event()

        def iter_post_bounded(
            self,
            _query: str,
            _start: float,
            _end: float,
            *,
            timeout_seconds: float,
            max_results: int | None,
            cancel: Any = None,
        ) -> Any:
            if cancel is not None:
                cancel.bind(self.cancelled.set)
            while True:
                yield {"i": "1"}
                time.sleep(0.01)

    source = _Endless()
    budget = _budget(query_seconds=0.05, job_seconds=0.05)
    with pytest.raises(HuntDeadlineExceededError):
        HuntExecutor(source, budget).read('| tstats count where index="i"', 0.0, 1.0, kind="x")

    assert source.cancelled.wait(5.0)  # the transport's own job cancellation ran


def test_the_transport_read_path_accepts_the_cancel_handle() -> None:
    parameters = inspect.signature(SplunkWindowSource.iter_post_bounded).parameters
    assert "cancel" in parameters


def test_a_cut_at_the_shared_row_budget_keeps_its_rows_and_the_next_read_stops() -> None:
    source = _CappedSource([{"i": str(index)} for index in range(9)])
    budget = _budget(events=3)
    budget.update(phase="investigating")
    executor = HuntExecutor(source, budget)

    cut = executor.read('search index="i" | table _raw', 0.0, 1.0, kind="evidence")
    assert cut.censored is True
    assert cut.reason == "row_cap"
    assert [row["i"] for row in cut.rows] == ["0", "1", "2"]  # the evidence is kept
    assert budget.snapshot()["event_count"] == 3  # the shared budget is now spent

    with pytest.raises(HuntBudgetExceededError, match="result_budget_exhausted"):
        executor.read('search index="i" | table _raw', 0.0, 1.0, kind="evidence")
    assert budget.exhausted == "result_budget_exhausted"


def test_every_kind_reports_requests_seconds_and_censored_reads() -> None:
    class _Censoring(_CappedSource):
        def iter_post_bounded(self, *_args: Any, **_kwargs: Any) -> Any:
            raise WindowFetchError(
                "subsearch truncated",
                sid="sid-c",
                censored=True,
                coverage={"sid": "sid-c"},
                reason="censored",
            )

    budget = _budget()
    executor = HuntExecutor(_Censoring([]), budget)
    executor.read('| tstats count where index="i" by host _time span=1h', 0.0, 1.0, kind="volume")
    executor.read('| tstats count where index="i" by host _time span=1h', 0.0, 1.0, kind="volume")
    executor.read('| tstats count where index="i" by host source', 0.0, 1.0, kind="source")

    kinds = budget.snapshot()["request_kinds"]
    assert kinds["volume"]["requests"] == 2
    assert kinds["volume"]["censored"] == 2
    assert kinds["volume"]["seconds"] >= 0
    assert kinds["source"]["requests"] == 1
    assert kinds["source"]["censored"] == 1


def test_read_many_uses_shared_concurrency_and_keeps_input_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUNT_SPLUNK_CONCURRENCY", "3")

    class _Concurrent:
        def __init__(self) -> None:
            self.lock = threading.Lock()
            self.active = 0
            self.peak = 0

        def iter_post_bounded(self, query: str, *_args: Any, **_kwargs: Any) -> Any:
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            time.sleep(0.02)
            with self.lock:
                self.active -= 1
            yield {"query": query}

    source = _Concurrent()
    executor = HuntExecutor(source, _budget())
    requests = [(str(i), 0.0, 1.0, "sample", 1) for i in range(12)]

    reads = executor.read_many(requests)

    assert source.peak == 3
    assert [read.rows[0]["query"] for read in reads] == [str(i) for i in range(12)]


def test_retryable_splunk_status_retries_spend_shared_request_budget() -> None:
    class _RetryOnce:
        def __init__(self) -> None:
            self.attempts = 0

        def iter_post_bounded(self, *_args: Any, **_kwargs: Any) -> Any:
            self.attempts += 1
            if self.attempts < 3:
                request = httpx.Request("POST", "https://splunk.invalid")
                response = httpx.Response(503, request=request)
                raise httpx.HTTPStatusError("busy", request=request, response=response)
            yield {"value": "ok"}

    source = _RetryOnce()
    budget = _budget()

    read = HuntExecutor(source, budget).read("search index=i", 0.0, 1.0, kind="audit")

    assert read.rows == [{"value": "ok"}]
    assert source.attempts == 3
    assert budget.queries == 3
    assert budget.snapshot()["request_kinds"]["audit"]["requests"] == 3


def test_retryable_quota_response_retries_before_returning_coverage() -> None:
    class _QuotaOnce:
        def __init__(self) -> None:
            self.attempts = 0

        def iter_post_bounded(self, *_args: Any, **_kwargs: Any) -> Any:
            self.attempts += 1
            if self.attempts == 1:
                raise WindowFetchError("search quota exceeded", censored=True)
            yield {"value": "ok"}

    source = _QuotaOnce()
    budget = _budget()

    read = HuntExecutor(source, budget).read("search index=i", 0.0, 1.0, kind="audit")

    assert read.rows == [{"value": "ok"}]
    assert read.reason is None
    assert source.attempts == 2
    assert budget.queries == 2


def test_a_deadline_ends_the_job_partial(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    blocked = threading.Event()

    class _Blocked:
        def iter_post_bounded(self, *_args: Any, **_kwargs: Any) -> Any:
            blocked.wait()
            yield {"count": "1"}

    monkeypatch.setattr(hunt_jobs, "_ROOT", tmp_path)
    try:
        hunt_jobs._run(
            "hunt-deadline",
            _Blocked(),
            "idx",
            0.0,
            2.0,
            1,
            budgets={
                "query_seconds": 0.05,
                "job_seconds": 0.05,
                "requests": 10,
                "cells": 10,
                "events": 10,
            },
        )
    finally:
        blocked.set()

    job = hunt_jobs.load("hunt-deadline")
    assert job is not None
    assert job["status"] == "PARTIAL"
    assert job["progress"]["exhausted_reason"] == "job_deadline_exceeded"
    assert job["finished"] - job["started"] < 5.0


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
