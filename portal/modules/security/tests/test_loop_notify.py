"""Unit tests for loop notification + checkpoint/resume (TASK_SEC_LOOP_NOTIFY_V1)."""

from __future__ import annotations

import json
import time

from portal.modules.security.core import loop
from portal.modules.security.core.loop import (
    EngagementState,
    _write_checkpoint,
    resume_engagement,
)

_BASE_PB = {
    "name": "test-pb",
    "scope": {"targets": ["10.10.11.50"]},
    "budget": {"max_iterations": 1, "max_wall_clock_sec": 600, "max_lab_actions": 10},
    "stop_conditions": [{"field": "never", "equals": "never"}],
    "phases": [{"id": "p1", "steps": [{"target": "10.10.11.50"}]}],
}


def _fresh_state(eng_id: str = "test-eng") -> EngagementState:
    return EngagementState(
        engagement_id=eng_id, playbook_name="test-pb", started_at=time.monotonic()
    )


class TestLoopNotifyEvents:
    def test_event_types_defined(self):
        from portal.platform.inference.notifications.events import EventType

        assert EventType.ENGAGEMENT_ESCALATED.value == "engagement_escalated"
        assert EventType.ENGAGEMENT_STUCK.value == "engagement_stuck"
        assert EventType.ENGAGEMENT_COMPLETE.value == "engagement_complete"
        assert EventType.VALIDATION_ALERT.value == "validation_alert"

    def test_event_types_formatted_in_slack_and_telegram_and_pushover(self):
        from portal.platform.inference.notifications.events import AlertEvent, EventType

        for et in (
            EventType.ENGAGEMENT_ESCALATED,
            EventType.ENGAGEMENT_STUCK,
            EventType.ENGAGEMENT_COMPLETE,
            EventType.VALIDATION_ALERT,
        ):
            event = AlertEvent(type=et, message="test")
            assert "bell" not in event.format_slack()  # not the generic fallback
            assert "[ALERT]" not in event.format_telegram() or et == EventType.VALIDATION_ALERT
            assert event.format_pushover()


