"""Regression coverage for test-only security runtime writes."""

from __future__ import annotations

from portal.modules.security.core import field_journal, loop


def test_journal_and_checkpoint_writes_use_test_sandbox(isolated_security_writes):
    journal_path = field_journal.write_entry(
        {
            "ts": "2026-07-29T00:00:00Z",
            "scenario_category": "test",
            "engagement_id": "isolated",
        }
    )
    checkpoint_path = loop._write_checkpoint(
        loop.EngagementState(
            engagement_id="isolated",
            playbook_name="test",
        ),
        "test",
    )

    assert journal_path.parent == isolated_security_writes["journal"]
    assert checkpoint_path.parent == isolated_security_writes["checkpoints"]
