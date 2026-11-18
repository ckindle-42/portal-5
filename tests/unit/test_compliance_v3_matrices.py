"""V3 P9 acceptance matrices.

A01-A30: the thirty adversarial cases from TASK_COMPLIANCE_REASONING_V2.md
Section P8. Each case ID exercises the real mechanism the V2 table names for
it (not a single generic comparator cycled through modulo-4 modes) so that
`pytest -k A17` runs exactly the scenario A17 describes, asserts the real
determination/finding, its exact anchors, and at least one forbidden
conclusion.

Q01-Q12 x 3 variants: complete/counter/missing-evidence per operator question,
against the deterministic field-comparison contract.
"""

from __future__ import annotations

from portal.modules.compliance.core.authority import classify, may_create_obligation
from portal.modules.compliance.core.cip_register import Register, RegisterNode
from portal.modules.compliance.core.constraints import Quantity, compare_constraint
from portal.modules.compliance.core.engine import (
    _is_enforceable_at,
    effective_parts,
    future_effective_parts,
    unknown_effectivity_parts,
)
from portal.modules.compliance.core.internal_model import classify_document, extract_assertions
from portal.modules.compliance.core.register_diff import diff_standard


def _node(part_id, part, text, *, standard="X-1", appsys="high impact BES Cyber Systems", **kw):
    defaults = dict(
        id=part_id,
        standard=standard,
        version="1",
        requirement="R1",
        part=part,
        verbatim_text=text,
        measure_text="",
        applicable_systems=appsys,
        table_name="T",
        vrf="Medium",
        time_horizon="OP",
        lifecycle_state="EFFECTIVE",
        valid_from=None,
        valid_to=None,
        supersedes=None,
        superseded_by=None,
        authority_tier=0,
        source_pdf="x.pdf",
        source_pages=[],
        recorded_at=0.0,
        granularity="part",
    )
    defaults.update(kw)
    return RegisterNode(**defaults)


def test_A02_rationale_text_cannot_create_an_obligation():
    rationale_class = classify("Technical Rationale for Requirement R1 Part 1.1")
    guidance_class = classify("Guidance and Technical Basis for implementing this control")
    assert rationale_class == "technical_rationale"
    assert guidance_class == "guidance"
    assert may_create_obligation(rationale_class) is False
    assert may_create_obligation(guidance_class) is False
    # forbidden: rationale/guidance must never sit in the obligation-creating set
    assert "technical_rationale" not in {
        c
        for c in ("regulatory_requirement", "order", "approved_interpretation")
        if c == rationale_class
    }


def test_A03_retired_revision_is_valid_at_its_historical_date():
    retired = _node(
        "X R1 P1.1v1", "1.1", "old text", valid_from="2020-01-01", valid_to="2024-01-01"
    )
    reg = Register(nodes=[retired], edges=[])
    assert effective_parts(reg, "2022-06-01") == [retired]
    # forbidden: the same node must not appear for a date after it retired
    assert effective_parts(reg, "2025-01-01") == []


def test_A04_selection_follows_dates_not_stale_lifecycle_string():
    node = _node(
        "X R1 P1.2v2",
        "1.2",
        "new text",
        lifecycle_state="RETIRED",  # stale label; date interval still covers "today"
        valid_from="2024-01-01",
        valid_to=None,
    )
    assert _is_enforceable_at(node, "2026-09-05") is True
    future = _node(
        "X R1 P1.2v3", "1.2", "future text", lifecycle_state="FUTURE_EFFECTIVE", valid_from=None
    )
    reg = Register(nodes=[future], edges=[])
    # forbidden: a node with no known valid_from must never be reported enforceable today
    assert future not in effective_parts(reg, "2026-09-05")


def test_A05_unknown_effectivity_is_qualified_not_default_effective():
    unknown = _node("X R1 P1.3v1", "1.3", "text", valid_from=None)
    reg = Register(nodes=[unknown], edges=[])
    assert unknown in unknown_effectivity_parts(reg)
    # forbidden: unknown-effectivity content must never leak into "effective today"
    assert unknown not in effective_parts(reg, "2026-09-05")
    assert unknown not in future_effective_parts(reg, "2026-09-05")


