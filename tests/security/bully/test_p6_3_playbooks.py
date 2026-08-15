"""P6.3 -- PLAY: learned-playbook lifecycle + canary/auto-revert (M8).

Hermetic (`tmp_path`, no network). Feeds C11 PLAY: CAS on the active
pointer; canary-failure auto-revert; absence-is-neutral; activation requires
operator actor.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully import playbooks
from portal.modules.security.core.bully.contracts import DecisionEvent
from portal.modules.security.core.bully.store import OperatorActorRequiredError, Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "hunt_state.db")
    yield s
    s.close()


def _emit(store, *, event_id, hunt_id, kind, rationale):
    store.record_decision(
        DecisionEvent(
            event_id=event_id,
            hunt_id=hunt_id,
            iteration_id=None,
            actor="system:test",
            kind=kind,
            subject_id="c1",
            rationale=rationale,
        )
    )


def _seed_trajectory(store, hunt_id="h1"):
    _emit(
        store,
        event_id=f"{hunt_id}-e1",
        hunt_id=hunt_id,
        kind="target_select",
        rationale="check lateral movement first",
    )
    _emit(
        store,
        event_id=f"{hunt_id}-e2",
        hunt_id=hunt_id,
        kind="grade",
        rationale="discriminator: wmic process create",
    )
    _emit(
        store,
        event_id=f"{hunt_id}-e3",
        hunt_id=hunt_id,
        kind="kill",
        rationale="scheduled backup, not an attack",
    )


def _to_awaiting_operator(store, playbook_id, *, canary_success=0.9):
    playbooks.mark_replay_validated(store, playbook_id, replay_result={"success_rate": 0.9})
    return playbooks.run_canary(store, playbook_id, canary_result={"success_rate": canary_success})


# ── absence is neutral ──────────────────────────────────────────────────


def test_for_hunt_returns_none_when_no_active_playbook(store):
    assert playbooks.for_hunt(store, "lateral_movement") is None


# ── draft -> replay -> canary -> awaiting_operator -> active ──────────────


def test_draft_update_builds_instruction_set_from_trajectory(store):
    _seed_trajectory(store)
    draft = playbooks.draft_update(store, "lateral_movement", "h1")
    assert draft["status"] == "draft"
    assert draft["instruction_set"]["recall_priorities"] == ["check lateral movement first"]
    assert draft["instruction_set"]["common_kills"] == ["scheduled backup, not an attack"]


def test_full_lifecycle_to_active_and_for_hunt(store):
    _seed_trajectory(store)
    draft = playbooks.draft_update(store, "lateral_movement", "h1")
    pid = draft["playbook_id"]
    result = _to_awaiting_operator(store, pid)
    assert result["status"] == "awaiting_operator"

    activation = playbooks.activate(store, pid, "operator:alice")
    assert activation["status"] == "active"

    active = playbooks.for_hunt(store, "lateral_movement")
    assert active["playbook_id"] == pid
    assert active["status"] == "active"


# ── canary-failure auto-revert ─────────────────────────────────────────────


def test_canary_failure_auto_reverts_with_recorded_cause(store):
    _seed_trajectory(store)
    draft = playbooks.draft_update(store, "lateral_movement", "h1")
    pid = draft["playbook_id"]
    playbooks.mark_replay_validated(store, pid, replay_result={"success_rate": 0.9})
    result = playbooks.run_canary(store, pid, canary_result={"success_rate": 0.1})
    assert result["status"] == "rolled_back"
    assert result["revert_cause"] is not None

    row = store.playbook_get(pid)
    assert row["status"] == "rolled_back"
    assert "below floor" in row["revert_cause"]
    # A rolled-back playbook never becomes active -- for_hunt still sees nothing.
    assert playbooks.for_hunt(store, "lateral_movement") is None


def test_replay_below_floor_stays_draft(store):
    _seed_trajectory(store)
    draft = playbooks.draft_update(store, "lateral_movement", "h1")
    pid = draft["playbook_id"]
    result = playbooks.mark_replay_validated(store, pid, replay_result={"success_rate": 0.1})
    assert result["status"] == "draft"
    assert result["passed"] is False


# ── activation: confirm-only + CAS on the active pointer ───────────────────


def test_activate_requires_operator_actor(store):
    _seed_trajectory(store)
    draft = playbooks.draft_update(store, "lateral_movement", "h1")
    pid = draft["playbook_id"]
    _to_awaiting_operator(store, pid)
    with pytest.raises(OperatorActorRequiredError):
        playbooks.activate(store, pid, "system:auto")


def test_activate_requires_awaiting_operator_status(store):
    _seed_trajectory(store)
    draft = playbooks.draft_update(store, "lateral_movement", "h1")
    pid = draft["playbook_id"]
    with pytest.raises(playbooks.PlaybookError):
        playbooks.activate(store, pid, "operator:alice")  # still 'draft'


def test_activation_cas_supersedes_prior_active_for_class(store):
    _seed_trajectory(store, hunt_id="h1")
    draft1 = playbooks.draft_update(store, "lateral_movement", "h1")
    pid1 = draft1["playbook_id"]
    _to_awaiting_operator(store, pid1)
    playbooks.activate(store, pid1, "operator:alice")
    assert playbooks.for_hunt(store, "lateral_movement")["playbook_id"] == pid1

    _seed_trajectory(store, hunt_id="h2")
    draft2 = playbooks.draft_update(store, "lateral_movement", "h2")
    pid2 = draft2["playbook_id"]
    _to_awaiting_operator(store, pid2)
    playbooks.activate(store, pid2, "operator:alice")

    active = playbooks.for_hunt(store, "lateral_movement")
    assert active["playbook_id"] == pid2
    prior = store.playbook_get(pid1)
    assert prior["status"] == "retired"
    assert prior["superseded_by"] == pid2
