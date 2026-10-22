"""Host-quiet preflight tests with synthetic process and engine state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts import host_quiet


def test_process_scan_finds_dispatch_pytest_wfe_and_bench() -> None:
    lines = [
        "101 1 python /Users/x/.claude/orchestrate/bin/dispatch.py run lane",
        "102 1 /venv/bin/python -m pytest -n 4 tests/unit",
        "103 1 python -m tests.wfe.campaign --plan private.yaml",
        "104 1 python scripts/bench_engine_h2h.py --repeat 10",
        "105 106 python scripts/uat_engines.py",
        "106 107 python scripts/uat_engines.py",
        "107 1 python /Users/x/.claude/orchestrate/bin/dispatch.py run this lane",
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


def test_active_orchestrate_registry_entry_blocks(tmp_path: Path) -> None:
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


def test_low_headroom_and_heavy_work_block_start() -> None:
    snapshot = {
        "headroom_gib": 0.5,
        "minimum_headroom_gib": 1.5,
        "other_heavy_processes": [
            {"pid": 41, "kind": "dispatch lane job", "process": "dispatch.py"}
        ],
        "busy_requests": 0,
    }

    reasons = host_quiet.blockers(snapshot)

    assert reasons == [
        "dispatch lane job is running (pid 41): dispatch.py",
        "host memory headroom 0.5 GiB is below 1.5 GiB",
    ]


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
