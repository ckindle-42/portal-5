"""P2.3 -- HEART adversarial council + durable objection gate.

Hermetic (`tmp_path`, no network): seat responses are scripted deterministic
fixtures injected via `call_model`, exercised through the real aggregation/
objection-classification code (mirrors C8's own METHOD).

FINAL_VALIDATION C8:
CLAIM 1: a material objection left unrebutted BLOCKS promotion.
CLAIM 2: a rebutted objection (falsification re-pass) unblocks.
CLAIM 3: non-material objections do not block but persist.
CLAIM 4: sub-floor participation invalidates the review -> operator escalation.
CLAIM 5: roster family-diversity constraint rejects a mono-family roster.
CLAIM 6: withdrawal requires the originating/equivalent seat; an unauthorized
waiver is denied; an authorized waiver records identity/reason.
"""

from __future__ import annotations

import json

import pytest

from portal.modules.security.core.bully import adversary, contracts
from portal.modules.security.core.bully.contracts import Decomposition
from portal.modules.security.core.bully.store import Store

_HUNT_CONFIG = {
    "models": {"council_workspace": "blueteam-council", "council_field": "council_models"},
}
_HEART_CONFIG = {
    "roster": {"min_seats": 3, "min_independence_families": 2},
    "floors": {"min_participation": 0.6},
    "waiver": {"requires_operator_actor": True, "requires_durable_reason": True},
    "materiality_version": "bully-heart-materiality-v1",
}

_ROSTER = [
    {"seat_id": "seat-0", "model": "granite4.1:30b-ctx16k", "family": "granite"},
    {"seat_id": "seat-1", "model": "mistral-small3.2:24b", "family": "mistral"},
    {"seat_id": "seat-2", "model": "qwen3.6:27b-q4_K_M", "family": "qwen"},
]


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
    return store.candidate_get(candidate_id)


def _scripted_call_model(responses: dict[str, dict]):
    def _call(model: str, messages: list[dict]) -> dict:
        payload = responses.get(model, {"recommendation": "ABSTAIN", "confidence": 0.0})
        return {"content": json.dumps(payload)}

    return _call


def _fixed_roster(monkeypatch, roster=_ROSTER):
    monkeypatch.setattr(adversary, "resolve_roster", lambda **_: list(roster))


_SUPPORT = {"recommendation": "SUPPORT", "confidence": 0.8, "findings": []}


def _reject_material(category_phrase: str) -> dict:
    return {
        "recommendation": "REJECT",
        "confidence": 0.9,
        "findings": [],
        "strongest_objection": category_phrase,
        "missing_evidence": ["a corroborating log"],
    }


# ── CLAIM 5: roster diversity ────────────────────────────────────────────


def test_mono_family_roster_rejected_at_load(monkeypatch, store):
    mono = [
        {"seat_id": "seat-0", "model": "granite4.1:8b", "family": "granite"},
        {"seat_id": "seat-1", "model": "granite4.1:30b", "family": "granite"},
        {"seat_id": "seat-2", "model": "granite4.1:2b", "family": "granite"},
    ]
    _fixed_roster(monkeypatch, mono)
    candidate = _make_candidate(store)
    with pytest.raises(ValueError, match="mono-family"):
        adversary.review(
            candidate,
            {},
            store=store,
            hunt_config=_HUNT_CONFIG,
            heart_config=_HEART_CONFIG,
            call_model=_scripted_call_model({}),
        )


def test_too_few_seats_rejected_at_load(monkeypatch, store):
    _fixed_roster(monkeypatch, _ROSTER[:2])
    candidate = _make_candidate(store)
    with pytest.raises(ValueError, match="needs >="):
        adversary.review(
            candidate,
            {},
            store=store,
            hunt_config=_HUNT_CONFIG,
            heart_config=_HEART_CONFIG,
            call_model=_scripted_call_model({}),
        )


# ── CLAIM 1/2: material objection blocks until rebutted ─────────────────


def test_material_objection_blocks_promotion(monkeypatch, store):
    _fixed_roster(monkeypatch)
    candidate = _make_candidate(store, candidate_id="cand-block")
    responses = {
        "granite4.1:30b-ctx16k": _SUPPORT,
        "mistral-small3.2:24b": _reject_material(
            "this evidence contradicts the observed telemetry timeline"
        ),
        "qwen3.6:27b-q4_K_M": _SUPPORT,
    }
    record = adversary.review(
        candidate,
        {},
        store=store,
        hunt_config=_HUNT_CONFIG,
        heart_config=_HEART_CONFIG,
        call_model=_scripted_call_model(responses),
    )
    assert record.review_valid is True
    assert record.unresolved is True
    assert any(o.material for o in record.objections)


