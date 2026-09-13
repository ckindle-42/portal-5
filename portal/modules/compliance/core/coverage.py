"""Coverage by enumeration (T3 Phase 6).

Iterate the **applicable** register Parts. Retrieval proposes candidate policy
and procedure spans; approved mappings short-circuit. Classify **policy,
procedure, and evidence separately** — a procedure can satisfy a requirement the
policy is silent on — with quoted spans from both sides.

**Report examined and substantively resolved as separate counts** (the Bully's
gate GP — *"Crogl is reported as comprehension, not exposure"*); a
degenerate-fixture test fails if the two collapse.

**A ``FULL`` requires a quoted span from both sides that a deterministic checker
can locate** in the cited document.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from portal.modules.compliance.core.applicability import AssetScope, applicable
from portal.modules.compliance.core.cip_register import Register, RegisterNode
from portal.modules.compliance.core.engine import effective_parts
from portal.modules.compliance.core.mapping_store import Mapping, MappingStore
from portal.modules.compliance.core.text_signals import keywords
from portal.modules.compliance.core.tiers import ComplianceConflict, Span, detect_conflicts

# A duration/modal mismatch is only a real COMPLIANCE_CONFLICT when the two
# compared spans are actually about the same obligation. Live on the real
# corpus, `detect_conflicts` flagged a password-rotation cadence against an
# unrelated sub-item's access-revocation deadline mentioned in the same
# paragraph of a genuinely relevant, locatable procedure chunk — filtering to
# locatable spans (coverage_matrix) doesn't catch this, since a real
# multi-topic paragraph is legitimately locatable for the Part it substantively
# restates AND still carries an unrelated neighbor's number. Requiring the two
# spans to share this much topical vocabulary is a cheap, disclosed proxy for
# "same obligation" — not semantic understanding, but it closes the specific
# false-positive class observed live.
_CONFLICT_TOPIC_OVERLAP = 3


def _shares_topic(conflict: ComplianceConflict) -> bool:
    return (
        len(keywords(conflict.higher.text) & keywords(conflict.lower.text))
        >= _CONFLICT_TOPIC_OVERLAP
    )


# FULL/PARTIAL/NONE remain valid values for a human-approved mapping's own
# recorded verdict (an authenticated SME decision), and legacy fixtures — but
# `_classify` (the automated proposer-based path) can no longer produce them
# on its own (P1.2/F03): full obligation-atom comparison is P5 work. Until
# then the automated path reports UNRESOLVED, never a resolved FULL or a
# resolved NONE from either textual presence or from empty candidates.
_COVERAGE = ("FULL", "PARTIAL", "NONE", "NOT_APPLICABLE", "NEEDS_REVIEW", "UNRESOLVED")

# what a proposer returns per side: [{"document_id", "section_id", "span",
# "locatable": bool}]  — `locatable` is True only when a deterministic checker
# re-found `span` verbatim in the cited document.
ProposeFn = Callable[[RegisterNode, str], list[dict[str, Any]]]


class ProposalError(RuntimeError):
    """Retrieval could not judge coverage; absence of results is not a gap."""

    def __init__(self, stage: str, detail: str):
        super().__init__(detail)
        self.stage = stage


@dataclass
class CoverageCell:
    requirement_id: str
    applies: bool
    applicability_reason: str
    policy_spans: list[dict[str, Any]] = field(default_factory=list)
    procedure_spans: list[dict[str, Any]] = field(default_factory=list)
    evidence_spans: list[dict[str, Any]] = field(default_factory=list)
    coverage: str = "NEEDS_REVIEW"
    from_approved_mapping: bool = False
    approved_mapping_ids: list[str] = field(default_factory=list)
    substantively_resolved: bool = False
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    stale_citations: list[str] = field(default_factory=list)
    note: str = ""
    retrieval_errors: list[dict[str, Any]] = field(default_factory=list)
    # ── canonical assessment projection (IMPLEMENTATION_BRIEF §6) ────────────
    # The cell is a projection of one persisted AssessmentResult; the raw
    # retrieval diagnostics above stay separate from the canonical decision.
    assessment_id: str = ""
    documentary_coverage: str = ""
    applicability: str = ""
    applicability_basis: str = ""
    engine_version: str = ""
    snapshot_fingerprint: str = ""
    covered: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    uncertainties: list[dict[str, Any]] = field(default_factory=list)
    #: exact system-owned slices for the canonical opinion's support and
    #: counterevidence — never a model-reconstructed quote.
    canonical_support: list[dict[str, Any]] = field(default_factory=list)
    canonical_counterevidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "applies": self.applies,
            "applicability_reason": self.applicability_reason,
            "coverage": self.coverage,
            "from_approved_mapping": self.from_approved_mapping,
            "approved_mapping_ids": self.approved_mapping_ids,
            "substantively_resolved": self.substantively_resolved,
            "policy": [s.get("section_id") for s in self.policy_spans],
            "procedure": [s.get("section_id") for s in self.procedure_spans],
            "evidence": [s.get("section_id") for s in self.evidence_spans],
            "conflicts": self.conflicts,
            "stale_citations": self.stale_citations,
            "note": self.note,
            "retrieval_errors": self.retrieval_errors,
            "assessment_id": self.assessment_id,
            "documentary_coverage": self.documentary_coverage,
            "applicability": self.applicability,
            "applicability_basis": self.applicability_basis,
            "engine_version": self.engine_version,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "covered": self.covered,
            "gaps": self.gaps,
            "uncertainties": self.uncertainties,
            "canonical_support": self.canonical_support,
            "canonical_counterevidence": self.canonical_counterevidence,
        }


def _qualified(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A span whose source location is verified AND whose relevance is
    confidently established (P1.1) — never certified by a relevance score
    alone. Falls back to the legacy ``locatable`` field for pre-P1 fixtures
    that only set that single flag."""
    out = []
    for s in spans:
        if "anchor_verified" in s or "relevant" in s:
            if s.get("anchor_verified") and s.get("relevant"):
                out.append(s)
        elif s.get("locatable"):
            out.append(s)
    return out