class TestLoopNotifyFiring:
    """Assert _notify is invoked at the right stop points with a monkeypatched
    fake — no real dispatcher/channel is exercised."""

    def test_escalation_fires_engagement_escalated_with_resume_cmd(self, monkeypatch):
        fired = []
        monkeypatch.setattr(
            loop,
            "_notify",
            lambda et, msg, **kw: fired.append((et, kw.get("resume_cmd"))),
        )
        pb = {
            **_BASE_PB,
            "budget": {"max_iterations": 10, "max_wall_clock_sec": 600, "max_lab_actions": 200},
            "phases": [{"id": "p1", "manual": True}],
        }
        state = _fresh_state()
        report = loop._run_loop(pb, state, [], False, None, False, False)
        assert report["stop_reason"].startswith("escalated:")
        assert fired
        event_type, resume_cmd = fired[-1]
        assert event_type == "ENGAGEMENT_ESCALATED"
        assert resume_cmd == "python3 -m portal.modules.security.core loop resume test-eng"

    def test_out_of_scope_step_target_escalates_and_notifies(self, monkeypatch):
        """Regression: _check_escalate's out_of_scope_action trigger previously
        did an exact list-membership check against state.escalations, but the
        step-execution path only ever appends the suffixed
        "out_of_scope_action:<target>" — so this trigger could never fire.
        Fixed to a startswith match; this proves the fix end-to-end."""
        fired = []
        monkeypatch.setattr(loop, "_notify", lambda et, msg, **kw: fired.append(et))
        pb = {
            **_BASE_PB,
            "budget": {"max_iterations": 10, "max_wall_clock_sec": 600, "max_lab_actions": 200},
            "scope": {"targets": ["10.10.11.50"]},
            "phases": [{"id": "p1", "steps": [{"target": "10.10.99.99"}]}],
            "escalate_when": ["out_of_scope_action"],
        }
        state = _fresh_state()
        report = loop._run_loop(pb, state, [], False, None, False, False)
        assert report["stop_reason"] == "escalated:out_of_scope_action"
        assert fired == ["ENGAGEMENT_ESCALATED"]

    def test_hard_cap_fires_engagement_stuck(self, monkeypatch):
        fired = []
        monkeypatch.setattr(loop, "_notify", lambda et, msg, **kw: fired.append(et))
        state = _fresh_state()
        report = loop._run_loop(_BASE_PB, state, [], False, None, False, False)
        assert report["stop_reason"] == "hard_cap"
        assert fired == ["ENGAGEMENT_STUCK"]

    def test_no_runnable_phase_fires_engagement_stuck(self, monkeypatch):
        fired = []
        monkeypatch.setattr(loop, "_notify", lambda et, msg, **kw: fired.append(et))
        pb = {
            **_BASE_PB,
            "budget": {"max_iterations": 50, "max_wall_clock_sec": 600, "max_lab_actions": 200},
            "phases": [{"id": "p1", "depends_on": ["never-exists"], "steps": []}],
        }
        state = _fresh_state()
        report = loop._run_loop(pb, state, [], False, None, False, False)
        assert report["stop_reason"] == "no_runnable_phase"
        assert fired == ["ENGAGEMENT_STUCK"]

    def test_goal_met_no_notify_by_default(self, monkeypatch):
        fired = []
        monkeypatch.setattr(loop, "_notify", lambda et, msg, **kw: fired.append(et))
        pb = {
            **_BASE_PB,
            "stop_conditions": [{"field": "done", "equals": True}],
        }
        state = _fresh_state()
        state.observations["done"] = True
        report = loop._run_loop(pb, state, [], False, None, False, False)
        assert report["stop_reason"] == "goal_met"
        assert fired == []

    def test_goal_met_notifies_when_opted_in(self, monkeypatch):
        fired = []
        monkeypatch.setattr(loop, "_notify", lambda et, msg, **kw: fired.append(et))
        pb = {
            **_BASE_PB,
            "stop_conditions": [{"field": "done", "equals": True}],
        }
        state = _fresh_state()
        state.observations["done"] = True
        report = loop._run_loop(pb, state, [], False, None, False, True)
        assert report["stop_reason"] == "goal_met"
        assert fired == ["ENGAGEMENT_COMPLETE"]

    def test_notify_failure_is_swallowed(self, monkeypatch):
        """A real _notify failure must never abort the engagement."""

        def _boom(*a, **kw):
            raise RuntimeError("dispatcher exploded")

        monkeypatch.setattr(loop, "_get_shared_dispatcher", _boom)
        monkeypatch.setattr(loop, "_loop_notify_enabled", lambda: True)
        state = _fresh_state()
        # Calling the REAL _notify (not monkeypatched away) must not raise.
        loop._notify("ENGAGEMENT_STUCK", "test", engagement_id=state.engagement_id)

    def test_notifications_disabled_is_a_noop(self, monkeypatch):
        calls = []
        monkeypatch.setattr(loop, "_loop_notify_enabled", lambda: False)
        monkeypatch.setattr(
            loop, "_get_shared_dispatcher", lambda: calls.append("should-not-be-called")
        )
        loop._notify("ENGAGEMENT_STUCK", "test", engagement_id="x")
        assert calls == []


class TestCheckpointResume:
    def test_checkpoint_writes_and_roundtrips(self, monkeypatch, tmp_path):
        monkeypatch.setattr("portal.modules.security.core.loop.CHECKPOINT_DIR", tmp_path)
        state = EngagementState(
            engagement_id="test-eng-001",
            playbook_name="test-playbook",
        )
        state.observations["open_ports"] = [True]
        state.completed_phases = ["recon"]
        state.iterations = 3
        path = _write_checkpoint(state, "test_pause")
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["engagement_id"] == "test-eng-001"
        assert data["checkpoint_reason"] == "test_pause"
        assert "methodology_version" in data

    def test_resume_not_found(self):
        result = resume_engagement("nonexistent-checkpoint-id")
        assert result["status"] == "error"
