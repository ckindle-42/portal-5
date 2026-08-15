"""P6.1 -- flywheel tables (playbooks/datasets/trained_models/roster) (M8).

Hermetic (`tmp_path`, no network). Proves the SS4.8 DB checks this migration
adds: one active playbook per class, one active model alias per role,
immutable dataset versions after release, immutable trained-model artifact
fields, roster content-keyed idempotency, and every activation/release/serve
path requiring an operator actor.
"""

from __future__ import annotations

import sqlite3

import pytest

from portal.modules.security.core.bully.store import OperatorActorRequiredError, Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "hunt_state.db")
    yield s
    s.close()


def test_migration_009_applies_and_is_idempotent(tmp_path):
    s1 = Store(tmp_path / "hunt_state.db")
    s1.close()
    s2 = Store(tmp_path / "hunt_state.db")  # re-open: migration already applied
    row = s2._conn.execute("SELECT version FROM schema_migrations WHERE version=9").fetchone()
    assert row is not None
    s2.close()


# ── playbooks: draft / activate / one-active-per-class ────────────────────


def test_playbook_draft_put_and_get_round_trips(store):
    version = store.playbook_draft_put(
        playbook_id="pb-1",
        scenario_class="lateral_movement",
        content_hash="h1",
        instruction_set={"recall_priorities": ["a"]},
        source_hunts=["hunt-1"],
    )
    assert version == 1
    row = store.playbook_get("pb-1")
    assert row["status"] == "draft"
    assert row["instruction_set"] == {"recall_priorities": ["a"]}


def test_playbook_activate_requires_operator_actor(store):
    store.playbook_draft_put(
        playbook_id="pb-1",
        scenario_class="lateral_movement",
        content_hash="h1",
        instruction_set={},
        source_hunts=[],
    )
    with pytest.raises(OperatorActorRequiredError):
        store.playbook_activate("pb-1", operator_actor="system:auto")


def test_playbook_activation_supersedes_prior_active(store):
    store.playbook_draft_put(
        playbook_id="pb-1",
        scenario_class="lateral_movement",
        content_hash="h1",
        instruction_set={},
        source_hunts=[],
    )
    store.playbook_activate("pb-1", operator_actor="operator:alice")
    store.playbook_draft_put(
        playbook_id="pb-2",
        scenario_class="lateral_movement",
        content_hash="h2",
        instruction_set={},
        source_hunts=[],
        supersedes="pb-1",
    )
    store.playbook_activate("pb-2", operator_actor="operator:alice")

    prior = store.playbook_get("pb-1")
    assert prior["status"] == "retired"
    assert prior["superseded_by"] == "pb-2"
    active = store.playbook_active_for_class("lateral_movement")
    assert active["playbook_id"] == "pb-2"


def test_one_active_playbook_per_class_db_backstop(store):
    """Even bypassing the application-level CAS, the DB refuses two rows in
    status='active' for the same scenario_class (SS4.8)."""
    store.playbook_draft_put(
        playbook_id="pb-1",
        scenario_class="lateral_movement",
        content_hash="h1",
        instruction_set={},
        source_hunts=[],
    )
    store.playbook_draft_put(
        playbook_id="pb-2",
        scenario_class="lateral_movement",
        content_hash="h2",
        instruction_set={},
        source_hunts=[],
    )
    store.playbook_activate("pb-1", operator_actor="operator:alice")
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute(
            "UPDATE playbooks SET status='active', activated_by='operator:alice' "
            "WHERE playbook_id='pb-2'"
        )


def test_playbook_canary_auto_revert_records_cause(store):
    store.playbook_draft_put(
        playbook_id="pb-1",
        scenario_class="lateral_movement",
        content_hash="h1",
        instruction_set={},
        source_hunts=[],
    )
    store.playbook_set_status("pb-1", "canary")
    store.playbook_set_status(
        "pb-1", "rolled_back", revert_cause="canary macro-F1 regressed -3.2pt"
    )
    row = store.playbook_get("pb-1")
    assert row["status"] == "rolled_back"
    assert "regressed" in row["revert_cause"]


