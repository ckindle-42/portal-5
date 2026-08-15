"""P5.1 -- detection-proposal lifecycle tables + KNOWN_COVERED check (M7).

Hermetic (`tmp_path`, no network). Feeds D1: a proof-leg failure blocks the
package at the DB level; rebuild produces a superseding version; rejection
requires a rationale; deployment is operator-only and deduplicates;
KNOWN_COVERED is refused without a deployment + a passed post-deploy replay.
"""

from __future__ import annotations

import sqlite3

import pytest

from portal.modules.security.core.bully import contracts
from portal.modules.security.core.bully.contracts import Decomposition
from portal.modules.security.core.bully.store import (
    OperatorActorRequiredError,
    Store,
)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "hunt_state.db")
    yield s
    s.close()


def _make_candidate(store, *, candidate_id="cand-1", hunt_id="hunt-1"):
    store.hunt_create(
        hunt_id=hunt_id,
        objective="prove cousin discovery",
        neighborhood_scope="lab-default",
        authorization_ref="auth-1",
        config_version="cfg-1",
        role_snapshot={},
        budgets={},
    )
    sig_id = f"sig-{candidate_id}"

    class _Sig:
        def __init__(self, signature_id):
            self.signature_id = signature_id
            self.episode_ref = f"ep-{signature_id}"
            self.signature_algorithm_version = "v1"
            self.input_manifest_hash = f"hash-{signature_id}"
            self.canonical_fingerprint = "fp"
            self.action_sequence = []
            self.event_graph = {}
            self.parameter_families = {}
            self.context_topology = {}
            self.artifacts = {}
            self.attack_mappings = []
            self.telemetry_shape = {}
            self.detector_outcomes = {}
            self.evidence_manifest_id = None
            self.completeness = 1.0
            self.created_at = 0.0

    store.record_signature(_Sig(sig_id))
    assessment_id = f"assess-{candidate_id}"
    store.record_cousin(
        contracts.CousinAssessment(
            assessment_id=assessment_id,
            subject_signature_id=sig_id,
            reference_signature_id=None,
            candidate_set_id="cs-1",
            decomposition=Decomposition(
                behavior=0.1, telemetry=0.1, semantic=0.1, attack=0.1, context=0.1
            ),
            composite=0.1,
            relationship="SAME",
            nonsemantic_channels=1,
            vetoes=[],
            defense_response="COVERED",
            nearest_knowns=[],
            confidence=0.9,
            completeness=1.0,
            algorithm_version="v1",
            thresholds_version="v1",
        )
    )
    store.candidate_create(
        candidate_id=candidate_id,
        hunt_id=hunt_id,
        assessment_id=assessment_id,
        evidence_manifest_id=None,
        gate_policy_version="bin-gates-v1",
    )
    return candidate_id, hunt_id


# ── migration ────────────────────────────────────────────────────────────


def test_migration_008_applies_and_is_idempotent(tmp_path):
    s1 = Store(tmp_path / "hunt_state.db")
    s1.close()
    s2 = Store(tmp_path / "hunt_state.db")  # re-open: migration already applied
    row = s2._conn.execute("SELECT version FROM schema_migrations WHERE version=8").fetchone()
    assert row is not None
    s2.close()


# ── detection_proposals: create / supersede ────────────────────────────────


def test_detection_proposal_put_and_get_round_trips(store):
    candidate_id, hunt_id = _make_candidate(store)
    version = store.detection_proposal_put(
        proposal_id="prop-1",
        candidate_id=candidate_id,
        hunt_id=hunt_id,
        family="T1558.003",
        package={"spl": "search index=x"},
        content_hash="abc",
    )
    assert version == 1
    row = store.detection_proposal_get("prop-1")
    assert row["status"] == "draft"
    assert row["package"] == {"spl": "search index=x"}
    assert row["fires_on_attack"] == 0


def test_rebuild_produces_superseding_version(store):
    candidate_id, hunt_id = _make_candidate(store)
    store.detection_proposal_put(
        proposal_id="prop-1",
        candidate_id=candidate_id,
        hunt_id=hunt_id,
        family="T1558.003",
        package={},
        content_hash="v1",
    )
    version = store.detection_proposal_put(
        proposal_id="prop-2",
        candidate_id=candidate_id,
        hunt_id=hunt_id,
        family="T1558.003",
        package={},
        content_hash="v2",
        supersedes="prop-1",
    )
    assert version == 2
    prior = store.detection_proposal_get("prop-1")
    assert prior["superseded_by"] == "prop-2"
    latest = store.detection_proposal_latest_for_candidate(candidate_id)
    assert latest["proposal_id"] == "prop-2"


# ── proof-leg failure blocks the package (DB-level backstop) ──────────────


