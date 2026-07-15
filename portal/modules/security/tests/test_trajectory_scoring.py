"""Slice 2 gate tests (DESIGN §7): the measurement must be honest before it runs.

Proves on replayed/fixture trajectories: objective is verified by state (not
narration), synthetic-derived is NEVER PROVEN, and the verdict is deterministic.
"""

from __future__ import annotations

from portal.modules.security.core.trajectory_score import StepRecord, score_trajectory


def _landed(step_id, cap, synthetic=False, det="DETECTION_CONFIRMED"):
    return StepRecord(step_id, cap, "RED_LANDED", det, used_synthetic=synthetic)


DA_STATE = {"sessions": [{"host_role": "dc", "privilege": "da_equivalent", "verified": True}]}


def test_reached_and_clean_is_proven():
    v = score_trajectory("da_equivalent", [_landed("s1", "c1"), _landed("s2", "c2")], DA_STATE)
    assert v.verdict == "PROVEN" and v.objective_reached is True


def test_synthetic_step_never_proven():
    steps = [_landed("s1", "c1"), _landed("s2", "c2", synthetic=True)]
    v = score_trajectory("da_equivalent", steps, DA_STATE)
    assert v.objective_reached is True
    assert v.verdict != "PROVEN"  # the crown-jewel invariant
    assert v.verdict == "INDETERMINATE"


def test_objective_from_state_not_narration():
    # Steps claim success, but observed state does not show DA -> not reached.
    v = score_trajectory("da_equivalent", [_landed("s1", "c1")], {"sessions": []})
    assert v.objective_reached is False and v.verdict == "FAILED"


def test_unknown_objective_class_never_reached():
    v = score_trajectory("not_a_class", [_landed("s1", "c1")], DA_STATE)
    assert v.objective_reached is False and v.verdict == "FAILED"


def test_no_landed_steps_unavailable():
    stalled = [StepRecord("s1", "c1", "RED_EXECUTION_FAILED", "DETECTION_NOT_RUN")]
    v = score_trajectory("da_equivalent", stalled, DA_STATE)
    assert v.verdict == "UNAVAILABLE"


def test_deterministic():
    a = score_trajectory("da_equivalent", [_landed("s1", "c1")], DA_STATE)
    b = score_trajectory("da_equivalent", [_landed("s1", "c1")], DA_STATE)
    assert a.verdict == b.verdict == "PROVEN"
