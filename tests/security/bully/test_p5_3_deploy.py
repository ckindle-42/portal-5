"""P5.3 -- detection deployment + post-deploy replay -> cell closure (M7).

Hermetic (`tmp_path`, no network). Tests: KNOWN_COVERED refused without
deployment+replay; DISPROVED (rejected) requires rationale and is
ORG-indexed; provenance appended; operator-only gates; the promotion ->
handoff wiring in `orchestrator.queue_resolve` (opt-in via `handoff_inputs`,
never changing pre-P5 default behavior).
"""

from __future__ import annotations

import sqlite3

import pytest

from portal.modules.security.core.bully import contracts, handoff, orchestrator
from portal.modules.security.core.bully.contracts import Decomposition
from portal.modules.security.core.bully.orchestrator import OperatorRequiredError
from portal.modules.security.core.bully.store import OperatorActorRequiredError, Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "hunt_state.db")
    yield s
    s.close()


class _Sig:
    def __init__(self, signature_id, technique_id):
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
        self.attack_mappings = [{"technique_id": technique_id}]
        self.telemetry_shape = {}
        self.detector_outcomes = {}
        self.evidence_manifest_id = None
        self.completeness = 1.0
        self.created_at = 0.0


def _make_promoted_candidate(
    store, *, candidate_id="cand-1", hunt_id="hunt-1", technique_id="T1558.003"
):
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
    store.record_signature(_Sig(sig_id, technique_id))
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
    manifest_id = f"em-{candidate_id}"
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
    store.candidate_create(
        candidate_id=candidate_id,
        hunt_id=hunt_id,
        assessment_id=assessment_id,
        evidence_manifest_id=manifest_id,
        gate_policy_version="bin-gates-v1",
    )
    for gate_id in ("G-1", "G0", "G1a", "G1b", "G2", "G5", "G3"):
        store.gate_result_put(
            result_id=f"gr-{candidate_id}-{gate_id}",
            candidate_id=candidate_id,
            alert_version=1,
            gate_id=gate_id,
            attempt=1,
            outcome="pass",
            validator_version="bin-gates-v1",
            inputs={},
            evidence={"benign_fires": False, "vetoes": []} if gate_id == "G2" else {},
            checks=[],
            reasons=[],
        )
    for target in (
        "G_MINUS_1_PASS",
        "G0_PASS",
        "G1A_PASS",
        "G1B_PASS",
        "G2_PASS",
        "COUNCIL_PASS",
        "G3_PASS",
        "AWAITING_OPERATOR",
    ):
        row = store.candidate_get(candidate_id)
        store.candidate_advance(candidate_id, target, expected_version=row["version"])
    row = store.candidate_get(candidate_id)
    store.candidate_promote(
        candidate_id, expected_version=row["version"], operator_actor="operator:alice"
    )
    return candidate_id, hunt_id


def _no_call_model(*args, **kwargs):
    raise AssertionError("model should not be called in a hermetic test")


_PASSING_LEGS = {
    "call_model": _no_call_model,
    "fires_on_attack_evidence": {"replay": {"ok": True}, "syntax_ok": True, "dry_exec_hits": 1},
    "quiet_on_benign_evidence": {"benign_hits": 0, "benign_sample_size": 12},
    "no_regression_evidence": {"bq": "PASS", "az": "PASS"},
}


def _build_submitted_proposal(store, **kwargs):
    candidate_id, hunt_id = _make_promoted_candidate(store, **kwargs)
    pkg = handoff.build_package(store, candidate_id, owner="operator:alice", **_PASSING_LEGS)
    assert store.detection_proposal_get(pkg.proposal_id)["status"] == "submitted"
    return pkg, candidate_id, hunt_id


class _FakeOrgan:
    """Stands in for `Organ` in hermetic tests -- proves the ORG record
    really reaches `index_emissions`, no lancedb/network required."""

    def __init__(self):
        self.indexed = []
        self.closed = False

    def index_emissions(self, records):
        self.indexed.extend(records)
        return [r.get("record_id", "") for r in records]

    def close(self):
        self.closed = True


# ── handoff.deploy: proof-leg gate + operator-only ─────────────────────────


def test_deploy_blocked_without_all_proof_legs_passing(store):
    candidate_id, hunt_id = _make_promoted_candidate(store)
    pkg = handoff.build_package(
        store,
        candidate_id,
        call_model=_no_call_model,
        fires_on_attack_evidence={"replay": {"ok": True}, "syntax_ok": True, "dry_exec_hits": 0},
        quiet_on_benign_evidence={"benign_hits": 0, "benign_sample_size": 12},
        no_regression_evidence={"bq": "PASS", "az": "PASS"},
    )
    with pytest.raises(sqlite3.IntegrityError):
        handoff.deploy(
            store,
            pkg.proposal_id,
            operator_actor="operator:alice",
            spl_commit_ref="deadbeef",
            receipt_hash="h1",
        )


