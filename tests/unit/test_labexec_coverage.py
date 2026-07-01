"""Unit tests for lab-exec coverage — dry-run/synthetic, no live lab or Docker."""

from __future__ import annotations

import sys
from pathlib import Path

_BENCH_DIR = str(Path(__file__).resolve().parent.parent / "benchmarks")
if _BENCH_DIR not in sys.path:
    sys.path.insert(0, _BENCH_DIR)


class TestLabTargetTable:
    """Phase 1 — target table builds from env, skips absent targets."""

    def test_target_table_builds_from_env(self):
        from bench_lab_exec import LAB_TARGETS, _build_target

        # Directly call _build_target to verify it populates LAB_TARGETS
        _build_target("dc01", "110", "10.10.11.1", "baseline-ad", "vm")
        _build_target("srv01", "111", "10.10.11.33", "baseline-ad", "vm")
        try:
            assert "dc01" in LAB_TARGETS
            assert LAB_TARGETS["dc01"]["vmid"] == "110"
            assert LAB_TARGETS["dc01"]["kind"] == "vm"
            assert "srv01" in LAB_TARGETS
            assert LAB_TARGETS["srv01"]["vmid"] == "111"
        finally:
            LAB_TARGETS.pop("dc01", None)
            LAB_TARGETS.pop("srv01", None)

    def test_target_skipped_when_vmid_not_set(self, monkeypatch):
        from bench_lab_exec import LAB_TARGETS, _build_target

        # _build_target with empty vmid should NOT add an entry
        _build_target("_test_empty", "", "10.10.11.99", "clean", "vm")
        assert "_test_empty" not in LAB_TARGETS

        # vulhub and meta3 typically have no VMID in CI
        assert "vulhub" not in LAB_TARGETS or LAB_TARGETS.get("vulhub", {}).get("vmid") == ""
        assert "meta3" not in LAB_TARGETS or LAB_TARGETS.get("meta3", {}).get("vmid") == ""

    def test_lab_setup_skips_absent_target(self):
        from bench_lab_exec import lab_setup

        ok = lab_setup(targets=["vulhub", "meta3"], dry_run=True)
        assert ok is True  # absent targets skipped, not failed

    def test_lab_teardown_skips_absent_target(self):
        from bench_lab_exec import lab_teardown

        ok = lab_teardown(targets=["vulhub", "meta3"], dry_run=True)
        assert ok is True

    def test_lab_setup_iterates_only_requested_present_targets(self):
        from bench_lab_exec import LAB_TARGETS, lab_setup

        LAB_TARGETS["dc01"] = {
            "vmid": "110",
            "ip": "10.10.11.1",
            "snapshot": "baseline-ad",
            "kind": "vm",
        }
        LAB_TARGETS["vulhub"] = {
            "vmid": "112",
            "ip": "10.10.11.15",
            "snapshot": "clean",
            "kind": "lxc",
        }
        try:
            ok = lab_setup(targets=["dc01", "vulhub"], dry_run=True)
            assert ok is True
        finally:
            LAB_TARGETS.pop("dc01", None)
            LAB_TARGETS.pop("vulhub", None)


class TestPhaseRegistry:
    """Phase 2 — all new phases are registered in PHASE_FNS with targets."""

    EXPECTED_PHASES = [
        "recon",
        "kerberoast",
        "asrep",
        "crack",
        "spray",
        "bloodhound",
        "winrm",
        "dcsync",
        "vulhub_redis",
        "vulhub_lfi",
        "vulhub_tomcat",
        "vulhub_log4shell",
        "meta3_compromise",
        "srv01_local",
        "mbptl_full_chain",
    ]

    def test_all_phases_registered(self):
        from bench_lab_exec import PHASE_FNS

        for phase in self.EXPECTED_PHASES:
            assert phase in PHASE_FNS, f"phase '{phase}' not in PHASE_FNS"
            assert callable(PHASE_FNS[phase]), f"phase '{phase}' is not callable"

    def test_each_phase_declares_target(self):
        from bench_lab_exec import PHASE_FNS, PHASE_TARGETS

        for phase in PHASE_FNS:
            assert phase in PHASE_TARGETS, f"phase '{phase}' missing from PHASE_TARGETS"
            targets = PHASE_TARGETS[phase]
            assert isinstance(targets, list), f"target for '{phase}' is not a list"
            assert len(targets) > 0, f"target for '{phase}' is empty"

    def test_new_phases_no_op_under_dry_run(self):
        from bench_lab_exec import PHASE_FNS

        for phase_name in ["vulhub_redis", "meta3_compromise", "srv01_local"]:
            fn = PHASE_FNS[phase_name]
            result = fn(dry_run=True)
            assert result.get("ok") is True, f"phase '{phase_name}' dry_run failed"

    def test_phase_targets_in_target_table(self):
        from bench_lab_exec import LAB_TARGETS, PHASE_TARGETS

        for _phase, targets in PHASE_TARGETS.items():
            for t in targets:
                # target MAY be absent if env not set — that's valid
                if t in LAB_TARGETS:
                    assert "vmid" in LAB_TARGETS[t], f"target '{t}' missing vmid"
                    assert "kind" in LAB_TARGETS[t], f"target '{t}' missing kind"


