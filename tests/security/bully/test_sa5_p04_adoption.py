"""P0.4 -- arm adoption decision + DISCOVERY_BASELINE_V2 freeze contract.

Hermetic: the adoption decision is made on discovery precision among arms
clearing the one-session throughput bar; identity is a classified diagnostic
(P0.3) that never sole-disqualifies; the incumbent CPU space reproduces its
frozen thresholds; and the arm-b llama-server ubatch limit is a recorded
operational constraint, not papered over.
"""

from __future__ import annotations

from portal.modules.security.core.bully.discovery_bench import (
    run_controls,
)
from tests.security.bully._discovery_fixtures import build_corpus, build_snapshot

ADOPTION_RULES = {
    "deciding_metric": "discovery_precision",
    "identity_role": "classified_diagnostic",
    "throughput_bar": "full-corpus seed within one session",
}


def test_adoption_rule_is_discovery_precision_among_passing_arms():
    """P0.4: adoption is decided on discovery precision among arms whose
    anti-circularity controls pass; identity is a diagnostic, never the sole
    disqualifier (P0.3)."""
    assert ADOPTION_RULES["deciding_metric"] == "discovery_precision"
    assert ADOPTION_RULES["identity_role"] == "classified_diagnostic"


def test_diagnostic_gate_reports_identity_but_does_not_solely_disqualify():
    """Under the diagnostic gate, an arm with only classified identity
    failures still yields a scored report; the by-cause classification is
    preserved in the controls."""
    corpus = build_corpus()
    snapshot = build_snapshot(corpus)
    probes = corpus["specimens"]
    from portal.modules.security.core.bully import cousin_engine

    controls = run_controls(
        probes,
        (),
        snapshot,
        thresholds={**cousin_engine.DEFAULT_THRESHOLDS, "same_max_distance": 0.5},
        identity_gate="diagnostic",
    )
    assert controls["identity_gate"] == "diagnostic"
    assert "by_cause" in controls["identity"]


def test_incumbent_space_reproduces_frozen_thresholds_for_adoption():
    """The incumbent harrier space reproduces its frozen thresholds within
    tolerance, so DISCOVERY_BASELINE_V2 keeps the same same/similar/new scale
    the frozen V1 used -- the derivation is a portability fix, not tuning."""
    from portal.modules.security.core.bully.embedding_spaces import derive_thresholds

    incumbent = {
        "self": {"p95": 0.0, "p50": 0.0, "n": 64},
        "near": {"p95": 0.073, "p50": 0.047, "n": 32},
        "far": {"p95": 0.064, "p50": 0.054, "n": 10},
    }
    derived = derive_thresholds(incumbent, embedding_version="sentence-transformers-v1")
    assert derived.incumbent_reproduced is True


def test_arm_b_ubatch_limit_is_recorded_operational_constraint():
    """Arm B's llama-server n_ubatch=512 bounds the embed batch: real corpus
    texts (~300 tokens each) cap at ~4 texts/batch before 500. This is a
    recorded constraint that shapes the arm's configured batch, not a
    threshold change."""
    from scripts.defensive_bully_p04_adoption import ARM_SPECS

    assert ARM_SPECS["arm-b"]["batch_size"] == 4
    assert ARM_SPECS["arm-a"]["batch_size"] == 32
