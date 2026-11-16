"""Hunt query cancellation and shared effort bounds."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from portal.modules.security.core.hunt import jobs as hunt_jobs
from portal.modules.security.core.hunt.engine import Lead
from portal.modules.security.core.hunt.executor import HuntExecutor
from portal.modules.security.core.hunt.investigate import Case, Investigator, Pivot
from portal.modules.security.core.hunt.jobs import (
    BudgetedSearch,
    HuntBudget,
    HuntBudgetExceededError,
    HuntCoverageError,
    HuntSearchFailedError,
    query_budget_kind,
)
from portal.modules.security.core.review.window import (
    JobCancel,
    SplunkWindowSource,
    WindowFetchError,
)


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
        'search index="i" host="h" | eval _k=md5(_raw) | sort 2000 _k _time _raw '
        "| head 2000 | table _raw punct": "events",
        'search index="i" (host="h" source="s" _time>=0 _time<1) "t" '
        "| head 501 | table _time host source punct _raw": "events",
    }
    for query, kind in cases.items():
        assert query_budget_kind(query) == kind, query
    # ranking reads are discovery effort regardless of shape
    for query in cases:
        assert query_budget_kind(query, phase="ranking") == "discovery", query


class _RowSource:
    """Records the result cap each query was given, then serves its rows up to that cap."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.caps: list[int | None] = []

    def iter_post_bounded(
        self,
        _query: str,
        _start: float,
        _end: float,
        *,
        timeout_seconds: float,
        max_results: int | None,
    ) -> list[dict[str, Any]]:
        self.caps.append(max_results)
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

    budget.update(phase="investigating")

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


def test_ranking_reads_are_discovery_effort_with_per_sample_caps() -> None:
    budget = HuntBudget(
        {"query_seconds": 1, "job_seconds": 10, "requests": 9, "cells": 5, "events": 5}
    )
    source = _RowSource([{"i": str(i)} for i in range(20000)])
    search = BudgetedSearch(source, budget)  # the job lifecycle starts in the ranking phase
    sample = 'search index="i" host="h" | eval r=random() % 1000 | sort r | head 2000 | table _raw'
    link = '| tstats count where index="i" TERM("t") by host source'

    assert len(list(search.iter_post(sample, 0.0, 1.0))) == 2000  # per-sample cap, not events
    assert source.caps[-1] == 2000
    assert len(list(search.iter_post(link, 0.0, 1.0))) == 20000  # link enumerations stream
    assert source.caps[-1] is None

    progress = budget.snapshot()
    assert progress["discovery_row_count"] == 22000
    assert progress["event_count"] == 0
    assert progress["cell_count"] == 0

    budget.update(phase="investigating")

    assert len(list(search.iter_post(sample, 0.0, 1.0))) == 5  # now bound by events remaining
    assert source.caps[-1] == 5
    assert budget.snapshot()["event_count"] == 5

    with pytest.raises(HuntBudgetExceededError, match="result_budget_exhausted"):
        list(search.iter_post(sample, 0.0, 1.0))


