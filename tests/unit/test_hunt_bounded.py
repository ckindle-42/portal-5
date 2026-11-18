"""Hunt query cancellation and shared effort bounds."""

from __future__ import annotations

from typing import Any

import httpx

from portal.modules.security.core.hunt.executor import HuntExecutor
from portal.modules.security.core.hunt.jobs import (
    HuntBudget,
    query_budget_kind,
)
from portal.modules.security.core.review.window import (
    JobCancel,
    SplunkWindowSource,
)


def _response(request: httpx.Request, payload: dict[str, Any], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload, request=request)


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
