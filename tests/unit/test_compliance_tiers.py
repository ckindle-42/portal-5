"""T3 Phase 3 — authority tiers + COMPLIANCE_CONFLICT as a code rule with a test.

Tier 0/Tier 3 contradiction fixtures must produce COMPLIANCE_CONFLICT, not a
reconciliation. A lower tier never wins.
"""

from __future__ import annotations

from portal.modules.compliance.core.tiers import Span, classify_tier, detect_conflicts


def test_tier_classification_and_unknown_is_lowest():
    assert classify_tier("nerc_standard") == 0
    assert classify_tier("RSAW") == 1
    assert classify_tier("policy") == 2
    assert classify_tier("procedure") == 3
    assert classify_tier("audit_evidence") == 4
    # anything unrecognised can never silently override a standard
    assert classify_tier("some_new_doc_type") == 4
    assert classify_tier("") == 4


def test_quantitative_cross_tier_conflict_is_emitted_not_reconciled():
    std = Span(
        "The Responsible Entity shall complete the review at least once every 15 calendar months.",
        tier=0,
        citation="CIP-003-9 R1",
        doc_class="standard",
    )
    proc = Span(
        "Procedure: the policy review shall be performed at least once every 18 months.",
        tier=3,
        citation="OT-PROC-003 §2.1 p4",
        doc_class="procedure",
    )
    conflicts = detect_conflicts([std, proc], obligation="policy review cadence")
    assert len(conflicts) == 1
    c = conflicts[0].to_dict()
    assert c["signal"] == "COMPLIANCE_CONFLICT"
    assert c["kind"] == "quantitative"
    assert (
        c["higher_authority"]["tier"] == 0 and c["higher_authority"]["citation"] == "CIP-003-9 R1"
    )
    assert c["lower_authority"]["tier"] == 3
    assert "15 calendar months" in c["detail"] and "18 months" in c["detail"]
    # never averaged, never reconciled
    assert "NOT reconciled" in c["resolution"]
    assert "16" not in c["detail"] and "16.5" not in c["detail"]


def test_same_tier_disagreement_is_not_a_tier_conflict():
    a = Span("review every 15 calendar months", tier=2, citation="POL-A")
    b = Span("review every 18 months", tier=2, citation="POL-B")
    assert detect_conflicts([a, b]) == []


def test_deontic_conflict_shall_vs_should():
    std = Span("The entity shall encrypt data in transit.", tier=0, citation="CIP-012-2 R1")
    pol = Span("Staff should encrypt sensitive data where feasible.", tier=2, citation="SEC-POL §7")
    conflicts = detect_conflicts([std, pol])
    assert len(conflicts) == 1 and conflicts[0].kind == "deontic"
    assert conflicts[0].higher.citation == "CIP-012-2 R1"


def test_matching_durations_across_tiers_are_not_a_conflict():
    std = Span(
        "evaluate patches at least once every 35 calendar days",
        tier=0,
        citation="CIP-007-6 R2 Part 2.2",
    )
    proc = Span("we evaluate patches monthly, within 35 days", tier=3, citation="PATCH-PROC")
    # 35 days == "monthly, within 35 days" (35d both) -> no quantitative conflict
    assert not any(c.kind == "quantitative" for c in detect_conflicts([std, proc]))
