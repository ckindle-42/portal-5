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
from typing import Any, Literal

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
    # ── reading-architecture codes (IMPLEMENTATION_BRIEF_COMPLIANCE_READING) ──
    # A semantic alignment pass that cannot establish SAME/DIFFERENT with quorum
    # must return UNKNOWN — it may never be silently dropped or fed to arithmetic.
    "U09_SEMANTIC_ALIGNMENT_UNKNOWN": "link_id + governing/candidate refs + missing context",
    # The council ran but no determination reached quorum (drop/timeout/invalid).
    "U10_COUNCIL_UNRESOLVED": "raw-opinion trace + the failure that prevented quorum",
    # The source-linked explanation violated a closed consistency/evidence rule.
    "U11_ASSESSMENT_CONTRACT_FAILED": "violated report rule + the offending ref/field",
    # A SAME link carried a quantity the reviewed comparator cannot place.
    "U12_CONSTRAINT_INCOMPARABLE": "bound operands + comparator explanation",
    # The pinned corpus/source fingerprint moved between acquisition and use.
    "U13_SNAPSHOT_MISMATCH": "expected fingerprint + actual fingerprint",
    # ── product-contract codes (END_TO_END P1 / foundation §P1) ──────────────
    # A required governing-bundle component (Measure, Technical Basis, lead-in,
    # applicability, implementation plan) was missing or truncated.
    "U14_INCOMPLETE_SOURCE_BUNDLE": "requirement_id + the missing/truncated component",
    # A graph/lexical/vector projection no longer matches the canonical snapshot.
    "U15_PROJECTION_MISMATCH": "projection kind + canonical fingerprint + projection fingerprint",
    # A result cited an id that does not resolve to a pinned source span.
    "U16_INVALID_CITATION": "the unresolvable citation id + where it was cited",
    # Two governing readings each with source support; not an engineering defect.
    "U17_INTERPRETIVE_CONFLICT": "both readings + the source spans supporting each",
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
    missing_fact: dict[str, Any] = field(default_factory=dict)
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
    missing_fact: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.determination not in DETERMINATIONS:
            raise DeterminationContractError(f"unknown determination: {self.determination}")
        if self.determination == "UNRESOLVED" and self.unresolved_code not in UNRESOLVED_CODES:
            raise DeterminationContractError("UNRESOLVED requires a code (C2)")


# ── reading-architecture records ────────────────────────────────────────────
# These are the shared contracts of the one authoritative assessment path
# (IMPLEMENTATION_BRIEF_COMPLIANCE_READING_20260912 §4). They are deliberately
# data-only: the orchestration lives in assessment.py, the semantic reading in
# obligation_alignment.py, the arithmetic in gate.py, the reporting in
# assessment_report.py. Every projection (CoverageCell, operations.Determination,
# AtomResult, RequirementResult) is derived from one AssessmentResult — never an
# independent decision engine.

#: documentary coverage values — the public verdict vocabulary.
DOCUMENTARY_COVERAGE: tuple[str, ...] = (
    "FULL",
    "PARTIAL",
    "NONE",
    "UNRESOLVED",
    "NEEDS_REVIEW",
    "NOT_APPLICABLE",
)
#: acquisition modes for a pinned CandidateSet.
ACQUISITION_MODES: tuple[str, ...] = ("RETRIEVAL", "EXPLICIT_SET")
#: completeness states for a corpus/boundary snapshot.
COMPLETENESS_STATES: tuple[str, ...] = ("COMPLETE", "PARTIAL", "UNKNOWN")
#: source-function classification read semantically by the alignment pass.
SOURCE_FUNCTIONS: tuple[str, ...] = (
    "OPERATIVE_COMMITMENT",
    "DEFINITION",
    "AUTHORITY_RECORD",
    "CROSS_REFERENCE_TABLE",
    "CONTENTS",
    "OTHER",
)
#: categorical relation between a candidate clause and the governing duty.
ALIGNMENT_RELATIONS: tuple[str, ...] = ("SAME", "DIFFERENT", "UNKNOWN")
#: population overlap reading.
POPULATION_OVERLAPS: tuple[str, ...] = ("OVERLAPPING", "DISJOINT", "UNKNOWN")