def test_deploy_requires_operator_actor(store):
    pkg, _, _ = _build_submitted_proposal(store)
    with pytest.raises(OperatorActorRequiredError):
        handoff.deploy(
            store,
            pkg.proposal_id,
            operator_actor="system:auto",
            spl_commit_ref="deadbeef",
            receipt_hash="h1",
        )


def test_deploy_with_passing_legs_succeeds_and_appends_provenance(store, monkeypatch):
    recorded = []
    monkeypatch.setattr(
        "portal.platform.wiki.provenance_ledger.append_entry",
        lambda **kwargs: recorded.append(kwargs),
    )
    pkg, candidate_id, hunt_id = _build_submitted_proposal(store)
    result = handoff.deploy(
        store,
        pkg.proposal_id,
        operator_actor="operator:alice",
        spl_commit_ref="deadbeef",
        receipt_hash="h1",
    )
    assert result["status"] == "deployed"
    assert store.detection_proposal_get(pkg.proposal_id)["status"] == "deployed"
    assert len(recorded) == 1
    assert recorded[0]["capability_verdict"] == "DEPLOYED"


# ── KNOWN_COVERED requires deployment + passed post-deploy replay ─────────


def test_record_replay_passed_closes_cell_to_known_covered(store):
    pkg, candidate_id, hunt_id = _build_submitted_proposal(store)
    deploy_result = handoff.deploy(
        store,
        pkg.proposal_id,
        operator_actor="operator:alice",
        spl_commit_ref="deadbeef",
        receipt_hash="h1",
    )
    result = handoff.record_replay(
        store, deploy_result["deployment_id"], passed=True, detail="clean replay"
    )
    assert result["status"] == "replay-validated"
    assert result["org_record"] is None
    known = store._conn.execute(
        "SELECT * FROM known_state WHERE subject=? AND kind='known_covered'",
        (f"cell:{pkg.family}",),
    ).fetchone()
    assert known is not None
    assert known["deployment_id"] == deploy_result["deployment_id"]
    proposal = store.detection_proposal_get(pkg.proposal_id)
    assert proposal["coverage_validation_ref"] == known["entry_id"]


def test_record_replay_failed_never_writes_known_covered_and_is_org_indexed(store):
    pkg, candidate_id, hunt_id = _build_submitted_proposal(store)
    deploy_result = handoff.deploy(
        store,
        pkg.proposal_id,
        operator_actor="operator:alice",
        spl_commit_ref="deadbeef",
        receipt_hash="h1",
    )
    result = handoff.record_replay(
        store, deploy_result["deployment_id"], passed=False, detail="fired on unrelated traffic"
    )
    assert result["status"] == "replay-failed"
    known = store._conn.execute(
        "SELECT * FROM known_state WHERE subject=? AND kind='known_covered'",
        (f"cell:{pkg.family}",),
    ).fetchone()
    assert known is None  # never fabricated -- DB backstop never even reached
    assert result["org_record"]["kind"] == "detection_change"
    assert result["org_record"]["detection_response"] == "replay-failed"


# ── operator reject: rationale required, ORG-indexed ───────────────────────


def test_reject_requires_operator_actor(store):
    pkg, _, _ = _build_submitted_proposal(store)
    with pytest.raises(OperatorActorRequiredError):
        handoff.reject(store, pkg.proposal_id, operator_actor="system:auto", rationale="x")


def test_reject_without_rationale_blocked_at_db_level(store):
    pkg, _, _ = _build_submitted_proposal(store)
    with pytest.raises(sqlite3.IntegrityError):
        handoff.reject(store, pkg.proposal_id, operator_actor="operator:alice", rationale="")


def test_reject_with_rationale_succeeds_and_is_org_indexable(store):
    pkg, _, _ = _build_submitted_proposal(store)
    result = handoff.reject(
        store, pkg.proposal_id, operator_actor="operator:alice", rationale="benign automation"
    )
    assert result["status"] == "rejected"
    row = store.detection_proposal_get(pkg.proposal_id)
    assert row["rationale"] == "benign automation"
    assert result["org_record"]["kind"] == "detection_change"
    assert result["org_record"]["detection_response"] == "rejected"


# ── orchestrator wiring: operator gate + real ORG indexing ─────────────────


