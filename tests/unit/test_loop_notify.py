"""Unit tests for loop notification + checkpoint/resume."""

from __future__ import annotations

import json

from tests.benchmarks.bench_security.loop import (
    EngagementState,
    _write_checkpoint,
    resume_engagement,
)


class TestLoopNotifyEvents:
    def test_event_types_defined(self):
        from portal_pipeline.notifications.events import EventType

        assert EventType.ENGAGEMENT_ESCALATED.value == "engagement_escalated"
        assert EventType.ENGAGEMENT_STUCK.value == "engagement_stuck"
        assert EventType.ENGAGEMENT_COMPLETE.value == "engagement_complete"
        assert EventType.VALIDATION_ALERT.value == "validation_alert"


class TestCheckpointResume:
    def test_checkpoint_writes_and_roundtrips(self, monkeypatch, tmp_path):
        monkeypatch.setattr("tests.benchmarks.bench_security.loop.CHECKPOINT_DIR", tmp_path)
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
