"""Hunt query cancellation and shared effort bounds."""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest

from portal.modules.security.core.hunt.jobs import (
    BudgetedSearch,
    HuntBudget,
    HuntBudgetExceededError,
    HuntSearchFailedError,
    query_budget_kind,
)
from portal.modules.security.core.review.window import SplunkWindowSource, WindowFetchError


def _response(request: httpx.Request, payload: dict[str, Any], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload, request=request)


def test_bounded_search_cancels_server_job_after_deadline() -> None:
    cancelled = False
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal cancelled
        calls.append((request.method, request.url.path))
        if request.url.path.endswith("/services/search/jobs"):
            return _response(request, {"sid": "sid-1"})
        if request.url.path.endswith("/sid-1/control"):
            cancelled = True
            return _response(request, {"messages": []})
        if request.url.path.endswith("/sid-1"):
            state = "CANCELED" if cancelled else "RUNNING"
            return _response(
                request,
                {"entry": [{"content": {"isDone": cancelled, "dispatchState": state}}]},
            )
        raise AssertionError(request.url)

    source = SplunkWindowSource(
        url="http://splunk",
        user="user",
        password="password",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(WindowFetchError, match="exceeded"):
        list(
            source.iter_post_bounded(
                "search index=idx", 0.0, 1.0, timeout_seconds=0.03, max_results=10
            )
        )

    assert cancelled
    assert any(path.endswith("/sid-1/control") and method == "POST" for method, path in calls)
    assert calls[-1][1].endswith("/sid-1")


def test_bounded_search_returns_completed_job_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/services/search/jobs"):
            return _response(request, {"sid": "sid-2"})
        if request.url.path.endswith("/sid-2"):
            return _response(
                request,
                {"entry": [{"content": {"isDone": True, "dispatchState": "DONE"}}]},
            )
        if request.url.path.endswith("/sid-2/results"):
            return _response(request, {"results": [{"count": "3"}]})
        raise AssertionError(request.url)

    source = SplunkWindowSource(
        url="http://splunk",
        user="user",
        password="password",
        transport=httpx.MockTransport(handler),
    )

    rows = list(
        source.iter_post_bounded(
            "| tstats count where index=idx", 0.0, 1.0, timeout_seconds=1, max_results=10
        )
    )

    assert rows == [{"count": "3"}]


def test_finalized_before_completion_is_not_returned_as_complete() -> None:
    canceled: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/services/search/jobs"):
            return _response(request, {"sid": "sid-3"})
        if request.url.path.endswith("/control"):
            canceled.append(request.url.path)
            return _response(request, {})
        if request.url.path.endswith("/sid-3"):
            return _response(
                request,
                {
                    "entry": [
                        {
                            "content": {
                                "isDone": True,
                                "isFinalized": True,
                                "dispatchState": "DONE",
                            }
                        }
                    ]
                },
            )
        raise AssertionError(request.url)

    source = SplunkWindowSource(
        url="http://splunk",
        user="user",
        password="password",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(WindowFetchError, match="finalized early"):
        list(
            source.iter_post_bounded(
                "search index=idx", 0.0, 1.0, timeout_seconds=1, max_results=10
            )
        )
    assert canceled == ["/services/search/jobs/sid-3/control"]


def test_finalized_job_with_lagging_cursor_is_censored() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/services/search/jobs"):
            return _response(request, {"sid": "sid-cursor"})
        if request.url.path.endswith("/control"):
            return _response(request, {})
        if request.url.path.endswith("/sid-cursor"):
            return _response(
                request,
                {
                    "entry": [
                        {
                            "content": {
                                "isDone": True,
                                "dispatchState": "DONE",
                                "cursorTime": "100",
                                "latestTime": "5000",
                            }
                        }
                    ]
                },
            )
        raise AssertionError(request.url)

    source = SplunkWindowSource(
        url="http://splunk",
        user="user",
        password="password",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(WindowFetchError, match="incomplete coverage") as excinfo:
        list(
            source.iter_post_bounded(
                "search index=idx", 0.0, 1.0, timeout_seconds=1, max_results=10
            )
        )
    assert excinfo.value.sid == "sid-cursor"
    assert excinfo.value.censored
    assert excinfo.value.coverage["sid"] == "sid-cursor"


def test_failed_cancellation_preserves_sid_and_coverage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/services/search/jobs"):
            return _response(request, {"sid": "sid-4"})
        if request.url.path.endswith("/control"):
            return _response(request, {}, status=500)
        if request.url.path.endswith("/sid-4"):
            return _response(
                request,
                {
                    "entry": [
                        {
                            "content": {
                                "isDone": True,
                                "isFinalized": True,
                                "dispatchState": "DONE",
                                "doneProgress": 0.4,
                            }
                        }
                    ]
                },
            )
        raise AssertionError(request.url)

    source = SplunkWindowSource(
        url="http://splunk",
        user="user",
        password="password",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(WindowFetchError) as excinfo:
        list(
            source.iter_post_bounded(
                "search index=idx", 0.0, 1.0, timeout_seconds=1, max_results=10
            )
        )
    error = excinfo.value
    assert error.sid == "sid-4"
    assert error.censored
    assert error.coverage["sid"] == "sid-4"
    assert error.coverage["censored"] is True
    assert "cancellation_error" in error.coverage
    assert "cancellation of sid-4 failed" in str(error)


def test_uncapped_streaming_paginates_all_results() -> None:
    result_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/services/search/jobs"):
            return _response(request, {"sid": "sid-page"})
        if request.url.path.endswith("/sid-page"):
            return _response(
                request, {"entry": [{"content": {"isDone": True, "dispatchState": "DONE"}}]}
            )
        if request.url.path.endswith("/results"):
            offset = int(request.url.params["offset"])
            result_calls.append(str(offset))
            if offset == 0:
                rows = [{"i": str(i)} for i in range(5000)]
            elif offset == 5000:
                rows = [{"i": str(5000 + i)} for i in range(5000)]
            else:
                rows = [{"i": "10000"}]
            return _response(request, {"results": rows})
        raise AssertionError(request.url)

    source = SplunkWindowSource(
        url="http://splunk",
        user="user",
        password="password",
        transport=httpx.MockTransport(handler),
    )

    rows = list(
        source.iter_post_bounded(
            "| tstats count where index=idx", 0.0, 1.0, timeout_seconds=5, max_results=None
        )
    )

    assert len(rows) == 10001
    assert rows[-1] == {"i": "10000"}
    assert result_calls == ["0", "5000", "10000"]


class _BoundedSearch:
    def iter_post_bounded(
        self,
        _query: str,
        _start: float,
        _end: float,
        *,
        timeout_seconds: float,
        max_results: int | None,
    ) -> list[dict[str, Any]]:
        time.sleep(min(0.02, timeout_seconds / 2))
        return [{"count": "1"}][: max_results or None]


def test_shared_job_deadline_and_request_budget_cover_all_calls() -> None:
    budget = HuntBudget(
        {"query_seconds": 0.05, "job_seconds": 0.1, "requests": 1, "cells": 10, "events": 10}
    )
    search = BudgetedSearch(_BoundedSearch(), budget)

    assert list(search.iter_post("| tstats count", 0.0, 1.0)) == [{"count": "1"}]
    with pytest.raises(HuntBudgetExceededError, match="request_budget_exhausted"):
        list(search.iter_post("| tstats count", 0.0, 1.0))

    assert budget.queries == 1
    assert budget.snapshot()["coverage_complete"] is False


def test_transport_failure_is_distinct_from_budget_exhaustion() -> None:
    class FailedSearch:
        def iter_post_bounded(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            raise OSError("Splunk unavailable")

    search = BudgetedSearch(
        FailedSearch(),
        HuntBudget(
            {"query_seconds": 1, "job_seconds": 2, "requests": 2, "cells": 10, "events": 10}
        ),
    )

    with pytest.raises(HuntSearchFailedError, match="bounded_search_failed:OSError"):
        list(search.iter_post("| tstats count", 0.0, 1.0))


def test_query_budget_kinds_cover_every_owned_query_shape() -> None:
    cases = {
        # indexed aggregates: totals, ladder, series, reduced template inventory
        '| tstats count where index="i"': "discovery",
        '| tstats min(_time) as lo max(_time) as hi where index="i"': "discovery",
        '| tstats count where index="i" TERM("t") by _time span=3600s': "discovery",
        '| tstats count where index="i" by _time span=1h | stats count': "discovery",
        '| tstats count where index="i" by host source punct _time span=60s '
        "| dedup host source punct sortby +_time": "discovery",
        '| tstats count where index="i" by host source punct': "discovery",
        # evidence-location cell enumerations
        '| tstats count where index="i" TERM("h") by host source _time span=3600s': "cells",
        '| tstats count where index="i" TERM("t") by host source': "cells",
        # raw reads
        'search index="i" host="h" | eval r=random() % 1000 | sort r | head 2000 | table _raw': "events",
        'search index="i" (host="h" source="s" _time>=0 _time<1) "t" '
        "| head 501 | table _time host source punct _raw": "events",
    }
    for query, kind in cases.items():
        assert query_budget_kind(query) == kind, query


class _RowSource:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def iter_post_bounded(
        self,
        _query: str,
        _start: float,
        _end: float,
        *,
        timeout_seconds: float,
        max_results: int | None,
    ) -> list[dict[str, Any]]:
        return self.rows[: max_results or None]


def test_discovery_streaming_does_not_consume_evidence_budgets() -> None:
    budget = HuntBudget(
        {"query_seconds": 1, "job_seconds": 10, "requests": 9, "cells": 5, "events": 5}
    )
    source = _RowSource([{"i": str(i)} for i in range(30)])
    search = BudgetedSearch(source, budget)
    reduced = (
        '| tstats count where index="i" by host source punct _time span=60s '
        "| dedup host source punct sortby +_time"
    )

    assert len(list(search.iter_post(reduced, 0.0, 1.0))) == 30
    progress = budget.snapshot()
    assert progress["discovery_row_count"] == 30
    assert progress["cell_count"] == 0
    assert progress["event_count"] == 0

    assert len(list(search.iter_post('search index="i" | table _raw', 0.0, 1.0))) == 5
    assert budget.snapshot()["event_count"] == 5

    assert (
        len(
            list(
                search.iter_post(
                    '| tstats count where index="i" TERM("x") by host source', 0.0, 1.0
                )
            )
        )
        == 5
    )
    assert budget.snapshot()["cell_count"] == 5

    with pytest.raises(HuntBudgetExceededError, match="result_budget_exhausted"):
        list(search.iter_post('| tstats count where index="i" TERM("x") by host source', 0.0, 1.0))
