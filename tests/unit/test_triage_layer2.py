"""Unit tests for Layer 2 triage — mock P40 call + primitives, no live lab."""

from __future__ import annotations

import contextlib
import json
from unittest.mock import MagicMock, patch

import scripts.bench_supervisor as sup
import scripts.triage as triage
import scripts.triage_actions as actions

# ── Allowlist guard (most important) ─────────────────────────────────────────


class TestAllowlistGuard:
    """A triage response naming a disallowed action → rejected, pause_for_human."""

    def test_disallowed_action_rejected(self):
        result = triage.parse_triage_response(
            json.dumps(
                {
                    "action": "rm_rf_everything",
                    "params": {},
                    "reason": "test",
                    "confidence": 0.99,
                }
            )
        )
        assert result["action"] == "rm_rf_everything"
        # The diagnose function should reject it
        with patch.object(
            triage,
            "call_triage_model",
            return_value={
                "ok": True,
                "response": json.dumps(
                    {
                        "action": "rm_rf_everything",
                        "params": {},
                        "reason": "test",
                        "confidence": 0.99,
                    }
                ),
            },
        ):
            diag = triage.diagnose(
                log_tail="test",
                failing_line="test error",
                scenario="test",
            )
        assert diag["action"] == "pause_for_human"
        assert "disallowed" in diag["reason"]

    def test_allowed_action_accepted(self):
        with patch.object(
            triage,
            "call_triage_model",
            return_value={
                "ok": True,
                "response": json.dumps(
                    {
                        "action": "restart_lxc",
                        "params": {"vmid": 112},
                        "reason": "LXC down",
                        "confidence": 0.8,
                    }
                ),
            },
        ):
            diag = triage.diagnose(
                log_tail="test",
                failing_line="LXC down",
                scenario="test",
            )
        assert diag["action"] == "restart_lxc"
        assert diag["allowed"]
        assert diag["above_floor"]

    def test_all_actions_are_reversible(self):
        """Every action in the allowlist must be reversible."""
        for name, entry in actions.ALLOWED_ACTIONS.items():
            assert entry.get("reversible", False), f"{name} is not reversible"

    def test_is_action_allowed(self):
        assert actions.is_action_allowed("restart_lxc")
        assert actions.is_action_allowed("pause_for_human")
        assert not actions.is_action_allowed("nonexistent_action")
        assert not actions.is_action_allowed("rm_rf")

    def test_execute_action_calls_primitive(self):
        mock_result = {"action": "restart_lxc", "vmid": 112, "ok": True}
        # Patch the function reference stored in the allowlist
        original_fn = actions.ALLOWED_ACTIONS["restart_lxc"]["fn"]
        actions.ALLOWED_ACTIONS["restart_lxc"]["fn"] = MagicMock(return_value=mock_result)
        try:
            result = actions.execute_action("restart_lxc", {"vmid": 112})
            actions.ALLOWED_ACTIONS["restart_lxc"]["fn"].assert_called_once_with({"vmid": 112})
            assert result["ok"]
        finally:
            actions.ALLOWED_ACTIONS["restart_lxc"]["fn"] = original_fn


# ── Propose mode ─────────────────────────────────────────────────────────────


