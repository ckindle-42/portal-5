"""Tests for orchestration_acceptance.py against the fake Pipeline rig."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tests" / "unit"), str(ROOT / "scripts")]

import orchestration_acceptance as acceptance  # noqa: E402
from orchestration_fake_pipeline import FakePipeline, finish_response  # noqa: E402

from portal.platform.inference.router import auth  # noqa: E402


def _run_scenario(name: str, workdir: Path, live: bool = False) -> dict[str, Any]:
    return acceptance.run_scenario(
        name, workdir, live=live, pipeline_url="", api_key="", fast_digest="", deep_digest=""
    )


def _run_live_scenario(name: str, workdir: Path, pipeline_url: str) -> dict[str, Any]:
    return acceptance.run_scenario(
        name,
        workdir,
        live=True,
        pipeline_url=pipeline_url,
        api_key=auth.PIPELINE_API_KEY,
        fast_digest="fast-digest",
        deep_digest="deep-digest",
    )


def test_live_happy_path_accepts_a_goal_stated_answer(tmp_path: Path):
    """N1: the live criterion is satisfiable because the goal states the checked token."""
    bite = acceptance._live_bite()
    assert bite["accept"] == [{"type": "contains", "value": acceptance.LIVE_TOKEN}]
    assert acceptance.LIVE_TOKEN in bite["goal"]

    pipeline = FakePipeline()
    pipeline.add("fast", finish_response(acceptance.LIVE_TOKEN))
    try:
        result = _run_live_scenario("happy_path", tmp_path, pipeline.url)
    finally:
        pipeline.close()

    assert result["status"] == "PASS", result["evidence"]
    assert pipeline.requests[0]["model"] == "auto-daily::fast"


def test_live_happy_path_reports_the_failed_check(tmp_path: Path):
    """N1: a wrong live answer fails with its cause, not an empty AssertionError."""
    pipeline = FakePipeline()
    for _ in range(3):
        pipeline.add("fast", finish_response("no token here"))
    pipeline.add("deep", finish_response("no token here"))
    try:
        result = _run_live_scenario("happy_path", tmp_path, pipeline.url)
    finally:
        pipeline.close()

    assert result["status"] == "FAIL"
    assert "BLOCKED after 4 attempt(s)" in result["evidence"]
    assert "not found" in result["evidence"]


def test_acceptance_dry_run_repeats_in_the_same_workdir(tmp_path: Path):
    """N2: a second run in the same workdir must not collide with the first run's tasks."""
    first = acceptance.run_dry_run(tmp_path)
    second = acceptance.run_dry_run(tmp_path)

    assert first["summary"]["failed"] == 0
    assert second["summary"] == first["summary"], second["summary"]
    for result in second["results"]:
        assert result["status"] == "PASS", f"{result['scenario']}: {result['evidence']}"


def test_acceptance_dry_run_all_scenarios_pass(tmp_path: Path):
    """The full dry-run passes and reports a truthful summary."""
    receipt = acceptance.run_dry_run(tmp_path)

    assert receipt["head"] and receipt["utc"]
    assert receipt["mode"] == "dry-run"
    assert receipt["gate_evidence"] is False
    assert receipt["summary"] == {
        "total": len(acceptance.SCENARIOS),
        "passed": len(acceptance.SCENARIOS),
        "failed": 0,
        "skipped": 0,
        "required_skipped": 0,
    }
    for result in receipt["results"]:
        assert result["status"] == "PASS", f"{result['scenario']}: {result['evidence']}"


def test_acceptance_dry_run_phase_filter(tmp_path: Path):
    """--phase filters the dry-run exactly like live mode."""
    phase_one = acceptance.run_dry_run(tmp_path, phases=[1])
    phase_two = acceptance.run_dry_run(tmp_path / "phase2", phases=[2])

    assert {row["phase"] for row in phase_one["results"]} == {"1"}
    assert {row["phase"] for row in phase_two["results"]} == {"2"}
    assert len(phase_one["results"]) + len(phase_two["results"]) == len(acceptance.SCENARIOS)


