"""P2.1 -- bin/council/queue tables + promotion constraints.

Hermetic (`tmp_path`, no network). FINAL_VALIDATION C1 ("bin state machine")
setup + C7 gate-chain setup: illegal skip-a-gate transition rejected,
synthetic-blocks-G0 constraint, evidence-change invalidation, queue actor
check.
"""

from __future__ import annotations

import sqlite3

import pytest

from portal.modules.security.core.bully import contracts
from portal.modules.security.core.bully.contracts import Decomposition
from portal.modules.security.core.bully.store import (
    IllegalBinTransitionError,
    OperatorActorRequiredError,
    Store,
    StoreError,
)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "hunt_state.db")
    yield s
    s.close()


def _make_hunt(store, hunt_id="hunt-1"):
    store.hunt_create(
        hunt_id=hunt_id,
        objective="prove cousin discovery",
        neighborhood_scope="lab-default",
        authorization_ref="auth-1",
        config_version="cfg-1",
        role_snapshot={"investigator": "some-tag"},
        budgets={"max_iterations": 5},
    )


def _make_assessment(store, assessment_id="assess-1", signature_id="sig-1"):
    store.record_signature(
        _sig(signature_id),
    )
    store.record_cousin(
        contracts.CousinAssessment(
            assessment_id=assessment_id,
            subject_signature_id=signature_id,
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
    return assessment_id


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


def _sig(signature_id):
    return _Sig(signature_id)


def _make_candidate(store, *, hunt_id="hunt-1", candidate_id="cand-1", evidence_manifest_id=None):
    _make_hunt(store, hunt_id)
    assessment_id = _make_assessment(
        store, assessment_id=f"assess-{candidate_id}", signature_id=f"sig-{candidate_id}"
    )
    store.candidate_create(
        candidate_id=candidate_id,
        hunt_id=hunt_id,
        assessment_id=assessment_id,
        evidence_manifest_id=evidence_manifest_id,
        gate_policy_version="bin-gates-v1",
    )
    return candidate_id


def _observed_manifest(store, manifest_id="em-observed"):
    store.evidence_manifest_put(
        manifest_id=manifest_id,
        episode_id="ep-1",
        required_types=["packet"],
        items=[
            {
                "evidence_id": f"{manifest_id}-item",
                "type": "packet",
                "uri": "capture://x",
                "content_hash": "abc123",
                "synthetic": False,
                "origin": "observed_packet",
            }
        ],
        completeness=1.0,
        reasons=[],
    )
    return manifest_id


def _synthetic_manifest(store, manifest_id="em-synthetic"):
    store.evidence_manifest_put(
        manifest_id=manifest_id,
        episode_id="ep-1",
        required_types=["packet"],
        items=[
            {
                "evidence_id": f"{manifest_id}-item",
                "type": "packet",
                "uri": "capture://x",
                "content_hash": "def456",
                "synthetic": True,
                "origin": "synthetic_fixture",
            }
        ],
        completeness=1.0,
        reasons=[],
    )
    return manifest_id


# ── migration ────────────────────────────────────────────────────────────


def test_migration_002_applies_and_is_idempotent(tmp_path):
    db_path = tmp_path / "hunt_state.db"
    s1 = Store(db_path)
    s1.close()
    s2 = Store(db_path)
    versions = {r["version"] for r in s2._conn.execute("SELECT version FROM schema_migrations")}
    assert {1, 2}.issubset(versions)  # 002_bin_heart.sql applied; later phases may add more
    s2.close()


# ── C1 setup: candidate state machine ───────────────────────────────────


def test_candidate_create_starts_at_created(store):
    cid = _make_candidate(store)
    row = store.candidate_get(cid)
    assert row["current_state"] == "CREATED"
    assert row["alert_version"] == 1


def test_legal_bin_transition_succeeds(store):
    cid = _make_candidate(store)
    store.candidate_advance(cid, "G_MINUS_1_PASS", expected_version=0)
    row = store.candidate_get(cid)
    assert row["current_state"] == "G_MINUS_1_PASS"
    assert row["version"] == 1


def test_illegal_skip_a_gate_transition_rejected(store):
    """C7: 'an unauthorized scope/mutation class cannot create a candidate' +
    the general bin-machine claim that a skip-a-gate transition is rejected."""
    cid = _make_candidate(store)
    with pytest.raises(IllegalBinTransitionError):
        store.candidate_advance(cid, "G1A_PASS", expected_version=0)


def test_stale_expected_version_rejected(store):
    cid = _make_candidate(store)
    store.candidate_advance(cid, "G_MINUS_1_PASS", expected_version=0)
    with pytest.raises(IllegalBinTransitionError):
        store.candidate_advance(cid, "G0_PASS", expected_version=0)  # stale


def test_terminal_states_reachable_from_any_nonterminal_state(store):
    cid = _make_candidate(store)
    store.candidate_advance(cid, "BLOCKED", expected_version=0)
    row = store.candidate_get(cid)
    assert row["current_state"] == "BLOCKED"


def test_blocked_never_bare_transitions_onward(store):
    cid = _make_candidate(store)
    store.candidate_advance(cid, "BLOCKED", expected_version=0)
    with pytest.raises(IllegalBinTransitionError):
        store.candidate_advance(cid, "G_MINUS_1_PASS", expected_version=1)


# ── C2/SS4.8: synthetic never passes G0 ─────────────────────────────────


def test_synthetic_only_manifest_blocks_g0_pass_at_db_level(store):
    manifest_id = _synthetic_manifest(store)
    cid = _make_candidate(store, candidate_id="cand-synth", evidence_manifest_id=manifest_id)
    with pytest.raises(sqlite3.IntegrityError):
        store.gate_result_put(
            result_id="gr-1",
            candidate_id=cid,
            alert_version=1,
            gate_id="G0",
            attempt=1,
            outcome="pass",
            validator_version="v1",
            inputs={},
            evidence={},
            checks=[],
            reasons=["synthetic only"],
        )


def test_observed_origin_manifest_allows_g0_pass(store):
    manifest_id = _observed_manifest(store)
    cid = _make_candidate(store, candidate_id="cand-obs", evidence_manifest_id=manifest_id)
    store.gate_result_put(
        result_id="gr-2",
        candidate_id=cid,
        alert_version=1,
        gate_id="G0",
        attempt=1,
        outcome="pass",
        validator_version="v1",
        inputs={},
        evidence={},
        checks=[],
        reasons=[],
    )
    rows = store.gate_results_for_candidate(cid)
    assert rows[0]["outcome"] == "pass"


def test_synthetic_manifest_can_still_record_a_g0_fail(store):
    """The trigger only blocks a *pass*; a fail/blocked outcome for a
    synthetic-only manifest is exactly what should happen and must not be
    rejected by the same guard."""
    manifest_id = _synthetic_manifest(store)
    cid = _make_candidate(store, candidate_id="cand-synth-fail", evidence_manifest_id=manifest_id)
    store.gate_result_put(
        result_id="gr-3",
        candidate_id=cid,
        alert_version=1,
        gate_id="G0",
        attempt=1,
        outcome="fail",
        validator_version="v1",
        inputs={},
        evidence={},
        checks=[],
        reasons=["synthetic-only evidence"],
    )
    rows = store.gate_results_for_candidate(cid)
    assert rows[0]["outcome"] == "fail"


# ── evidence-change invalidation ────────────────────────────────────────


def test_evidence_manifest_change_bumps_alert_version_and_resets_state(store):
    manifest_id = _observed_manifest(store)
    cid = _make_candidate(store, candidate_id="cand-evchg", evidence_manifest_id=manifest_id)
    store.candidate_advance(cid, "G_MINUS_1_PASS", expected_version=0)
    store.candidate_advance(cid, "G0_PASS", expected_version=1)
    row = store.candidate_get(cid)
    assert row["current_state"] == "G0_PASS"
    assert row["alert_version"] == 1

    new_manifest_id = _observed_manifest(store, manifest_id="em-observed-v2")
    new_alert_version = store.candidate_bump_alert_version(
        cid, expected_version=2, new_evidence_manifest_id=new_manifest_id
    )
    assert new_alert_version == 2
    row = store.candidate_get(cid)
    assert row["current_state"] == "G_MINUS_1_PASS"
    assert row["alert_version"] == 2
    assert row["evidence_manifest_id"] == new_manifest_id


def test_stale_alert_version_gate_passes_do_not_satisfy_promotion(store):
    """A gate 'pass' recorded at an old alert_version must not count toward
    the PROMOTED trigger's gate-chain requirement at the new version."""
    manifest_id = _observed_manifest(store)
    cid = _make_candidate(store, candidate_id="cand-stale", evidence_manifest_id=manifest_id)
    for i, gate in enumerate(("G-1", "G0", "G1a", "G1b", "G2", "G5", "G3")):
        store.gate_result_put(
            result_id=f"gr-stale-{i}",
            candidate_id=cid,
            alert_version=1,
            gate_id=gate,
            attempt=1,
            outcome="pass",
            validator_version="v1",
            inputs={},
            evidence={},
            checks=[],
            reasons=[],
        )
    # Bump the alert version (evidence changed) -- the alert_version=1 passes
    # are now stale.
    new_manifest_id = _observed_manifest(store, manifest_id="em-observed-v3")
    store.candidate_bump_alert_version(
        cid, expected_version=0, new_evidence_manifest_id=new_manifest_id
    )
    row = store.candidate_get(cid)
    assert row["alert_version"] == 2
    # Force current_state to AWAITING_OPERATOR by direct SQL (bypassing the
    # normal gate sequence, since this test's only interest is exercising
    # the PROMOTED trigger's COUNT-at-current-alert_version logic) then try
    # to promote -- must fail because no gate has passed at alert_version=2.
    store._conn.execute(
        "UPDATE candidates SET current_state='AWAITING_OPERATOR' WHERE candidate_id=?", (cid,)
    )
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute(
            "UPDATE candidates SET current_state='PROMOTED' WHERE candidate_id=?", (cid,)
        )


def test_full_gate_chain_at_current_version_allows_promoted(store):
    manifest_id = _observed_manifest(store, manifest_id="em-full")
    cid = _make_candidate(store, candidate_id="cand-full", evidence_manifest_id=manifest_id)
    for i, gate in enumerate(("G-1", "G0", "G1a", "G1b", "G2", "G5", "G3")):
        store.gate_result_put(
            result_id=f"gr-full-{i}",
            candidate_id=cid,
            alert_version=1,
            gate_id=gate,
            attempt=1,
            outcome="pass",
            validator_version="v1",
            inputs={},
            evidence={},
            checks=[],
            reasons=[],
        )
    store._conn.execute(
        "UPDATE candidates SET current_state='AWAITING_OPERATOR', version=version+1 "
        "WHERE candidate_id=?",
        (cid,),
    )
    row = store.candidate_get(cid)
    store.candidate_promote(cid, expected_version=row["version"], operator_actor="operator:alice")
    row = store.candidate_get(cid)
    assert row["current_state"] == "PROMOTED"
    assert row["decided_by"] == "operator:alice"


# ── promotion_queue actor checks (SS4.8) ────────────────────────────────


def test_promotion_queue_resolve_requires_operator_actor(store):
    store.promotion_enqueue(
        queue_id="q-1", item_kind="cousin_detection", item_id="cand-x", hunt_id=None
    )
    with pytest.raises(OperatorActorRequiredError):
        store.promotion_resolve("q-1", actor="system:auto", state="confirmed")


def test_promotion_queue_resolve_by_operator_succeeds(store):
    store.promotion_enqueue(
        queue_id="q-2", item_kind="cousin_detection", item_id="cand-x", hunt_id=None
    )
    store.promotion_resolve("q-2", actor="operator:bob", state="confirmed", rationale="looks solid")
    row = store.promotion_get("q-2")
    assert row["state"] == "confirmed"
    assert row["resolved_by"] == "operator:bob"


def test_promotion_queue_reject_requires_rationale(store):
    store.promotion_enqueue(
        queue_id="q-3", item_kind="cousin_detection", item_id="cand-y", hunt_id=None
    )
    with pytest.raises(StoreError):
        store.promotion_resolve("q-3", actor="operator:bob", state="rejected", rationale="")


def test_promotion_queue_db_trigger_also_refuses_non_operator_actor_directly(store):
    """Defense-in-depth: even a raw SQL UPDATE bypassing store.promotion_resolve
    is refused by the DB trigger, not just the Python-level guard."""
    store.promotion_enqueue(
        queue_id="q-4", item_kind="cousin_detection", item_id="cand-z", hunt_id=None
    )
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute(
            "UPDATE promotion_queue SET state='confirmed', resolved_by='system:auto' "
            "WHERE queue_id='q-4'"
        )
