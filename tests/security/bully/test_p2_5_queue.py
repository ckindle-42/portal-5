"""P2.5 -- promotion queue + machine-enforced confirm/reject.

Hermetic (`tmp_path`, no network). Tests: promote without operator actor ->
refused; reject requires rationale; queue-arrival notification fired;
provenance entry appended.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully import contracts, orchestrator, promotion
from portal.modules.security.core.bully.contracts import Decomposition
from portal.modules.security.core.bully.orchestrator import (
    HonestBlockedError,
    OperatorRequiredError,
)
from portal.modules.security.core.bully.store import Store
from portal.modules.security.core.commands.hunt_modes import hunt_main


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


def _make_candidate_awaiting_operator(store, *, candidate_id="cand-1", hunt_id="hunt-1"):
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
    return outcome.queue_id


# ── operator-actor enforcement ────────────────────────────────────────


def test_queue_confirm_without_operator_actor_refused(store):
    queue_id = _make_candidate_awaiting_operator(store)
    with pytest.raises(OperatorRequiredError):
        orchestrator.queue_resolve(
            item_id=queue_id, actor="system:auto", rationale="", action="confirm", store=store
        )
    row = store.promotion_get(queue_id)
    assert row["state"] == "pending"


def test_queue_confirm_by_operator_promotes_candidate(store):
    queue_id = _make_candidate_awaiting_operator(store, candidate_id="cand-confirm")
    result = orchestrator.queue_resolve(
        item_id=queue_id,
        actor="operator:alice",
        rationale="solid finding",
        action="confirm",
        store=store,
    )
    assert result["state"] == "confirmed"
    row = store.promotion_get(queue_id)
    assert row["state"] == "confirmed"
    assert row["resolved_by"] == "operator:alice"
    candidate = store.candidate_get("cand-confirm")
    assert candidate["current_state"] == "PROMOTED"


# ── reject requires rationale ───────────────────────────────────────────


def test_queue_reject_without_rationale_refused(store):
    queue_id = _make_candidate_awaiting_operator(store, candidate_id="cand-reject-norationale")
    with pytest.raises(HonestBlockedError):
        orchestrator.queue_resolve(
            item_id=queue_id, actor="operator:alice", rationale="", action="reject", store=store
        )
    row = store.promotion_get(queue_id)
    assert row["state"] == "pending"


def test_queue_reject_with_rationale_kills_candidate(store):
    queue_id = _make_candidate_awaiting_operator(store, candidate_id="cand-reject")
    result = orchestrator.queue_resolve(
        item_id=queue_id,
        actor="operator:alice",
        rationale="false positive, benign automation",
        action="reject",
        store=store,
    )
    assert result["state"] == "rejected"
    row = store.promotion_get(queue_id)
    assert row["state"] == "rejected"
    assert row["rationale"] == "false positive, benign automation"
    candidate = store.candidate_get("cand-reject")
    assert candidate["current_state"] == "DISPROVED"


# ── CLI wiring ────────────────────────────────────────────────────────


def test_cli_hunt_queue_reject_without_actor_denied(store, monkeypatch, tmp_path):
    queue_id = _make_candidate_awaiting_operator(store, candidate_id="cand-cli")
    monkeypatch.setenv("PORTAL5_HUNT_DIR", str(tmp_path))
    # Point the CLI's own store at a *different*, empty DB to prove the
    # gate check happens before any real store lookup for a non-operator
    # actor -- rc must be 1 regardless of what's in the DB.
    rc = hunt_main(["queue", "--reject", queue_id, "--actor", "not-an-operator", "--reason", "x"])
    assert rc == 1


# ── queue-arrival notification ──────────────────────────────────────────


def test_queue_arrival_fires_notification(store, monkeypatch):
    calls = []
    monkeypatch.setattr(promotion, "_bully_notify_enabled", lambda: True)

    class _FakeDispatcher:
        def add_channel(self, channel):
            pass

        def dispatch(self, event):
            calls.append(event)
            return None

        def _schedule(self, coro):
            pass

    monkeypatch.setattr(
        "portal.platform.inference.notifications.NotificationDispatcher", _FakeDispatcher
    )
    _make_candidate_awaiting_operator(store, candidate_id="cand-notify")
    assert len(calls) == 1
    assert calls[0].metadata["item_kind"] == "cousin_detection"


def test_notify_disabled_fires_nothing(store, monkeypatch):
    monkeypatch.setattr(promotion, "_bully_notify_enabled", lambda: False)
    calls = []

    class _FakeDispatcher:
        def add_channel(self, channel):
            pass

        def dispatch(self, event):
            calls.append(event)
            return None

        def _schedule(self, coro):
            pass

    monkeypatch.setattr(
        "portal.platform.inference.notifications.NotificationDispatcher", _FakeDispatcher
    )
    _make_candidate_awaiting_operator(store, candidate_id="cand-notify-off")
    assert calls == []


# ── provenance entry appended on promotion ───────────────────────────────


def test_provenance_entry_appended_on_confirm(store, monkeypatch, tmp_path):
    recorded = []

    def _fake_append_entry(**kwargs):
        recorded.append(kwargs)
        return kwargs

    monkeypatch.setattr("portal.platform.wiki.provenance_ledger.append_entry", _fake_append_entry)
    queue_id = _make_candidate_awaiting_operator(store, candidate_id="cand-provenance")
    orchestrator.queue_resolve(
        item_id=queue_id,
        actor="operator:alice",
        rationale="confirmed",
        action="confirm",
        store=store,
    )
    assert len(recorded) == 1
    assert recorded[0]["capability_verdict"] == "CONFIRMED"
    assert recorded[0]["event"] == "bully_promotion"


# ── list pending ──────────────────────────────────────────────────────


def test_queue_list_pending_with_no_item_id(store):
    _make_candidate_awaiting_operator(store, candidate_id="cand-list")
    result = orchestrator.queue_resolve(item_id=None, actor="operator:alice", store=store)
    assert len(result["pending"]) == 1
    assert result["pending"][0]["item_id"] == "cand-list"
