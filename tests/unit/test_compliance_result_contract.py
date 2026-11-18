"""Product/result contract tests (END_TO_END Phase 1 / foundation P1).

Covers the §3 dimension vocabularies, the legacy-coverage → alignment mapping,
the truth-class table map, the review projection (SME reasons vs engineering
triage), the new controlled failure codes, the non-destructive migration onto a
populated store, and the reading/council-disagreement path that previously
emitted an unregistered unresolved code.
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.determination import (
    UNRESOLVED_CODES,
    AssessmentResult,
    DeterminationContractError,
    GroundedGap,
)
from portal.modules.compliance.core.result_contract import (
    APPLICABILITY_STATES,
    DOCUMENTARY_ALIGNMENT,
    IMPLEMENTATION_EVIDENCE,
    SOURCE_READINESS,
    SOURCE_ROLES,
    TEMPORAL_CURRENCY,
    TRUTH_CLASSES,
    dimensions_of,
    documentary_alignment_of,
    is_source_role,
    review_reason_for,
    truth_class_of_table,
)


def _result(**overrides):
    base: dict = {
        "assessment_id": "a1",
        "run_id": "r1",
        "engine_version": "t",
        "input_fingerprint": "f",
        "requirement_id": "CIP-007-6 R2 Part 2.2",
    }
    base.update(overrides)
    return AssessmentResult(**base)


def test_source_role_vocabulary_is_the_contract_set():
    expected = {
        "REGULATORY_REQUIREMENT",
        "APPLICABILITY",
        "DEFINITION",
        "MEASURE",
        "TECHNICAL_BASIS",
        "IMPLEMENTATION_PLAN",
        "FORMAL_INTERPRETATION",
        "REGULATORY_ORDER",
        "INTERNAL_POLICY",
        "OPERATIVE_PROCEDURE",
        "WORK_INSTRUCTION",
        "TRACEABILITY_ASSERTION",
        "EVIDENCE_SPECIFICATION",
        "EVIDENCE_ARTIFACT",
        "COMMENTARY",
        # P4 additions: structural internal-corpus text is never operative,
        # and document-control pages source metadata rather than duties.
        "TABLE_OF_CONTENTS",
        "DOCUMENT_CONTROL",
        # DATA_TRUTH D3 / D-DT-19: a dated change-history entry (a headingless
        # revision table leaks section-shaped rows); never operative content.
        "REVISION_LOG",
    }
    assert set(SOURCE_ROLES) == expected
    assert all(SOURCE_ROLES[r] for r in SOURCE_ROLES)  # meaning text is load-bearing
    assert is_source_role("MEASURE") and not is_source_role("authority_tier_1")


def test_dimension_vocabularies_match_the_spec():
    assert SOURCE_READINESS == ("READY", "INCOMPLETE", "CONFLICTED", "UNKNOWN")
    assert TEMPORAL_CURRENCY == ("CURRENT", "FUTURE", "HISTORICAL", "UNKNOWN")
    assert APPLICABILITY_STATES == ("APPLIES", "DOES_NOT_APPLY", "UNKNOWN")
    assert DOCUMENTARY_ALIGNMENT == ("ALIGNED", "PARTIAL", "MISALIGNED", "UNRESOLVED")
    assert IMPLEMENTATION_EVIDENCE == ("SUFFICIENT", "PARTIAL", "ABSENT", "NOT_ASSESSED")
    assert TRUTH_CLASSES == ("source_fact", "derived_assertion", "organizational_decision")


def test_truth_class_covers_every_canonical_table_and_rejects_unknowns():
    known = {
        "source_documents",
        "document_revisions",
        "source_sections",
        "source_spans",
        "standard_revisions",
        "requirement_nodes",
        "definitions",
        "effectivity_assertions",
        "authority_assertions",
        "entity_profiles",
        "scope_revisions",
        "asset_groups",
        "obligation_atoms",
        "obligation_expressions",
        "relationship_assertions",
        "internal_controls",
        "activities",
        "evidence_specs",
        "evidence_artifacts",
        "analysis_runs",
        "claims",
        "claim_evidence",
        "findings",
        "assessment_results",
        "corpus_boundary_proofs",
        "corpus_snapshots",
        "catalog_snapshots",
        "index_manifests",
        "outbox_events",
        "review_events",
        "policy_decisions",
        "change_scenarios",
        "work_items",
    }
    for t in known:
        assert truth_class_of_table(t) in TRUTH_CLASSES, t
    with pytest.raises(ValueError):
        truth_class_of_table("definitely_not_a_table")


def test_documentary_alignment_maps_every_legacy_label():
    assert documentary_alignment_of("FULL") == "ALIGNED"
    assert documentary_alignment_of("PARTIAL") == "PARTIAL"
    assert documentary_alignment_of("NONE") == "MISALIGNED"
    assert documentary_alignment_of("UNRESOLVED") == "UNRESOLVED"
    assert documentary_alignment_of("NEEDS_REVIEW") == "UNRESOLVED"
    assert documentary_alignment_of("NOT_APPLICABLE") == "UNRESOLVED"
    assert documentary_alignment_of("SOMETHING_NEW") == "UNRESOLVED"


def test_contradiction_gap_upgrades_partial_to_misaligned():
    weaker = GroundedGap(gap_id="g1", kind="WEAKER_COMMITMENT", missing_commitment="x")
    conflict = GroundedGap(gap_id="g2", kind="CONTRADICTION", missing_commitment="y")
    assert documentary_alignment_of("PARTIAL", [weaker]) == "PARTIAL"
    assert documentary_alignment_of("PARTIAL", [conflict]) == "MISALIGNED"
    assert documentary_alignment_of("FULL", []) == "ALIGNED"


def test_review_is_a_projection_not_a_gate():
    result = _result(documentary_coverage="PARTIAL")
    assert review_reason_for(result) == ""
    assert dimensions_of(result)["review_required"] is False


def test_engineering_failures_are_not_review_reasons():
    for code in (
        "U02_MISSING_GOVERNING_SOURCE",
        "U03_EXTRACTION_FAILED",
        "U04_RETRIEVAL_INCOMPLETE",
        "U09_SEMANTIC_ALIGNMENT_UNKNOWN",
        "U14_INCOMPLETE_SOURCE_BUNDLE",
        "U15_PROJECTION_MISMATCH",
        "U16_INVALID_CITATION",
    ):
        result = _result(
            documentary_coverage="UNRESOLVED",
            unresolved_code=code,
            missing_fact={"x": 1},
        )
        assert review_reason_for(result) == "", code  # engineering triage, not SME


def test_interpretive_conflict_and_scope_are_named_review_reasons():
    conflict = _result(
        documentary_coverage="UNRESOLVED",
        unresolved_code="U17_INTERPRETIVE_CONFLICT",
        missing_fact={"readings": []},
        uncertainties=[],
    )
    assert review_reason_for(conflict) == "S04_INTERPRETATION_DISPUTE"

    scope = _result(
        documentary_coverage="UNRESOLVED",
        unresolved_code="U05_SCOPE_UNDECLARED",
        missing_fact={"scope": "external fact"},
    )
    assert review_reason_for(scope) == "S01_SCOPE_DECLARATION"


def test_readiness_follows_source_failure_codes():
    assert dimensions_of(_result(documentary_coverage="PARTIAL"))["source_readiness"] == "READY"
    for code in (
        "U02_MISSING_GOVERNING_SOURCE",
        "U03_EXTRACTION_FAILED",
        "U14_INCOMPLETE_SOURCE_BUNDLE",
        "U15_PROJECTION_MISMATCH",
    ):
        r = _result(
            documentary_coverage="UNRESOLVED",
            unresolved_code=code,
            missing_fact={"requirement_id": "x"},
        )
        assert dimensions_of(r)["source_readiness"] == "INCOMPLETE", code
    for code in ("U06_CONFLICTING_INTERNAL_SOURCES", "U17_INTERPRETIVE_CONFLICT"):
        r = _result(
            documentary_coverage="UNRESOLVED",
            unresolved_code=code,
            missing_fact={"requirement_id": "x"},
        )
        assert dimensions_of(r)["source_readiness"] == "CONFLICTED", code


def test_model_failures_leave_sources_ready():
    r = _result(
        documentary_coverage="UNRESOLVED",
        unresolved_code="U09_SEMANTIC_ALIGNMENT_UNKNOWN",
        missing_fact={"failure": ""},
    )
    assert dimensions_of(r)["source_readiness"] == "READY"


def test_new_controlled_failure_codes_exist():
    for code in (
        "U14_INCOMPLETE_SOURCE_BUNDLE",
        "U15_PROJECTION_MISMATCH",
        "U16_INVALID_CITATION",
        "U17_INTERPRETIVE_CONFLICT",
    ):
        assert code in UNRESOLVED_CODES
        assert UNRESOLVED_CODES[code]  # names its required payload


def test_reading_council_disagreement_is_a_valid_unresolved_result():
    """Regression: the disagreement path emitted an unregistered code and would
    have crashed AssessmentResult.__post_init__ before this phase."""
    result = _result(
        documentary_coverage="UNRESOLVED",
        unresolved_code="U17_INTERPRETIVE_CONFLICT",
        missing_fact={
            "reading_documentary_coverage": "NONE",
            "council_determination": "SUPPORTED",
            "reading_rationale": "r",
            "council_rationale": "c",
            "reading_source_slice_ids": ["gov-x"],
        },
    )
    assert result.unresolved_code == "U17_INTERPRETIVE_CONFLICT"
    dims = dimensions_of(result)
    assert dims["source_readiness"] == "CONFLICTED"
    assert dims["review_reason"] == "S04_INTERPRETATION_DISPUTE"
    assert dims["review_required"] is True


def test_assessment_result_rejects_unknown_dimension_values():
    with pytest.raises(DeterminationContractError):
        _result(source_readiness="PROBABLY")
