"""Hunt query cancellation and shared effort bounds."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx

from portal.modules.security.core.hunt.executor import REQUEST_BUDGET_EXHAUSTED, HuntExecutor
from portal.modules.security.core.hunt.jobs import (
    HuntBudget,
    query_budget_kind,
)
from portal.modules.security.core.hunt.notables.__main__ import main as notables_main
from portal.modules.security.core.hunt.notables.run import behaviours_stage
from portal.modules.security.core.hunt.notables.sample import (
    IndexFile,
    SourceFacts,
    read_card_sample,
    read_files,
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


def _budget() -> HuntBudget:
    return HuntBudget(
        {"query_seconds": 1, "job_seconds": 5, "requests": 100, "cells": 100, "events": 100}
    )


def test_a_notables_run_after_an_expired_stage_starts_its_own_clock(tmp_path: Path) -> None:
    """`--stage all`: the stage before ran past its job clock and left `job_deadline_exceeded`
    sticky, so every notables read — alerts, exact counts, the deviation series — was refused."""
    search = SimpleNamespace(executor=HuntExecutor(_results_source("sid-clock", []), _budget()))
    out = tmp_path / "run"
    out.mkdir()
    (out / "sources.json").write_text(json.dumps({"index": "i", "cards": []}), "utf-8")
    behaviours_stage(out=out, search=search)
    budget = search.executor.budget
    budget.exhausted = "job_deadline_exceeded"
    budget.started -= budget.limits["job_seconds"]

    code = notables_main(
        ["--index", "i", "--out", str(out), "--stage", "notables", "--generators", "deviation"],
        search=search,
    )

    ledger = [json.loads(line) for line in (out / "ledger.jsonl").read_text().splitlines()]
    reasons = [row["reason"] for row in ledger if row["stage"] == "notables"]
    assert code == 0
    assert reasons and set(reasons) == {None}
    assert budget.exhausted is None


def test_per_file_reads_stream_the_newest_rows_without_a_leading_sort() -> None:
    """A `sort` before `head` scans the whole window first: on a wide window of a
    high-volume source the read is censored with no rows, where `head` streams."""
    executor = HuntExecutor(
        _results_source("sid-head", [{"count": "1000", "_time": "5.0", "host": "h", "_raw": "x"}]),
        _budget(),
    )
    queries: list[str] = []
    executor.read_observer = lambda query, *_args: queries.append(query)
    files = tuple(
        IndexFile(path=path, events=1000, hosts=("h",), first=0.0, last=100.0)
        for path in ("a", "b")
    )
    facts = SourceFacts(
        index="i",
        sourcetype="s",
        events=1000,
        first=0.0,
        last=100.0,
        hosts=("h",),
        host_count=1,
        sources=("a", "b"),
        source_count=2,
        files=files,
    )

    read_files(executor, facts, [(0.0, 100.0)], per_window=400, kind="behavior_events")
    read_card_sample(executor, facts, kind="sample")

    raw = [query for query in queries if query.startswith("search ")]
    assert len(raw) >= 4
    assert all(re.fullmatch(r'search index="i" source="[ab]" \| head \d+', query) for query in raw)


def test_read_many_censors_remaining_requests_on_request_budget_exhaustion() -> None:
    """Budget exhaustion mid-read_many censors remaining reads into the ledger without raising."""
    budget = HuntBudget(
        {"query_seconds": 1, "job_seconds": 5, "requests": 2, "cells": 100, "events": 100},
        concurrency=2,
    )
    executor = HuntExecutor(_results_source("sid-many", [{"_raw": "x"}]), budget)
    observed: list[tuple[str, bool, str | None]] = []
    executor.read_observer = lambda query, _s, _e, read, _src, _part: observed.append(
        (query, read.censored, read.reason)
    )
    requests = [
        (f'search index="i" TERM("k{idx}") | head 5', 0.0, 1.0, "relate", 5) for idx in range(5)
    ]

    outcomes = executor.read_many(requests)

    assert len(outcomes) == 5
    succeeded = [read for read in outcomes if not read.censored]
    censored = [read for read in outcomes if read.censored]
    assert len(succeeded) == 2
    assert len(censored) == 3
    assert all(read.rows == [] and read.reason == REQUEST_BUDGET_EXHAUSTED for read in censored)
    assert budget.queries == 2
    assert budget.exhausted == REQUEST_BUDGET_EXHAUSTED
    assert len(observed) == 5
    assert (
        sum(1 for _q, is_c, reason in observed if is_c and reason == REQUEST_BUDGET_EXHAUSTED) == 3
    )