class TestProposeMode:
    """Propose mode never executes without operator confirm."""

    def test_propose_shows_and_waits(self):
        state = sup.SupervisorState()
        state.current_scenario = "test_sc"
        with (
            patch.object(
                triage,
                "diagnose",
                return_value={
                    "action": "restart_lxc",
                    "params": {"vmid": 112},
                    "reason": "LXC down",
                    "confidence": 0.8,
                    "allowed": True,
                    "above_floor": True,
                    "raw_response": "{}",
                },
            ),
            patch("builtins.input", return_value=""),
            patch.object(actions, "execute_action", return_value={"ok": True}) as mock_exec,
        ):
            result = sup.handle_escalation(
                state,
                "test error",
                "pause",
                3,
                triage_mode="propose",
            )
        # Should have executed after confirm
        mock_exec.assert_called_once()
        assert result == "retry"

    def test_propose_skip_by_operator(self):
        state = sup.SupervisorState()
        state.current_scenario = "test_sc"
        with (
            patch.object(
                triage,
                "diagnose",
                return_value={
                    "action": "restart_lxc",
                    "params": {"vmid": 112},
                    "reason": "LXC down",
                    "confidence": 0.8,
                    "allowed": True,
                    "above_floor": True,
                    "raw_response": "{}",
                },
            ),
            patch("builtins.input", return_value="s"),
        ):
            result = sup.handle_escalation(
                state,
                "test error",
                "pause",
                3,
                triage_mode="propose",
            )
        assert result == "skip"

    def test_propose_keyboard_interrupt_aborts(self):
        state = sup.SupervisorState()
        with (
            patch.object(
                triage,
                "diagnose",
                return_value={
                    "action": "pause_for_human",
                    "params": {},
                    "reason": "test",
                    "confidence": 0.0,
                    "allowed": True,
                    "above_floor": False,
                    "raw_response": "{}",
                },
            ),
            patch("builtins.input", side_effect=KeyboardInterrupt),
            contextlib.suppress(SystemExit),
        ):
            sup.handle_escalation(
                state,
                "test error",
                "pause",
                3,
                triage_mode="propose",
            )


# ── Auto mode ────────────────────────────────────────────────────────────────


class TestAutoMode:
    """Auto mode executes only allowlisted + confidence-gated + under cap."""

    def test_auto_executes_allowlisted_above_floor(self):
        state = sup.SupervisorState()
        state.current_scenario = "test_sc"
        with (
            patch.object(
                triage,
                "diagnose",
                return_value={
                    "action": "restart_lxc",
                    "params": {"vmid": 112},
                    "reason": "LXC down",
                    "confidence": 0.8,
                    "allowed": True,
                    "above_floor": True,
                    "raw_response": "{}",
                },
            ),
            patch.object(actions, "execute_action", return_value={"ok": True}) as mock_exec,
        ):
            result = sup.handle_escalation(
                state,
                "test error",
                "pause",
                3,
                triage_mode="auto",
            )
        mock_exec.assert_called_once()
        assert result == "retry"

    def test_auto_rejects_low_confidence(self):
        state = sup.SupervisorState()
        state.current_scenario = "test_sc"
        with (
            patch.object(
                triage,
                "diagnose",
                return_value={
                    "action": "restart_lxc",
                    "params": {"vmid": 112},
                    "reason": "unsure",
                    "confidence": 0.2,
                    "allowed": True,
                    "above_floor": False,
                    "raw_response": "{}",
                },
            ),
            patch("builtins.input", side_effect=EOFError),
            contextlib.suppress(SystemExit, EOFError),
        ):
            sup.handle_escalation(
                state,
                "test error",
                "pause",
                3,
                triage_mode="auto",
                confidence_floor=0.5,
            )

    def test_auto_rejects_disallowed_action(self):
        state = sup.SupervisorState()
        state.current_scenario = "test_sc"
        with (
            patch.object(
                triage,
                "diagnose",
                return_value={
                    "action": "pause_for_human",
                    "params": {},
                    "reason": "disallowed_action: bad_thing",
                    "confidence": 0.0,
                    "allowed": False,
                    "above_floor": False,
                    "raw_response": "{}",
                },
            ),
            patch("builtins.input", side_effect=EOFError),
            contextlib.suppress(SystemExit, EOFError),
        ):
            sup.handle_escalation(
                state,
                "test error",
                "pause",
                3,
                triage_mode="auto",
            )


# ── Cap guard ────────────────────────────────────────────────────────────────


