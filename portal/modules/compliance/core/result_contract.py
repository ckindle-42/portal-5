"""The product/result contract dimensions (END_TO_END P1 / foundation §3).

`AssessmentResult` already separates the documentary verdict from
applicability. This module adds the remaining dimensions the product contract
requires — source readiness, temporal currency, implementation evidence, and
the review projection — plus the controlled vocabularies they draw from:

* **Truth classes** (§3.1): every canonical table is a source fact, a
  machine-derived assertion, or an organizational decision. The class is a
  property of the table, exposed so serialization and audits can mark every
  persisted row — a derived claim may never masquerade as a source fact.
* **Source roles** (§3.2): a controlled role vocabulary for source material.
  Precedence is contextual (relationship- and question-specific); the
  vocabulary deliberately carries NO numeric authority tier.
* **Result dimensions** (§3.4): readiness, currency, applicability,
  documentary alignment, implementation evidence, and review need are separate
  fields. `review_required` is an OUTPUT (a projection of named reasons), never
  a prerequisite for comparison.

The old public verdict (`documentary_coverage`: FULL/PARTIAL/NONE/…) remains
the route vocabulary; `documentary_alignment_of` maps it explicitly onto the
contract's ALIGNED/PARTIAL/MISALIGNED/UNRESOLVED so no legacy label silently
changes meaning.
"""

from __future__ import annotations

from typing import Any

# ── §3.1 three classes of truth ─────────────────────────────────────────────

TRUTH_CLASSES: tuple[str, ...] = ("source_fact", "derived_assertion", "organizational_decision")

_SOURCE_FACT_TABLES = frozenset(
    {
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
    }
)
_DERIVED_ASSERTION_TABLES = frozenset(
    {
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
    }
)
_ORGANIZATIONAL_DECISION_TABLES = frozenset(
    {
        "review_events",
        "policy_decisions",
        "change_scenarios",
        "work_items",
    }
)


def truth_class_of_table(table: str) -> str:
    """The truth class a canonical table's rows belong to.

    Unknown tables are NOT guessed into a class — an unmapped table means the
    contract has a hole and the caller must fail loudly (or map it) rather
    than persist an unlabelled assertion.
    """
    if table in _SOURCE_FACT_TABLES:
        return "source_fact"
    if table in _DERIVED_ASSERTION_TABLES:
        return "derived_assertion"
    if table in _ORGANIZATIONAL_DECISION_TABLES:
        return "organizational_decision"
    raise ValueError(f"table {table!r} is not mapped to a truth class")


# ── §3.2 contextual source roles ────────────────────────────────────────────
# Meaning text is load-bearing: it is what the reader packet and the report
# surface next to material of that role, so a Measure can never silently read
# as an extra requirement. No numeric tier — precedence is question-specific.

SOURCE_ROLES: dict[str, str] = {
    "REGULATORY_REQUIREMENT": "Governing mandatory text for the selected jurisdiction/date.",
    "APPLICABILITY": "Determines entity/system/asset scope.",
    "DEFINITION": "Controls defined-term meaning.",
    "MEASURE": "Evidence examples/expectations; not an additional unstated duty.",
    "TECHNICAL_BASIS": "Interpretive and design context; does not silently become binding text.",
    "IMPLEMENTATION_PLAN": "Transition, phased applicability, and effective-date rules.",
    "FORMAL_INTERPRETATION": "Authoritative clarification with its own jurisdiction/effectivity.",
    "REGULATORY_ORDER": "Approval/directive context with explicitly modeled effect.",
    "INTERNAL_POLICY": "Organization-level direction and risk choice.",
    "OPERATIVE_PROCEDURE": "Instructions used to implement the obligation.",
    "WORK_INSTRUCTION": "Lower-level execution steps.",
    "TRACEABILITY_ASSERTION": "A claimed mapping or copied requirement; not implementation by itself.",
    "EVIDENCE_SPECIFICATION": "What the organization says must be retained or demonstrated.",
    "EVIDENCE_ARTIFACT": "Evidence of actual performance, distinct from documented design.",
    "COMMENTARY": "Nonbinding explanation.",
    # P4 additions for the internal corpus: structural text is never operative,
    # and document-control pages are the SOURCE of metadata, not duties.
    "TABLE_OF_CONTENTS": "Structural navigation text; never operative content.",
    "DOCUMENT_CONTROL": "Document-control metadata (owner, approvals, revision history); "
    "sources effectivity/version facts, never operative text.",
}


def is_source_role(role: str) -> bool:
    return role in SOURCE_ROLES


# ── §3.4 separated result dimensions ────────────────────────────────────────