def test_orchestrator_handoff_deploy_requires_operator_actor(store):
    pkg, _, _ = _build_submitted_proposal(store)
    with pytest.raises(OperatorRequiredError):
        orchestrator.handoff_deploy(
            proposal_id=pkg.proposal_id,
            actor="not-an-operator",
            spl_commit_ref="deadbeef",
            receipt_hash="h1",
            store=store,
        )


def test_orchestrator_handoff_reject_requires_operator_actor(store):
    pkg, _, _ = _build_submitted_proposal(store)
    with pytest.raises(OperatorRequiredError):
        orchestrator.handoff_reject(
            proposal_id=pkg.proposal_id, actor="not-an-operator", rationale="x", store=store
        )


def test_orchestrator_handoff_record_replay_indexes_org_on_failure(store):
    pkg, _, _ = _build_submitted_proposal(store)
    deploy_result = orchestrator.handoff_deploy(
        proposal_id=pkg.proposal_id,
        actor="operator:alice",
        spl_commit_ref="deadbeef",
        receipt_hash="h1",
        store=store,
    )
    fake_organ = _FakeOrgan()
    orchestrator.handoff_record_replay(
        deployment_id=deploy_result["deployment_id"],
        passed=False,
        detail="noisy",
        store=store,
        organ=fake_organ,
    )
    assert len(fake_organ.indexed) == 1
    assert fake_organ.indexed[0]["kind"] == "detection_change"


def test_orchestrator_handoff_reject_indexes_org(store):
    pkg, _, _ = _build_submitted_proposal(store)
    fake_organ = _FakeOrgan()
    orchestrator.handoff_reject(
        proposal_id=pkg.proposal_id,
        actor="operator:alice",
        rationale="false positive",
        store=store,
        organ=fake_organ,
    )
    assert len(fake_organ.indexed) == 1
    assert fake_organ.indexed[0]["detection_response"] == "rejected"


# ── promotion -> handoff wiring (ARCH SS4.2), opt-in via handoff_inputs ────


def test_queue_confirm_with_handoff_inputs_builds_the_package(store):
    from portal.modules.security.core.bully import promotion

    candidate_id, hunt_id = "cand-wired", "hunt-wired"
    store.hunt_create(
        hunt_id=hunt_id,
        objective="x",
        neighborhood_scope="lab-default",
        authorization_ref="auth-1",
        config_version="cfg-1",
        role_snapshot={},
        budgets={},
    )
    sig_id = "sig-wired"
    store.record_signature(_Sig(sig_id, "T1558.003"))
    assessment_id = "assess-wired"
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
    manifest_id = "em-wired"
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
    store.candidate_create(
        candidate_id=candidate_id,
        hunt_id=hunt_id,
        assessment_id=assessment_id,
        evidence_manifest_id=manifest_id,
        gate_policy_version="bin-gates-v1",
    )

    def _council_pass(candidate_row, packet):
        from types import SimpleNamespace

        return SimpleNamespace(
            review_valid=True, unresolved=False, participation=1.0, packet_id="pkt-1"
        )

    def _soc_pass(candidate_row):
        return contracts.SOCDeliveryReceipt(
            delivery_id="soc-1",
            candidate_id=candidate_row["candidate_id"],
            correlation_key="corr-1",
            producer_ack=True,
            consumer_query_ran=True,
            consumer_triage_report={"severity": "P2"},
            priority="P2",
            latency_s=1.2,
            content_hash_match=True,
            load_profile="baseline",
        )

    outcome = promotion.process(
        store,
        candidate_id,
        gate_inputs={
            "G-1": {"approved_scope": {"approved": True}},
            "G0": {"telemetry_healthy": True},
            "G1a": {"has_spl_hit": True, "within_window": True, "target_match": True},
            "G1b": {"reexecution_runs": [True, True, True]},
            "G2": {"benign_corpus_fires": False},
        },
        council_review=_council_pass,
        soc_deliver=_soc_pass,
    )
    assert outcome.state == "AWAITING_OPERATOR"

    result = orchestrator.queue_resolve(
        item_id=outcome.queue_id,
        actor="operator:alice",
        rationale="solid finding",
        action="confirm",
        store=store,
        handoff_inputs={**_PASSING_LEGS, "owner": "operator:alice"},
    )
    assert result["state"] == "confirmed"
    assert "handoff" in result
    assert result["handoff"]["family"] == "T1558.003"
    proposal = store.detection_proposal_get(result["handoff"]["proposal_id"])
    assert proposal["status"] == "submitted"
