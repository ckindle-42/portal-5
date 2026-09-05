"""The determination contract (TASK_COMPLIANCE_REASONING_V3 P1).

Every obligation-level result the module produces is exactly one ``Determination``.
Four of the five are *answers*. ``UNRESOLVED`` is the only non-answer, and it may
never be emitted without an ``UnresolvedCode`` and the specific missing fact that
would settle it.

The distinction that matters: ``ABSENT`` means "we read the corpus to its declared
boundary and nothing addresses this obligation" — a gap, a real finding, the answer
to 'where are our gaps'. ``UNRESOLVED`` means "the module could not decide" — a
defect budget item, not a result. Collapsing the two is what made the previous build
report zero gaps against a real corpus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ── determinations ──────────────────────────────────────────────────────────
# SUPPORTED     internal text satisfies the atom; anchors on both sides resolve
# PARTIAL       requirement-level: some mandatory atoms supported, others not
# CONTRADICTED  internal text conflicts with the governing constraint; both anchors
# ABSENT        exhaustive search of the declared corpus found nothing addressing it
# UNRESOLVED    could not decide — requires an UnresolvedCode and a missing fact
Determination = Literal["SUPPORTED", "PARTIAL", "CONTRADICTED", "ABSENT", "UNRESOLVED"]
DETERMINATIONS: tuple[str, ...] = (
    "SUPPORTED",
    "PARTIAL",
    "CONTRADICTED",
    "ABSENT",
    "UNRESOLVED",
)
ANSWERS: tuple[str, ...] = ("SUPPORTED", "PARTIAL", "CONTRADICTED", "ABSENT")

# ── closed enum of reasons the module could not decide ──────────────────────
# Each code names a required payload field. A code with an empty payload is
# invalid and must be rejected at the repository boundary, not logged and kept.
UNRESOLVED_CODES: dict[str, str] = {
    "U01_AMBIGUOUS_GOVERNING_LOGIC": "expression_id + the two readings, verbatim",
    "U02_MISSING_GOVERNING_SOURCE": "logical_id/URL of the governing source that did not resolve",
    "U03_EXTRACTION_FAILED": "revision_id + page/section + parser error",
    "U04_RETRIEVAL_INCOMPLETE": "index_generation + truncation flag + budget that was hit",
    "U05_SCOPE_UNDECLARED": "the asset/function fact that is missing",
    "U06_CONFLICTING_INTERNAL_SOURCES": "both assertion_ids and both verbatim spans",
    "U07_INTENT_UNKNOWN": "control_id whose policy_decisions row is absent",
    "U08_EVIDENCE_PERIOD_UNAVAILABLE": "evidence_spec_id + the period requested",
}

# ── closed enum of decisions an SME may be asked for ────────────────────────
# Anything outside this set in the review queue is a defect: it means the module
# pushed a question at a human that the source text already answers.
SME_DECISION_KINDS: dict[str, str] = {
    "S01_SCOPE_DECLARATION": "which assets/functions/jurisdictions are in scope",
    "S02_INTENTIONAL_STRICTNESS": "is this stricter-than-required internal rule deliberate",
    "S03_ACCEPT_PROPOSED_REDLINE": "accept, amend or decline a generated draft revision",
    "S04_INTERPRETATION_DISPUTE": "two readings each with source support — both must be attached",
    "S05_EVIDENCE_ATTESTATION": "did the recurring activity actually occur in the period",
}

FieldName = Literal[
    "actor",
    "action",
    "object",
    "population",
    "trigger",
    "modality",
    "condition",
    "exception",
    "deadline_cadence",
    "evidence_expectation",
]
FIELDS: tuple[str, ...] = (
    "actor",
    "action",
    "object",
    "population",
    "trigger",
    "modality",
    "condition",
    "exception",
    "deadline_cadence",
    "evidence_expectation",
)


class DeterminationContractError(ValueError):
    """A result violated the contract. Never downgrade this to a warning."""


@dataclass
class FieldResult:
    """One field of one obligation atom compared against internal text."""

    field: str
    determination: str
    governing_anchor_id: str = ""
    internal_anchor_id: str = ""
    governing_value: str = ""
    internal_value: str = ""
    comparator: str = ""  # e.g. "max_interval", "min_retention", "set_membership"
    note: str = ""

    def __post_init__(self) -> None:
        if self.field not in FIELDS:
            raise DeterminationContractError(f"unknown field: {self.field}")
        if self.determination not in DETERMINATIONS:
            raise DeterminationContractError(f"unknown determination: {self.determination}")


@dataclass
class AtomResult:
    """The determination for one obligation atom, with its evidence."""

    atom_id: str
    determination: str
    field_results: list[FieldResult] = field(default_factory=list)
    governing_anchor_ids: list[str] = field(default_factory=list)
    internal_anchor_ids: list[str] = field(default_factory=list)
    counterevidence_anchor_ids: list[str] = field(default_factory=list)
    unresolved_code: str = ""
    missing_fact: dict = field(default_factory=dict)
    boundary_proof_id: str = ""  # required for ABSENT — see P4
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.determination not in DETERMINATIONS:
            raise DeterminationContractError(f"unknown determination: {self.determination}")
        if self.determination == "UNRESOLVED":
            if self.unresolved_code not in UNRESOLVED_CODES:
                raise DeterminationContractError(
                    "UNRESOLVED requires a code from UNRESOLVED_CODES, got "
                    f"{self.unresolved_code!r}"
                )
            if not self.missing_fact:
                raise DeterminationContractError(
                    f"{self.unresolved_code} requires missing_fact: "
                    f"{UNRESOLVED_CODES[self.unresolved_code]}"
                )
        if self.determination in ("SUPPORTED", "CONTRADICTED"):
            if not self.governing_anchor_ids or not self.internal_anchor_ids:
                raise DeterminationContractError(
                    f"{self.determination} requires anchors on both sides (C4)"
                )
        if self.determination == "ABSENT" and not self.boundary_proof_id:
            raise DeterminationContractError(
                "ABSENT requires a corpus boundary proof (C1/P4) — absence of a "
                "search result is not absence of a control"
            )


@dataclass
class RequirementResult:
    """The rolled-up determination for one requirement/Part."""

    node_id: str
    determination: str
    atom_results: list[AtomResult] = field(default_factory=list)
    expression_id: str = ""
    valid_at: str = ""
    known_at: str = ""
    applicability: str = ""  # APPLIES | NOT_APPLICABLE | UNKNOWN | CONFLICTED
    unresolved_code: str = ""
    missing_fact: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.determination not in DETERMINATIONS:
            raise DeterminationContractError(f"unknown determination: {self.determination}")
        if self.determination == "UNRESOLVED" and self.unresolved_code not in UNRESOLVED_CODES:
            raise DeterminationContractError("UNRESOLVED requires a code (C2)")


def is_answer(determination: str) -> bool:
    return determination in ANSWERS
