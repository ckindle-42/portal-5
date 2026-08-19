"""J.2 -- bin gates over relation claims: pedigree alone neither passes nor
fails a claim; gate verdicts are recorded."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from portal.modules.security.core.bully import relation as relation_mod
from portal.modules.security.core.bully import relation_promotion
from portal.modules.security.core.bully import signatures as sig_mod
from portal.modules.security.core.bully.anchors import AnchorLibrary
from portal.modules.security.core.bully.store import Store
from portal.modules.security.core.telemetry import IMPORTED_OBSERVED, OBSERVED_TARGET_LOG


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "hunt_state.db")
    yield s
    s.close()


def _hunt(store, hunt_id: str) -> None:
    store.hunt_create(
        hunt_id=hunt_id,
        objective="prove relation-driven discovery",
        neighborhood_scope="lab-default",
        authorization_ref="auth-1",
        config_version="cfg-1",
        role_snapshot={"investigator": "some-tag"},
        budgets={"max_iterations": 5},
    )


def _relation(episode_id: str = "ep-1"):
    lib = AnchorLibrary()
    lib.load_attack_episode(
        source_id="attack_data",
        record={"action_sequence": ["proc_create", "net_connect"]},
        techniques=("T1059",),
    )
    signature = sig_mod.build_signature(
        {"target_host": "host1", "episode_id": episode_id},
        {
            "action_sequence": ["proc_create", "net_connect"],
            "attack_mappings": [{"technique_id": "T1059"}],
        },
    )
    return signature, relation_mod.relate(signature, lib)


def _strong_gate_inputs() -> dict:
    return {
        "G-1": {"approved_scope": {"approved": True, "mutation_class": "recon"}},
        "G0": {"telemetry_healthy": True},
        "G1a": {"has_spl_hit": True, "within_window": True, "target_match": True},
        "G1b": {"reexecution_runs": [True, True, True]},
        "G2": {"benign_corpus_fires": False},
    }


def _thin_gate_inputs() -> dict:
    inputs = _strong_gate_inputs()
    inputs["G1b"] = {"reexecution_runs": [True, False, False]}  # below 2-of-3
    return inputs


def _fake_council_pass(candidate_row, packet):
    return SimpleNamespace(
        review_valid=True, unresolved=False, participation=1.0, packet_id="pkt-1"
    )


def _fake_soc_pass(candidate_row):
    from portal.modules.security.core.bully import contracts

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


def test_imperfect_source_with_strong_evidence_passes(store):
    signature, relation = _relation()
    _hunt(store, "hunt-imperfect")
    outcome = relation_promotion.submit_relation_claim(
        store,
        relation,
        signature,
        hunt_id="hunt-imperfect",
        candidate_id="cand-imperfect",
        origin=IMPORTED_OBSERVED,
        trust_tier="IMPORTED_UNVERIFIED",
        synthetic=False,
        gate_inputs=_strong_gate_inputs(),
        council_review=_fake_council_pass,
        soc_deliver=_fake_soc_pass,
    )
    assert outcome.state == "AWAITING_OPERATOR"
    assert all(v == "pass" for v in outcome.gate_results.values())


def test_clean_source_with_thin_evidence_does_not_pass(store):
    signature, relation = _relation()
    _hunt(store, "hunt-clean")
    outcome = relation_promotion.submit_relation_claim(
        store,
        relation,
        signature,
        hunt_id="hunt-clean",
        candidate_id="cand-clean-thin",
        origin=OBSERVED_TARGET_LOG,
        trust_tier="VALIDATED",
        synthetic=False,
        gate_inputs=_thin_gate_inputs(),
    )
    assert outcome.state == "DISPROVED"
    assert outcome.gate_results["G1b"] == "fail"


def test_pedigree_alone_does_not_change_the_verdict_given_identical_evidence(store):
    """Same gate_inputs, different trust_tier/origin -- identical outcome."""
    signature_a, relation_a = _relation("ep-a")
    signature_b, relation_b = _relation("ep-b")
    _hunt(store, "hunt-a")
    outcome_a = relation_promotion.submit_relation_claim(
        store,
        relation_a,
        signature_a,
        hunt_id="hunt-a",
        candidate_id="cand-a",
        origin=IMPORTED_OBSERVED,
        trust_tier="IMPORTED_UNVERIFIED",
        gate_inputs=_strong_gate_inputs(),
        council_review=_fake_council_pass,
        soc_deliver=_fake_soc_pass,
    )
    outcome_b = relation_promotion.submit_relation_claim(
        store,
        relation_b,
        signature_b,
        hunt_id="hunt-a",
        candidate_id="cand-b",
        origin=OBSERVED_TARGET_LOG,
        trust_tier="VALIDATED",
        gate_inputs=_strong_gate_inputs(),
        council_review=_fake_council_pass,
        soc_deliver=_fake_soc_pass,
    )
    assert outcome_a.state == outcome_b.state == "AWAITING_OPERATOR"
    assert outcome_a.gate_results == outcome_b.gate_results


def test_gate_verdicts_are_recorded(store):
    signature, relation = _relation()
    _hunt(store, "hunt-record")
    outcome = relation_promotion.submit_relation_claim(
        store,
        relation,
        signature,
        hunt_id="hunt-record",
        candidate_id="cand-record",
        gate_inputs=_thin_gate_inputs(),
    )
    recorded = store.gate_results_for_candidate("cand-record", alert_version=1)
    assert any(g["gate_id"] == "G1b" and g["outcome"] == "fail" for g in recorded)
    assert outcome.gate_results["G1b"] == "fail"
