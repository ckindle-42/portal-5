"""P2.2 -- BIN promotion machine, gates G-1 -> G0 -> G1a -> G1b -> G2 -> HEART
(G5) -> G3.

Hermetic (`tmp_path`, no network): gate internals that would otherwise touch
Splunk/capture bytes are exercised through `gate_inputs` (mirrors
orchestrator.py's own `lab_driver` injection pattern from P1); HEART/G3 are
exercised through injected `council_review`/`soc_deliver` callables since
adversary.py/soc.py land in P2.3/P2.4.

FINAL_VALIDATION C7: full gate pipeline pass; each gate's fail path;
infra-vs-gate distinction; synthetic blocked at G0; static-alone cannot
promote.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from portal.modules.security.core.bully import contracts, promotion
from portal.modules.security.core.bully.contracts import Decomposition
from portal.modules.security.core.bully.store import OperatorActorRequiredError, Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "hunt_state.db")
    yield s
    s.close()


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


def _make_candidate(store, *, candidate_id="cand-1", hunt_id="hunt-1", synthetic=False):
    store.hunt_create(
        hunt_id=hunt_id,
        objective="prove cousin discovery",
        neighborhood_scope="lab-default",
        authorization_ref="auth-1",
        config_version="cfg-1",
        role_snapshot={"investigator": "some-tag"},
        budgets={"max_iterations": 5},
    )
    sig_id = f"sig-{candidate_id}"
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
                "synthetic": synthetic,
                "origin": "synthetic_fixture" if synthetic else "observed_packet",
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
    return candidate_id


_PASSING_G1A_INPUT = {"has_spl_hit": True, "within_window": True, "target_match": True}


def _passing_gate_inputs(**overrides) -> dict:
    inputs = {
        "G-1": {"approved_scope": {"approved": True, "mutation_class": "recon"}},
        "G0": {"telemetry_healthy": True},
        "G1a": dict(_PASSING_G1A_INPUT),
        "G1b": {"reexecution_runs": [True, True, True]},
        "G2": {"benign_corpus_fires": False},
    }
    inputs.update(overrides)
    return inputs


def _fake_council_pass(candidate_row, packet):
    return SimpleNamespace(
        review_valid=True, unresolved=False, participation=1.0, packet_id="pkt-1"
    )


def _fake_council_block(candidate_row, packet):
    return SimpleNamespace(review_valid=True, unresolved=True, participation=1.0, packet_id="pkt-2")


def _fake_council_subfloor(candidate_row, packet):
    return SimpleNamespace(
        review_valid=False, unresolved=False, participation=0.2, packet_id="pkt-3"
    )


def _fake_soc_pass(candidate_row):
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


def _fake_soc_ack_only(candidate_row):
    return contracts.SOCDeliveryReceipt(
        delivery_id="soc-2",
        candidate_id=candidate_row["candidate_id"],
        correlation_key="corr-2",
        producer_ack=True,
        consumer_query_ran=False,
        consumer_triage_report=None,
        priority="P2",
        latency_s=None,
        content_hash_match=False,
        load_profile="baseline",
    )


# ── full pipeline pass ──────────────────────────────────────────────────


def test_full_gate_pipeline_pass_reaches_awaiting_operator(store):
    cid = _make_candidate(store, candidate_id="cand-pass")
    outcome = promotion.process(
        store,
        cid,
        gate_inputs=_passing_gate_inputs(),
        council_review=_fake_council_pass,
        soc_deliver=_fake_soc_pass,
    )
    assert outcome.state == "AWAITING_OPERATOR"
    assert outcome.queue_id is not None
    assert all(v == "pass" for v in outcome.gate_results.values())
    assert set(outcome.gate_results) == {"G-1", "G0", "G1a", "G1b", "G2", "G5", "G3"}

    queue_row = store.promotion_get(outcome.queue_id)
    assert queue_row["item_kind"] == "cousin_detection"
    assert queue_row["state"] == "pending"


def test_operator_promote_after_full_pipeline_pass(store):
    cid = _make_candidate(store, candidate_id="cand-promote")
    promotion.process(
        store,
        cid,
        gate_inputs=_passing_gate_inputs(),
        council_review=_fake_council_pass,
        soc_deliver=_fake_soc_pass,
    )
    result = promotion.promote(store, cid, operator_actor="operator:alice", note="looks solid")
    assert result["state"] == "PROMOTED"
    row = store.candidate_get(cid)
    assert row["current_state"] == "PROMOTED"


def test_promote_without_operator_actor_refused(store):
    cid = _make_candidate(store, candidate_id="cand-promote-refuse")
    promotion.process(
        store,
        cid,
        gate_inputs=_passing_gate_inputs(),
        council_review=_fake_council_pass,
        soc_deliver=_fake_soc_pass,
    )
    with pytest.raises(OperatorActorRequiredError):
        promotion.promote(store, cid, operator_actor="system:auto")


# ── G-1 fail (unauthorized scope) ───────────────────────────────────────


def test_g_minus_1_fails_closed_without_approved_scope(store):
    cid = _make_candidate(store, candidate_id="cand-g-1-fail")
    outcome = promotion.process(store, cid, gate_inputs={})
    assert outcome.state == "DISPROVED"
    assert outcome.gate_results["G-1"] == "fail"
    row = store.candidate_get(cid)
    assert row["terminal_reason"] == "G-1"


# ── G0: synthetic blocked ────────────────────────────────────────────────


def test_synthetic_only_candidate_fails_at_g0(store):
    cid = _make_candidate(store, candidate_id="cand-synth", synthetic=True)
    outcome = promotion.process(store, cid, gate_inputs=_passing_gate_inputs())
    assert outcome.state == "DISPROVED"
    assert outcome.gate_results["G0"] == "fail"


def test_observed_origin_candidate_passes_g0(store):
    cid = _make_candidate(store, candidate_id="cand-obs")
    outcome = promotion.process(
        store,
        cid,
        gate_inputs=_passing_gate_inputs(),
        council_review=_fake_council_pass,
        soc_deliver=_fake_soc_pass,
    )
    assert outcome.gate_results["G0"] == "pass"


# ── G1a static-alone cannot promote ──────────────────────────────────────


def test_static_alone_cannot_promote_without_g1b_evidence(store):
    """C7: 'G1a pass + no G1b evidence cannot advance.'"""
    cid = _make_candidate(store, candidate_id="cand-static-alone")
    inputs = _passing_gate_inputs()
    inputs["G1b"] = {}  # no reexecution_runs supplied
    outcome = promotion.process(store, cid, gate_inputs=inputs)
    assert outcome.gate_results["G1a"] == "pass"
    assert outcome.state == "BLOCKED"
    assert outcome.gate_results["G1b"] == "blocked"


def test_g1b_below_2_of_3_fails(store):
    cid = _make_candidate(store, candidate_id="cand-g1b-fail")
    inputs = _passing_gate_inputs()
    inputs["G1b"] = {"reexecution_runs": [True, False, False]}
    outcome = promotion.process(store, cid, gate_inputs=inputs)
    assert outcome.state == "DISPROVED"
    assert outcome.gate_results["G1b"] == "fail"


def test_g1b_2_of_3_passes(store):
    cid = _make_candidate(store, candidate_id="cand-g1b-pass")
    inputs = _passing_gate_inputs()
    inputs["G1b"] = {"reexecution_runs": [True, True, False]}
    outcome = promotion.process(
        store,
        cid,
        gate_inputs=inputs,
        council_review=_fake_council_pass,
        soc_deliver=_fake_soc_pass,
    )
    assert outcome.gate_results["G1b"] == "pass"
    assert outcome.state == "AWAITING_OPERATOR"


# ── G2: benign fire fails ────────────────────────────────────────────────


def test_g2_fails_on_benign_corpus_fire(store):
    cid = _make_candidate(store, candidate_id="cand-g2-fail")
    inputs = _passing_gate_inputs(**{"G2": {"benign_corpus_fires": True}})
    outcome = promotion.process(store, cid, gate_inputs=inputs)
    assert outcome.state == "DISPROVED"
    assert outcome.gate_results["G2"] == "fail"


# ── HEART (G5): council block vs pass ────────────────────────────────────


def test_council_block_disproves_candidate(store):
    cid = _make_candidate(store, candidate_id="cand-council-block")
    outcome = promotion.process(
        store,
        cid,
        gate_inputs=_passing_gate_inputs(),
        council_review=_fake_council_block,
    )
    assert outcome.state == "DISPROVED"
    assert outcome.gate_results["G5"] == "fail"
    assert outcome.council_record_ref == "pkt-2"


def test_council_pass_advances_to_g3(store):
    cid = _make_candidate(store, candidate_id="cand-council-pass")
    outcome = promotion.process(
        store,
        cid,
        gate_inputs=_passing_gate_inputs(),
        council_review=_fake_council_pass,
        soc_deliver=_fake_soc_pass,
    )
    assert outcome.gate_results["G5"] == "pass"
    assert outcome.state == "AWAITING_OPERATOR"


def test_council_subfloor_participation_escalates_never_autopass(store):
    cid = _make_candidate(store, candidate_id="cand-subfloor")
    outcome = promotion.process(
        store,
        cid,
        gate_inputs=_passing_gate_inputs(),
        council_review=_fake_council_subfloor,
    )
    assert outcome.state == "OPERATOR_ESCALATED"
    queued = store.promotion_list(state="pending")
    assert any(q["item_kind"] == "review_escalation" and q["item_id"] == cid for q in queued)


# ── G3: producer-ack-without-consume is insufficient ─────────────────────


def test_g3_ack_without_consume_is_insufficient(store):
    cid = _make_candidate(store, candidate_id="cand-g3-fail")
    outcome = promotion.process(
        store,
        cid,
        gate_inputs=_passing_gate_inputs(),
        council_review=_fake_council_pass,
        soc_deliver=_fake_soc_ack_only,
    )
    assert outcome.state == "DISPROVED"
    assert outcome.gate_results["G3"] == "fail"


# ── infra-vs-gate distinction ────────────────────────────────────────────


def test_g0_blocked_when_manifest_missing_is_infra_not_gate_failure(store):
    cid = _make_candidate(store, candidate_id="cand-no-manifest")
    store._conn.execute(
        "UPDATE candidates SET evidence_manifest_id=NULL WHERE candidate_id=?", (cid,)
    )
    outcome = promotion.process(store, cid, gate_inputs=_passing_gate_inputs())
    assert outcome.state == "BLOCKED"
    assert outcome.gate_results["G0"] == "blocked"
    row = store.candidate_get(cid)
    assert row["current_state"] == "BLOCKED"
    assert row["terminal_reason"] == "G0"


def test_heart_missing_council_review_is_infra_blocked(store):
    cid = _make_candidate(store, candidate_id="cand-no-heart")
    outcome = promotion.process(store, cid, gate_inputs=_passing_gate_inputs())
    assert outcome.state == "BLOCKED"
    assert outcome.gate_results["G5"] == "blocked"


# ── idempotent re-run ─────────────────────────────────────────────────────


def test_rerun_after_partial_progress_skips_already_passed_gates(store):
    cid = _make_candidate(store, candidate_id="cand-rerun")
    inputs = _passing_gate_inputs()
    inputs["G1b"] = {}  # blocks at G1b first
    outcome1 = promotion.process(store, cid, gate_inputs=inputs)
    assert outcome1.state == "BLOCKED"

    inputs["G1b"] = {"reexecution_runs": [True, True, True]}
    outcome2 = promotion.process(
        store,
        cid,
        gate_inputs=inputs,
        council_review=_fake_council_pass,
        soc_deliver=_fake_soc_pass,
    )
    assert outcome2.state == "AWAITING_OPERATOR"
    # G-1/G0/G1a were not re-run (only one 'pass' row each at this alert_version).
    g1a_passes = [
        g
        for g in store.gate_results_for_candidate(cid, alert_version=1)
        if g["gate_id"] == "G1a" and g["outcome"] == "pass"
    ]
    assert len(g1a_passes) == 1
