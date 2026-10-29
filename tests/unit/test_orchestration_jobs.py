"""Offline tests for arm job specs, preconditions, resume and receipts."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from portal.modules.orchestration import jobs as jobmod
from portal.modules.orchestration.cli import orchestration_app
from portal.modules.orchestration.jobs import JobPreconditions, JobRunner, parse_job_spec
from portal.modules.orchestration.queue import OvernightQueue, QueueGate, QueueLedger
from portal.modules.orchestration.service import StubNoticeSink
from portal.modules.orchestration.telegram import TelegramNoticeSink
from portal_channels.telegram.arm_bridge import ArmTelegramStore

REPORT_FIELDS = [
    "status",
    "steps",
    "outputs",
    "checkpoints",
    "failures",
    "memory",
    "duration",
    "resume",
]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "tests" / "wfe").mkdir(parents=True)
    return root


def _script(repo: Path, name: str, body: str, *, executable: bool = True) -> str:
    path = repo / "scripts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755 if executable else 0o644)
    return f"scripts/{name}"


def _python_script(repo: Path, name: str, body: str) -> str:
    return _script(repo, name, "#!/usr/bin/env python3\n" + body)


def _watcher(tmp_path: Path, *, trip_after: float | None = None) -> Path:
    path = tmp_path / "memory_watch.py"
    body = "#!/usr/bin/env python3\nimport sys, time\n"
    if trip_after is None:
        body += "time.sleep(0.05)\nsys.exit(0)\n"
    else:
        body += (
            f"time.sleep({trip_after})\n"
            "log = sys.argv[sys.argv.index('--log') + 1]\n"
            "open(log, 'a').write('MEMORY SAFETY TRIP: fixture\\n')\n"
            "sys.exit(2)\n"
        )
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


class _Gate:
    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason

    def external_reason(self) -> str | None:
        return self.reason


def _raw_spec(
    argv: list[str],
    *,
    job_id: str = "job-a",
    **overrides: Any,
) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "id": job_id,
        "purpose": "exercise the offline job runner",
        "preconditions": {"stack": "down", "free_memory_gib": 0, "disk_free_gib": 0},
        "steps": [{"id": "one", "argv": argv, "timeout_seconds": 5}],
        "report": {"fields": REPORT_FIELDS},
    }
    raw.update(overrides)
    return raw


def _spec(repo: Path, argv: list[str], **overrides: Any) -> Any:
    return parse_job_spec(_raw_spec(argv, **overrides), repo_root=repo)


def _runner(
    tmp_path: Path,
    repo: Path,
    *,
    gate: Any = None,
    watcher: Path | None = None,
    stack: str = "down",
    memory: float | None = 64.0,
    disk: float | None = 64.0,
    notices: StubNoticeSink | None = None,
) -> JobRunner:
    return JobRunner(
        tmp_path / "tasks",
        repo_root=repo,
        gate=gate or _Gate(),
        notices=notices or StubNoticeSink(),
        dispatch_lock_dir=tmp_path / "dispatch-locks",
        memory_watch_script=watcher or _watcher(tmp_path),
        stack_probe=lambda: stack,
        memory_probe=lambda: memory,
        disk_probe=lambda _path: disk,
        poll_seconds=0.02,
    )


def _receipt(task_root: Path, job_id: str = "job-a") -> dict[str, Any]:
    return json.loads((task_root / job_id / "receipt.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "argv",
    [
        ["/bin/sh", "-c", "echo hi"],
        ["bash", "-c", "echo hi"],
        ["rm", "-rf", "/"],
        ["scripts/../outside.sh"],
        ["uv", "run", "python", "-c", "import os"],
        ["uv", "run", "python", "-m", "tests.evil"],
        ["scripts/missing.sh"],
    ],
)
def test_job_spec_rejects_argv_outside_the_allowlist(repo: Path, argv: list[str]) -> None:
    with pytest.raises(ValueError, match="allowlist|not executable"):
        parse_job_spec(_raw_spec(argv), repo_root=repo)


def test_job_spec_accepts_repo_scripts_and_wfe_modules(repo: Path) -> None:
    _script(repo, "ok.sh", "#!/bin/sh\nexit 0\n")
    _script(repo, "tool.py", "print('tool')\n", executable=False)
    allowed = (
        ["scripts/ok.sh", "--flag"],
        ["uv", "run", "python", "scripts/tool.py"],
        ["uv", "run", "python", "-m", "tests.wfe.campaign", "--status"],
    )
    for argv in allowed:
        spec = parse_job_spec(_raw_spec(argv), repo_root=repo)
        assert spec.steps[0].argv == tuple(argv)
    raw = _raw_spec(["scripts/ok.sh"])
    raw["report"] = ["status"]
    assert parse_job_spec(raw, repo_root=repo).report_fields == ("status",)


def test_job_spec_rejects_a_non_executable_direct_script(repo: Path) -> None:
    _script(repo, "tool.py", "print('tool')\n", executable=False)
    with pytest.raises(ValueError, match="not executable"):
        parse_job_spec(_raw_spec(["scripts/tool.py"]), repo_root=repo)


def test_step_quiet_host_parses_and_round_trips(tmp_path: Path, repo: Path) -> None:
    _script(repo, "ok.sh", "#!/bin/sh\nexit 0\n")
    steps = [{"id": "one", "argv": ["scripts/ok.sh"], "timeout_seconds": 5, "quiet_host": False}]
    spec = parse_job_spec(_raw_spec(["scripts/ok.sh"], steps=steps), repo_root=repo)

    assert spec.steps[0].quiet_host is False
    assert spec.as_dict()["steps"][0]["quiet_host"] is False
    # Absent stays absent so specs written before the flag stay byte-stable on resume.
    assert "quiet_host" not in _spec(repo, ["scripts/ok.sh"]).as_dict()["steps"][0]
    assert parse_job_spec(spec.as_dict(), repo_root=repo).steps[0].quiet_host is False


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("stack", "stack is up"),
        ("memory", "free memory"),
        ("disk", "disk free"),
        ("dispatch", "dispatch lane lock"),
        ("gate", "queue yield gate"),
    ],
)
def test_preconditions_refuse_before_a_step_runs(
    tmp_path: Path, repo: Path, case: str, reason: str
) -> None:
    marker = tmp_path / "ran"
    script = _python_script(
        repo,
        "write_marker.py",
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
    )
    preconditions = {"stack": "down", "free_memory_gib": 8, "disk_free_gib": 20}
    gate = _Gate()
    stack, memory, disk = "down", 64.0, 64.0
    if case == "stack":
        stack = "up"
    elif case == "memory":
        memory = 1.0
    elif case == "disk":
        disk = 1.0
    elif case == "dispatch":
        lock_dir = tmp_path / "dispatch-locks"
        lock_dir.mkdir()
        (lock_dir / "lane.lock").write_text(f"{os.getpid()}\n", encoding="utf-8")
    elif case == "gate":
        gate = _Gate("yield lock bench.pid is active (pid 123)")
    runner = _runner(tmp_path, repo, gate=gate, stack=stack, memory=memory, disk=disk)
    spec = _spec(repo, [script], preconditions=preconditions)
    result = runner.run(spec)

    assert result.status == "WAITING"
    assert reason in str(result.reason)
    assert not marker.exists()
    receipt = _receipt(tmp_path / "tasks")
    assert receipt["status"] == "WAITING"
    assert receipt["steps"][0]["state"] == "pending"


def test_checkpoint_is_copied_before_the_step_overwrites_it(tmp_path: Path, repo: Path) -> None:
    checkpoint = tmp_path / "campaign.json"
    checkpoint.write_text("old checkpoint\n", encoding="utf-8")
    script = _python_script(
        repo,
        "overwrite.py",
        "import pathlib, sys\npathlib.Path(sys.argv[1]).write_text('new checkpoint\\n')\n",
    )
    spec = parse_job_spec(
        _raw_spec(
            [script, str(checkpoint)],
            steps=[
                {
                    "id": "sweep",
                    "argv": [script, str(checkpoint)],
                    "timeout_seconds": 5,
                    "checkpoints": [str(checkpoint)],
                }
            ],
        ),
        repo_root=repo,
    )

    result = _runner(tmp_path, repo).run(spec)

    assert result.status == "PASS"
    receipt = _receipt(tmp_path / "tasks")
    backup = receipt["steps"][0]["checkpoint_backups"][0]
    assert backup["backed_up"] is True
    assert Path(backup["backup"]).read_text(encoding="utf-8") == "old checkpoint\n"
    assert backup["bytes"] == len("old checkpoint\n")
    assert backup["sha256"] == hashlib.sha256(b"old checkpoint\n").hexdigest()
    assert checkpoint.read_text(encoding="utf-8") == "new checkpoint\n"
    assert receipt["report"]["checkpoints"][0]["path"] == str(checkpoint)


def test_job_level_output_and_checkpoint_paths_are_honoured(tmp_path: Path, repo: Path) -> None:
    checkpoint = tmp_path / "campaign.json"
    checkpoint.write_text("original\n", encoding="utf-8")
    output = tmp_path / "summary.txt"
    script = _python_script(
        repo,
        "campaign.py",
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text('updated\\n')\n"
        "pathlib.Path(sys.argv[2]).write_text('summary\\n')\n",
    )
    spec = parse_job_spec(
        _raw_spec(
            [script, str(checkpoint), str(output)],
            steps=[
                {
                    "id": "campaign",
                    "argv": [script, str(checkpoint), str(output)],
                    "timeout_seconds": 5,
                }
            ],
            outputs=[str(output)],
            checkpoints=[str(checkpoint)],
        ),
        repo_root=repo,
    )

    result = _runner(tmp_path, repo).run(spec)

    assert result.status == "PASS"
    receipt = _receipt(tmp_path / "tasks")
    assert Path(receipt["checkpoints"][0]["backup"]).read_text(encoding="utf-8") == "original\n"
    assert [item["path"] for item in receipt["outputs"]] == [str(output)]
    assert receipt["report"]["outputs"][0]["bytes"] == len("summary\n")


def test_resume_skips_done_steps_and_rerun_forces_one_step(tmp_path: Path, repo: Path) -> None:
    marker = tmp_path / "step-one.log"
    counter = tmp_path / "step-two.count"
    step_one = _python_script(
        repo,
        "step_one.py",
        f"from pathlib import Path\n"
        f"with Path({str(marker)!r}).open('a') as handle:\n"
        "    handle.write('x')\n",
    )
    step_two = _python_script(
        repo,
        "step_two.py",
        f"from pathlib import Path\n"
        f"path = Path({str(counter)!r})\n"
        "count = int(path.read_text()) if path.exists() else 0\n"
        "path.write_text(str(count + 1))\n"
        "raise SystemExit(0 if count else 1)\n",
    )
    spec = parse_job_spec(
        _raw_spec(
            [step_one],
            steps=[
                {"id": "one", "argv": [step_one], "timeout_seconds": 5},
                {"id": "two", "argv": [step_two], "timeout_seconds": 5},
            ],
        ),
        repo_root=repo,
    )
    runner = _runner(tmp_path, repo)

    first = runner.run(spec)
    assert first.status == "BLOCKED"
    assert marker.read_text(encoding="utf-8") == "x"
    assert counter.read_text(encoding="utf-8") == "1"

    second = runner.run(spec)
    assert second.status == "PASS"
    assert marker.read_text(encoding="utf-8") == "x"
    receipt = _receipt(tmp_path / "tasks")
    assert [step["attempts"] for step in receipt["steps"]] == [1, 2]

    third = runner.run(spec, rerun="one")
    assert third.status == "PASS"
    assert marker.read_text(encoding="utf-8") == "xx"
    assert counter.read_text(encoding="utf-8") == "2"


def test_receipt_records_argv_exit_duration_peak_tails_outputs_and_report(
    tmp_path: Path, repo: Path
) -> None:
    output = tmp_path / "artifact.txt"
    script = _python_script(
        repo,
        "emit.py",
        "import pathlib, sys\n"
        "print('hello stdout')\n"
        "print('hello stderr', file=sys.stderr)\n"
        f"pathlib.Path({str(output)!r}).write_text('payload')\n",
    )
    notices = StubNoticeSink()
    spec = parse_job_spec(
        _raw_spec(
            [script],
            steps=[
                {
                    "id": "emit",
                    "argv": [script],
                    "timeout_seconds": 5,
                    "outputs": [str(output)],
                }
            ],
        ),
        repo_root=repo,
    )

    result = _runner(tmp_path, repo, notices=notices).run(spec)

    assert result.status == "PASS"
    receipt = _receipt(tmp_path / "tasks")
    step = receipt["steps"][0]
    assert step["argv"] == [script]
    assert step["exit_code"] == 0
    assert step["duration_seconds"] >= 0
    assert "peak_footprint_bytes" in step
    assert "hello stdout" in step["stdout_tail"]
    assert "hello stderr" in step["stderr_tail"]
    assert step["outputs"][0]["path"] == str(output)
    assert step["outputs"][0]["bytes"] == 7
    assert step["outputs"][0]["sha256"] == hashlib.sha256(b"payload").hexdigest()
    assert set(receipt["report"]) == set(REPORT_FIELDS)
    assert receipt["report"]["status"] == "PASS"
    assert receipt["totals"]["duration_seconds"] >= 0
    assert notices.job_notices[0]["job_id"] == "job-a"
    assert notices.job_notices[0]["status"] == "PASS"


def test_memory_trip_stops_the_step_and_records_it(tmp_path: Path, repo: Path) -> None:
    script = _python_script(repo, "long.py", "import time\ntime.sleep(10)\n")
    runner = _runner(tmp_path, repo, watcher=_watcher(tmp_path, trip_after=0.1))
    spec = _spec(repo, [script])

    result = runner.run(spec)

    assert result.status == "STOPPED"
    assert "memory safety" in str(result.reason)
    receipt = _receipt(tmp_path / "tasks")
    step = receipt["steps"][0]
    assert step["state"] == "stopped"
    assert "MEMORY SAFETY TRIP" in step["memory_trip"]["reason"]
    assert step["duration_seconds"] < 5


def test_step_timeout_blocks_the_job(tmp_path: Path, repo: Path) -> None:
    script = _python_script(repo, "long.py", "import time\ntime.sleep(10)\n")
    spec = parse_job_spec(
        _raw_spec(
            [script],
            steps=[{"id": "one", "argv": [script], "timeout_seconds": 0.2}],
        ),
        repo_root=repo,
    )

    result = _runner(tmp_path, repo).run(spec)

    assert result.status == "BLOCKED"
    assert "timed out" in str(result.reason)
    step = _receipt(tmp_path / "tasks")["steps"][0]
    assert step["timed_out"] is True
    assert step["state"] == "failed"


def test_output_marker_stops_the_job(tmp_path: Path, repo: Path) -> None:
    script = _python_script(
        repo,
        "marker.py",
        "import time\nprint('BLOCKED: preflight failed', flush=True)\ntime.sleep(10)\n",
    )
    spec = _spec(
        repo,
        [script],
        stop_conditions={"output_markers": ["BLOCKED:"]},
    )

    result = _runner(tmp_path, repo).run(spec)

    assert result.status == "STOPPED"
    assert "stop marker" in str(result.reason)
    step = _receipt(tmp_path / "tasks")["steps"][0]
    assert "BLOCKED: preflight failed" in step["stdout_tail"]


def test_queue_runs_a_job_without_the_arm_service(tmp_path: Path, repo: Path) -> None:
    script = _python_script(repo, "ok.py", "print('ok')\n")
    task_root = tmp_path / "tasks"
    spec = _spec(repo, [script])
    with QueueLedger(task_root) as ledger:
        ledger.enqueue_job(spec, repo)
    gate = QueueGate(
        {},
        {"yield_lock_dir": str(tmp_path / "locks")},
        pid_file=tmp_path / "memory-pids",
    )
    queue = OvernightQueue(
        task_root,
        None,
        gate,
        repo_root=repo,
        notices=StubNoticeSink(),
        job_factory=lambda: _runner(tmp_path, repo),
    )

    result = queue.run_next()

    assert result.status == "DONE"
    assert result.task_id == "job-a"
    assert result.receipt_path is not None and result.receipt_path.is_file()
    with QueueLedger(task_root) as ledger:
        rows = ledger.items()
    assert rows[0]["kind"] == "job"
    assert rows[0]["state"] == "done"


def test_queue_defers_a_job_until_its_preconditions_clear(tmp_path: Path, repo: Path) -> None:
    marker = tmp_path / "ran"
    script = _python_script(
        repo,
        "wait.py",
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
    )
    task_root = tmp_path / "tasks"
    spec = _spec(repo, [script])
    with QueueLedger(task_root) as ledger:
        ledger.enqueue_job(spec, repo)
    state = {"stack": "up"}
    gate = QueueGate(
        {},
        {"yield_lock_dir": str(tmp_path / "locks")},
        pid_file=tmp_path / "memory-pids",
    )
    queue = OvernightQueue(
        task_root,
        None,
        gate,
        repo_root=repo,
        notices=StubNoticeSink(),
        job_factory=lambda: _runner(tmp_path, repo, stack=state["stack"]),
    )

    first = queue.run_next()
    assert first.status == "WAITING"
    assert "stack is up" in str(first.reason)
    assert not marker.exists()
    with QueueLedger(task_root) as ledger:
        assert ledger.items()[0]["state"] == "queued"

    state["stack"] = "down"
    second = queue.run_next()
    assert second.status == "DONE"
    assert marker.read_text(encoding="utf-8") == "ran"
    with QueueLedger(task_root) as ledger:
        assert ledger.items()[0]["state"] == "done"


def test_queue_ledger_adds_kind_to_an_existing_database(tmp_path: Path) -> None:
    task_root = tmp_path / "tasks"
    task_root.mkdir()
    with sqlite3.connect(task_root / "queue.sqlite3") as db:
        db.execute(
            "CREATE TABLE queue_task ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL UNIQUE, "
            "plan_json TEXT NOT NULL, source_dir TEXT NOT NULL, state TEXT NOT NULL, "
            "runner_pid INTEGER, receipt_status TEXT, last_error TEXT, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
    with QueueLedger(task_root) as ledger:
        item, active = ledger.claim_next()
    assert item is None and not active
    with sqlite3.connect(task_root / "queue.sqlite3") as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(queue_task)")}
    assert "kind" in columns


def test_enqueue_job_cli_persists_a_valid_spec(tmp_path: Path) -> None:
    spec_file = tmp_path / "job.yaml"
    spec_file.write_text(
        yaml.safe_dump(_raw_spec(["uv", "run", "python", "-m", "tests.wfe.campaign", "--status"])),
        encoding="utf-8",
    )
    tasks_dir = tmp_path / "tasks"

    result = CliRunner().invoke(
        orchestration_app,
        ["enqueue-job", str(spec_file), "--tasks-dir", str(tasks_dir)],
    )

    assert result.exit_code == 0, result.output
    assert "queued job job-a" in result.output
    assert (tasks_dir / "job-a" / "job.json").is_file()

    status = CliRunner().invoke(
        orchestration_app,
        ["job-status", "job-a", "--tasks-dir", str(tasks_dir)],
    )
    assert status.exit_code == 0, status.output
    assert '"purpose": "exercise the offline job runner"' in status.output


def test_telegram_job_notice_reaches_the_outbox(tmp_path: Path) -> None:
    sink = TelegramNoticeSink(path=tmp_path / "telegram.sqlite3")

    sink.job_finished(
        "job-a",
        "STOPPED",
        {
            "purpose": "long campaign",
            "reason": "memory safety trip",
            "steps": "1/2 done",
            "duration_seconds": 12,
        },
    )

    notices = ArmTelegramStore(tmp_path / "telegram.sqlite3").outbox()
    assert notices[0].kind == "job"
    assert "Orchestration job STOPPED." in notices[0].message
    assert "Reason: memory safety trip" in notices[0].message


def test_a_job_blocked_by_cloud_lanes_claims_the_window_until_it_finishes(
    tmp_path: Path, repo: Path
) -> None:
    script = _python_script(repo, "noop.py", "pass\n")
    preconditions = {"stack": "down", "free_memory_gib": 8, "disk_free_gib": 20}
    lock_dir = tmp_path / "dispatch-locks"
    lock_dir.mkdir()
    lane = lock_dir / "lane.lock"
    lane.write_text(f"{os.getpid()}\n", encoding="utf-8")
    runner = _runner(tmp_path, repo)
    claim = tmp_path / "state" / "jarvis_local_window.json"
    spec = _spec(repo, [script], preconditions=preconditions)

    assert runner.run(spec).status == "WAITING"
    assert json.loads(claim.read_text(encoding="utf-8"))["pid"] == os.getpid()  # held while waiting

    lane.unlink()
    assert runner.run(spec).status == "PASS"
    assert not claim.exists()  # released once the job is done


def test_bully_r0b_real_dryrun_spec_parses_against_the_repo() -> None:
    spec_path = (
        Path(__file__).resolve().parents[2] / "config" / "arm_jobs" / "bully-r0b-real-dryrun.yaml"
    )
    repo_root = spec_path.parents[2]
    spec = parse_job_spec(
        yaml.safe_load(spec_path.read_text(encoding="utf-8")), repo_root=repo_root
    )
    assert spec.job_id == "bully-r0b-real-dryrun"
    assert [step.step_id for step in spec.steps] == ["acquire", "dry-run"]
    assert "--dry-run" in spec.steps[1].argv  # never --ship from a job
    assert not any("--ship" in step.argv for step in spec.steps)


def test_the_window_is_held_while_a_step_runs(tmp_path: Path, repo: Path) -> None:
    claim = tmp_path / "state" / "jarvis_local_window.json"
    seen = tmp_path / "seen"
    script = _python_script(
        repo,
        "peek.py",
        f"from pathlib import Path\nPath({str(seen)!r}).write_text(str(Path({str(claim)!r}).exists()))\n",
    )
    spec = _spec(
        repo, [script], preconditions={"stack": "down", "free_memory_gib": 8, "disk_free_gib": 20}
    )
    assert _runner(tmp_path, repo).run(spec).status == "PASS"
    assert seen.read_text() == "True"  # claimed during the step
    assert not claim.exists()  # released after


def test_a_quiet_host_false_step_runs_while_a_lane_lock_exists(tmp_path: Path, repo: Path) -> None:
    claim = tmp_path / "state" / "jarvis_local_window.json"
    seen = tmp_path / "seen"
    script = _python_script(
        repo,
        "peek.py",
        f"from pathlib import Path\nPath({str(seen)!r}).write_text(str(Path({str(claim)!r}).exists()))\n",
    )
    lock_dir = tmp_path / "dispatch-locks"
    lock_dir.mkdir()
    (lock_dir / "lane.lock").write_text(f"{os.getpid()}\n", encoding="utf-8")
    spec = _spec(
        repo,
        [script],
        steps=[{"id": "report", "argv": [script], "timeout_seconds": 5, "quiet_host": False}],
        preconditions={"stack": "down", "free_memory_gib": 8, "disk_free_gib": 20},
    )

    result = _runner(tmp_path, repo).run(spec)

    assert result.status == "PASS"
    assert seen.read_text() == "False"  # ran without holding the window
    assert not claim.exists()
    receipt = _receipt(tmp_path / "tasks")
    assert "dispatch lane lock" in receipt["preconditions"]["dispatch_locks"]


def test_a_waiting_quiet_host_false_job_holds_no_window_claim(tmp_path: Path, repo: Path) -> None:
    script = _python_script(repo, "noop.py", "pass\n")
    lock_dir = tmp_path / "dispatch-locks"
    lock_dir.mkdir()
    (lock_dir / "lane.lock").write_text(f"{os.getpid()}\n", encoding="utf-8")
    spec = _spec(
        repo,
        [script],
        steps=[{"id": "report", "argv": [script], "timeout_seconds": 5, "quiet_host": False}],
        preconditions={"stack": "down", "free_memory_gib": 64, "disk_free_gib": 20},
    )
    claim = tmp_path / "state" / "jarvis_local_window.json"

    result = _runner(tmp_path, repo, memory=1.0).run(spec)

    assert result.status == "WAITING"
    assert "free memory" in str(result.reason)
    assert not claim.exists()  # a waiting report-only job does not hold the window


def test_a_report_step_runs_while_a_campaign_step_still_waits(tmp_path: Path, repo: Path) -> None:
    marker = tmp_path / "reported"
    report = _python_script(
        repo, "report.py", f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n"
    )
    campaign = _python_script(repo, "campaign.py", "pass\n")
    lock_dir = tmp_path / "dispatch-locks"
    lock_dir.mkdir()
    lane = lock_dir / "lane.lock"
    lane.write_text(f"{os.getpid()}\n", encoding="utf-8")
    claim = tmp_path / "state" / "jarvis_local_window.json"
    spec = _spec(
        repo,
        [campaign],
        steps=[
            {"id": "report", "argv": [report], "timeout_seconds": 5, "quiet_host": False},
            {"id": "campaign", "argv": [campaign], "timeout_seconds": 5},
        ],
        preconditions={"stack": "down", "free_memory_gib": 8, "disk_free_gib": 20},
    )
    runner = _runner(tmp_path, repo)

    waiting = runner.run(spec)

    assert waiting.status == "WAITING"
    assert "dispatch lane lock" in str(waiting.reason)
    assert marker.exists()  # the report ran despite the active lanes
    assert json.loads(claim.read_text(encoding="utf-8"))["pid"] == os.getpid()  # held to drain

    lane.unlink()
    assert runner.run(spec).status == "PASS"
    assert not claim.exists()  # released once the campaign is done


def _sleeper(*extra: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)", *extra],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is None:
        proc.kill()
    proc.wait(timeout=5)


def _lagging_watcher(tmp_path: Path, *, trip: bool) -> Path:
    line = ""
    if trip:
        line = (
            "line = 'MEMORY SAFETY TRIP: swap free 712.8 MiB is below 1024 MiB'\n"
            "open(log, 'a').write(line + '\\n')\n"
        )
    path = tmp_path / ("trip_watch.py" if trip else "kill_watch.py")
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import os, signal, sys, time\n"
        "log = sys.argv[sys.argv.index('--log') + 1]\n"
        "pid_file = sys.argv[sys.argv.index('--pid-file') + 1]\n"
        "pid = int(open(pid_file).read().strip())\n"
        f"{line}"
        "os.kill(pid, signal.SIGTERM)\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def test_trip_line_is_recorded_when_the_watcher_has_not_exited(tmp_path: Path, repo: Path) -> None:
    script = _python_script(repo, "long.py", "import time\ntime.sleep(30)\n")
    result = _runner(tmp_path, repo, watcher=_lagging_watcher(tmp_path, trip=True)).run(
        _spec(repo, [script])
    )

    assert result.status == "STOPPED"
    step = _receipt(tmp_path / "tasks")["steps"][0]
    reason = "MEMORY SAFETY TRIP: swap free 712.8 MiB is below 1024 MiB"
    assert step["exit_code"] == -15
    assert step["memory_trip"]["reason"] == reason
    assert step["reason"] == f"memory safety trip: {reason}"


def test_a_trip_line_from_before_this_attempt_is_ignored(tmp_path: Path) -> None:
    log = tmp_path / "watch.log"
    log.write_text("old MEMORY SAFETY TRIP: stale\n", encoding="utf-8")
    offset = log.stat().st_size
    log.write_text(log.read_text(encoding="utf-8") + "still running\n", encoding="utf-8")

    assert jobmod._trip_line_since(log, offset) is None


def test_sigterm_without_a_trip_line_stays_a_plain_exit(tmp_path: Path, repo: Path) -> None:
    script = _python_script(repo, "long.py", "import time\ntime.sleep(30)\n")
    result = _runner(tmp_path, repo, watcher=_lagging_watcher(tmp_path, trip=False)).run(
        _spec(repo, [script])
    )

    assert result.status == "BLOCKED"
    step = _receipt(tmp_path / "tasks")["steps"][0]
    assert step["exit_code"] == -15
    assert step["memory_trip"] is None
    assert step["reason"] == "step exited -15"


def test_a_live_lock_matching_start_time_blocks(tmp_path: Path) -> None:
    proc = _sleeper()
    try:
        started = jobmod._ps_field(proc.pid, "lstart")
        assert started
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        (job_dir / "run.lock").write_text(
            json.dumps({"pid": proc.pid, "started": started}) + "\n",
            encoding="utf-8",
        )
        with pytest.raises(RuntimeError, match="already running"):
            JobRunner._acquire_lock(job_dir, "job-a")
    finally:
        _stop(proc)


def test_a_reused_pid_lock_is_stale(tmp_path: Path) -> None:
    proc = _sleeper()
    try:
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        (job_dir / "run.lock").write_text(
            json.dumps({"pid": proc.pid, "started": "Thu Jan 1 00:00:00 1970"}) + "\n",
            encoding="utf-8",
        )
        lock = JobRunner._acquire_lock(job_dir, "job-a")
        payload = json.loads(lock.read_text(encoding="utf-8"))
        assert payload["pid"] == os.getpid()
        assert payload["started"] == jobmod._ps_field(os.getpid(), "lstart")
    finally:
        _stop(proc)


def test_a_dead_pid_lock_is_stale(tmp_path: Path) -> None:
    proc = _sleeper()
    pid = proc.pid
    _stop(proc)
    assert jobmod._pid_alive(pid) is False
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "run.lock").write_text(f"{pid}\n", encoding="utf-8")

    lock = JobRunner._acquire_lock(job_dir, "job-a")

    assert json.loads(lock.read_text(encoding="utf-8"))["pid"] == os.getpid()


def test_a_bare_pid_lock_is_held_only_for_portal_arm(tmp_path: Path) -> None:
    other = _sleeper()
    arm = _sleeper("portal arm")
    try:
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        (other_dir / "run.lock").write_text(f"{other.pid}\n", encoding="utf-8")
        assert "portal arm" not in (jobmod._ps_field(other.pid, "command") or "")
        JobRunner._acquire_lock(other_dir, "job-a")

        arm_dir = tmp_path / "arm"
        arm_dir.mkdir()
        (arm_dir / "run.lock").write_text(f"{arm.pid}\n", encoding="utf-8")
        assert "portal arm" in (jobmod._ps_field(arm.pid, "command") or "")
        with pytest.raises(RuntimeError, match="already running"):
            JobRunner._acquire_lock(arm_dir, "job-a")
    finally:
        _stop(other)
        _stop(arm)


def test_an_unreadable_command_keeps_a_bare_pid_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = _sleeper()
    try:
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        (job_dir / "run.lock").write_text(f"{proc.pid}\n", encoding="utf-8")
        monkeypatch.setattr(jobmod, "_ps_field", lambda _pid, _field: None)
        with pytest.raises(RuntimeError, match="already running"):
            JobRunner._acquire_lock(job_dir, "job-a")
    finally:
        _stop(proc)


def test_window_claim_records_start_and_a_reused_pid_does_not_release(
    tmp_path: Path, repo: Path
) -> None:
    pre = JobPreconditions(repo, dispatch_lock_dir=tmp_path / "locks")
    pre.claim_window("job-a")
    payload = json.loads(pre.window_claim.read_text(encoding="utf-8"))
    assert payload["pid"] == os.getpid()
    assert payload["started"] == jobmod._ps_field(os.getpid(), "lstart")

    payload["started"] = "Thu Jan 1 00:00:00 1970"
    pre.window_claim.write_text(json.dumps(payload), encoding="utf-8")
    pre.release_window()
    assert pre.window_claim.is_file()

    payload["started"] = jobmod._ps_field(os.getpid(), "lstart")
    pre.window_claim.write_text(json.dumps(payload), encoding="utf-8")
    pre.release_window()
    assert not pre.window_claim.exists()


def test_a_legacy_window_claim_releases_on_pid_alone(tmp_path: Path, repo: Path) -> None:
    pre = JobPreconditions(repo, dispatch_lock_dir=tmp_path / "locks")
    pre.window_claim.parent.mkdir(parents=True)
    pre.window_claim.write_text(json.dumps({"pid": os.getpid(), "job": "job-a"}), encoding="utf-8")

    pre.release_window()

    assert not pre.window_claim.exists()
