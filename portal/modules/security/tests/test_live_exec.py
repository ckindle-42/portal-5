"""Live-lab execution foundation — guards the governing rule: no path may emit
`verified` without real host output. All host/mcp calls are mocked; no live lab in CI.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.matrix import (
    _PHASE_MAP,
    DISPATCH_NOT_RUN,
    RunUnit,
    _dispatch_exec_sequence,
    _execute_unit,
    _expand_vulhub_globs,
    _resolve_env,
    _run_against_target,
)


@pytest.fixture(autouse=True)
def _no_real_ssh(monkeypatch):
    """Never make a real ssh call in the unit suite; tests override per-case."""
    monkeypatch.setattr(
        "scripts.lab_host._host_exec", lambda cmd, timeout=20: {"ok": True, "output": ""}
    )


def _unit(**kwargs) -> RunUnit:
    base = {
        "id": "u1",
        "kind": "scenario",
        "target_spec": "lab-vulhub",
        "oracle": "rce_shell",
        "scoring": "oracle",
        "domain": "web",
        "spin": "static",
        "scenario_key": "redis_to_rce",
    }
    base.update(kwargs)
    return RunUnit(**base)


# ── False-verified guard (most important) ──────────────────────────────────────


class TestFalseVerifiedGuard:
    def test_dispatch_not_run_is_never_verified(self):
        """A scenario_key with no phase and no exec_sequence -> DISPATCH_NOT_RUN -> indeterminate,
        never verified, regardless of which oracle is named."""
        unit = _unit(scenario_key="totally_unknown_scenario_key")
        assert _run_against_target(unit, lab_exec=False) == DISPATCH_NOT_RUN
        result = _execute_unit(unit, lab_exec=False, purple=False)
        assert result.status == "indeterminate"
        assert result.status != "verified"

    def test_dispatch_not_run_never_verified_for_every_registered_oracle(self):
        """Sweep every oracle id — DISPATCH_NOT_RUN must never slip through as verified for any of them."""
        from portal.modules.security.core.oracles import ORACLES

        for oracle_id in ORACLES:
            unit = _unit(scenario_key="totally_unknown_scenario_key", oracle=oracle_id)
            result = _execute_unit(unit, lab_exec=False, purple=False)
            assert result.status != "verified", f"oracle {oracle_id} let DISPATCH_NOT_RUN verify"

    def test_dry_run_halt_transcript_never_verified(self, monkeypatch):
        """A dry-run tier-2 transcript (lab_exec=False) must never accidentally satisfy an
        oracle's default markers and score verified."""
        unit = _unit(scenario_key="redis_to_rce", oracle="rce_shell")
        result = _execute_unit(unit, lab_exec=False, purple=False)
        assert result.status != "verified"

    def test_failed_step_halt_never_verified(self, monkeypatch):
        """A tier-2 (exec_sequence, not tier-1 phase) sequence where a required step fails
        halts and must never verify."""
        monkeypatch.setattr(
            "bench_lab_exec._mcp_call",
            lambda cmd, timeout=120: {"ok": False, "output": "connection refused"},
        )
        # smb_enum_relay is tier-2 only (real exec_sequence, no _phase_ function)
        unit = _unit(scenario_key="smb_enum_relay", oracle="rce_shell")
        result = _execute_unit(unit, lab_exec=True, purple=False)
        assert result.status != "verified"
        assert "dispatch-halt" in result.lab_output


# ── Resolution goes through _host_exec (the host), never local glob ────────────


class TestHostResolution:
    def test_expand_vulhub_globs_calls_host_exec(self, monkeypatch):
        calls = []

        def _fake(cmd, timeout=20):
            calls.append(cmd)
            return {"ok": True, "output": ""}

        monkeypatch.setattr("scripts.lab_host._host_exec", _fake)
        _expand_vulhub_globs(["fastjson/*"], "/opt/vulhub")
        assert calls, "_expand_vulhub_globs must dispatch via _host_exec"
        assert (
            "pct exec" not in calls[0]
        )  # _host_exec already wraps pct exec; cmd is the inner command


# ── cmd_up / cmd_down issue real pct exec docker compose (mocked) ──────────────


class TestSpinUpDown:
    def test_cmd_up_issues_docker_compose_via_host_exec(self, monkeypatch):
        calls = []

        def _fake(cmd, timeout=30):
            calls.append(cmd)
            if "test -f" in cmd:
                return {"ok": True, "output": "EXISTS"}
            if "docker compose" in cmd and "up -d" in cmd:
                return {"ok": True, "output": "Started"}
            if "docker ps" in cmd:
                return {"ok": True, "output": ""}
            return {"ok": True, "output": ""}

        # cmd_up/cmd_down import _host_exec at module load time (`from scripts.lab_host
        # import _host_exec`) — patch the bound name in scripts.lab_targets, not the source.
        monkeypatch.setattr("scripts.lab_targets._host_exec", _fake)
        monkeypatch.setattr(
            "scripts.lab_targets._wait_reachable", lambda host, port, timeout_s=30.0: True
        )

        from scripts.lab_targets import cmd_up

        result = cmd_up("fastjson/CVE-x", dry_run=False)
        assert result["status"] != "placeholder"
        assert any("docker compose" in c and "up -d" in c for c in calls)

    def test_cmd_down_issues_docker_compose_down_via_host_exec(self, monkeypatch):
        calls = []

        def _fake(cmd, timeout=30):
            calls.append(cmd)
            return {"ok": True, "output": "Stopped"}

        monkeypatch.setattr("scripts.lab_targets._host_exec", _fake)

        from scripts.lab_targets import cmd_down

        result = cmd_down("fastjson/CVE-x", dry_run=False)
        assert result["status"] != "placeholder"
        assert any("docker compose" in c and "down" in c for c in calls)


