"""Trace matching by workspace + recency must never pick an OWUI task call.

OWUI's title/tag/follow-up generation arrives as an ordinary chat turn on the same
workspace seconds after the graded one (context_inject._is_owui_task_prompt), so a
summary matched only on identity + recency can return the task call's trace. The
producer marks such turns (owui_task) and both time-based matchers skip them; the
summary also carries `requested`, which both matchers include in their identity set.
"""

from __future__ import annotations

import importlib

bench = importlib.import_module("scripts.bench_security_qat")
owui_client = importlib.import_module("tests.qat.owui_client")

TURN = {
    "correlation_id": "p5-turn",
    "workspace": "auto-security",
    "started_at": 100.0,
}
TASK = {
    "correlation_id": "p5-task",
    "workspace": "auto-security",
    "started_at": 200.0,
    "owui_task": True,
}


def test_bench_newest_trace_skips_the_owui_task_row(monkeypatch) -> None:
    fetched: list[str] = []

    def fake_pipe(path: str) -> dict:
        if path.startswith("/v1/trace?"):
            return {"data": [TASK, TURN]}
        fetched.append(path)
        return {"correlation_id": path.rsplit("/", 1)[-1]}

    monkeypatch.setattr(bench, "pipe", fake_pipe)

    trace = bench.newest_trace("auto-security", 50.0)

    assert trace["correlation_id"] == "p5-turn"
    assert fetched == ["/v1/trace/p5-turn"]


def test_bench_newest_trace_still_skips_unrelated_workspaces(monkeypatch) -> None:
    def fake_pipe(_path: str) -> dict:
        return {"data": [{"correlation_id": "p5-x", "workspace": "other", "started_at": 200.0}]}

    monkeypatch.setattr(bench, "pipe", fake_pipe)
    assert bench.newest_trace("auto-security", 50.0) is None


def test_qat_row_matcher_skips_the_owui_task_row() -> None:
    match = owui_client._trace_row_matches
    assert match(TASK, {"auto-security"}, 50.0) is False
    assert match(TURN, {"auto-security"}, 50.0) is True
    assert match({"workspace": "other", "started_at": 100.0}, {"auto-security"}, 50.0) is False