def _results_source(sid: str, rows: list[dict[str, Any]]) -> SplunkWindowSource:
    """A bounded source over a results-API-shaped payload, served in 5000-row pages."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/results"):
            offset = int(request.url.params["offset"])
            return _response(request, {"results": rows[offset : offset + 5000]})
        if request.url.path.endswith(f"/{sid}"):
            return _response(
                request, {"entry": [{"content": {"isDone": True, "dispatchState": "DONE"}}]}
            )
        if request.url.path.endswith("/services/search/jobs"):
            return _response(request, {"sid": sid})
        raise AssertionError(request.url)

    return SplunkWindowSource(
        url="http://splunk",
        user="user",
        password="password",
        transport=httpx.MockTransport(handler),
    )


ISO_TIME = "2021-03-22T15:06:00.000+00:00"
ISO_EPOCH = datetime(2021, 3, 22, 15, 6, tzinfo=UTC).timestamp()


def test_results_api_iso_time_normalizes_to_epoch_for_capped_reads() -> None:
    rows = [
        {
            "_time": ISO_TIME,
            "host": ["web01", "web01"],  # real results-API multivalue shape
            "source": "auth",
            "punct": ":::: ",
            "count": "3",
        }
    ]

    out = list(
        _results_source("sid-iso", rows).iter_post_bounded(
            '| tstats count where index="idx"', 0.0, 1.0, timeout_seconds=1, max_results=10
        )
    )

    assert out[0]["_time"] == ISO_EPOCH
    assert out[0]["host"] == "web01"  # multivalue flattened to its first value
    assert out[0]["count"] == "3"  # non-time fields keep their wire values


def test_fractional_seconds_and_tz_offsets_survive_normalization() -> None:
    rows = [{"_time": "2021-03-22T10:06:00.250-05:00"}]

    out = list(
        _results_source("sid-frac", rows).iter_post_bounded(
            'search index="idx"', 0.0, 1.0, timeout_seconds=1, max_results=10
        )
    )

    assert out[0]["_time"] == datetime(2021, 3, 22, 15, 6, 0, 250000, tzinfo=UTC).timestamp()


def test_export_style_numeric_time_strings_still_normalize() -> None:
    rows = [{"_time": "1616430360.0"}]

    out = list(
        _results_source("sid-num", rows).iter_post_bounded(
            'search index="idx"', 0.0, 1.0, timeout_seconds=1, max_results=10
        )
    )

    assert out[0]["_time"] == 1616430360.0


def test_malformed_time_fails_loudly_and_never_yields_zero() -> None:
    rows = [{"_time": "2021-13-99T99:99:99+00:00"}]

    with pytest.raises(WindowFetchError, match="unparseable _time") as excinfo:
        list(
            _results_source("sid-bad", rows).iter_post_bounded(
                'search index="idx"', 0.0, 1.0, timeout_seconds=1, max_results=10
            )
        )
    assert excinfo.value.sid == "sid-bad"
    assert not excinfo.value.censored  # a decode failure is a failure, not censored coverage


def test_paginated_results_normalize_iso_time_on_every_page() -> None:
    rows = [{"_time": ISO_TIME, "i": str(i)} for i in range(5002)]

    out = list(
        _results_source("sid-page", rows).iter_post_bounded(
            "| tstats count where index=idx", 0.0, 1.0, timeout_seconds=5, max_results=None
        )
    )

    assert len(out) == 5002
    assert all(row["_time"] == ISO_EPOCH for row in out)


def _message_source(
    sid: str,
    job_messages: list[dict[str, str]],
    results: dict[str, Any],
) -> SplunkWindowSource:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/services/search/jobs"):
            return _response(request, {"sid": sid})
        if request.url.path.endswith("/control"):
            return _response(request, {})
        if request.url.path.endswith("/results"):
            return _response(request, results)
        if request.url.path.endswith(f"/{sid}"):
            return _response(
                request,
                {
                    "entry": [
                        {
                            "content": {
                                "isDone": True,
                                "dispatchState": "DONE",
                                "messages": job_messages,
                            }
                        }
                    ]
                },
            )
        raise AssertionError(request.url)

    return SplunkWindowSource(
        url="http://splunk",
        user="user",
        password="password",
        transport=httpx.MockTransport(handler),
    )


def test_subsearch_warnings_censor_a_done_job_and_benign_warnings_do_not() -> None:
    job_warn = _message_source(
        "sid-sub",
        [{"type": "WARN", "text": "subsearch maxtime limit reached"}],
        {"results": [{"count": "9"}]},
    )
    with pytest.raises(WindowFetchError, match="incomplete work") as job_error:
        list(
            job_warn.iter_post_bounded(
                "search index=idx", 0.0, 1.0, timeout_seconds=1, max_results=10
            )
        )
    assert job_error.value.censored is True
    assert job_error.value.sid == "sid-sub"

    results_warn = _message_source(
        "sid-out",
        [],
        {
            "messages": [{"type": "ERROR", "text": "maxout truncation in subsearch"}],
            "results": [{"_ht": "0", "_hn": "1", "_hs": "1:1"}],
        },
    )
    with pytest.raises(WindowFetchError, match="results reported incomplete") as results_error:
        list(
            results_warn.iter_post_bounded(
                "search index=idx", 0.0, 1.0, timeout_seconds=1, max_results=10
            )
        )
    assert results_error.value.censored is True
    assert results_error.value.sid == "sid-out"

    benign = _message_source(
        "sid-ok",
        [
            {"type": "INFO", "text": "The search scanned 2 buckets"},
            {"type": "WARN", "text": "lookup table geo is not available"},
        ],
        {"messages": [{"type": "INFO", "text": "results ready"}], "results": [{"count": "3"}]},
    )
    rows = list(
        benign.iter_post_bounded("search index=idx", 0.0, 1.0, timeout_seconds=1, max_results=10)
    )
    assert rows == [{"count": "3"}]


def test_censored_transport_stays_a_coverage_error() -> None:
    class _Censored:
        def iter_post_bounded(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            raise WindowFetchError(
                "subsearch truncated",
                sid="sid-c",
                censored=True,
                coverage={"sid": "sid-c", "censored": True},
            )

    search = BudgetedSearch(
        _Censored(),
        HuntBudget(
            {"query_seconds": 1, "job_seconds": 2, "requests": 2, "cells": 10, "events": 10}
        ),
    )

    with pytest.raises(HuntCoverageError, match="subsearch truncated") as excinfo:
        list(search.iter_post("search index=idx", 0.0, 1.0))
    assert excinfo.value.sid == "sid-c"


def test_checkpoint_persists_cases_before_a_spent_wall_clock_raises() -> None:
    seen: list[list[Any]] = []
    budget = HuntBudget(
        {"query_seconds": 1.0, "job_seconds": 0.0, "requests": 10, "cells": 10, "events": 10}
    )
    search = BudgetedSearch(object(), budget)
    search.on_case_checkpoint = lambda _phase, _snapshot, cases: seen.append(list(cases))

    with pytest.raises(HuntBudgetExceededError, match="job_deadline_exceeded"):
        search.checkpoint("investigating", cases=["prior", "current"])

    assert seen == [["prior", "current"]]


def test_no_further_query_is_reserved_after_the_budget_is_spent() -> None:
    budget = HuntBudget(
        {"query_seconds": 1, "job_seconds": 10, "requests": 10, "cells": 10, "events": 1}
    )
    budget.update(phase="investigating")
    search = BudgetedSearch(_RowSource([{"i": "0"}]), budget)

    assert list(search.iter_post('search index="i" | table _raw', 0.0, 1.0)) == [{"i": "0"}]
    with pytest.raises(HuntBudgetExceededError, match="result_budget_exhausted"):
        list(search.iter_post('search index="i" | table _raw', 0.0, 1.0))
    reserved = budget.queries
    with pytest.raises(HuntBudgetExceededError, match="result_budget_exhausted"):
        search.executor.read('search index="i" | table _raw', 0.0, 1.0, kind="read")
    assert budget.queries == reserved


class _InitSearch:
    """Answers the investigator's startup aggregates through the bounded transport."""

    def iter_post_bounded(
        self,
        q: str,
        _start: float,
        _end: float,
        *,
        timeout_seconds: float,
        max_results: int | None,
    ) -> list[dict[str, Any]]:
        if " by _time span=1h" in q:
            return [{"count": 1}]
        if " by host source punct" in q:
            return []
        if q.startswith("| tstats"):
            return [{"count": 1}]
        raise AssertionError(q)