@dataclass
class SourceSlice:
    """An exact, verified span of a stored source chunk.

    ``char_start``/``char_end`` are half-open offsets **within the stored chunk
    text** — never the original document/Docling coordinates, which are kept
    separately in ``doc_char_start``/``doc_char_end`` and are not
    interchangeable. A slice is only ever emitted by the application from stored
    text; a model's reconstructed quote is never accepted as a slice.
    """

    slice_id: str
    ref: str  # operator/model-visible locator, e.g. "V11 #chunk27 p8"
    document_id: str
    revision_hash: str
    chunk_id: str
    locator: str = ""  # section/heading/page, human-readable
    text: str = ""
    char_start: int = 0
    char_end: int = 0
    doc_char_start: int | None = None
    doc_char_end: int | None = None
    role: str = "candidate"  # governing | candidate | reference | proposed


@dataclass
class CorpusSnapshot:
    """A pinned view of the retrieved corpus for one assessment."""

    snapshot_id: str
    kb_id: str
    manifest_hash: str = ""
    index_generation: str = ""
    table_name: str = ""
    table_version: int = 0
    document_revision_hashes: dict[str, str] = field(default_factory=dict)
    candidate_identities: list[str] = field(default_factory=list)
    acquisition_mode: str = "RETRIEVAL"
    completeness: str = "UNKNOWN"
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if self.acquisition_mode not in ACQUISITION_MODES:
            raise DeterminationContractError(
                f"acquisition_mode must be one of {ACQUISITION_MODES}, got {self.acquisition_mode!r}"
            )
        if self.completeness not in COMPLETENESS_STATES:
            raise DeterminationContractError(
                f"completeness must be one of {COMPLETENESS_STATES}, got {self.completeness!r}"
            )


@dataclass
class CandidateRecord:
    """One full retrieved candidate — text and identifiers preserved."""

    candidate_id: str
    document_id: str
    chunk_id: str
    text: str
    locator: str = ""
    layer: str = ""
    rerank_score: float = 0.0
    relevant: bool = False
    anchor_verified: bool = True
    revision_hash: str = ""
    char_start: int = 0
    char_end: int = 0
    unresolved_reason: str = ""
    source_slice: SourceSlice | None = None


@dataclass
class CandidateSet:
    """Every supplied locatable text candidate plus its retrieval diagnostics.

    ``retrieval_annotations`` (scores/``relevant`` flags) and ``unresolved``
    (non-text pointers, missing chunks) are diagnostics that travel with the
    candidates. A non-text pointer can never become quoted documentary evidence,
    and an unread candidate is never silently discarded to manufacture absence.
    """

    records: list[CandidateRecord] = field(default_factory=list)
    retrieval_annotations: list[dict[str, Any]] = field(default_factory=list)
    acquisition_receipt: dict[str, Any] = field(default_factory=dict)
    unresolved: list[dict[str, Any]] = field(default_factory=list)

    def by_id(self, candidate_id: str) -> CandidateRecord | None:
        return next((r for r in self.records if r.candidate_id == candidate_id), None)


@dataclass
class ScenarioEdit:
    """One exact edit in a ScenarioOverlay.

    REPLACE requires ``expected_old_hash`` — the sha256 of the exact old slice —
    plus the target document/chunk/range. ADD requires a named target document
    and section, or an explicitly new proposed procedure. Overlapping edits and
    stale hashes are rejected by the overlay materialiser, never applied.
    """

    operation: str  # REPLACE | ADD
    target_document: str
    target_section: str = ""
    chunk_id: str = ""
    char_start: int = 0
    char_end: int = 0
    expected_old_hash: str = ""
    expected_old_text: str = ""
    new_text: str = ""
    label: str = ""  # a bare legacy patch string defaults to ADD, labelled

    def __post_init__(self) -> None:
        op = self.operation.upper()
        if op not in ("REPLACE", "ADD"):
            raise DeterminationContractError(
                f"ScenarioEdit.operation must be REPLACE/ADD, got {op!r}"
            )
        self.operation = op


@dataclass
class ScenarioOverlay:
    """Ordered, non-overlapping edits over a pinned base snapshot."""

    base_snapshot_fingerprint: str
    edits: list[ScenarioEdit] = field(default_factory=list)
    overlay_id: str = ""


@dataclass
class GoverningBundle:
    """The authoritative governing text for one Part, assembled once.

    ``part_text`` is the complete Part as stored — never trimmed after an
    extracted role, never reduced to a first atom. ``lead_in`` is the verified
    parent lead-in; ``definitions``/``references`` carry the cited definition and
    reference texts the reader needs to resolve the duty and its exceptions.
    """

    ref: str
    part_text: str
    lead_in: str = ""
    definitions: list[dict[str, Any]] = field(default_factory=list)
    references: list[dict[str, Any]] = field(default_factory=list)
    meta: list[dict[str, Any]] = field(default_factory=list)
    source_slices: list[SourceSlice] = field(default_factory=list)
    fingerprint: str = ""