SOURCE_READINESS: tuple[str, ...] = ("READY", "INCOMPLETE", "CONFLICTED", "UNKNOWN")
TEMPORAL_CURRENCY: tuple[str, ...] = ("CURRENT", "FUTURE", "HISTORICAL", "UNKNOWN")
APPLICABILITY_STATES: tuple[str, ...] = ("APPLIES", "DOES_NOT_APPLY", "UNKNOWN")
DOCUMENTARY_ALIGNMENT: tuple[str, ...] = ("ALIGNED", "PARTIAL", "MISALIGNED", "UNRESOLVED")
IMPLEMENTATION_EVIDENCE: tuple[str, ...] = ("SUFFICIENT", "PARTIAL", "ABSENT", "NOT_ASSESSED")

#: legacy public verdict → contract alignment. Explicit, total, and the only
#: place the mapping lives, so `documentary_coverage` can be marked deprecated
#: at route boundaries without meaning drift.
_ALIGNMENT_MAP: dict[str, str] = {
    "FULL": "ALIGNED",
    "PARTIAL": "PARTIAL",
    "NONE": "MISALIGNED",
    "UNRESOLVED": "UNRESOLVED",
    # applicability carries the meaning for these two; alignment is undefined
    "NEEDS_REVIEW": "UNRESOLVED",
    "NOT_APPLICABLE": "UNRESOLVED",
}


def documentary_alignment_of(documentary_coverage: str, gaps: list[Any] | None = None) -> str:
    """Map the public coverage verdict onto the contract's alignment field.

    A CONTRADICTION gap is a misalignment even when other duties carry a
    PARTIAL verdict — the conflict is the stronger signal for this dimension.
    """
    alignment = _ALIGNMENT_MAP.get(documentary_coverage, "UNRESOLVED")
    if alignment == "PARTIAL" and any(
        str(getattr(g, "kind", "")) == "CONTRADICTION" for g in gaps or []
    ):
        return "MISALIGNED"
    return alignment


def review_reason_for(result: Any) -> str:
    """The named SME review reason for a result, or "" when none applies.

    Only genuine human questions produce review: interpretation disputes with
    source support on both sides (S04), intentional-strictness facts (S02),
    real scope facts the sources cannot settle (S01), exception/attestation
    questions. Engineering defects (UNRESOLVED_* codes, extraction and
    retrieval failures) are NOT review reasons — they route to engineering
    triage and the module owes an answer, not a question.
    """
    if result.documentary_coverage == "NOT_APPLICABLE":
        return ""
    if str(getattr(result, "unresolved_code", "")) == "U17_INTERPRETIVE_CONFLICT":
        return "S04_INTERPRETATION_DISPUTE"
    uncertainties = list(getattr(result, "uncertainties", []) or [])
    codes = {
        str(u.get("code", "")) if isinstance(u, dict) else str(getattr(u, "code", ""))
        for u in uncertainties
    }
    council = getattr(result, "council_result", None)
    escalated = bool(council) and str(
        (council or {}).get("escalation", "") if isinstance(council, dict) else ""
    )
    if "U17_INTERPRETIVE_CONFLICT" in codes or escalated:
        return "S04_INTERPRETATION_DISPUTE"
    if (
        result.documentary_coverage == "UNRESOLVED"
        and str(getattr(result, "unresolved_code", "")) == "U05_SCOPE_UNDECLARED"
    ):
        # a real external scope fact only — the module first owes its best
        # reading of what the documents themselves settle
        return "S01_SCOPE_DECLARATION"
    return ""


def dimensions_of(result: Any) -> dict[str, Any]:
    """Compute the §3.4 dimension fields for one AssessmentResult.

    Readiness/currency/evidence start honest: READY only when the governing
    bundle resolved, currency UNKNOWN until the lifecycle layer (Phase 5)
    supplies sourced effectivity, evidence NOT_ASSESSED until the evidence
    layer (Phase 10) runs. `review_required` is the projection's boolean.
    """
    reason = review_reason_for(result)
    code = str(getattr(result, "unresolved_code", ""))
    # Readiness derives from the source layer's own failure codes: a missing
    # or damaged component is INCOMPLETE; conflicting governing material is
    # CONFLICTED. Model-side codes (U09/U10/U11/U12) leave readiness READY —
    # the sources were fine, the reading question failed.
    if code in (
        "U02_MISSING_GOVERNING_SOURCE",
        "U03_EXTRACTION_FAILED",
        "U04_RETRIEVAL_INCOMPLETE",
        "U14_INCOMPLETE_SOURCE_BUNDLE",
        "U15_PROJECTION_MISMATCH",
    ):
        readiness = "INCOMPLETE"
    elif code in ("U06_CONFLICTING_INTERNAL_SOURCES", "U17_INTERPRETIVE_CONFLICT"):
        readiness = "CONFLICTED"
    else:
        readiness = "READY"
    return {
        "source_readiness": readiness,
        "temporal_currency": "UNKNOWN",
        "documentary_alignment": documentary_alignment_of(
            str(getattr(result, "documentary_coverage", "UNRESOLVED")),
            list(getattr(result, "gaps", []) or []),
        ),
        "implementation_evidence": "NOT_ASSESSED",
        "review_required": bool(reason),
        "review_reason": reason,
    }