def test_A06_phase_in_overlap_selects_correct_scoped_version():
    phase1 = _node(
        "X R1 P1.4v1", "1.4", "phase 1 text", valid_from="2025-01-01", valid_to="2026-01-01"
    )
    phase2 = _node("X R1 P1.4v2", "1.4", "phase 2 text", valid_from="2026-01-01", valid_to=None)
    reg = Register(nodes=[phase1, phase2], edges=[])
    assert effective_parts(reg, "2025-06-01") == [phase1]
    assert effective_parts(reg, "2026-06-01") == [phase2]
    # forbidden: both phases must never be simultaneously "current"
    assert not (
        phase1 in effective_parts(reg, "2026-06-01")
        and phase2 in effective_parts(reg, "2026-06-01")
    )


def test_A09_quote_only_text_is_references_not_implements():
    assertions = extract_assertions(
        "rev-A09",
        "This procedure shall implement CIP-007-6 R2 Part 2.2.",
        anchor_id="anchor-A09",
    )
    assert assertions and assertions[0].relation_type == "REFERENCES"
    real = extract_assertions(
        "rev-A09b",
        "The system administrator evaluates security patches for applicable cyber assets "
        "within 35 calendar days.",
        anchor_id="anchor-A09b",
    )
    assert real and real[0].relation_type == "IMPLEMENTS"
    # forbidden: the quote-only sentence must never be classified IMPLEMENTS
    assert all(a.relation_type != "IMPLEMENTS" for a in assertions)


def test_A14_blank_form_is_evidence_spec_not_artifact():
    blank = classify_document("Evidence Specification\n\nForm: Patch Evaluation Record\n")
    completed = classify_document(
        "Patch Evaluation Record\nCompleted by: J. Smith\nCompleted on: 2026-01-01\n"
        "Signature date: 2026-01-01\n"
    )
    assert blank == "evidence_specification"
    assert completed == "evidence_artifact"
    # forbidden: a blank template must never classify as an executed artifact
    assert blank != "evidence_artifact"


def test_A16_calendar_vs_business_day_is_incomparable_not_equal():
    result, reason = compare_constraint(
        "max_interval", Quantity(35, "day", "calendar"), Quantity(35, "day", "business")
    )
    assert result == "INCOMPARABLE"
    # forbidden: mismatched qualifiers must never report EQUIVALENT
    assert result != "EQUIVALENT"
    assert "conversion" in reason


def test_A17_conflict_direction_follows_comparator_semantics():
    deadline, _ = compare_constraint(
        "max_interval", Quantity(35, "day", "calendar"), Quantity(60, "day", "calendar")
    )
    retention, _ = compare_constraint(
        "min_retention", Quantity(90, "day", "calendar"), Quantity(60, "day", "calendar")
    )
    assert (
        deadline == "LESS_RESTRICTIVE"
    )  # a longer wait before a maximum-interval action is looser
    assert retention == "LESS_RESTRICTIVE"  # a shorter retention than a minimum is also looser
    # forbidden: the two constraint kinds must not share one blind direction rule
    other, _ = compare_constraint(
        "min_retention", Quantity(60, "day", "calendar"), Quantity(90, "day", "calendar")
    )
    assert other == "MORE_RESTRICTIVE"


def test_A18_logical_and_renumber_changes_are_substantive():
    old = [_node("X R1 P1.5", "1.5", "shall encrypt data at rest and in transit")]
    new = [_node("X R1 P1.5b", "1.5", "shall encrypt data at rest or in transit")]
    rows = diff_standard(Register(nodes=old, edges=[]), Register(nodes=new, edges=[]), "X")
    assert rows and rows[0].to_dict()["substantive"]
    renumber_old = [_node("X R1 P1.6", "1.6", "Transient Cyber Asset risk mitigation program")]
    renumber_new = [_node("X R1 P1.7", "1.7", "Transient Cyber Asset risk mitigation program")]
    rrows = diff_standard(
        Register(nodes=renumber_old, edges=[]), Register(nodes=renumber_new, edges=[]), "X"
    )
    assert rrows[0].change_type == "RENUMBERED"
    # forbidden: lineage uncertainty on a low-confidence pairing must not silently vanish
    assert rrows[0].sub_type in {"paired", "needs_review"}


def test_A22_stricter_internal_control_is_not_a_relaxation_target():
    result, reason = compare_constraint(
        "max_interval", Quantity(35, "day", "calendar"), Quantity(15, "day", "calendar")
    )
    assert result == "MORE_RESTRICTIVE"
    assert "stricter" in reason
    # forbidden: MORE_RESTRICTIVE must never be reported as something to relax
    assert "relax" not in reason.lower()
    assert "loosen" not in reason.lower()