def test_deploy_without_all_proof_legs_blocked_at_db_level(store):
    candidate_id, hunt_id = _make_candidate(store)
    store.detection_proposal_put(
        proposal_id="prop-1",
        candidate_id=candidate_id,
        hunt_id=hunt_id,
        family="T1558.003",
        package={},
        content_hash="v1",
    )
    store.detection_proposal_set_proof_legs(
        "prop-1",
        fires_on_attack=True,
        quiet_on_benign=True,
        no_regression=False,  # one leg still failing
        proof_legs={"no_regression": {"outcome": "fail"}},
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.detection_proposal_set_status("prop-1", "deployed")


def test_deploy_with_all_proof_legs_passing_succeeds(store):
    candidate_id, hunt_id = _make_candidate(store)
    store.detection_proposal_put(
        proposal_id="prop-1",
        candidate_id=candidate_id,
        hunt_id=hunt_id,
        family="T1558.003",
        package={},
        content_hash="v1",
    )
    store.detection_proposal_set_proof_legs(
        "prop-1",
        fires_on_attack=True,
        quiet_on_benign=True,
        no_regression=True,
        proof_legs={"all": "pass"},
    )
    store.detection_proposal_set_status("prop-1", "deployed")
    assert store.detection_proposal_get("prop-1")["status"] == "deployed"


def test_reject_without_rationale_blocked_at_db_level(store):
    candidate_id, hunt_id = _make_candidate(store)
    store.detection_proposal_put(
        proposal_id="prop-1",
        candidate_id=candidate_id,
        hunt_id=hunt_id,
        family="T1558.003",
        package={},
        content_hash="v1",
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.detection_proposal_set_status("prop-1", "rejected")


def test_reject_with_rationale_succeeds(store):
    candidate_id, hunt_id = _make_candidate(store)
    store.detection_proposal_put(
        proposal_id="prop-1",
        candidate_id=candidate_id,
        hunt_id=hunt_id,
        family="T1558.003",
        package={},
        content_hash="v1",
    )
    store.detection_proposal_set_status("prop-1", "rejected", rationale="benign automation")
    row = store.detection_proposal_get("prop-1")
    assert row["status"] == "rejected"
    assert row["rationale"] == "benign automation"


# ── deployments: operator-only + dedup ─────────────────────────────────────


def test_deployment_put_requires_operator_actor(store):
    candidate_id, hunt_id = _make_candidate(store)
    store.detection_proposal_put(
        proposal_id="prop-1",
        candidate_id=candidate_id,
        hunt_id=hunt_id,
        family="T1558.003",
        package={},
        content_hash="v1",
    )
    with pytest.raises(OperatorActorRequiredError):
        store.deployment_put(
            deployment_id="dep-1",
            proposal_id="prop-1",
            spl_commit_ref="deadbeef",
            deployed_by="system:auto",
            receipt_hash="h1",
        )


def test_deployment_put_deduplicates_by_proposal_and_commit(store):
    candidate_id, hunt_id = _make_candidate(store)
    store.detection_proposal_put(
        proposal_id="prop-1",
        candidate_id=candidate_id,
        hunt_id=hunt_id,
        family="T1558.003",
        package={},
        content_hash="v1",
    )
    d1 = store.deployment_put(
        deployment_id="dep-1",
        proposal_id="prop-1",
        spl_commit_ref="deadbeef",
        deployed_by="operator:alice",
        receipt_hash="h1",
    )
    d2 = store.deployment_put(
        deployment_id="dep-2",  # ignored -- same (proposal_id, spl_commit_ref) dedups
        proposal_id="prop-1",
        spl_commit_ref="deadbeef",
        deployed_by="operator:alice",
        receipt_hash="h1",
    )
    assert d1 == d2 == "dep-1"


# ── KNOWN_COVERED requires deployment + passed post-deploy replay ─────────


def _deploy(store, candidate_id, hunt_id, *, proposal_id="prop-1", deployment_id="dep-1"):
    store.detection_proposal_put(
        proposal_id=proposal_id,
        candidate_id=candidate_id,
        hunt_id=hunt_id,
        family="T1558.003",
        package={},
        content_hash="v1",
    )
    return store.deployment_put(
        deployment_id=deployment_id,
        proposal_id=proposal_id,
        spl_commit_ref="deadbeef",
        deployed_by="operator:alice",
        receipt_hash="h1",
    )


def test_known_covered_without_deployment_refused(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.update_known_state(
            "cell-T1558.003", "known_covered", {"episode_ref": "ep-1"}, hunt_id="hunt-1"
        )


def test_known_covered_with_deployment_but_no_replay_refused_at_db_level(store):
    candidate_id, hunt_id = _make_candidate(store)
    deployment_id = _deploy(store, candidate_id, hunt_id)
    with pytest.raises(sqlite3.IntegrityError):
        store.update_known_state(
            "cell-T1558.003",
            "known_covered",
            {"episode_ref": "ep-1"},
            hunt_id=hunt_id,
            deployment_id=deployment_id,
        )


def test_known_covered_with_failed_replay_refused_at_db_level(store):
    candidate_id, hunt_id = _make_candidate(store)
    deployment_id = _deploy(store, candidate_id, hunt_id)
    store.replay_validation_put(
        validation_id="val-1", deployment_id=deployment_id, passed=False, detail="fired on benign"
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.update_known_state(
            "cell-T1558.003",
            "known_covered",
            {"episode_ref": "ep-1"},
            hunt_id=hunt_id,
            deployment_id=deployment_id,
        )


def test_known_covered_with_passed_replay_succeeds(store):
    candidate_id, hunt_id = _make_candidate(store)
    deployment_id = _deploy(store, candidate_id, hunt_id)
    store.replay_validation_put(
        validation_id="val-1", deployment_id=deployment_id, passed=True, detail="clean"
    )
    entry_id = store.update_known_state(
        "cell-T1558.003",
        "known_covered",
        {"episode_ref": "ep-1"},
        hunt_id=hunt_id,
        deployment_id=deployment_id,
    )
    assert entry_id.startswith("ks-")