def test_acceptance_receipts_written(tmp_path: Path):
    """JSON and Markdown receipts carry mode, scope and summary."""
    receipt = acceptance.run_dry_run(tmp_path, phases=[1])
    json_path, md_path = acceptance.write_receipts(tmp_path, receipt)

    loaded = json.loads(json_path.read_text())
    assert loaded["mode"] == "dry-run"
    assert loaded["gate_evidence"] is False
    assert loaded["summary"]["passed"] == 8

    md = md_path.read_text()
    assert "# Orchestration Acceptance Receipt" in md
    assert "**Gate evidence**: no" in md
    assert "**Summary**: 8 passed, 0 failed, 0 skipped (0 required)" in md


def test_markdown_escapes_table_cells(tmp_path: Path):
    """A pipe or newline in evidence cannot break the Markdown table."""
    receipt = {
        "head": "abc",
        "utc": "2026-01-01T00:00:00Z",
        "mode": "dry-run",
        "gate_evidence": False,
        "scope": "test",
        "workdir": str(tmp_path),
        "summary": {"total": 1, "passed": 0, "failed": 1, "skipped": 0, "required_skipped": 0},
        "results": [
            {
                "scenario": "x",
                "phase": "1",
                "status": "FAIL",
                "required": True,
                "evidence": "a | b\nc",
            }
        ],
    }

    _, md_path = acceptance.write_receipts(tmp_path, receipt)

    assert "a \\| b c" in md_path.read_text()


def test_live_scenarios_are_required_and_skip(tmp_path: Path):
    """Skipped live checks are SKIP, never PASS; every scenario is required."""
    assert all(meta.get("required") for meta in acceptance.SCENARIOS.values())

    result = _run_scenario("red_flag_retry", tmp_path, live=True)

    assert result["status"] == "SKIP"
    assert result["required"] is True
    assert "requires controllable responses" in result["evidence"]


@pytest.mark.parametrize(
    ("receipt", "expected"),
    [
        ({"results": [{"status": "PASS"}]}, 0),
        ({"results": [{"status": "FAIL"}]}, 1),
        ({"results": [{"status": "SKIP", "required": True}]}, 1),
        ({"results": [{"status": "SKIP", "required": False}]}, 0),
        ({"results": [], "blocked": "WFE active"}, 3),
        ({"results": [], "interrupted": True}, 130),
        ({"results": [{"status": "PASS"}], "aborted": "WFE started"}, 1),
    ],
)
def test_exit_code_never_treats_required_skips_as_success(receipt: dict, expected: int):
    assert acceptance._exit_code(receipt) == expected


def test_run_live_wait_for_quiet_uses_the_shared_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = {}

    def start(*_args, force=False, wait=False, poll_s=30, max_wait_s=1200):
        seen.update(force=force, wait=wait, poll_s=poll_s, max_wait_s=max_wait_s)
        return {
            "allowed": False,
            "force_requested": force,
            "override_reason": None,
            "blockers": ["WFE/bench run is running (pid 43): memory-safety PID file"],
            "start": {},
        }

    monkeypatch.setattr(acceptance.host_quiet, "start_run", start)
    monkeypatch.setattr(
        acceptance.host_quiet, "finish_run", lambda record, *a: record.update(end={})
    )

    receipt = acceptance.run_live(
        tmp_path,
        "http://127.0.0.1:9099",
        "key",
        "fd",
        "dd",
        wait=True,
        poll_s=15,
        max_wait_s=60,
    )

    assert seen == {"force": False, "wait": True, "poll_s": 15, "max_wait_s": 60}
    assert "memory-safety PID file" in receipt["blocked"]


