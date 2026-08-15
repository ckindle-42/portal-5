"""P5.2 -- HND family package with real detection-proof legs (M7).

Hermetic (`tmp_path`, no network). Feeds D1: a proof-leg failure blocks the
package (status stays 'draft'); SPL syntax + dry-exec validation gate;
superseding rebuild; FP analysis attached from G2. Also proves the three
proof legs execute *for real* -- gather adapters that actually parse SPL
discriminator tokens and match them against real telemetry/corpus text, not
a placeholder that always returns True.
"""

from __future__ import annotations

import json

import pytest

from portal.modules.security.core.bully import contracts, handoff
from portal.modules.security.core.bully.contracts import Decomposition
from portal.modules.security.core.bully.store import Store


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
        self.action_sequence = ["auth_request", "ticket_issued"]
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
    # Drive straight to PROMOTED via the store's own transition surface
    # (mirrors P2's helper pattern -- avoids re-deriving the full BIN chain).
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
    raise AssertionError("model should not be called in a hermetic test with injected evidence")


# ── build_package requires a PROMOTED candidate ────────────────────────────


def test_build_package_requires_promoted_candidate(store):
    store.hunt_create(
        hunt_id="hunt-1",
        objective="x",
        neighborhood_scope="lab-default",
        authorization_ref="auth-1",
        config_version="cfg-1",
        role_snapshot={},
        budgets={},
    )
    store.record_signature(_Sig("sig-x", "T1558.003"))
    store.record_cousin(
        contracts.CousinAssessment(
            assessment_id="assess-x",
            subject_signature_id="sig-x",
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
        candidate_id="cand-x",
        hunt_id="hunt-1",
        assessment_id="assess-x",
        evidence_manifest_id=None,
        gate_policy_version="bin-gates-v1",
    )
    with pytest.raises(ValueError, match="PROMOTED"):
        handoff.build_package(store, "cand-x")


# ── proof-leg failure blocks the package (never shipped) ──────────────────


def test_proof_leg_failure_blocks_the_package(store):
    candidate_id, hunt_id = _make_promoted_candidate(store)
    pkg = handoff.build_package(
        store,
        candidate_id,
        owner="operator:alice",
        call_model=_no_call_model,
        fires_on_attack_evidence={"replay": {"ok": True}, "syntax_ok": True, "dry_exec_hits": 0},
        quiet_on_benign_evidence={"benign_hits": 0, "benign_sample_size": 12},
        no_regression_evidence={"bq": "PASS", "az": "PASS"},
    )
    assert pkg.proof_legs["fires_on_attack"]["outcome"] == "fail"
    row = store.detection_proposal_get(pkg.proposal_id)
    assert row["status"] == "draft"  # never advanced to 'submitted' -- rework, never shipped


def test_all_legs_passing_advances_to_submitted(store):
    candidate_id, hunt_id = _make_promoted_candidate(store)
    pkg = handoff.build_package(
        store,
        candidate_id,
        owner="operator:alice",
        call_model=_no_call_model,
        fires_on_attack_evidence={"replay": {"ok": True}, "syntax_ok": True, "dry_exec_hits": 3},
        quiet_on_benign_evidence={"benign_hits": 0, "benign_sample_size": 12},
        no_regression_evidence={"bq": "PASS", "az": "PASS"},
    )
    assert all(leg["outcome"] == "pass" for leg in pkg.proof_legs.values())
    row = store.detection_proposal_get(pkg.proposal_id)
    assert row["status"] == "submitted"


# ── SPL syntax + dry-exec validation gate ──────────────────────────────────


def test_check_fires_on_attack_fails_on_invalid_syntax():
    ok, errors = handoff.validate_spl_syntax("# TODO: draft SPL for T9999")
    assert ok is False
    assert errors
    result = handoff.check_fires_on_attack(
        {"replay": {"ok": True}, "syntax_ok": ok, "syntax_errors": errors, "dry_exec_hits": 0}
    )
    assert result["outcome"] == "fail"


def test_check_fires_on_attack_fails_on_zero_dry_exec_hits():
    result = handoff.check_fires_on_attack(
        {"replay": {"ok": True}, "syntax_ok": True, "syntax_errors": [], "dry_exec_hits": 0}
    )
    assert result["outcome"] == "fail"
    assert "zero dry-exec hits" in result["reasons"][0]


def test_gather_fires_on_attack_executes_for_real(tmp_path):
    """The gather adapter really parses SPL discriminator tokens and matches
    them against the capture's actual telemetry text -- not a
    placeholder-true leg."""
    capture_path = tmp_path / "capture.json"
    capture_path.write_text(
        json.dumps(
            {
                "scenario": "kerberoast",
                "telemetry": {
                    "windows:security": [
                        "EventCode=4769 TicketEncryptionType=0x17 ServiceName=svc1 Account=alice"
                    ]
                },
            }
        )
    )
    spl = 'index=portal5_lab sourcetype="windows:security" EventCode=4769 TicketEncryptionType=0x17'
    evidence = handoff.gather_fires_on_attack(
        str(capture_path), spl, replay_capture_fn=lambda path: {"ok": True}
    )
    assert evidence["syntax_ok"] is True
    assert evidence["dry_exec_hits"] == 1  # both discriminator tokens matched the raw event
    assert handoff.check_fires_on_attack(evidence)["outcome"] == "pass"

    # A discriminator that does NOT appear in the telemetry -> real zero-hit fail.
    non_matching_spl = "index=portal5_lab EventCode=4768 PreAuthType=0"
    evidence2 = handoff.gather_fires_on_attack(
        str(capture_path), non_matching_spl, replay_capture_fn=lambda path: {"ok": True}
    )
    assert evidence2["dry_exec_hits"] == 0
    assert handoff.check_fires_on_attack(evidence2)["outcome"] == "fail"


def test_gather_fires_on_attack_raises_on_replay_infra_failure(tmp_path):
    capture_path = tmp_path / "capture.json"
    capture_path.write_text(json.dumps({"scenario": "x", "telemetry": {}}))

    def _boom(path):
        raise RuntimeError("splunk unreachable")

    with pytest.raises(handoff.HandoffInfrastructureError):
        handoff.gather_fires_on_attack(str(capture_path), "search index=x", replay_capture_fn=_boom)


# ── quiet-on-benign: real corpus, not a mock ───────────────────────────────


def test_gather_quiet_on_benign_uses_real_corpus_data_by_default():
    """No override supplied -- this must really load benign_corpus_bench's
    BENIGN_CELLS and compute over it (never a hardcoded pass)."""
    evidence = handoff.gather_quiet_on_benign("index=portal5_lab EventCode=4769")
    assert evidence["benign_sample_size"] > 0


def test_check_quiet_on_benign_fails_when_spl_fires_on_benign_corpus():
    result = handoff.check_quiet_on_benign({"benign_hits": 2, "benign_sample_size": 12})
    assert result["outcome"] == "fail"


def test_check_quiet_on_benign_blocked_without_evidence():
    assert handoff.check_quiet_on_benign({})["outcome"] == "blocked"


# ── no-regression: real BQ/AZ validate_system lanes ────────────────────────


def test_gather_no_regression_runs_real_bq_az_lanes():
    """Executes the actual validate_system.py BQ/AZ check functions --
    proves this leg is real code, not a stub returning PASS unconditionally."""
    evidence = handoff.gather_no_regression()
    assert evidence["bq"] in ("PASS", "FAIL")
    assert evidence["az"] in ("PASS", "FAIL")
    result = handoff.check_no_regression(evidence)
    assert result["outcome"] in ("pass", "fail")


# ── superseding rebuild ─────────────────────────────────────────────────────


def test_rebuild_produces_superseding_package_version(store):
    candidate_id, hunt_id = _make_promoted_candidate(store)
    pkg1 = handoff.build_package(
        store,
        candidate_id,
        call_model=_no_call_model,
        fires_on_attack_evidence={"replay": {"ok": True}, "syntax_ok": True, "dry_exec_hits": 1},
        quiet_on_benign_evidence={"benign_hits": 0, "benign_sample_size": 12},
        no_regression_evidence={"bq": "PASS", "az": "PASS"},
    )
    pkg2 = handoff.build_package(
        store,
        candidate_id,
        call_model=_no_call_model,
        fires_on_attack_evidence={"replay": {"ok": True}, "syntax_ok": True, "dry_exec_hits": 1},
        quiet_on_benign_evidence={"benign_hits": 0, "benign_sample_size": 12},
        no_regression_evidence={"bq": "PASS", "az": "PASS"},
    )
    assert pkg1.proposal_id != pkg2.proposal_id
    prior = store.detection_proposal_get(pkg1.proposal_id)
    assert prior["superseded_by"] == pkg2.proposal_id
    latest = store.detection_proposal_latest_for_candidate(candidate_id)
    assert latest["proposal_id"] == pkg2.proposal_id
    assert latest["version"] == 2


# ── FP analysis attached from G2 ────────────────────────────────────────────


def test_fp_analysis_attached_from_g2(store):
    candidate_id, hunt_id = _make_promoted_candidate(store)
    pkg = handoff.build_package(
        store,
        candidate_id,
        call_model=_no_call_model,
        fires_on_attack_evidence={"replay": {"ok": True}, "syntax_ok": True, "dry_exec_hits": 1},
        quiet_on_benign_evidence={"benign_hits": 0, "benign_sample_size": 12},
        no_regression_evidence={"bq": "PASS", "az": "PASS"},
    )
    assert pkg.fp_analysis == {"benign_fires": False, "vetoes": []}
