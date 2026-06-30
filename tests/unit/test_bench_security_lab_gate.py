"""Unit tests for the lab reachability gate and raw-output capture wrapper.

Pure logic tests — mocks _lab_mcp_call, no Docker, no network. Added 2026-06-30
alongside the gate itself; see docs/LAB_REACHABILITY_DIAGNOSTIC_2026-06-30.md for why.
"""

from __future__ import annotations

import json

from tests.benchmarks.bench_security import lab as lab_mod


def test_gate_skips_when_lab_exec_unavailable(monkeypatch):
    monkeypatch.setattr(lab_mod, "_LAB_EXEC_AVAILABLE", False)
    assert lab_mod.verify_lab_targets_reachable() is True


def test_gate_skips_on_dry_run(monkeypatch):
    monkeypatch.setattr(lab_mod, "_LAB_EXEC_AVAILABLE", True)
    assert lab_mod.verify_lab_targets_reachable(dry_run=True) is True


def test_gate_passes_when_both_reachable(monkeypatch):
    monkeypatch.setattr(lab_mod, "_LAB_EXEC_AVAILABLE", True)
    monkeypatch.setattr(lab_mod, "_lab_mcp_call", lambda *a, **k: {"output": "REACHABLE"})
    assert lab_mod.verify_lab_targets_reachable() is True


def test_gate_fails_when_both_unreachable(monkeypatch):
    monkeypatch.setattr(lab_mod, "_LAB_EXEC_AVAILABLE", True)
    monkeypatch.setattr(lab_mod, "_lab_mcp_call", lambda *a, **k: {"output": "UNREACHABLE"})
    assert lab_mod.verify_lab_targets_reachable() is False


def test_gate_warns_but_passes_on_partial_reachability(monkeypatch):
    monkeypatch.setattr(lab_mod, "_LAB_EXEC_AVAILABLE", True)
    calls = {"n": 0}

    def _fake_call(*_a, **_k):
        calls["n"] += 1
        return {"output": "REACHABLE" if calls["n"] == 1 else "UNREACHABLE"}

    monkeypatch.setattr(lab_mod, "_lab_mcp_call", _fake_call)
    assert lab_mod.verify_lab_targets_reachable() is True


def test_gate_handles_mcp_call_exception(monkeypatch):
    monkeypatch.setattr(lab_mod, "_LAB_EXEC_AVAILABLE", True)

    def _raise(*_a, **_k):
        raise RuntimeError("sandbox unreachable")

    monkeypatch.setattr(lab_mod, "_lab_mcp_call", _raise)
    assert lab_mod.verify_lab_targets_reachable() is False


def test_lab_dispatch_writes_raw_log_when_env_set(monkeypatch, tmp_path):
    log_path = tmp_path / "raw.jsonl"
    monkeypatch.setenv("BENCH_LAB_RAW_LOG", str(log_path))
    monkeypatch.setattr(
        lab_mod, "_lab_dispatch_inner", lambda fn, args, dry_run=False: "OK: synthetic"
    )
    result = lab_mod.lab_dispatch("run_nmap_scan", {"target": "10.10.11.21"})
    assert result == "OK: synthetic"
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["fn_name"] == "run_nmap_scan"
    assert entry["raw_output"] == "OK: synthetic"


def test_lab_dispatch_no_log_when_env_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("BENCH_LAB_RAW_LOG", raising=False)
    monkeypatch.setattr(
        lab_mod, "_lab_dispatch_inner", lambda fn, args, dry_run=False: "OK: synthetic"
    )
    # Should not raise even though no log path is configured.
    result = lab_mod.lab_dispatch("check_cve", {})
    assert result == "OK: synthetic"


def test_lab_dispatch_log_failure_does_not_raise(monkeypatch):
    monkeypatch.setenv("BENCH_LAB_RAW_LOG", "/nonexistent-dir-xyz/raw.jsonl")
    monkeypatch.setattr(
        lab_mod, "_lab_dispatch_inner", lambda fn, args, dry_run=False: "OK: synthetic"
    )
    # Bad log path must not break the bench run.
    result = lab_mod.lab_dispatch("exploit_service", {})
    assert result == "OK: synthetic"