def _stalled_case() -> Case:
    case = Case(seed="h@1", seed_hour=1, partial=True)
    case.pivots.append(Pivot("tok1", 1, 1, 1, 0, 1.0))
    case.events["e"] = {
        "host": "h",
        "source": "s",
        "time": 1.0,
        "raw": "tok1 event",
        "via": "tok1",
        "weight": 1.0,
    }
    return case


def test_budget_and_unexpected_terminals_keep_the_in_progress_partial_case(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hunt_jobs, "_ROOT", tmp_path)
    lead = Lead(hour=1, host="h", novelty=1.0, hosts_novel_that_hour=1, novel_templates=[])
    monkeypatch.setattr(hunt_jobs, "hunt", lambda *_args, **_kwargs: [lead])
    real_checkpoint = hunt_jobs.BudgetedSearch.checkpoint

    def checkpoint_then_wall(self: BudgetedSearch, phase: str, **values: Any) -> None:
        has_cases = "cases" in values
        real_checkpoint(self, phase, **values)
        if has_cases:
            raise HuntBudgetExceededError("job_wall_time_budget_exhausted")

    monkeypatch.setattr(hunt_jobs.BudgetedSearch, "checkpoint", checkpoint_then_wall)

    def budget_blow(self: Investigator, _lead: Lead, **_kwargs: Any) -> Case:
        case = _stalled_case()
        self._stalled = case
        raise HuntBudgetExceededError("result_budget_exhausted")

    monkeypatch.setattr(Investigator, "investigate", budget_blow)
    hunt_jobs._run("hunt-wall", _InitSearch(), "idx", 0.0, 2.0, 1)
    budget_job = hunt_jobs.load("hunt-wall")
    assert budget_job is not None
    assert budget_job["status"] == "PARTIAL"
    assert budget_job["completed_case_count"] == 0
    assert budget_job["cases"][0]["partial"] is True
    assert budget_job["cases"][0]["pivots"][0]["token"] == "tok1"

    def unexpected_blow(self: Investigator, _lead: Lead, **_kwargs: Any) -> Case:
        case = _stalled_case()
        self._stalled = case
        raise RuntimeError("lookup failed")

    monkeypatch.setattr(Investigator, "investigate", unexpected_blow)
    hunt_jobs._run("hunt-fail", _InitSearch(), "idx", 0.0, 2.0, 1)
    failed = hunt_jobs.load("hunt-fail")
    assert failed is not None
    assert failed["status"] == "FAILED"
    assert failed["completed_case_count"] == 0
    assert failed["cases"][0]["partial"] is True
    assert failed["cases"][0]["evidence"]