# ── dataset_versions: build / release / immutability ───────────────────────


def test_dataset_version_put_is_content_keyed(store):
    ok1 = store.dataset_version_put(
        dataset_version="dv-1",
        role="hunter",
        window={"w": 1},
        counts={"n": 10},
        split_manifest={},
        dedup_leakage_report={},
        replay_mix_sources=[],
        manifest_path="/tmp/m.json",
    )
    ok2 = store.dataset_version_put(
        dataset_version="dv-1",
        role="hunter",
        window={"w": 1},
        counts={"n": 10},
        split_manifest={},
        dedup_leakage_report={},
        replay_mix_sources=[],
        manifest_path="/tmp/m.json",
    )
    assert ok1 is True
    assert ok2 is False  # same content hash -> no-op, not a duplicate


def test_dataset_version_release_requires_operator_actor(store):
    store.dataset_version_put(
        dataset_version="dv-1",
        role="hunter",
        window={},
        counts={},
        split_manifest={},
        dedup_leakage_report={},
        replay_mix_sources=[],
        manifest_path=None,
    )
    with pytest.raises(OperatorActorRequiredError):
        store.dataset_version_release("dv-1", operator_actor="system:auto", approval_ref="ref-1")


def test_dataset_version_immutable_after_release(store):
    store.dataset_version_put(
        dataset_version="dv-1",
        role="hunter",
        window={},
        counts={},
        split_manifest={},
        dedup_leakage_report={},
        replay_mix_sources=[],
        manifest_path=None,
    )
    store.dataset_version_release("dv-1", operator_actor="operator:alice", approval_ref="ref-1")
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute(
            "UPDATE dataset_versions SET counts_json='{\"n\":999}' WHERE dataset_version='dv-1'"
        )


# ── trained_models + model_aliases: immutability / operator-only serve ────


def _make_dataset(store, dv="dv-1"):
    store.dataset_version_put(
        dataset_version=dv,
        role="hunter",
        window={},
        counts={},
        split_manifest={},
        dedup_leakage_report={},
        replay_mix_sources=[],
        manifest_path=None,
    )


def test_trained_model_artifact_fields_immutable(store):
    _make_dataset(store)
    store.trained_model_put(
        model_tag="mt-1",
        role="hunter",
        base_model="base:1",
        base_digest="d1",
        dataset_version="dv-1",
        seed=1,
        hyperparams={"lr": 1e-4},
        toolchain_versions={},
        acceptance_policy_version="v1",
        provenance={},
    )
    store.trained_model_set_reports("mt-1", gguf_path="/tmp/a.gguf", gguf_hash="hash1")
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute("UPDATE trained_models SET base_model='base:2' WHERE model_tag='mt-1'")
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute(
            "UPDATE trained_models SET gguf_path='/tmp/b.gguf' WHERE model_tag='mt-1'"
        )


def test_trained_model_serve_requires_operator_actor(store):
    _make_dataset(store)
    store.trained_model_put(
        model_tag="mt-1",
        role="hunter",
        base_model="base:1",
        base_digest=None,
        dataset_version="dv-1",
        seed=1,
        hyperparams={},
        toolchain_versions={},
        acceptance_policy_version="v1",
        provenance={},
    )
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute("UPDATE trained_models SET verdict='served' WHERE model_tag='mt-1'")
    store.trained_model_set_verdict("mt-1", "served", operator_actor="operator:alice")
    assert store.trained_model_get("mt-1")["verdict"] == "served"


def test_trained_model_non_gain_verdict_never_requires_operator(store):
    """MASTER SS8: 'training failure -> active alias unchanged' -- recording
    a no-gain/failed verdict is a system action, not an operator gate."""
    _make_dataset(store)
    store.trained_model_put(
        model_tag="mt-1",
        role="hunter",
        base_model="base:1",
        base_digest=None,
        dataset_version="dv-1",
        seed=1,
        hyperparams={},
        toolchain_versions={},
        acceptance_policy_version="v1",
        provenance={},
    )
    store.trained_model_set_verdict("mt-1", "declined_no_gain")
    assert store.trained_model_get("mt-1")["verdict"] == "declined_no_gain"


