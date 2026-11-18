"""Unit tests for loop notification + checkpoint/resume (TASK_SEC_LOOP_NOTIFY_V1)."""

from __future__ import annotations

from portal.modules.security.core.loop import (
    resume_engagement,
)

_BASE_PB = {
    "name": "test-pb",
    "scope": {"targets": ["10.10.11.50"]},
    "budget": {"max_iterations": 1, "max_wall_clock_sec": 600, "max_lab_actions": 10},
    "stop_conditions": [{"field": "never", "equals": "never"}],
    "phases": [{"id": "p1", "steps": [{"target": "10.10.11.50"}]}],
}


class TestLoopNotifyEvents:
    def test_event_types_defined(self) -> None:
        from portal.platform.inference.notifications.events import EventType

        assert EventType.ENGAGEMENT_ESCALATED.value == "engagement_escalated"
        assert EventType.ENGAGEMENT_STUCK.value == "engagement_stuck"
        assert EventType.ENGAGEMENT_COMPLETE.value == "engagement_complete"
        assert EventType.VALIDATION_ALERT.value == "validation_alert"

    def test_event_types_formatted_in_slack_and_telegram_and_pushover(self) -> None:
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


class TestCheckpointResume:
    def test_resume_not_found(self) -> None:
        result = resume_engagement("nonexistent-checkpoint-id")
        assert result["status"] == "error"
