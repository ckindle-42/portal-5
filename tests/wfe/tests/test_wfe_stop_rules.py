"""Arms stop on a failover at once, and on repeated instrument errors."""

from __future__ import annotations

import pytest

from tests.wfe import campaign


@pytest.fixture(autouse=True)
def _clean():
    campaign._RECENT.clear()
    yield
    campaign._RECENT.clear()


def test_failover_row_stops_the_arm_at_once():
    row = {"outcome": "BLOCKED", "notes": campaign.SEAT_BLOCK + "pipeline served x"}
    assert campaign.arm_stop_reason("a", row)


def test_three_consecutive_harness_errors_stop_the_arm():
    err = {"outcome": "HARNESS_ERROR", "notes": "boom"}
    assert campaign.arm_stop_reason("a", err) is None
    assert campaign.arm_stop_reason("a", err) is None
    assert "3 consecutive" in campaign.arm_stop_reason("a", err)


def test_a_model_outcome_resets_the_count_and_arms_are_independent():
    err, ok = {"outcome": "HARNESS_ERROR", "notes": ""}, {"outcome": "FAIL", "notes": ""}
    for r in (err, err, ok, err, err):
        assert campaign.arm_stop_reason("a", r) is None
    assert campaign.arm_stop_reason("b", err) is None