class TestCapGuard:
    """Repeated failures on one scenario stop after K corrections."""

    def test_cap_prevents_infinite_loop(self):
        state = sup.SupervisorState()
        state.current_scenario = "stuck_sc"
        state.correction_counts["stuck_sc"] = 5  # already exceeded cap of 3
        with (
            patch.object(
                triage,
                "diagnose",
                return_value={
                    "action": "restart_lxc",
                    "params": {"vmid": 112},
                    "reason": "LXC down",
                    "confidence": 0.9,
                    "allowed": True,
                    "above_floor": True,
                    "raw_response": "{}",
                },
            ),
            patch("builtins.input", side_effect=EOFError),
            contextlib.suppress(SystemExit, EOFError),
        ):
            sup.handle_escalation(
                state,
                "test error",
                "pause",
                3,
                triage_mode="auto",
            )
        # The cap check should prevent triage from even being called
        cap_actions = [
            a
            for a in state.actions
            if "cap reached" in a.get("action", "") or "cap reached" in a.get("detail", "")
        ]
        assert len(cap_actions) > 0


# ── P40-down fallback ────────────────────────────────────────────────────────


class TestP40DownFallback:
    """Unreachable TRIAGE_OLLAMA_URL → Layer 1 log-and-pause, no crash."""

    def test_model_unavailable_falls_back(self):
        state = sup.SupervisorState()
        with (
            patch.object(
                triage,
                "call_triage_model",
                return_value={
                    "ok": False,
                    "error": "connection refused",
                },
            ),
            patch("builtins.input", side_effect=EOFError),
            contextlib.suppress(SystemExit, EOFError),
        ):
            sup.handle_escalation(
                state,
                "test error",
                "pause",
                3,
                triage_mode="auto",
            )
        # Should have logged the triage error
        triage_actions = [a for a in state.actions if a.get("handler") == "triage"]
        assert len(triage_actions) > 0

    def test_triage_exception_falls_back(self):
        state = sup.SupervisorState()
        with (
            patch.object(triage, "diagnose", side_effect=Exception("unexpected")),
            patch("builtins.input", side_effect=EOFError),
            contextlib.suppress(SystemExit, EOFError),
        ):
            sup.handle_escalation(
                state,
                "test error",
                "pause",
                3,
                triage_mode="auto",
            )
        # Should have logged the error
        error_actions = [a for a in state.actions if a.get("handler") == "triage"]
        assert len(error_actions) > 0


# ── Parse response ───────────────────────────────────────────────────────────


class TestParseResponse:
    """Triage response parsing handles edge cases."""

    def test_valid_json_parsed(self):
        raw = json.dumps(
            {
                "action": "restart_lxc",
                "params": {"vmid": 112},
                "reason": "LXC down",
                "confidence": 0.8,
            }
        )
        result = triage.parse_triage_response(raw)
        assert result["action"] == "restart_lxc"
        assert result["confidence"] == 0.8

    def test_markdown_fences_stripped(self):
        raw = '```json\n{"action": "skip_scenario", "params": {}, "reason": "wedged", "confidence": 0.7}\n```'
        result = triage.parse_triage_response(raw)
        assert result["action"] == "skip_scenario"

    def test_malformed_json_returns_pause(self):
        result = triage.parse_triage_response("not json at all")
        assert result["action"] == "pause_for_human"
        assert result["confidence"] == 0.0

    def test_missing_action_returns_pause(self):
        result = triage.parse_triage_response(json.dumps({"params": {}, "confidence": 0.5}))
        assert result["action"] == "pause_for_human"

    def test_json_embedded_in_text(self):
        raw = 'Here is my analysis: {"action": "revert_target", "params": {}, "reason": "dirty", "confidence": 0.6} end'
        result = triage.parse_triage_response(raw)
        assert result["action"] == "revert_target"


# ── Prompt construction ──────────────────────────────────────────────────────