# ── Tier-1 routes to the proven phase by scenario_key ───────────────────────────


class TestTier1Routing:
    def test_known_scenario_keys_route_to_phase_map(self):
        for key in (
            "kerberoasting",
            "asrep_roasting",
            "log4shell_rce",
            "redis_to_rce",
            "tomcat_manager",
            "htb_lfi_log_poison",
        ):
            assert key in _PHASE_MAP, f"{key} should be a tier-1 phase"

    def test_excluded_keys_not_in_phase_map(self):
        """dcsync/meta3_compromise/srv01_local_privesc/mbptl_full_chain are not PROMPTS keys,
        so no scenario-derived unit can ever carry them — must not be mapped (task Instruction #1)."""
        for key in ("dcsync", "meta3_compromise", "srv01_local_privesc", "mbptl_full_chain"):
            assert key not in _PHASE_MAP

    def test_tier1_dispatch_calls_the_mapped_phase(self, monkeypatch):
        called = {}

        def _fake_phase(dry_run):
            called["dry_run"] = dry_run
            return {"ok": True, "output": "uid=0(root) gid=0(root)", "detail": "shell obtained"}

        monkeypatch.setitem(_PHASE_MAP, "redis_to_rce", _fake_phase)
        unit = _unit(scenario_key="redis_to_rce")
        evidence = _run_against_target(unit, lab_exec=True)
        assert called["dry_run"] is False
        assert "uid=0(root)" in evidence


# ── Tier-2 dispatches each step, halts on required-step failure ────────────────


class TestTier2Dispatch:
    def test_dry_run_produces_transcript_without_real_calls(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            "bench_lab_exec._mcp_call",
            lambda *a, **k: called.append(1) or {"ok": True, "output": ""},
        )
        seq = [
            {"step": "exploit", "tool": "execute_bash", "tool_hint": "curl $LAB_TARGET_WEB:6379"},
        ]
        unit = _unit(scenario_key="redis_to_rce")
        out = _dispatch_exec_sequence(unit, seq, lab_exec=False)
        assert "[dry-run]" in out
        assert not called, "dry-run must not call _mcp_call"

    def test_lab_exec_halts_on_failed_required_step(self, monkeypatch):
        calls = []

        def _fake_mcp(cmd, timeout=120):
            calls.append(cmd)
            if len(calls) == 1:
                return {"ok": True, "output": "step1 ok"}
            return {"ok": False, "output": "step2 failed"}

        monkeypatch.setattr("bench_lab_exec._mcp_call", _fake_mcp)
        seq = [
            {"step": "step1", "tool_hint": "echo one"},
            {"step": "step2", "tool_hint": "echo two"},
            {"step": "step3", "tool_hint": "echo three"},
        ]
        unit = _unit(scenario_key="redis_to_rce")
        out = _dispatch_exec_sequence(unit, seq, lab_exec=True)
        assert len(calls) == 2, "must halt after the failed required step, never reach step3"
        assert "dispatch-halt" in out

    def test_non_dict_steps_skipped_without_crash(self):
        """EXEC_SEQUENCES['chain_inherits'] is a list of plain strings, not step dicts —
        defensive guard against a future scenario_key alias colliding with it."""
        unit = _unit(scenario_key="redis_to_rce")
        out = _dispatch_exec_sequence(unit, ["kerberoasting", "asrep_roasting"], lab_exec=False)
        assert out == ""


# ── _resolve_env substitutes known lab vars, leaves unknowns literal ───────────


class TestResolveEnv:
    def test_substitutes_known_var(self, monkeypatch):
        monkeypatch.setattr("bench_lab_exec.WEB", "10.10.11.50")
        assert "10.10.11.50" in _resolve_env("curl http://$LAB_TARGET_WEB:6379")

    def test_unset_var_left_literal(self, monkeypatch):
        monkeypatch.setattr("bench_lab_exec.DC", "")
        out = _resolve_env("nxc smb $LAB_TARGET_DC -u a")
        assert "$LAB_TARGET_DC" in out

    def test_unknown_var_left_literal(self):
        out = _resolve_env("echo $LAB_NETWORK/24")
        assert "$LAB_NETWORK" in out


# ── A class with no host env -> indeterminate ───────────────────────────────────


class TestNoHostEnvIndeterminate:
    def test_class_with_zero_resolved_envs_is_indeterminate(self, monkeypatch):
        monkeypatch.setattr(
            "scripts.lab_host._host_exec", lambda cmd, timeout=20: {"ok": True, "output": ""}
        )
        from portal.modules.security.core.matrix import _resolve_challenge_class

        paths = _resolve_challenge_class({"vulhub": ["nonexistent_category/*"]}, "/opt/vulhub")
        assert paths == []

    def test_no_oracle_heuristic_unit_is_indeterminate(self):
        """The 10 no-oracle blue prompts still score indeterminate (heuristic, not verified)."""
        unit = _unit(scenario_key="redis_to_rce", oracle=None, scoring="heuristic")
        result = _execute_unit(unit, lab_exec=False, purple=False)
        assert result.status == "indeterminate"