def test_rebuttal_with_falsification_repass_unblocks(monkeypatch, store):
    _fixed_roster(monkeypatch)
    candidate = _make_candidate(store, candidate_id="cand-rebut")
    responses = {
        "granite4.1:30b-ctx16k": _SUPPORT,
        "mistral-small3.2:24b": _reject_material("this evidence contradicts the timeline"),
        "qwen3.6:27b-q4_K_M": _SUPPORT,
    }
    record = adversary.review(
        candidate,
        {},
        store=store,
        hunt_config=_HUNT_CONFIG,
        heart_config=_HEART_CONFIG,
        call_model=_scripted_call_model(responses),
    )
    assert record.unresolved is True
    material_objection = next(o for o in record.objections if o.material)

    rebuttal = adversary.rebut(
        store,
        material_objection.objection_id,
        author="operator:bob",
        claim="re-ran the replay on the same evidence version; timeline is consistent",
        evidence_citations=["replay-run-42"],
        falsification_repass=True,
    )
    assert rebuttal.re_review_result == "confirmed"

    packet = store.council_packet_get(record.packet_id)
    assert packet["unresolved"] == 0


def test_rebuttal_without_falsification_repass_stays_open(monkeypatch, store):
    _fixed_roster(monkeypatch)
    candidate = _make_candidate(store, candidate_id="cand-rereview")
    responses = {
        "granite4.1:30b-ctx16k": _SUPPORT,
        "mistral-small3.2:24b": _reject_material("this evidence contradicts the timeline"),
        "qwen3.6:27b-q4_K_M": _SUPPORT,
    }
    record = adversary.review(
        candidate,
        {},
        store=store,
        hunt_config=_HUNT_CONFIG,
        heart_config=_HEART_CONFIG,
        call_model=_scripted_call_model(responses),
    )
    material_objection = next(o for o in record.objections if o.material)
    adversary.rebut(
        store,
        material_objection.objection_id,
        author="operator:bob",
        claim="disputing the objection, re-review requested",
        evidence_citations=[],
        falsification_repass=False,
    )
    packet = store.council_packet_get(record.packet_id)
    assert packet["unresolved"] == 1  # still standing -- re_review, not closed


# ── CLAIM 3: non-material objections persist but do not block ───────────


def test_non_material_objection_does_not_block(monkeypatch, store):
    _fixed_roster(monkeypatch)
    candidate = _make_candidate(store, candidate_id="cand-nonmaterial")
    revise_with_objection = {
        "recommendation": "REVISE",
        "confidence": 0.5,
        "strongest_objection": "telemetry health looks marginal but not disqualifying",
        "missing_evidence": [],
    }
    responses = {
        "granite4.1:30b-ctx16k": _SUPPORT,
        "mistral-small3.2:24b": revise_with_objection,
        "qwen3.6:27b-q4_K_M": _SUPPORT,
    }
    record = adversary.review(
        candidate,
        {},
        store=store,
        hunt_config=_HUNT_CONFIG,
        heart_config=_HEART_CONFIG,
        call_model=_scripted_call_model(responses),
    )
    assert record.unresolved is False
    assert len(record.objections) == 1
    assert record.objections[0].material is False


# ── CLAIM 4: sub-floor participation -> operator escalation ─────────────


def test_subfloor_participation_invalidates_review(monkeypatch, store):
    _fixed_roster(monkeypatch)
    candidate = _make_candidate(store, candidate_id="cand-subfloor")
    responses = {
        "granite4.1:30b-ctx16k": {"recommendation": "ABSTAIN", "confidence": 0.0},
        "mistral-small3.2:24b": {"recommendation": "ABSTAIN", "confidence": 0.0},
        "qwen3.6:27b-q4_K_M": _SUPPORT,
    }
    record = adversary.review(
        candidate,
        {},
        store=store,
        hunt_config=_HUNT_CONFIG,
        heart_config=_HEART_CONFIG,
        call_model=_scripted_call_model(responses),
    )
    assert record.review_valid is False
    assert record.participation < 0.6
    # Sub-floor: even a would-be material objection never gets classified,
    # since materiality is only evaluated for a valid review.
    assert record.objections == []