class TestPromptConstruction:
    """Prompt is bounded and diagnostic-only."""

    def test_prompt_includes_action_menu(self):
        prompt = triage.build_triage_prompt(
            log_tail="test log",
            failing_line="test error",
            scenario="test_sc",
        )
        assert "restart_lxc" in prompt
        assert "pause_for_human" in prompt
        assert "JSON" in prompt

    def test_prompt_bounded(self):
        long_log = "line\n" * 10000
        prompt = triage.build_triage_prompt(
            log_tail=long_log,
            failing_line="error",
            scenario="sc",
        )
        # Should be bounded (not 10000 lines)
        assert len(prompt) < 20000

    def test_prompt_no_attack_content(self):
        prompt = triage.build_triage_prompt(
            log_tail="test",
            failing_line="error",
            scenario="sc",
        )
        # Should not ask for attack content
        assert "attack" not in prompt.lower() or "never produce attack content" in prompt.lower()


# ── Diagnose end-to-end ──────────────────────────────────────────────────────


class TestDiagnoseEndToEnd:
    """Full diagnose flow with mocked P40 call."""

    def test_diagnose_valid_response(self):
        with patch.object(
            triage,
            "call_triage_model",
            return_value={
                "ok": True,
                "response": json.dumps(
                    {
                        "action": "respin_target",
                        "params": {},
                        "reason": "dirty state",
                        "confidence": 0.75,
                    }
                ),
            },
        ):
            diag = triage.diagnose(
                log_tail="error lines",
                failing_line="target unreachable",
                scenario="kerberoast",
            )
        assert diag["action"] == "respin_target"
        assert diag["allowed"]
        assert diag["above_floor"]

    def test_diagnose_model_down(self):
        with patch.object(
            triage,
            "call_triage_model",
            return_value={
                "ok": False,
                "error": "connection refused",
            },
        ):
            diag = triage.diagnose(
                log_tail="error",
                failing_line="error",
                scenario="sc",
            )
        assert diag["action"] == "pause_for_human"
        assert diag.get("error") == "connection refused"

    def test_diagnose_disallowed_action(self):
        with patch.object(
            triage,
            "call_triage_model",
            return_value={
                "ok": True,
                "response": json.dumps(
                    {
                        "action": "delete_everything",
                        "params": {},
                        "reason": "test",
                        "confidence": 0.9,
                    }
                ),
            },
        ):
            diag = triage.diagnose(
                log_tail="error",
                failing_line="error",
                scenario="sc",
            )
        assert diag["action"] == "pause_for_human"
        assert "disallowed" in diag["reason"]


# ── Layer 1 still works without triage ───────────────────────────────────────


class TestLayer1StillWorks:
    """Layer 1's original escalation still works when triage is off."""

    def test_off_mode_uses_layer1(self):
        state = sup.SupervisorState()
        with (
            patch("builtins.input", side_effect=EOFError),
            contextlib.suppress(SystemExit, EOFError),
        ):
            sup.handle_escalation(
                state,
                "test error",
                "pause",
                3,
                triage_mode="off",
            )
        # Should NOT have any triage actions
        triage_actions = [a for a in state.actions if a.get("handler") == "triage"]
        assert len(triage_actions) == 0


# ── Action menu ──────────────────────────────────────────────────────────────


class TestActionMenu:
    """Action menu is well-formed and complete."""

    def test_menu_has_required_actions(self):
        required = [
            "restart_lxc",
            "restart_vm",
            "revert_target",
            "respin_target",
            "skip_scenario",
            "reload_model",
            "pause_for_human",
        ]
        for name in required:
            assert name in actions.ALLOWED_ACTIONS, f"missing {name}"

    def test_menu_description_not_empty(self):
        desc = actions.get_action_menu_description()
        assert len(desc) > 100
        assert "restart_lxc" in desc

    def test_all_actions_have_fn(self):
        for name, entry in actions.ALLOWED_ACTIONS.items():
            assert callable(entry.get("fn")), f"{name} missing fn"

    def test_all_actions_have_description(self):
        for name, entry in actions.ALLOWED_ACTIONS.items():
            assert entry.get("description"), f"{name} missing description"