# kept as a thin alias — some callers/tests still reference the old name.
_locatable = _qualified


def _classify(*args: Any, **kwargs: Any) -> tuple[Any, ...]:
    """Classify coverage.

    Two call shapes are supported:

    * ``_classify(policy, procedure, evidence)`` — the legacy span-list adapter
      kept for existing tests/CLI callers. It never decides satisfaction on the
      product path; the product path (``coverage_matrix(context=...)`` /
      ``_classify(node, candidate_set, context)``) delegates to
      ``assessment.assess_part`` and returns its canonical projection.
    * ``_classify(node_or_request, candidate_set, context)`` — the shared-service
      path; the first argument is a :class:`RegisterNode` or an
      :class:`AssessmentRequest`.
    """
    if len(args) == 3 and all(isinstance(a, list) for a in args):
        return _classify_legacy(args[0], args[1], args[2])
    return _classify_assessed(*args, **kwargs)


def _classify_legacy(
    policy: list[dict[str, Any]],
    procedure: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> tuple[str, bool, str]:
    """(coverage token, substantively_resolved, note) — legacy span adapter.

    Retrieval failure is handled by ``_propose_cell``; reaching this function
    with no qualified candidates therefore means the completed search found an
    absence, not that a reviewer must re-read it. This path is a compatibility
    adapter for pre-reading-architecture callers and tests; the product path
    goes through the shared assessment service below.
    """
    from portal.modules.compliance.core.assessment import assess_atom

    p_q, q_q, e_q = _qualified(policy), _qualified(procedure), _qualified(evidence)
    if p_q or q_q or e_q:
        candidate = (q_q or p_q or e_q)[0]
        text = candidate.get("span", "")
        result = assess_atom(
            {
                "atom_id": "coverage-adapter",
                "action": text,
                "source_anchor_ids": ["governing-register"],
            },
            [{"action": text, "anchor_id": candidate.get("section_id", "internal-section")}],
            {},
        )
        if result.determination == "SUPPORTED":
            coverage = "FULL" if q_q or p_q else "PARTIAL"
            return coverage, True, "source-backed deterministic field comparison"
        return "PARTIAL", True, result.rationale
    return "NONE", True, "exhaustive completed retrieval found no qualified implementation"


def _classify_assessed(
    node_or_request: Any,
    candidate_set: Any = None,
    context: Any = None,
    *,
    snapshot: Any = None,
    kb_id: str = "",
    effective_on: str = "",
    known_at: str = "",
) -> tuple[str, bool, str, dict[str, Any]]:
    """Classify one Part through the one authoritative service.

    Returns ``(coverage, substantively_resolved, note, projection_fields)`` where
    ``projection_fields`` carries the canonical assessment ID and its projections.
    """
    from portal.modules.compliance.core.assessment import assess_part
    from portal.modules.compliance.core.determination import AssessmentRequest

    if isinstance(node_or_request, AssessmentRequest):
        request = node_or_request
    else:
        request = _request_for_node(
            node_or_request,
            candidate_set,
            context,
            snapshot=snapshot,
            kb_id=kb_id or getattr(context, "kb_id", "") or "operator_corpus",
            effective_on=effective_on,
            known_at=known_at,
        )
    result = assess_part(request, context)
    return (
        str(result.coverage),
        bool(result.substantively_resolved),
        _assessment_note(result),
        _assessment_fields(result),
    )


def _request_for_node(
    node: RegisterNode,
    candidate_set: Any,
    context: Any,
    *,
    snapshot: Any = None,
    kb_id: str = "operator_corpus",
    effective_on: str = "",
    known_at: str = "",
) -> Any:
    """Build the shared request for a node from an explicit candidate set.

    When the caller supplies a pinned ``CandidateSet`` (and optionally a
    snapshot) the retrieval step is skipped entirely, so a caller can reuse an
    already-acquired set rather than re-retrieving it.
    """
    from portal.modules.compliance.core.assessment_source import (
        build_corpus_snapshot,
        resolve_governing_bundle,
    )
    from portal.modules.compliance.core.determination import AssessmentRequest
    from portal.modules.compliance.core.scope_derive import derive_scope

    scope = derive_scope(kb_id)[0]
    governing = resolve_governing_bundle(node.id)
    request = AssessmentRequest(
        requirement_id=node.id,
        kb_id=kb_id,
        scope=scope,
        effective_on=effective_on,
        known_at=known_at,
        governing=governing,
        snapshot=snapshot,
        candidate_set=candidate_set,
    )
    if request.snapshot is None:
        request.snapshot = build_corpus_snapshot(kb_id)
    return request


def _assessment_note(result: Any) -> str:
    if result.substantively_resolved:
        if result.gaps:
            kinds = ", ".join(
                sorted({str(g.get("kind", "")) for g in result.gaps if g.get("kind")})
            )
            return f"documentary {result.documentary_coverage}; demonstrated gap(s): {kinds}"
        return f"documentary {result.documentary_coverage}"
    if result.unresolved_code:
        return f"unresolved ({result.unresolved_code}) — {result.missing_fact}"
    return f"not substantively resolved: {result.documentary_coverage}"


def _assessment_fields(result: Any) -> dict[str, Any]:
    """Project one AssessmentResult into CoverageCell fields.

    Support/counterevidence slices are the system-owned exact slices cited by
    the covered commitments and grounded gaps — never a first retrieved row.
    """
    slices = {
        str(s.get("slice_id", "")): s
        for s in (result.selected_source_slices or [])
        if isinstance(s, dict)
    }
    covered = [c if isinstance(c, dict) else _asdict(c) for c in (result.covered or [])]
    gaps = [g if isinstance(g, dict) else _asdict(g) for g in (result.gaps or [])]
    uncertainties = [u if isinstance(u, dict) else _asdict(u) for u in (result.uncertainties or [])]

    support_ids: list[str] = []
    for item in covered:
        support_ids += [str(x) for x in item.get("internal_slice_ids", []) if x]
        support_ids += [str(x) for x in item.get("governing_slice_ids", []) if x]
    counter_ids: list[str] = []
    for item in gaps:
        counter_ids += [str(x) for x in item.get("internal_counterevidence_slice_ids", []) if x]
        counter_ids += [str(x) for x in item.get("governing_slice_ids", []) if x]

    return {
        "assessment_id": str(result.assessment_id),
        "documentary_coverage": str(result.documentary_coverage),
        "applicability": str(result.applicability),
        "applicability_basis": str(result.applicability_basis),
        "engine_version": str(result.engine_version),
        "snapshot_fingerprint": str((result.receipt or {}).get("snapshot_fingerprint", "")),
        "covered": covered,
        "gaps": gaps,
        "uncertainties": uncertainties,
        "canonical_support": _exact_slices(slices, support_ids),
        "canonical_counterevidence": _exact_slices(slices, counter_ids),
    }


def _exact_slices(slices: dict[str, dict[str, Any]], ids: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for slice_id in ids:
        if not slice_id or slice_id in seen:
            continue
        seen.add(slice_id)
        row = slices.get(slice_id)
        if row is not None:
            out.append(dict(row))
    return out


def _asdict(value: Any) -> dict[str, Any]:
    from dataclasses import asdict, is_dataclass

    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return dict(value) if isinstance(value, dict) else {}


@dataclass
class CoverageMatrix:
    effective_on: str
    scope_declared: bool
    cells: list[CoverageCell] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        applicable_cells = [c for c in self.cells if c.applies]
        # Final applicability/resolution, not mere result presence: an
        # UNRESOLVED or NEEDS_REVIEW cell is examined but never "resolved".
        resolved = [
            c
            for c in applicable_cells
            if c.substantively_resolved and c.coverage not in ("UNRESOLVED", "NEEDS_REVIEW")
        ]
        by_cov: dict[str, int] = dict.fromkeys(_COVERAGE, 0)
        for c in applicable_cells:
            by_cov[c.coverage] = by_cov.get(c.coverage, 0) + 1
        return {
            "effective_on": self.effective_on,
            "scope_declared": self.scope_declared,
            # examined and substantively resolved are DIFFERENT numbers (GP)
            "examined": len(applicable_cells),
            "substantively_resolved": len(resolved),
            "not_applicable": sum(1 for c in self.cells if not c.applies),
            "coverage_breakdown": by_cov,
            # P1.2/F03: NONE is no longer a resolved-absence verdict the
            # automated path can produce from empty/unqualified candidates —
            # it can now only come from a human-approved mapping's own
            # recorded decision. "full_gaps" would have implied confirmed
            # absence; report the honestly-unresolved set instead.
            "unresolved_items": [
                c.requirement_id for c in applicable_cells if c.coverage == "UNRESOLVED"
            ],
            "confirmed_gaps_none": [
                c.requirement_id for c in applicable_cells if c.coverage == "NONE"
            ],
            "from_approved_mappings": sum(1 for c in applicable_cells if c.from_approved_mapping),
        }


def _skip_node(node: RegisterNode, has_parts: set[tuple[str, str]]) -> bool:
    """An R-level node is skipped when its R has obligation-bearing Parts (they
    carry the judgement); a CIP-003 R1 topic-leaf Part is skipped because it is a
    policy topic label, not an obligation (R1 stays the unit of coverage)."""
    if node.granularity == "requirement":
        return (node.standard, node.requirement) in has_parts
    return (
        node.granularity == "part"
        and node.standard.startswith("CIP-003")
        and node.requirement == "R1"
    )


def _propose_cell(cell: CoverageCell, node: RegisterNode, propose: ProposeFn) -> bool:
    try:
        cell.policy_spans = propose(node, "policy")
        cell.procedure_spans = propose(node, "procedure")
        cell.evidence_spans = propose(node, "evidence")
    except ProposalError as exc:
        cell.retrieval_errors.append({"stage": exc.stage, "error": str(exc)})
        cell.note = f"{exc.stage} failed; coverage is unresolved — retry this Part"
        return False
    return True


def _mapping_endpoint_resolves(mapping: Mapping, sidecar: dict[str, Any]) -> bool:
    """Deterministic endpoint check (P1.3/F04): a mapping is only trustworthy
    if the document it names is actually present in the current ingested
    corpus. Approving a relationship to a document that was later removed, or
    that never existed, must not silently keep supplying a positive verdict."""
    return mapping.internal_document_id in sidecar


def _apply_approved_mappings(
    cell: CoverageCell, approved: list[Mapping], sidecar: dict[str, Any]
) -> None:
    """P1.3/F04: an approved mapping is authoritative over MODEL judgement,
    but it is not a bypass of assessment by lookup order. Collect ALL
    applicable approved mappings (not just the first), verify each endpoint
    still resolves in the ingested corpus, and surface — rather than silently
    pick a winner from — contradictory approved decisions."""
    cell.from_approved_mapping = True
    cell.approved_mapping_ids = [m.id for m in approved]
    unresolved = [m for m in approved if not _mapping_endpoint_resolves(m, sidecar)]
    coverages = {m.coverage for m in approved}
    if unresolved:
        cell.coverage = "UNRESOLVED"
        cell.substantively_resolved = False
        cell.note = (
            f"{len(unresolved)} of {len(approved)} approved mapping(s) reference a "
            "document/section not found in the current ingested corpus (stale or "
            "unavailable source) — "
            + "; ".join(f"{m.id}: {m.internal_document_id}" for m in unresolved)
        )
        return
    if len(coverages) > 1:
        cell.coverage = "NEEDS_REVIEW"
        cell.substantively_resolved = False
        cell.note = (
            f"{len(approved)} approved mappings disagree on coverage {sorted(coverages)} — "
            "contradictory decisions require SME reconciliation, not lookup order"
        )
        return
    cell.coverage = next(iter(coverages))
    cell.substantively_resolved = cell.coverage != "NEEDS_REVIEW"
    approvers = sorted({m.approved_by for m in approved if m.approved_by})
    cell.note = (
        f"{len(approved)} approved mapping(s) by {', '.join(approvers) or 'unknown'}; "
        "all endpoints resolved and agree"
    )


def coverage_matrix(
    reg: Register,
    scope: AssetScope,
    effective_on: str,
    propose: ProposeFn,
    store: MappingStore | None = None,
    document_sidecar: dict[str, Any] | None = None,
    context: Any = None,
) -> CoverageMatrix:
    """Enumerate applicable EFFECTIVE parts and classify each. ``propose(node,
    side)`` with side in {"policy","procedure","evidence"} returns candidate
    spans; approved mappings in ``store`` are authoritative over model
    judgement but must resolve and agree (see ``_apply_approved_mappings``).
    ``document_sidecar`` defaults to the real ingest sidecar; tests may pass
    an explicit dict.

    When ``context`` (an :class:`AssessmentContext`) is supplied, classification
    goes through the one authoritative ``assessment.assess_part`` service and
    each cell carries the canonical assessment ID; the legacy proposer-based
    path is used only when no context is given. ``propose`` is ignored on the
    shared-service path (candidate acquisition happens in the shared adapter).
    """
    if not scope.is_declared:
        raise ValueError(
            "coverage_matrix requires a declared AssetScope — an ungated matrix "
            "produces false gaps for out-of-scope requirements ([GATE] Phase 5)."
        )
    if context is not None:
        return _coverage_matrix_assessed(reg, scope, effective_on, context)
    store = store or MappingStore()
    m = CoverageMatrix(effective_on=effective_on, scope_declared=True)
    nodes = effective_parts(reg, effective_on)
    # skip an R-level node only when the same R has extracted Parts that are
    # themselves obligations (then the Parts carry the judgement). CIP-003 R1's
    # "parts" are policy *topics*, not sub-requirements — its 15-calendar-month
    # obligation is R-level, so R1 stays the unit of coverage.
    has_parts = {
        (n.standard, n.requirement)
        for n in nodes
        if n.granularity == "part"
        and not (n.standard.startswith("CIP-003") and n.requirement == "R1")
    }

    for node in nodes:
        if _skip_node(node, has_parts):
            continue
        applies, reason = applicable(node.applicable_systems, scope)
        cell = CoverageCell(requirement_id=node.id, applies=applies, applicability_reason=reason)
        if not applies:
            cell.coverage = "NOT_APPLICABLE"
            cell.substantively_resolved = True
            m.cells.append(cell)
            continue

        approved = store.approved_for(node.id, effective_on)
        if approved:
            if document_sidecar is None:
                from portal.modules.compliance.core.ingest import read_sidecar

                document_sidecar = read_sidecar()
            _apply_approved_mappings(cell, approved, document_sidecar)
            m.cells.append(cell)
            continue

        if not _propose_cell(cell, node, propose):
            m.cells.append(cell)
            continue

        # tier conflict: the standard node is the Tier-0 span; every proposed
        # policy/procedure span is Tier 2/3. detect_conflicts never reconciles.
        # Only LOCATABLE spans are compared — an ambiguous or below-threshold
        # candidate (a duration mentioned in an unrelated passage that merely
        # scored high enough to be retrieved) is not evidence the document
        # actually restates this obligation, and comparing its numbers against
        # the standard's produced real false COMPLIANCE_CONFLICTs live (a
        # policy-review cadence flagged against an unrelated delegation
        # deadline and an unrelated incident-response test cadence).
        spans = [Span(node.verbatim_text, tier=0, citation=node.id, doc_class="standard")]
        for s in _locatable(cell.policy_spans):
            spans.append(Span(s["span"], tier=2, citation=s["section_id"], doc_class="policy"))
        for s in _locatable(cell.procedure_spans):
            spans.append(Span(s["span"], tier=3, citation=s["section_id"], doc_class="procedure"))
        cell.conflicts = [
            c.to_dict() for c in detect_conflicts(spans, obligation=node.id) if _shares_topic(c)
        ]

        # stale citation: a span that cites a superseded version of this
        # standard by its EXACT identifier (F10) — a substring/prefix match
        # let a citation of the CURRENT id (e.g. "CIP-003-9") be flagged
        # stale merely because it shared the family prefix with a superseded
        # id ("CIP-003-8" -> prefix "CIP-003"). A stale REFERENCE (the text
        # cites an old id) is also distinct from a stale IMPLEMENTATION
        # (the text describes outdated behavior); this check only detects
        # the former.
        cell.stale_citations = _stale_citations(
            reg, node.standard, cell.policy_spans + cell.procedure_spans
        )

        cell.coverage, cell.substantively_resolved, classify_note = _classify(
            cell.policy_spans, cell.procedure_spans, cell.evidence_spans
        )
        cell.note = classify_note
        if cell.stale_citations:
            cell.note += f"; also cites a superseded standard id: {cell.stale_citations}"
        if cell.conflicts and cell.coverage not in ("NOT_APPLICABLE", "NONE"):
            cell.coverage = "PARTIAL"
            cell.substantively_resolved = True
            cell.note += "; contradictory internal constraint prevents full support"
        m.cells.append(cell)

    return m


def _superseded_standard_ids(reg: Register, standard: str) -> set[str]:
    return {e["dst"] for e in reg.edges if e["rel"] == "SUPERSEDES" and e["src"] == standard}


def _stale_citations(reg: Register, standard: str, spans: list[dict[str, Any]]) -> list[str]:
    """Exact superseded-reference advisories, kept separate from the verdict."""
    superseded = _superseded_standard_ids(reg, standard)
    out: list[str] = []
    for span in spans:
        text = str(span.get("span") or span.get("text") or "")
        citation = str(span.get("section_id") or span.get("ref") or "")
        for old in sorted(superseded):
            if re.search(rf"(?<![\w-]){re.escape(old)}(?![\w-])", text):
                out.append(
                    f"{citation} cites {old} (superseded reference, not necessarily an "
                    "obsolete implementation)"
                )
    return out


def _coverage_matrix_assessed(
    reg: Register,
    scope: AssetScope,
    effective_on: str,
    context: Any,
) -> CoverageMatrix:
    """Classify every applicable Part through the shared assessment service.

    No lexical conflict discovery and no blanket conflict-to-PARTIAL override:
    the substantive decision, its covered commitments, grounded gaps and
    uncertainties are whatever ``assess_part`` produced and persisted.
    """
    from portal.modules.compliance.core import assessment_runs

    m = CoverageMatrix(effective_on=effective_on, scope_declared=True)
    nodes = effective_parts(reg, effective_on)
    has_parts = {
        (n.standard, n.requirement)
        for n in nodes
        if n.granularity == "part"
        and not (n.standard.startswith("CIP-003") and n.requirement == "R1")
    }
    kb_id = str(getattr(context, "kb_id", "") or "operator_corpus")
    for node in nodes:
        if _skip_node(node, has_parts):
            continue
        applies, reason = applicable(node.applicable_systems, scope)
        cell = CoverageCell(requirement_id=node.id, applies=applies, applicability_reason=reason)
        if not applies:
            cell.coverage = "NOT_APPLICABLE"
            cell.documentary_coverage = "NOT_APPLICABLE"
            cell.substantively_resolved = True
            m.cells.append(cell)
            continue
        try:
            requests = assessment_runs.build_requests_for(
                node.id, kb_id=kb_id, scope=scope, effective_on=effective_on
            )
        except Exception as exc:  # noqa: BLE001 - retrieval failure is unresolved
            cell.retrieval_errors.append({"stage": "acquire", "error": str(exc)})
            cell.coverage = "UNRESOLVED"
            cell.note = f"source acquisition failed: {exc}"
            m.cells.append(cell)
            continue
        if not requests:
            cell.coverage = "UNRESOLVED"
            cell.note = "no assessment request could be built for this Part"
            m.cells.append(cell)
            continue
        coverage, resolved, note, fields = _classify(requests[0], context)
        for key, value in fields.items():
            setattr(cell, key, value)
        cell.coverage = coverage
        cell.substantively_resolved = resolved
        cell.note = note
        cell.stale_citations = _stale_citations(
            reg, node.standard, [*cell.canonical_support, *cell.canonical_counterevidence]
        )
        if cell.stale_citations:
            cell.note += f"; also cites a superseded standard id: {cell.stale_citations}"
        m.cells.append(cell)
    return m


def orphan_policy_spans(
    matrix_cells: list[CoverageCell], all_policy_sections: set[str]
) -> set[str]:
    """Reverse self-check: policy sections mapping to no requirement are either
    dead weight or evidence the register is incomplete — a cheap check on Phase 1."""
    mapped = {
        s.get("section_id")
        for c in matrix_cells
        for s in c.policy_spans + c.procedure_spans
        if s.get("locatable")
    }
    return all_policy_sections - {s for s in mapped if s}
