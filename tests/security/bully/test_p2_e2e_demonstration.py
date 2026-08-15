"""P2 exit-criteria demonstration: the full BIN+HEART+G3 gate pipeline run
end to end starting from a real P1-graded candidate (LOOP's own
`run_hunt_iteration` -> a real `cousin_assessments` row via the synthetic
lab + mocked models, exactly as `test_p1_7_orchestrator.py` establishes it)
-- not a hand-built fixture that skips P1's own grading path.

Demonstrates, from that one P1-graded assessment: a council BLOCK and a
council PASS (two separate candidates built from the same assessment, since
a DISPROVED candidate is terminal); synthetic evidence blocked at G0;
static-alone (G1a pass, no G1b evidence) cannot promote; G3 requires a real
consumer triage, not just a producer ack.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from portal.modules.security.core.bully import adversary, contracts, promotion
from portal.modules.security.core.bully import orchestrator as orch
from portal.modules.security.core.bully.investigation import InvestigationResult
from portal.modules.security.core.bully.organ import Organ
from portal.modules.security.core.bully.store import Store
from portal.modules.security.core.episode import Episode


def _fake_embed(dim: int = 8):
    def _embed(texts):
        return [[float((hash(t) >> i) % 7) for i in range(dim)] for t in texts]

    return _embed


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "hunt_state.db")
    yield s
    s.close()


@pytest.fixture
def organ(tmp_path, store):
    o = Organ(store=store, db_path=tmp_path / "hunt_memory")
    o._embed = _fake_embed()
    yield o
    o.close()


def _proven_episode() -> Episode:
    return Episode(
        episode_id="ep-20260101T000000Z-scn-e2edemo",
        scenario="lateral-movement-wmi",
        target_host="host-1",
        started_at=0.0,
        red_status="RED_LANDED",
        telemetry_status="TELEMETRY_INDEXED",
        detection_status="DETECTION_CONFIRMED",
    )


def _synthetic_lab_driver(target_cell, *, dry_run):
    return _proven_episode()


def _fake_investigation_arm(episode, *, models, dry_run=False):
    return InvestigationResult(
        verdict="CONFIRMED",
        technique_ids=("T1021.002",),
        grounded_technique_ids=("T1021.002",),
        dropped_technique_ids=(),
        contradicted_technique_ids=(),
        reasoning="mocked investigation arm",
        match_grade="EXACT",
        evidence=("wmic process call create observed",),
    )


@pytest.fixture
def graded_assessment_id(store, organ):
    """A real P1-graded cousin_assessments row -- LOOP's own
    run_hunt_iteration, synthetic lab + mocked models, exactly as P1's own
    E2E test establishes it (not a hand-built fixture skipping P1)."""
    store.hunt_create(
        hunt_id="hunt-e2e",
        objective="prove cousin discovery",
        neighborhood_scope="lab-default",
        authorization_ref="operator:alice",
        config_version="cfg-1",
        role_snapshot={},
        budgets={},
    )
    store.lease_acquire("hunt-e2e", owner="operator:alice")
    result = orch.run_hunt_iteration(
        store,
        organ,
        hunt_id="hunt-e2e",
        actor="operator:alice",
        neighborhood="lab-default",
        lab_driver=_synthetic_lab_driver,
        investigation_arm=_fake_investigation_arm,
    )
    assert result["stage"] == "CLOSED"
    return result["assessment_id"]


def _observed_manifest(store, manifest_id):
    store.evidence_manifest_put(
        manifest_id=manifest_id,
        episode_id="ep-20260101T000000Z-scn-e2edemo",
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


def _synthetic_manifest(store, manifest_id):
    store.evidence_manifest_put(
        manifest_id=manifest_id,
        episode_id="ep-20260101T000000Z-scn-e2edemo",
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


_PASSING_GATE_INPUTS = {
    "G-1": {"approved_scope": {"approved": True}},
    "G0": {"telemetry_healthy": True},
    "G1a": {"has_spl_hit": True, "within_window": True, "target_match": True},
    "G1b": {"reexecution_runs": [True, True, True]},
    "G2": {"benign_corpus_fires": False},
}


def _council_pass(candidate_row, packet):
    return SimpleNamespace(
        review_valid=True, unresolved=False, participation=1.0, packet_id="pkt-pass"
    )


def _council_block(candidate_row, packet):
    return SimpleNamespace(
        review_valid=True, unresolved=True, participation=1.0, packet_id="pkt-block"
    )


def _soc_pass(candidate_row):
    return contracts.SOCDeliveryReceipt(
        delivery_id="soc-e2e",
        candidate_id=candidate_row["candidate_id"],
        correlation_key="corr-e2e",
        producer_ack=True,
        consumer_query_ran=True,
        consumer_triage_report={"severity": "P2"},
        priority="P2",
        latency_s=0.5,
        content_hash_match=True,
        load_profile="baseline",
    )


def _soc_ack_only(candidate_row):
    return contracts.SOCDeliveryReceipt(
        delivery_id="soc-e2e-ackonly",
        candidate_id=candidate_row["candidate_id"],
        correlation_key="corr-e2e-2",
        producer_ack=True,
        consumer_query_ran=False,
        consumer_triage_report=None,
        priority="P2",
        latency_s=None,
        content_hash_match=False,
        load_profile="baseline",
    )


def test_council_block_then_council_pass_from_the_same_p1_graded_candidate(
    store, graded_assessment_id
):
    """The headline P2 demonstration: two candidates built from the SAME
    real P1-graded assessment -- one HEART blocks (material objection
    unrebutted -> DISPROVED, never reaches AWAITING_OPERATOR), the other
    HEART clears (-> AWAITING_OPERATOR, queued for operator confirm)."""
    manifest_block = "em-e2e-block"
    _observed_manifest(store, manifest_block)
    store.candidate_create(
        candidate_id="cand-e2e-block",
        hunt_id="hunt-e2e",
        assessment_id=graded_assessment_id,
        evidence_manifest_id=manifest_block,
        gate_policy_version="bin-gates-v1",
    )
    blocked = promotion.process(
        store,
        "cand-e2e-block",
        gate_inputs=_PASSING_GATE_INPUTS,
        council_review=_council_block,
    )
    assert blocked.state == "DISPROVED"
    assert blocked.gate_results["G5"] == "fail"

    manifest_pass = "em-e2e-pass"
    _observed_manifest(store, manifest_pass)
    store.candidate_create(
        candidate_id="cand-e2e-pass",
        hunt_id="hunt-e2e",
        assessment_id=graded_assessment_id,
        evidence_manifest_id=manifest_pass,
        gate_policy_version="bin-gates-v1",
    )
    passed = promotion.process(
        store,
        "cand-e2e-pass",
        gate_inputs=_PASSING_GATE_INPUTS,
        council_review=_council_pass,
        soc_deliver=_soc_pass,
    )
    assert passed.state == "AWAITING_OPERATOR"
    assert passed.queue_id is not None

    # Operator confirms -- the machine-enforced, gate-chain-checked promote.
    result = orch.queue_resolve(
        item_id=passed.queue_id,
        actor="operator:alice",
        rationale="confirmed",
        action="confirm",
        store=store,
    )
    assert result["state"] == "confirmed"
    assert store.candidate_get("cand-e2e-pass")["current_state"] == "PROMOTED"


def test_synthetic_evidence_blocked_at_g0_for_the_same_graded_candidate(
    store, graded_assessment_id
):
    manifest_id = "em-e2e-synthetic"
    _synthetic_manifest(store, manifest_id)
    store.candidate_create(
        candidate_id="cand-e2e-synth",
        hunt_id="hunt-e2e",
        assessment_id=graded_assessment_id,
        evidence_manifest_id=manifest_id,
        gate_policy_version="bin-gates-v1",
    )
    outcome = promotion.process(store, "cand-e2e-synth", gate_inputs=_PASSING_GATE_INPUTS)
    assert outcome.state == "DISPROVED"
    assert outcome.gate_results["G0"] == "fail"


def test_static_alone_cannot_promote_for_the_same_graded_candidate(store, graded_assessment_id):
    manifest_id = "em-e2e-static-alone"
    _observed_manifest(store, manifest_id)
    store.candidate_create(
        candidate_id="cand-e2e-static",
        hunt_id="hunt-e2e",
        assessment_id=graded_assessment_id,
        evidence_manifest_id=manifest_id,
        gate_policy_version="bin-gates-v1",
    )
    inputs = dict(_PASSING_GATE_INPUTS)
    inputs["G1b"] = {}  # no dynamic re-execution evidence
    outcome = promotion.process(store, "cand-e2e-static", gate_inputs=inputs)
    assert outcome.gate_results["G1a"] == "pass"
    assert outcome.state == "BLOCKED"  # never reaches AWAITING_OPERATOR/PROMOTED


def test_g3_requires_real_consumer_triage_for_the_same_graded_candidate(
    store, graded_assessment_id
):
    manifest_id = "em-e2e-g3"
    _observed_manifest(store, manifest_id)
    store.candidate_create(
        candidate_id="cand-e2e-g3",
        hunt_id="hunt-e2e",
        assessment_id=graded_assessment_id,
        evidence_manifest_id=manifest_id,
        gate_policy_version="bin-gates-v1",
    )
    outcome = promotion.process(
        store,
        "cand-e2e-g3",
        gate_inputs=_PASSING_GATE_INPUTS,
        council_review=_council_pass,
        soc_deliver=_soc_ack_only,  # producer ack, no consumer query
    )
    assert outcome.state == "DISPROVED"
    assert outcome.gate_results["G3"] == "fail"


def test_heart_real_adversary_module_wired_into_promotion(monkeypatch, store, graded_assessment_id):
    """Confirms adversary.review (not a hand-rolled fake) drives HEART's
    gate through promotion.process, with scripted deterministic seat
    responses standing in for the model calls (C8's own METHOD)."""
    roster = [
        {"seat_id": "seat-0", "model": "granite4.1:30b-ctx16k", "family": "granite"},
        {"seat_id": "seat-1", "model": "mistral-small3.2:24b", "family": "mistral"},
        {"seat_id": "seat-2", "model": "qwen3.6:27b-q4_K_M", "family": "qwen"},
    ]
    monkeypatch.setattr(adversary, "resolve_roster", lambda **_: list(roster))

    import json

    def _scripted_call_model(model, messages):
        return {"content": json.dumps({"recommendation": "SUPPORT", "confidence": 0.8})}

    def _real_council_review(candidate_row, packet):
        return adversary.review(
            candidate_row,
            packet,
            store=store,
            hunt_config={
                "models": {
                    "council_workspace": "blueteam-council",
                    "council_field": "council_models",
                }
            },
            heart_config={
                "roster": {"min_seats": 3, "min_independence_families": 2},
                "floors": {"min_participation": 0.6},
                "materiality_version": "bully-heart-materiality-v1",
            },
            call_model=_scripted_call_model,
        )

    manifest_id = "em-e2e-real-heart"
    _observed_manifest(store, manifest_id)
    store.candidate_create(
        candidate_id="cand-e2e-real-heart",
        hunt_id="hunt-e2e",
        assessment_id=graded_assessment_id,
        evidence_manifest_id=manifest_id,
        gate_policy_version="bin-gates-v1",
    )
    outcome = promotion.process(
        store,
        "cand-e2e-real-heart",
        gate_inputs=_PASSING_GATE_INPUTS,
        council_review=_real_council_review,
        soc_deliver=_soc_pass,
    )
    assert outcome.state == "AWAITING_OPERATOR"
    assert outcome.gate_results["G5"] == "pass"
