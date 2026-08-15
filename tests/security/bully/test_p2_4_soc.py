"""P2.4 -- G3 SOC visibility lane over blue_triage.

Hermetic (`tmp_path`, no network): producer_publish/consumer_poll/
consumer_enrich are injected fakes (mirrors orchestrator.py's own
lab_driver injection pattern) standing in for hec_ship/blue_triage's real
network calls.

Tests: ack-without-consume is insufficient; content-hash match required;
queue-load corpus wrapper drives blue_triage (i.e. the real functions are
called through, not bypassed, when no override is given for one of the
three steps).
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully import soc
from portal.modules.security.core.bully.store import Store


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
    from portal.modules.security.core.bully import contracts
    from portal.modules.security.core.bully.contracts import Decomposition

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


def _ok_publish(envelope):
    return {"ok": True}


def _fail_publish(envelope):
    return {"ok": False}


def _make_poll(correlation_key, *, payload_hash=None):
    def _poll(**kwargs):
        alert = {"correlation_key": correlation_key, "EventCode": 4769}
        if payload_hash is not None:
            alert["payload_hash"] = payload_hash
        return [alert]

    return _poll


def _empty_poll(**kwargs):
    return []


def _ok_enrich(alert):
    return {"triage": "P2 - credential access", "enriched": True}


# ── full success ──────────────────────────────────────────────────────


def test_full_delivery_producer_and_consumer_succeeds(store):
    candidate = _make_candidate(store)
    correlation_key = soc.correlation_key_for(candidate)
    envelope = soc.build_redacted_envelope(candidate, correlation_key=correlation_key)
    import hashlib
    import json

    envelope["payload_hash"] = hashlib.sha256(
        json.dumps(envelope, sort_keys=True, default=str).encode()
    ).hexdigest()

    receipt = soc.deliver(
        candidate,
        store=store,
        producer_publish=_ok_publish,
        consumer_poll=_make_poll(correlation_key, payload_hash=envelope["payload_hash"]),
        consumer_enrich=_ok_enrich,
    )
    assert receipt.producer_ack is True
    assert receipt.consumer_query_ran is True
    assert receipt.consumer_triage_report is not None
    assert receipt.sufficient is True

    row = store.soc_delivery_get(receipt.delivery_id)
    assert row["lifecycle_status"] == "visible"


# ── ack-without-consume insufficient ────────────────────────────────────


def test_producer_ack_without_consumer_query_is_insufficient(store):
    candidate = _make_candidate(store, candidate_id="cand-ack-only")

    def _poll_that_finds_nothing(**kwargs):
        raise RuntimeError("splunk unreachable")

    receipt = soc.deliver(
        candidate,
        store=store,
        producer_publish=_ok_publish,
        consumer_poll=_poll_that_finds_nothing,
        consumer_enrich=_ok_enrich,
    )
    assert receipt.producer_ack is True
    assert receipt.consumer_query_ran is False
    assert receipt.sufficient is False


def test_producer_ack_but_no_matching_alert_found_is_insufficient(store):
    candidate = _make_candidate(store, candidate_id="cand-nomatch")
    receipt = soc.deliver(
        candidate,
        store=store,
        producer_publish=_ok_publish,
        consumer_poll=_empty_poll,
        consumer_enrich=_ok_enrich,
    )
    assert receipt.producer_ack is True
    assert receipt.consumer_query_ran is True
    assert receipt.consumer_triage_report is None
    assert receipt.sufficient is False


def test_producer_publish_failure_never_attempts_consumer_step(store):
    candidate = _make_candidate(store, candidate_id="cand-pub-fail")
    polled = {"called": False}

    def _poll(**kwargs):
        polled["called"] = True
        return []

    receipt = soc.deliver(
        candidate, store=store, producer_publish=_fail_publish, consumer_poll=_poll
    )
    assert receipt.producer_ack is False
    assert polled["called"] is False
    assert receipt.sufficient is False


# ── content-hash mismatch ────────────────────────────────────────────────


def test_content_hash_mismatch_fails_g3(store):
    candidate = _make_candidate(store, candidate_id="cand-mismatch")
    correlation_key = soc.correlation_key_for(candidate)
    receipt = soc.deliver(
        candidate,
        store=store,
        producer_publish=_ok_publish,
        consumer_poll=_make_poll(correlation_key, payload_hash="not-the-real-hash"),
        consumer_enrich=_ok_enrich,
    )
    assert receipt.consumer_query_ran is True
    assert receipt.content_hash_match is False
    assert receipt.sufficient is False


# ── queue-load corpus wrapper drives the real blue_triage lane ──────────


def test_default_consumer_functions_are_the_real_blue_triage_lane(monkeypatch, store):
    """Confirms the *default* wiring (no override) calls through to
    siem.blue_triage.poll_alerts/enrich_alert -- proving G3 drives the real
    consumer lane, not a bypass, when the orchestrator doesn't inject a
    fake (I-7a "queue-load corpus wrapper drives blue_triage")."""
    from portal.modules.security.core.siem import blue_triage

    calls = {"poll": 0, "enrich": 0}

    def _fake_poll_alerts(**kwargs):
        calls["poll"] += 1
        return []

    def _fake_enrich_alert(alert):
        calls["enrich"] += 1
        return {}

    monkeypatch.setattr(blue_triage, "poll_alerts", _fake_poll_alerts)
    monkeypatch.setattr(blue_triage, "enrich_alert", _fake_enrich_alert)

    candidate = _make_candidate(store, candidate_id="cand-default-wiring")
    receipt = soc.deliver(candidate, store=store, producer_publish=_ok_publish)
    assert calls["poll"] == 1
    assert receipt.consumer_query_ran is True
    assert receipt.sufficient is False  # no matching alert in the empty poll result


# ── stable correlation key ───────────────────────────────────────────────


def test_correlation_key_stable_per_candidate_and_alert_version(store):
    candidate = _make_candidate(store, candidate_id="cand-corr")
    k1 = soc.correlation_key_for(candidate)
    k2 = soc.correlation_key_for(candidate)
    assert k1 == k2
    assert candidate["candidate_id"] in k1
    assert str(candidate["alert_version"]) in k1