@dataclass
class AssessmentContext:
    """Injected runtime dependencies for the assessment service.

    Deliberately NOT serializable request data: the source resolver, seats,
    ``SeatFn``, repository and policy graph are runtime handles, so a request
    cannot smuggle a different engine into its own input.
    """

    repository: Any = None
    seats: list[dict[str, str]] = field(default_factory=list)
    quorum: float = 0.66
    seat_fn: Any = None  # SeatFn (model, system, user) -> raw text
    report_fn: Any = None  # reporting transport; defaults to seat_fn
    report_model: str = ""
    policy_graph: Any = None
    source_resolver: Any = None
    arbiter_fn: Any = None
    kb_id: str = "operator_corpus"
    engine_version: str = "compliance-reading/1"


@dataclass
class AssessmentRequest:
    """A fully specified assessment request.

    The caller (context factory) must explicitly supply scope and snapshot; a
    silently-loaded unrelated default org graph is forbidden. Runtime
    dependencies (source resolver, seats/quorum, ``SeatFn``, repository) are
    injected separately through ``AssessmentContext`` and are NOT serializable
    request data here.
    """

    requirement_id: str
    kb_id: str = "operator_corpus"
    org_id: str = "default"
    scope: Any = None  # AssetScope — kept untyped to avoid an import cycle
    scope_basis: str = "actual"  # actual | conditional | approved_mapping
    effective_on: str = ""
    known_at: str = ""
    conditional_scope: bool = False
    governing: GoverningBundle | None = None
    snapshot: CorpusSnapshot | None = None
    candidate_set: CandidateSet | None = None
    overlay: ScenarioOverlay | None = None
    # Parts whose links are affected by an overlay replacement (impact set).
    affected_parts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConstraintBinding:
    """An exact operand binding selected by the alignment reader."""

    binding_id: str
    link_id: str
    governing_slice_id: str
    candidate_slice_id: str
    value: int
    unit: str
    qualifier: str | None = None
    constraint_kind: str = ""  # max_interval | min_retention
    direction: str = ""
    governing_quantity: dict[str, Any] | None = None
    internal_quantity: dict[str, Any] | None = None
    rationale: str = ""


@dataclass
class AlignmentRecord:
    """One candidate's relation to the governing duty, with bindings."""

    link_id: str
    governing_ref: str
    governing_slice_ids: list[str] = field(default_factory=list)
    candidate_ref: str = ""
    document_id: str = ""  # human-readable source name, e.g. "B22.txt"
    candidate_slice_ids: list[str] = field(default_factory=list)
    relation: str = "UNKNOWN"
    activity: str = ""
    object: str = ""
    trigger: str = ""
    population: str = ""
    population_overlap: str = "UNKNOWN"
    source_function: str = "OTHER"
    rationale: str = ""
    missing_facts: list[str] = field(default_factory=list)
    constraint_bindings: list[ConstraintBinding] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.relation not in ALIGNMENT_RELATIONS:
            raise DeterminationContractError(
                f"alignment relation must be one of {ALIGNMENT_RELATIONS}, got {self.relation!r}"
            )
        if self.source_function not in SOURCE_FUNCTIONS:
            raise DeterminationContractError(
                f"source_function must be one of {SOURCE_FUNCTIONS}, got {self.source_function!r}"
            )
        if self.population_overlap not in POPULATION_OVERLAPS:
            raise DeterminationContractError(
                f"population_overlap must be one of {POPULATION_OVERLAPS}, "
                f"got {self.population_overlap!r}"
            )


@dataclass
class AlignmentResult:
    """The complete alignment of a Part's full candidate set."""

    part_ref: str
    records: list[AlignmentRecord] = field(default_factory=list)  # SAME + DIFFERENT + UNKNOWN
    valid: bool = True
    failure: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def same(self) -> list[AlignmentRecord]:
        return [r for r in self.records if r.relation == "SAME"]

    def unknown(self) -> list[AlignmentRecord]:
        return [r for r in self.records if r.relation == "UNKNOWN"]


@dataclass
class CoveredCommitment:
    commitment: str
    governing_slice_ids: list[str] = field(default_factory=list)
    internal_slice_ids: list[str] = field(default_factory=list)


