"""Host-quiet preflight tests with synthetic process and engine state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts import host_quiet


def test_process_scan_finds_dispatch_pytest_wfe_and_bench() -> None:
    lines = [
        "101 1 python /srv/x/.claude/orchestrate/bin/dispatch.py run lane",
        "102 1 /venv/bin/python -m pytest -n 4 tests/unit",
        "103 1 python -m tests.wfe.campaign --plan private.yaml",
        "104 1 python scripts/bench_engine_h2h.py --repeat 10",
        "105 106 python scripts/uat_engines.py",
        "106 107 python scripts/uat_engines.py",
        "107 1 python /srv/x/.claude/orchestrate/bin/dispatch.py run this lane",
    ]

    ancestors = host_quiet._ancestor_pids(lines, 106)
    found = host_quiet._scan_processes(lines, own_pid=106, ignore_pids=ancestors)

    assert [(item["pid"], item["kind"]) for item in found] == [
        (101, "dispatch lane job"),
        (102, "pytest/xdist"),
        (103, "WFE/bench run"),
        (104, "WFE/bench run"),
    ]
    assert ancestors == {107, 1}
    assert all("private.yaml" not in item["process"] for item in found)


def test_snapshot_uses_mocked_http_and_records_residents(monkeypatch) -> None:
    monkeypatch.setenv("UAT_MAX_PYTEST_PROCESSES", "3")
    monkeypatch.setattr(
        host_quiet,
        "_process_lines",
        lambda: (["200 1 python -m pytest -n 4"], None),
    )
    monkeypatch.setattr(host_quiet, "_registry_processes", lambda **_kwargs: [])
    monkeypatch.setattr(host_quiet, "_pid_file_processes", lambda **_kwargs: [])
    monkeypatch.setattr(host_quiet, "_vm_stat_free_gib", lambda: (3.25, None))
    responses = {
        "/admin/load-plan": {"busy": False, "busy_requests": 0, "available_gib": 4.5},
        "/api/ps": {"models": [{"name": "ollama-model", "size": 1073741824}]},
        "/v1/models/status": {
            "models": [{"id": "omlx-model", "loaded": True}, {"id": "idle", "loaded": False}]
        },
    }
    calls: list[tuple[str, str, str, dict[str, Any] | None]] = []

    def fake_request(url, *, method="GET", api_key="", payload=None):
        calls.append((url, method, api_key, payload))
        return responses[next(path for path in responses if path in url)]

    monkeypatch.setattr(host_quiet, "_json_request", fake_request)

    snapshot = host_quiet.capture_snapshot("http://pipeline.test", "pipeline-key")

    assert snapshot["free_memory_gib"] == 3.25
    assert snapshot["headroom_gib"] == 4.5
    assert snapshot["headroom_source"] == "Pipeline /admin/load-plan available_gib"
    assert snapshot["ollama_residents"] == [{"name": "ollama-model", "size_gib": 1.0}]
    assert snapshot["omlx_residents"] == [{"name": "omlx-model"}]
    assert snapshot["other_heavy_processes"][0]["kind"] == "pytest/xdist"
    assert snapshot["maximum_pytest_processes"] == 3
    assert calls[0] == (
        "http://pipeline.test/admin/load-plan",
        "POST",
        "pipeline-key",
        {"models": []},
    )


def test_memory_safety_pid_and_orchestrate_locks_are_checked(monkeypatch, tmp_path: Path) -> None:
    pid_file = tmp_path / "pids"
    pid_file.write_text("41\n", encoding="utf-8")
    monkeypatch.setattr(host_quiet, "_pid_alive", lambda pid: pid == 41)
    assert host_quiet._pid_file_processes(pid_file) == [
        {"pid": 41, "kind": "WFE/bench run", "process": "memory-safety PID file"}
    ]
    assert host_quiet._pid_file_processes(pid_file, ignore_pids={41}) == []

    lock_root = tmp_path / "orchestrate"
    (lock_root / "locks").mkdir(parents=True)
    (lock_root / "locks" / "lane.lock").write_text("41", encoding="utf-8")
    assert host_quiet._registry_processes(lock_root) == [
        {"pid": 41, "kind": "dispatch lane job", "process": "active orchestrate lock"}
    ]
    assert host_quiet._registry_processes(lock_root, ignore_pids={41}) == []


def test_active_orchestrate_registry_entry_is_recorded(tmp_path: Path) -> None:
    root = tmp_path / "orchestrate"
    root.mkdir()
    registry = root / "registry.json"
    registry.write_text('{"roles":{"lane":{"runs":[{"status":"running"}]}}}')

    assert host_quiet._registry_processes(root) == [
        {
            "pid": None,
            "kind": "dispatch lane job",
            "process": "active orchestrate registry entry",
        }
    ]


def test_vm_stat_headroom_uses_free_and_inactive_pages(monkeypatch) -> None:
    class Result:
        returncode = 0
        stdout = (
            "Mach Virtual Memory Statistics: (page size of 4096 bytes)\n"
            "Pages free: 100.\nPages inactive: 200.\n"
        )

    monkeypatch.setattr(host_quiet.subprocess, "run", lambda *args, **kwargs: Result())

    free_gib, error = host_quiet._vm_stat_free_gib()

    assert free_gib == round(300 * 4096 / 1024**3, 2)
    assert error is None


def test_only_memory_safety_pid_excess_tests_and_low_headroom_block() -> None:
    snapshot = {
        "headroom_gib": 0.5,
        "minimum_headroom_gib": 1.5,
        "maximum_pytest_processes": 4,
        "other_heavy_processes": [
            {"pid": 41, "kind": "dispatch lane job", "process": "dispatch.py"},
            {"pid": 42, "kind": "WFE/bench run", "process": "tests.wfe.campaign"},
            {"pid": 43, "kind": "WFE/bench run", "process": "memory-safety PID file"},
            *[
                {"pid": pid, "kind": "pytest/xdist", "process": "pytest/xdist worker"}
                for pid in range(100, 105)
            ],
        ],
        "busy_requests": 0,
        "process_scan_error": "process table unavailable",
    }

    reasons = host_quiet.blockers(snapshot)

    assert reasons == [
        "WFE/bench run is running (pid 43): memory-safety PID file",
        "pytest/xdist process count 5 exceeds UAT_MAX_PYTEST_PROCESSES=4",
        "host memory headroom 0.5 GiB is below 1.5 GiB",
    ]


def test_dispatch_and_light_test_work_are_recorded_but_do_not_block() -> None:
    snapshot = {
        "headroom_gib": 4.0,
        "minimum_headroom_gib": 1.5,
        "maximum_pytest_processes": 4,
        "other_heavy_processes": [
            {"pid": 41, "kind": "dispatch lane job", "process": "dispatch.py"},
            {"pid": 42, "kind": "WFE/bench run", "process": "tests.wfe.campaign"},
            *[
                {"pid": pid, "kind": "pytest/xdist", "process": "pytest/xdist worker"}
                for pid in range(100, 104)
            ],
        ],
        "busy_requests": 3,
        "process_scan_error": "process table unavailable",
    }

    assert host_quiet.blockers(snapshot) == []


def test_start_and_end_snapshots_retain_dispatch_lane_jobs(monkeypatch) -> None:
    lane = {"pid": 41, "kind": "dispatch lane job", "process": "dispatch.py"}
    snapshots = [
        {"headroom_gib": 4.0, "other_heavy_processes": [lane]},
        {"headroom_gib": 3.0, "other_heavy_processes": [lane]},
    ]
    monkeypatch.setattr(host_quiet, "capture_snapshot", lambda *_args: snapshots.pop(0))

    context = host_quiet.begin_run("http://pipeline.test", "key")
    host_quiet.finish_run(context, "http://pipeline.test", "key")

    assert context["allowed"] is True
    assert context["start"]["other_heavy_processes"] == [lane]
    assert context["end"]["other_heavy_processes"] == [lane]


def test_force_records_which_host_blockers_were_overridden(monkeypatch) -> None:
    monkeypatch.setattr(
        host_quiet,
        "capture_snapshot",
        lambda _url, _key: {
            "headroom_gib": 0.5,
            "minimum_headroom_gib": 1.5,
            "other_heavy_processes": [],
            "busy_requests": 0,
        },
    )

    context = host_quiet.begin_run("http://pipeline.test", "key", force=True)

    assert context["allowed"] is True
    assert context["force_requested"] is True
    assert "host memory headroom 0.5 GiB" in context["override_reason"]
    assert context["blockers"] == ["host memory headroom 0.5 GiB is below 1.5 GiB"]


def test_pytest_headroom_and_wfe_blockers_are_transient() -> None:
    snapshot = {
        "headroom_gib": 0.5,
        "minimum_headroom_gib": 1.5,
        "maximum_pytest_processes": 4,
        "other_heavy_processes": [
            {"pid": 43, "kind": "WFE/bench run", "process": "memory-safety PID file"},
            *[
                {"pid": pid, "kind": "pytest/xdist", "process": "pytest/xdist worker"}
                for pid in range(100, 105)
            ],
        ],
    }

    transient, permanent = host_quiet.classify_blockers(host_quiet.blockers(snapshot))

    assert permanent == []
    assert any("pytest/xdist process count 5" in reason for reason in transient)
    assert any("host memory headroom 0.5 GiB" in reason for reason in transient)
    assert any("memory-safety PID file" in reason for reason in transient)
    assert host_quiet.classify_blockers(["uncommitted opencode.jsonc"]) == (
        [],
        ["uncommitted opencode.jsonc"],
    )


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, delay: float) -> None:
        self.slept.append(delay)
        self.now += delay


def _pytest_lines(count: int) -> list[str]:
    return [f"{300 + pid} 1 /tmp/venv/bin/python -m pytest -n 4 tests/unit" for pid in range(count)]


def _install_quiet_probes(monkeypatch, process_lines) -> None:
    monkeypatch.setenv("UAT_MAX_PYTEST_PROCESSES", "4")
    monkeypatch.setenv("UAT_MIN_HOST_HEADROOM_GIB", "1.5")
    monkeypatch.setattr(host_quiet, "_process_lines", process_lines)
    monkeypatch.setattr(host_quiet, "_registry_processes", lambda **_kwargs: [])
    monkeypatch.setattr(host_quiet, "_pid_file_processes", lambda **_kwargs: [])
    monkeypatch.setattr(host_quiet, "_vm_stat_free_gib", lambda: (8.0, None))

    def fake_request(url, *, method="GET", api_key="", payload=None):
        if "load-plan" in url:
            return {"busy_requests": 0, "available_gib": 8.0}
        return {"models": []}

    monkeypatch.setattr(host_quiet, "_json_request", fake_request)


def test_wait_for_quiet_retries_until_the_process_list_clears(monkeypatch) -> None:
    tables = [_pytest_lines(5), _pytest_lines(5), _pytest_lines(0)]

    def process_lines():
        return tables.pop(0), None

    _install_quiet_probes(monkeypatch, process_lines)
    clock = _Clock()
    logs: list[str] = []
    monkeypatch.setattr(host_quiet.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(host_quiet.time, "sleep", clock.sleep)
    monkeypatch.setattr(host_quiet, "_log_wait", logs.append)

    context = host_quiet.start_run(
        "http://pipeline.test", "key", wait=True, poll_s=30, max_wait_s=120
    )

    assert context["allowed"] is True
    assert clock.slept == [30.0, 30.0]
    assert len(logs) == 2
    assert "waiting 30s" in logs[0]
    assert "pytest/xdist process count 5 exceeds UAT_MAX_PYTEST_PROCESSES=4" in logs[0]
    assert context["quiet_waits"] == [
        {
            "delay_s": 30.0,
            "blockers": ["pytest/xdist process count 5 exceeds UAT_MAX_PYTEST_PROCESSES=4"],
        },
        {
            "delay_s": 30.0,
            "blockers": ["pytest/xdist process count 5 exceeds UAT_MAX_PYTEST_PROCESSES=4"],
        },
    ]


def test_wait_for_quiet_gives_up_when_the_process_list_stays_busy(monkeypatch) -> None:
    _install_quiet_probes(monkeypatch, lambda: (_pytest_lines(5), None))
    clock = _Clock()
    logs: list[str] = []
    monkeypatch.setattr(host_quiet.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(host_quiet.time, "sleep", clock.sleep)
    monkeypatch.setattr(host_quiet, "_log_wait", logs.append)

    context = host_quiet.start_run(
        "http://pipeline.test", "key", wait=True, poll_s=30, max_wait_s=45
    )

    assert context["allowed"] is False
    assert clock.slept == [30.0, 15.0]
    assert "expired after 45s" in logs[-1]
    assert "pytest/xdist process count 5" in context["blockers"][0]


def test_wait_for_quiet_does_not_sleep_on_a_permanent_blocker(monkeypatch) -> None:
    def begin(_url, _key, force=False):
        return {
            "allowed": False,
            "force_requested": force,
            "override_reason": None,
            "blockers": ["selected engine does not match the card"],
            "start": {},
        }

    monkeypatch.setattr(host_quiet, "begin_run", begin)
    monkeypatch.setattr(
        host_quiet.time, "sleep", lambda _delay: (_ for _ in ()).throw(AssertionError("slept"))
    )

    context = host_quiet.wait_for_quiet("http://pipeline.test", "key", poll_s=30, max_wait_s=120)

    assert context["allowed"] is False
    assert context["permanent_blockers"] == ["selected engine does not match the card"]
    assert context["quiet_waits"] == []


def test_start_run_force_does_not_wait(monkeypatch) -> None:
    monkeypatch.setattr(
        host_quiet,
        "begin_run",
        lambda *_args, **_kwargs: {"allowed": True, "blockers": ["host memory headroom"]},
    )
    monkeypatch.setattr(
        host_quiet,
        "wait_for_quiet",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("waited")),
    )

    context = host_quiet.start_run("http://pipeline.test", "key", force=True, wait=True)

    assert context["allowed"] is True
