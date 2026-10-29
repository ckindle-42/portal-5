"""Offline tests for arm job specs, preconditions, resume and receipts."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from portal.modules.orchestration.cli import orchestration_app
from portal.modules.orchestration.jobs import JobRunner, parse_job_spec
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