def test_seat_failure_is_a_non_participant_not_a_crash(monkeypatch, store):
    _fixed_roster(monkeypatch)
    candidate = _make_candidate(store, candidate_id="cand-seatfail")

    def _flaky_call_model(model, messages):
        if model == "mistral-small3.2:24b":
            raise RuntimeError("backend unavailable")
        return {"content": json.dumps(_SUPPORT)}

    record = adversary.review(
        candidate,
        {},
        store=store,
        hunt_config=_HUNT_CONFIG,
        heart_config=_HEART_CONFIG,
        call_model=_flaky_call_model,
    )
    failed = next(o for o in record.opinions if o.seat_id == "seat-1")
    assert failed.valid is False
    assert "RuntimeError" in failed.error


# ── CLAIM 6: withdrawal + waiver ─────────────────────────────────────────


def test_withdrawal_by_originating_seat_closes_objection(monkeypatch, store):
    _fixed_roster(monkeypatch)
    candidate = _make_candidate(store, candidate_id="cand-withdraw")
    responses = {
        "granite4.1:30b-ctx16k": _SUPPORT,
        "mistral-small3.2:24b": _reject_material("this evidence contradicts the timeline"),
        "qwen3.6:27b-q4_K_M": _SUPPORT,
    }
    record = adversary.review(
        candidate,
        {},
        store=store,
        hunt_config=_HUNT_CONFIG,
        heart_config=_HEART_CONFIG,
        call_model=_scripted_call_model(responses),
    )
    material_objection = next(o for o in record.objections if o.material)
    adversary.withdraw_objection(store, material_objection.objection_id, seat_id="seat-1")
    packet = store.council_packet_get(record.packet_id)
    assert packet["unresolved"] == 0
    row = store.objection_get(material_objection.objection_id)
    assert row["status"] == "withdrawn"


def test_withdrawal_by_unrelated_non_roster_actor_denied(monkeypatch, store):
    _fixed_roster(monkeypatch)
    candidate = _make_candidate(store, candidate_id="cand-withdraw-deny")
    responses = {
        "granite4.1:30b-ctx16k": _SUPPORT,
        "mistral-small3.2:24b": _reject_material("this evidence contradicts the timeline"),
        "qwen3.6:27b-q4_K_M": _SUPPORT,
    }
    record = adversary.review(
        candidate,
        {},
        store=store,
        hunt_config=_HUNT_CONFIG,
        heart_config=_HEART_CONFIG,
        call_model=_scripted_call_model(responses),
    )
    material_objection = next(o for o in record.objections if o.material)
    with pytest.raises(ValueError, match="withdrawal denied"):
        adversary.withdraw_objection(
            store, material_objection.objection_id, seat_id="seat-not-on-roster"
        )


def test_waiver_requires_operator_actor_and_reason(monkeypatch, store):
    _fixed_roster(monkeypatch)
    candidate = _make_candidate(store, candidate_id="cand-waiver")
    responses = {
        "granite4.1:30b-ctx16k": _SUPPORT,
        "mistral-small3.2:24b": _reject_material("this evidence contradicts the timeline"),
        "qwen3.6:27b-q4_K_M": _SUPPORT,
    }
    record = adversary.review(
        candidate,
        {},
        store=store,
        hunt_config=_HUNT_CONFIG,
        heart_config=_HEART_CONFIG,
        call_model=_scripted_call_model(responses),
    )
    material_objection = next(o for o in record.objections if o.material)

    with pytest.raises(ValueError, match="not an operator"):
        adversary.waive_objection(
            store, material_objection.objection_id, operator_actor="system:auto", reason="skip it"
        )
    with pytest.raises(ValueError, match="durable"):
        adversary.waive_objection(
            store, material_objection.objection_id, operator_actor="operator:alice", reason=""
        )

    adversary.waive_objection(
        store,
        material_objection.objection_id,
        operator_actor="operator:alice",
        reason="confirmed benign via out-of-band change ticket CHG-4471",
    )
    row = store.objection_get(material_objection.objection_id)
    assert row["status"] == "waived"
    packet = store.council_packet_get(record.packet_id)
    assert packet["unresolved"] == 0