@dataclass
class GroundedGap:
    gap_id: str
    kind: str  # OMISSION | WEAKER_COMMITMENT | CONTRADICTION | OUTDATED_LANGUAGE
    missing_commitment: str
    governing_slice_ids: list[str] = field(default_factory=list)
    internal_counterevidence_slice_ids: list[str] = field(default_factory=list)
    boundary_proof_id: str = ""


@dataclass
class ExplanationUncertainty:
    reason: str
    source_slice_ids: list[str] = field(default_factory=list)
    code: str = ""


@dataclass
class CoverageExplanation:
    """The bounded, source-linked report the explanation stage produces."""

    documentary_coverage: str = "UNRESOLVED"
    covered: list[CoveredCommitment] = field(default_factory=list)
    gaps: list[GroundedGap] = field(default_factory=list)
    uncertainties: list[ExplanationUncertainty] = field(default_factory=list)
    valid: bool = False
    failure: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.documentary_coverage not in DOCUMENTARY_COVERAGE:
            raise DeterminationContractError(
                f"documentary_coverage must be one of {DOCUMENTARY_COVERAGE}, "
                f"got {self.documentary_coverage!r}"
            )


@dataclass
class AssessmentResult:
    """The single authority for one assessed Part (brief §4)."""

    assessment_id: str
    run_id: str
    engine_version: str
    input_fingerprint: str
    requirement_id: str
    applicability: str = "UNKNOWN"
    applicability_basis: str = ""
    documentary_coverage: str = "UNRESOLVED"
    coverage: str = "UNRESOLVED"
    substantively_resolved: bool = False
    council_result: dict[str, Any] = field(default_factory=dict)
    covered: list[CoveredCommitment] = field(default_factory=list)
    gaps: list[GroundedGap] = field(default_factory=list)
    uncertainties: list[ExplanationUncertainty] = field(default_factory=list)
    confirmed_conflicts: list[dict[str, Any]] = field(default_factory=list)
    comparison_uncertainties: list[dict[str, Any]] = field(default_factory=list)
    selected_source_slices: list[dict[str, Any]] = field(default_factory=list)
    receipt: dict[str, Any] = field(default_factory=dict)
    unresolved_code: str = ""
    missing_fact: dict[str, Any] = field(default_factory=dict)
    engine_fingerprint: str = ""
    # ── product-contract dimensions (result_contract.py owns the vocabularies;
    #    these remain plain fields so the record stays serializable) ──────────
    source_readiness: str = "UNKNOWN"  # READY | INCOMPLETE | CONFLICTED | UNKNOWN
    temporal_currency: str = "UNKNOWN"  # CURRENT | FUTURE | HISTORICAL | UNKNOWN
    documentary_alignment: str = "UNRESOLVED"  # ALIGNED | PARTIAL | MISALIGNED | UNRESOLVED
    implementation_evidence: str = "NOT_ASSESSED"  # SUFFICIENT | PARTIAL | ABSENT | NOT_ASSESSED
    review_required: bool = False
    review_reason: str = ""

    def __post_init__(self) -> None:
        if self.documentary_coverage not in DOCUMENTARY_COVERAGE:
            raise DeterminationContractError(
                f"documentary_coverage must be one of {DOCUMENTARY_COVERAGE}, "
                f"got {self.documentary_coverage!r}"
            )
        from portal.modules.compliance.core.result_contract import (
            DOCUMENTARY_ALIGNMENT,
            IMPLEMENTATION_EVIDENCE,
            SOURCE_READINESS,
            TEMPORAL_CURRENCY,
        )

        for field_name, vocabulary in (
            ("source_readiness", SOURCE_READINESS),
            ("temporal_currency", TEMPORAL_CURRENCY),
            ("documentary_alignment", DOCUMENTARY_ALIGNMENT),
            ("implementation_evidence", IMPLEMENTATION_EVIDENCE),
        ):
            value = getattr(self, field_name)
            if value not in vocabulary:
                raise DeterminationContractError(
                    f"{field_name} must be one of {vocabulary}, got {value!r}"
                )
        if self.documentary_coverage == "UNRESOLVED":
            if self.unresolved_code not in UNRESOLVED_CODES:
                raise DeterminationContractError(
                    "a UNRESOLVED assessment requires a code from UNRESOLVED_CODES, got "
                    f"{self.unresolved_code!r}"
                )
            if not self.missing_fact:
                raise DeterminationContractError(
                    f"{self.unresolved_code} requires missing_fact: "
                    f"{UNRESOLVED_CODES[self.unresolved_code]}"
                )


def is_answer(determination: str) -> bool:
    return determination in ANSWERS
