"""The one budgeted executor: deadline hard stop, one classification, per-kind cost."""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from portal.modules.security.core.hunt import jobs as hunt_jobs
from portal.modules.security.core.review.window import SplunkWindowSource, WindowFetchError


def test_the_transport_read_path_accepts_the_cancel_handle() -> None:
    parameters = inspect.signature(SplunkWindowSource.iter_post_bounded).parameters
    assert "cancel" in parameters


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