def test_run_live_refuses_while_wfe_is_active(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Live mode fails closed before any request and does not touch config/portal.yaml."""
    portal_yaml = ROOT / "config" / "portal.yaml"
    before = portal_yaml.read_bytes()
    context = {
        "allowed": False,
        "force_requested": False,
        "override_reason": None,
        "blockers": ["WFE process is running"],
        "start": {"other_heavy_processes": []},
    }
    monkeypatch.setattr(acceptance.host_quiet, "begin_run", lambda *a, **k: context)
    monkeypatch.setattr(
        acceptance.host_quiet, "finish_run", lambda record, *a: record.update(end={})
    )

    receipt = acceptance.run_live(tmp_path, "http://127.0.0.1:9099", "key", "fd", "dd")

    assert "WFE process is running" in receipt["blocked"]
    assert receipt["results"] == []
    assert receipt["host_quiet"]["end"] == {}
    assert acceptance._exit_code(receipt) == 3
    assert portal_yaml.read_bytes() == before


def test_run_live_rechecks_before_each_scenario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A WFE run that starts mid-loop aborts the remaining scenarios."""
    executed: list[str] = []

    def fake_run(name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        executed.append(name)
        return {
            "scenario": name,
            "status": "PASS",
            "evidence": "ok",
            "phase": "1",
            "required": True,
        }

    context = {
        "allowed": True,
        "force_requested": False,
        "override_reason": None,
        "blockers": [],
        "start": {},
    }
    monkeypatch.setattr(acceptance.host_quiet, "begin_run", lambda *a, **k: context)
    monkeypatch.setattr(
        acceptance.host_quiet, "finish_run", lambda record, *a: record.update(end={})
    )
    reasons = iter([None, "WFE started"])
    monkeypatch.setattr(acceptance, "SCENARIOS", {name: {"phase": 1} for name in ("one", "two")})
    monkeypatch.setattr(acceptance, "run_scenario", fake_run)
    monkeypatch.setattr(acceptance, "_wfe_active", lambda: next(reasons))

    receipt = acceptance.run_live(tmp_path, "http://127.0.0.1:9099", "key", "fd", "dd")

    assert executed == ["one"]
    assert "WFE started" in receipt["aborted"]
    assert receipt["summary"]["passed"] == 1


def test_live_force_records_overridden_host_blockers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    context = {
        "allowed": True,
        "force_requested": True,
        "override_reason": "operator supplied --force; overridden blockers: WFE is running",
        "blockers": ["WFE is running"],
        "start": {},
    }
    monkeypatch.setattr(acceptance.host_quiet, "begin_run", lambda *a, **k: context)
    monkeypatch.setattr(
        acceptance.host_quiet, "finish_run", lambda record, *a: record.update(end={})
    )
    monkeypatch.setattr(acceptance, "SCENARIOS", {"one": {"phase": 1}})
    monkeypatch.setattr(
        acceptance,
        "run_scenario",
        lambda name, *a, **k: {
            "scenario": name,
            "status": "PASS",
            "evidence": "ok",
            "phase": "1",
            "required": True,
        },
    )
    monkeypatch.setattr(
        acceptance,
        "_wfe_active",
        lambda: (_ for _ in ()).throw(AssertionError("forced run must honor the override")),
    )

    receipt = acceptance.run_live(tmp_path, "http://127.0.0.1:9099", "key", "fd", "dd", force=True)

    assert receipt["host_quiet"]["override_reason"].endswith("WFE is running")
    assert receipt["host_quiet"]["end"] == {}


def test_live_receipt_carries_dispatch_lane_start_and_end_snapshots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    lane = {"pid": 41, "kind": "dispatch lane job", "process": "dispatch.py"}
    context = {
        "allowed": True,
        "force_requested": False,
        "override_reason": None,
        "blockers": [],
        "start": {"other_heavy_processes": [lane]},
    }
    monkeypatch.setattr(acceptance.host_quiet, "begin_run", lambda *a, **k: context)
    monkeypatch.setattr(
        acceptance.host_quiet,
        "finish_run",
        lambda record, *a: record.update(end={"other_heavy_processes": [lane]}),
    )
    monkeypatch.setattr(acceptance, "SCENARIOS", {})

    receipt = acceptance.run_live(tmp_path, "http://127.0.0.1:9099", "key", "fd", "dd")

    assert receipt["host_quiet"]["start"]["other_heavy_processes"] == [lane]
    assert receipt["host_quiet"]["end"]["other_heavy_processes"] == [lane]


def test_wfe_clear_without_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """No PID file and no WFE process means clear."""
    monkeypatch.setattr(acceptance, "WFE_PID_FILE", tmp_path / "pids")
    monkeypatch.setattr(acceptance, "_wfe_processes", lambda: [])

    assert acceptance._wfe_active() is None


def test_wfe_pid_file_live_pid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A live PID in the producer file blocks live acceptance."""
    pid_file = tmp_path / "pids"
    pid_file.write_text(f"{os.getpid()}\n")
    monkeypatch.setattr(acceptance, "WFE_PID_FILE", pid_file)
    monkeypatch.setattr(acceptance, "_wfe_processes", lambda: [])

    assert "is live" in acceptance._wfe_active()


def test_wfe_pid_file_dead_pid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A dead PID is not a running sweep."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    pid_file = tmp_path / "pids"
    pid_file.write_text(f"{child.pid}\n")
    monkeypatch.setattr(acceptance, "WFE_PID_FILE", pid_file)
    monkeypatch.setattr(acceptance, "_wfe_processes", lambda: [])

    assert acceptance._wfe_active() is None


def test_wfe_pid_file_malformed_line_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Corrupt state is treated as active, not as 'no WFE'."""
    pid_file = tmp_path / "pids"
    pid_file.write_text("123\n# a comment\n")
    monkeypatch.setattr(acceptance, "WFE_PID_FILE", pid_file)
    monkeypatch.setattr(acceptance, "_wfe_processes", lambda: [])

    assert "unparseable PID" in acceptance._wfe_active()


def test_wfe_process_scan_failure_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """An unreadable process table cannot prove the WFE is clear."""
    monkeypatch.setattr(acceptance, "WFE_PID_FILE", tmp_path / "pids")

    def explode(*args: Any, **kwargs: Any) -> None:
        raise OSError("ps unavailable")

    monkeypatch.setattr(acceptance.subprocess, "run", explode)

    assert "failing closed" in acceptance._wfe_active()


def test_process_scan_matches_campaign(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The unattended sweep has no PID file, so the process table must catch it."""
    monkeypatch.setattr(acceptance, "WFE_PID_FILE", tmp_path / "pids")

    class Result:
        returncode = 0
        stdout = " 42 python -m tests.wfe.campaign --plan plan.yaml\n"

    monkeypatch.setattr(acceptance.subprocess, "run", lambda *a, **k: Result())

    assert "tests.wfe.campaign" in acceptance._wfe_active()


def test_run_live_task_uses_repo_config_and_unattended_false(tmp_path: Path):
    """Live wiring reads the repo config (null Gate C threshold) and runs unattended=False."""
    pipeline = FakePipeline()
    pipeline.add("fast", finish_response({"answer": "right"}))
    try:
        receipt = acceptance._run_live_task(
            tmp_path / "tasks",
            "live",
            [acceptance._bite("b1", discipline="test_fixing")],
            pipeline.url,
            auth.PIPELINE_API_KEY,
            "fast-digest",
            "deep-digest",
        )
    finally:
        pipeline.close()

    assert receipt["status"] == "PASS"
    assert pipeline.requests[0]["model"] == "auto-daily::fast"
    assert (tmp_path / "tasks" / "live" / "plan.json").is_file()


def test_run_live_task_missing_config_fails_loudly(tmp_path: Path):
    """A missing config raises instead of silently reading the wrong path."""
    with pytest.raises(FileNotFoundError):
        acceptance._run_live_task(
            tmp_path,
            "live",
            [acceptance._bite("b1", discipline="test_fixing")],
            "http://127.0.0.1:9",
            "",
            "fd",
            "dd",
            config_path=tmp_path / "nope.yaml",
        )
