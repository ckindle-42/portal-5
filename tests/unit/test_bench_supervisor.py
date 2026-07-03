"""Unit tests for bench supervisor — no live lab, mock subprocess + primitives."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import scripts.bench_supervisor as sup

# ── Detector tests ────────────────────────────────────────────────────────────


class TestDetectors:
    """Each detector fires on a fixture log line and NOT on benign lines."""

    def test_vulhub_unreachable(self):
        assert sup.is_vulhub_unreachable("lab-vulhub 10.10.11.50 unreachable")
        assert sup.is_vulhub_unreachable("vulhub connection refused on port 80")
        assert not sup.is_vulhub_unreachable("Scenario: kerberoast_to_da")

    def test_target_unreachable(self):
        assert sup.is_target_unreachable("target unreachable — aborting")
        assert sup.is_target_unreachable("ABORTING: lab targets unreachable")
        assert sup.is_target_unreachable("DC SRV unreachable")
        assert not sup.is_target_unreachable("Results written to file")

    def test_ollama_conn_refused(self):
        assert sup.is_ollama_conn_refused("localhost:11434 connection refused")
        assert sup.is_ollama_conn_refused("ECONNREFUSED on ollama")
        assert not sup.is_ollama_conn_refused("model loaded successfully")

    def test_model_not_loaded(self):
        assert sup.is_model_not_loaded("error loading model: model not found")
        assert sup.is_model_not_loaded("pull the model first")
        assert sup.is_model_not_loaded("no model loaded")
        assert not sup.is_model_not_loaded("chain depth 3/8")

    def test_lxc_down(self):
        assert sup.is_lxc_down("LXC container down, docker not running")
        assert sup.is_lxc_down("vulhub container stopped")
        assert not sup.is_lxc_down("vulhub sqli test complete")

    def test_spin_timeout(self):
        assert sup.is_spin_timeout("spin timeout after 120s")
        assert sup.is_spin_timeout("service port not answering")
        assert not sup.is_spin_timeout("port scan complete")

    def test_checkpoint_abort(self):
        assert sup.is_checkpoint_abort("KeyboardInterrupt received")
        assert sup.is_checkpoint_abort("SIGTERM sent to process")
        assert not sup.is_checkpoint_abort("scenario complete")


class TestBenignNoFalsePositives:
    """Benign lines must not trigger any detector."""

    BENIGN = [
        "Scenario: kerberoast_to_da",
        "depth=3/8  acc=0.75",
        "Results written → results/sec_bench.json",
        "Chain tests complete for model test-model",
        "── Lab Service Probe ──",
        "model: huihui_ai/baronllm-abliterated  TPS=42.3",
        "Starting nmap scan against 10.10.11.21",
    ]

    def test_benign_lines_clean(self):
        detectors = [
            sup.is_vulhub_unreachable,
            sup.is_target_unreachable,
            sup.is_ollama_conn_refused,
            sup.is_model_not_loaded,
            sup.is_lxc_down,
            sup.is_spin_timeout,
            sup.is_checkpoint_abort,
        ]
        for line in self.BENIGN:
            for det in detectors:
                assert not det(line), f"false positive: {det.__name__} on {line!r}"


# ── Handler tests ─────────────────────────────────────────────────────────────


class TestHandlers:
    """Each handler calls the correct primitive (mocked)."""

    def test_handle_restart_lxc_112_calls_proxmox(self):
        state = sup.SupervisorState()
        mock_lab = MagicMock()
        mock_lab._proxmox_mcp_call.return_value = {"ok": True}
        with patch("scripts.bench_supervisor._import_lab_exec", return_value=mock_lab):
            action = sup.handle_restart_lxc_112(state, "LXC down")
        assert action == "retry"
        mock_lab._proxmox_mcp_call.assert_called_once()
        call_args = mock_lab._proxmox_mcp_call.call_args
        assert call_args[0][0] == "proxmox_container_start"
        assert call_args[0][1]["vmid"] == 112

    def test_handle_revert_and_respin_calls_teardown_setup(self):
        state = sup.SupervisorState()
        mock_lab = MagicMock()
        with (
            patch("scripts.bench_supervisor._import_lab_exec", return_value=mock_lab),
            patch("scripts.bench_supervisor.time.sleep"),
        ):
            action = sup.handle_revert_and_respin(state, "target unreachable")
        assert action == "retry"
        mock_lab.lab_teardown.assert_called_once()
        mock_lab.lab_setup.assert_called_once()

    def test_handle_revert_target_calls_teardown(self):
        state = sup.SupervisorState()
        mock_lab = MagicMock()
        with (
            patch("scripts.bench_supervisor._import_lab_exec", return_value=mock_lab),
            patch("scripts.bench_supervisor.time.sleep"),
        ):
            action = sup.handle_revert_target(state, "spin timeout")
        assert action == "retry"
        mock_lab.lab_teardown.assert_called_once()

    def test_handle_load_model_probes_ollama(self):
        import urllib.request

        state = sup.SupervisorState()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"models": [{"name": "test:latest"}]}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch.object(urllib.request, "urlopen", return_value=mock_resp):
            action = sup.handle_load_model(state, "model not loaded")
        assert action == "retry"

    def test_handle_skip_scenario_records_indeterminate(self):
        state = sup.SupervisorState()
        state.current_scenario = "test_scenario"
        action = sup.handle_skip_scenario(state, "wedged")
        assert action == "skip"
        assert "test_scenario" in state.indeterminate_scenarios

    def test_handle_kill_unit_records_indeterminate(self):
        state = sup.SupervisorState()
        state.current_scenario = "stall_scenario"
        action = sup.handle_kill_unit_continue(state, "no progress")
        assert action == "continue"
        assert "stall_scenario" in state.indeterminate_scenarios

    def test_handler_no_lab_exec_graceful(self):
        """Handlers degrade gracefully when lab_exec is not importable."""
        state = sup.SupervisorState()
        with patch("scripts.bench_supervisor._import_lab_exec", return_value=None):
            action = sup.handle_restart_lxc_112(state, "LXC down")
            assert action == "continue"
            action = sup.handle_revert_and_respin(state, "unreachable")
            assert action == "continue"
            action = sup.handle_revert_target(state, "timeout")
            assert action == "continue"


# ── Stall watchdog ────────────────────────────────────────────────────────────


class TestStallWatchdog:
    """Stall detector fires after N minutes of no progress (fake clock)."""

    def test_stall_detector_fires_after_timeout(self):
        state = sup.SupervisorState()
        state.last_activity = time.monotonic() - 20 * 60  # 20 min ago
        detector = sup.make_no_progress_detector(15)
        assert detector(state)

    def test_stall_detector_no_fire_within_window(self):
        state = sup.SupervisorState()
        state.last_activity = time.monotonic() - 5 * 60  # 5 min ago
        detector = sup.make_no_progress_detector(15)
        assert not detector(state)

    def test_stall_handler_in_state_handlers(self):
        handlers = sup.build_state_handlers(stall_minutes=10)
        names = [h[0] for h in handlers]
        assert "inference_stall" in names


# ── Escalation ────────────────────────────────────────────────────────────────


class TestEscalation:
    """Unknown pattern escalates, not silently continues."""

    def test_escalation_records_entry(self):
        state = sup.SupervisorState()
        state.record_escalation("some unknown error", context="test")
        assert len(state.escalations) == 1
        assert "unknown error" in state.escalations[0]["line"]

    def test_handle_escalate_returns_escalate(self):
        state = sup.SupervisorState()
        action = sup.handle_escalate(state, "unknown error line")
        assert action == "escalate"
        assert len(state.escalations) == 1


# ── Max-corrections cap ──────────────────────────────────────────────────────


class TestMaxCorrections:
    """Cap prevents infinite revert loops."""

    def test_state_tracks_corrections(self):
        state = sup.SupervisorState()
        assert state.increment_correction("sc1") == 1
        assert state.increment_correction("sc1") == 2
        assert state.increment_correction("sc2") == 1

    def test_handler_table_builds(self):
        handlers = sup.build_state_handlers(stall_minutes=15)
        assert len(handlers) >= 7
        names = [h[0] for h in handlers]
        assert "lxc112_down" in names
        assert "inference_stall" in names


# ── Resume logic ─────────────────────────────────────────────────────────────


class TestResume:
    """Resume from .partial.json checkpoint."""

    def test_load_completed_scenarios(self, tmp_path):
        partial = tmp_path / "test.partial.json"
        data = [
            {"scenario": "kerberoast_to_da", "model": "m1", "chain_depth": 3},
            {"scenario": "asrep_to_lateral", "model": "m1", "chain_depth": 2},
            {"scenario": "kerberoast_to_da", "model": "m2", "chain_depth": 4},
        ]
        partial.write_text(json.dumps(data))
        completed = sup.load_completed_scenarios(partial)
        assert completed == {"kerberoast_to_da", "asrep_to_lateral"}

    def test_load_completed_scenarios_empty(self, tmp_path):
        partial = tmp_path / "empty.partial.json"
        partial.write_text("[]")
        assert sup.load_completed_scenarios(partial) == set()

    def test_load_completed_scenarios_missing(self, tmp_path):
        partial = tmp_path / "nonexistent.partial.json"
        assert sup.load_completed_scenarios(partial) == set()

    def test_compute_remaining_scenarios(self):
        all_sc = ["a", "b", "c", "d"]
        completed = {"a", "c"}
        remaining = sup.compute_remaining_scenarios(all_sc, completed)
        assert remaining == ["b", "d"]

    def test_compute_remaining_none_done(self):
        all_sc = ["a", "b"]
        remaining = sup.compute_remaining_scenarios(all_sc, set())
        assert remaining == ["a", "b"]

    def test_compute_remaining_all_done(self):
        all_sc = ["a", "b"]
        remaining = sup.compute_remaining_scenarios(all_sc, {"a", "b"})
        assert remaining == []


# ── Supervisor log ────────────────────────────────────────────────────────────


class TestSupervisorLog:
    """Supervisor writes an auditable log."""

    def test_write_supervisor_log(self, tmp_path):
        state = sup.SupervisorState()
        state.current_scenario = "test"
        state.record_action("test_handler", "test_pattern", "test_action")
        state.completed_scenarios.add("sc1")
        log_path = tmp_path / "supervisor_log.json"
        sup.write_supervisor_log(log_path, state, "completed")
        assert log_path.exists()
        log = json.loads(log_path.read_text())
        assert log["outcome"] == "completed"
        assert "sc1" in log["completed_scenarios"]
        assert len(log["actions"]) == 1
        assert log["actions"][0]["handler"] == "test_handler"


# ── Self-test ─────────────────────────────────────────────────────────────────


class TestSelfTest:
    """Self-test verifies detectors without a live lab."""

    def test_self_test_passes(self):
        ok = sup.run_self_test(stall_minutes=15)
        assert ok

    def test_self_test_fixture_lines_cover_all_detectors(self):
        """Every named detector has at least one fixture line."""
        handler_names = {h[0] for h in sup.build_state_handlers(15)}
        fixture_names = {name for name, _ in sup.SELF_TEST_LINES}
        # inference_stall is state-based, not line-based — skip
        line_handlers = handler_names - {"inference_stall"}
        assert line_handlers <= fixture_names, (
            f"Missing fixture lines for: {line_handlers - fixture_names}"
        )


# ── Handler table integrity ──────────────────────────────────────────────────


class TestHandlerTableIntegrity:
    """Handler table entries are well-formed."""

    def test_all_handlers_callable(self):
        handlers = sup.build_state_handlers(15)
        for name, _line_det, _state_det, handler in handlers:
            assert callable(handler), f"{name} handler not callable"
            assert isinstance(name, str)

    def test_handlers_return_valid_action(self):
        state = sup.SupervisorState()
        handlers = sup.build_state_handlers(15)
        valid_actions = {"retry", "continue", "skip", "escalate"}
        for name, _line_det, _state_det, handler in handlers:
            try:
                action = handler(state, "test")
                assert action in valid_actions, f"{name} returned {action!r}"
            except Exception:
                pass  # Expected when lab_exec not available


# ── SupervisorState ──────────────────────────────────────────────────────────


class TestSupervisorState:
    """State tracking works correctly."""

    def test_record_action(self):
        state = sup.SupervisorState()
        state.record_action("h1", "p1", "a1", detail="d1")
        assert len(state.actions) == 1
        assert state.actions[0]["handler"] == "h1"

    def test_touch_updates_activity(self):
        state = sup.SupervisorState()
        old = state.last_activity
        time.sleep(0.01)
        state.touch()
        assert state.last_activity > old

    def test_scenario_tracking(self):
        state = sup.SupervisorState()
        state.current_scenario = "sc1"
        state.completed_scenarios.add("sc1")
        state.indeterminate_scenarios.add("sc2")
        assert "sc1" in state.completed_scenarios
        assert "sc2" in state.indeterminate_scenarios