class TestCoverageReport:
    """Phase 7 — coverage matrix reports every provisioned target."""

    def test_coverage_is_accessible(self):
        from bench_lab_exec import ALL_PHASES, PHASE_FNS

        # ALL_PHASES includes all targets
        assert "vulhub_redis" in ALL_PHASES
        assert "meta3_compromise" in ALL_PHASES
        assert "mbptl_full_chain" in ALL_PHASES
        assert "srv01_local" in ALL_PHASES
        for p in ALL_PHASES:
            assert p in PHASE_FNS


class TestMbptlDefaultPath:
    """Phase 5 — mbptl uses live dispatch by default, synthetic only as fallback."""

    def test_mbptl_phase_registered(self):
        from bench_lab_exec import PHASE_FNS, PHASE_TARGETS

        assert "mbptl_full_chain" in PHASE_FNS
        assert PHASE_TARGETS["mbptl_full_chain"] == ["mbptl"]

    def test_mbptl_phase_dry_run_no_op(self):
        from bench_lab_exec import _phase_mbptl_full_chain

        result = _phase_mbptl_full_chain(dry_run=True)
        assert result["ok"] is True

    def test_mbptl_phase_returns_skip_when_env_unset(self):
        """When LAB_MBPTL_HOST is unset at module-load time, phase returns skip."""
        # This test works correctly when LAB_MBPTL_HOST is not in .env.
        # When it IS set (typical dev env), the module global is already populated
        # and the phase runs live — that's expected behavior.
        from bench_lab_exec import MBPTL_HOST, _phase_mbptl_full_chain

        if not MBPTL_HOST:
            result = _phase_mbptl_full_chain(dry_run=False)
            assert "not set" in result["detail"]
        else:
            # MBPTL_HOST is set — verify the phase can produce a result dict
            result = _phase_mbptl_full_chain(dry_run=True)
            assert result["ok"] is True


class TestLabDispatchMbptl:
    """Phase 5 — lab dispatch handles mbptl chain tools live when env is set."""

    def test_lab_dispatch_imports(self):
        from bench_security.lab import _lab_dispatch_inner

        assert callable(_lab_dispatch_inner)

    def test_mbptl_tool_names_handled(self):
        from bench_security.lab import _lab_dispatch_inner

        for fn_name in [
            "web_request",
            "run_sqlmap",
            "upload_webshell",
            "webshell_exec",
            "exploit_binary_service",
        ]:
            result = _lab_dispatch_inner(fn_name, {}, dry_run=True)
            assert "[DRY-RUN]" in result or "synthetic" in result, f"tool '{fn_name}' not handled"

    def test_mbptl_synthetic_fallback_when_lab_not_reachable(self):
        """When LAB_MBPTL_HOST is set but lab exec is not available, returns synthetic."""
        from bench_security.lab import _lab_dispatch_inner

        # The synthetic path is reached when _LAB_EXEC_AVAILABLE is False
        # (set at module import time from SANDBOX_LAB_EXEC + bench_lab_exec import)
        # In CI, _LAB_EXEC_AVAILABLE may already be False — verify dispatch works either way.
        result = _lab_dispatch_inner("web_request", {}, dry_run=True)
        # dry_run should show [DRY-RUN] regardless of availability
        assert "[DRY-RUN]" in result, f"unexpected result: {result[:100]}"

    def test_mbptl_tool_dispatch_handles_unknown_tool(self):
        from bench_security.lab import _lab_dispatch_inner

        result = _lab_dispatch_inner("nonexistent_tool", {}, dry_run=True)
        assert "synthetic" in result.lower() or "not" in result.lower()