def test_model_alias_promote_and_rollback_is_atomic_repoint(store):
    _make_dataset(store)
    store.trained_model_put(
        model_tag="mt-1",
        role="hunter",
        base_model="base:1",
        base_digest=None,
        dataset_version="dv-1",
        seed=1,
        hyperparams={},
        toolchain_versions={},
        acceptance_policy_version="v1",
        provenance={},
    )
    store.trained_model_put(
        model_tag="mt-2",
        role="hunter",
        base_model="base:1",
        base_digest=None,
        dataset_version="dv-1",
        seed=2,
        hyperparams={},
        toolchain_versions={},
        acceptance_policy_version="v1",
        provenance={},
    )
    store.model_alias_promote("hunter", "mt-1", operator_actor="operator:alice")
    store.model_alias_promote("hunter", "mt-2", operator_actor="operator:alice")
    assert store.model_alias_get("hunter")["model_tag"] == "mt-2"

    target = store.model_alias_rollback(
        "hunter", operator_actor="operator:alice", reason="canary regression"
    )
    assert target == "mt-1"
    assert store.model_alias_get("hunter")["model_tag"] == "mt-1"


def test_model_alias_promote_requires_operator_actor(store):
    _make_dataset(store)
    store.trained_model_put(
        model_tag="mt-1",
        role="hunter",
        base_model="base:1",
        base_digest=None,
        dataset_version="dv-1",
        seed=1,
        hyperparams={},
        toolchain_versions={},
        acceptance_policy_version="v1",
        provenance={},
    )
    with pytest.raises(OperatorActorRequiredError):
        store.model_alias_promote("hunter", "mt-1", operator_actor="system:auto")


# ── roster_records: content-keyed idempotency + operator-only activation ──


def _roster_kwargs(**overrides):
    base = {
        "record_id": "rr-1",
        "seat_id": "seat-a",
        "window": {"w": 1},
        "independence_family": "fam1",
        "capability_suite_version": "v1",
        "citation_validity": 0.9,
        "objection_precision": 0.8,
        "objection_recall": 0.7,
        "cousin_call_correctness": 0.6,
        "abstention_quality": 0.5,
        "latency_cost": {},
        "eligibility": "eligible",
        "advisory_weight": 1.0,
        "rationale": {},
        "content_key": "ck-1",
    }
    base.update(overrides)
    return base


def test_roster_record_put_is_content_keyed_idempotent(store):
    rid1 = store.roster_record_put(**_roster_kwargs())
    rid2 = store.roster_record_put(**_roster_kwargs(record_id="rr-2"))
    assert rid1 == "rr-1"
    assert rid2 is None  # same content_key -> no-op


def test_roster_advisory_weight_bounded(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.roster_record_put(**_roster_kwargs(advisory_weight=3.0))


def test_roster_record_activate_requires_operator_actor(store):
    store.roster_record_put(**_roster_kwargs())
    with pytest.raises(OperatorActorRequiredError):
        store.roster_record_activate("rr-1", operator_actor="system:auto")


def test_roster_record_activation_supersedes_prior_active_for_seat(store):
    store.roster_record_put(**_roster_kwargs())
    store.roster_record_activate("rr-1", operator_actor="operator:alice")
    store.roster_record_put(**_roster_kwargs(record_id="rr-2", content_key="ck-2"))
    store.roster_record_activate("rr-2", operator_actor="operator:alice")

    prior = store.roster_record_get("rr-1")
    assert prior["state"] == "proposed"
    assert prior["superseded_by"] == "rr-2"
    active = store.roster_active_for_seat("seat-a")
    assert active["record_id"] == "rr-2"