def test_a_row_cap_yields_its_rows_and_is_never_a_time_bound_cut() -> None:
    """Wheeler's fatal read: the cap message says "exceeded", so text matching called a
    capped query slow. The transport now names the cut, and the executor keeps the rows."""
    source = _results_source("sid-cap", [{"i": str(index)} for index in range(4)])
    budget = HuntBudget(
        {"query_seconds": 1, "job_seconds": 5, "requests": 10, "cells": 10, "events": 10}
    )

    read = HuntExecutor(source, budget).read(
        'search index="idx" | table _raw', 0.0, 1.0, kind="sample", row_cap=3
    )

    assert [row["i"] for row in read.rows] == ["0", "1", "2"]
    assert read.censored is True
    assert read.reason == "row_cap"
    assert budget.exhausted is None


def test_a_cancel_requested_before_the_job_binds_still_cancels_it() -> None:
    token = JobCancel()
    fired: list[str] = []

    token.cancel()
    token.bind(lambda: fired.append("first"))
    token.bind(lambda: fired.append("second"))

    assert fired == ["first", "second"]


def test_a_cancel_after_release_does_nothing() -> None:
    token = JobCancel()
    fired: list[str] = []

    token.bind(lambda: fired.append("late"))
    token.release()
    token.cancel()

    assert fired == []
