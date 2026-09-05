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
ProposeFn = Callable[[RegisterNode, str], list[dict]]


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
    policy_spans: list[dict] = field(default_factory=list)
    procedure_spans: list[dict] = field(default_factory=list)
    evidence_spans: list[dict] = field(default_factory=list)
    coverage: str = "NEEDS_REVIEW"
    from_approved_mapping: bool = False
    approved_mapping_ids: list[str] = field(default_factory=list)
    substantively_resolved: bool = False
    conflicts: list[dict] = field(default_factory=list)
    stale_citations: list[str] = field(default_factory=list)
    note: str = ""
    retrieval_errors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
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
        }


def _qualified(spans: list[dict]) -> list[dict]:
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


def _classify(
    policy: list[dict], procedure: list[dict], evidence: list[dict]
) -> tuple[str, bool, str]:
    """(coverage token, substantively_resolved, note).

    P1.2 (F03): full obligation-atom comparison (actor/action/object/
    population/trigger/deadline/condition/exception — see P5) is not yet
    implemented. This classifier therefore can no longer certify a resolved
    ``FULL`` from textual presence on both sides, nor a resolved ``NONE`` from
    empty/unqualified candidates — both were unsafe verdicts observed live.
    Every automated path reports ``UNRESOLVED`` with the reason a human (or a
    future P5 assessment) needs; queued items still surface as
    ``NEEDS_REVIEW``. Nothing here is "substantively resolved" until P5 exists.
    """
    p_q, q_q, e_q = _qualified(policy), _qualified(procedure), _qualified(evidence)
    if any(s.get("queue_item_id") for s in policy + procedure + evidence):
        return (
            "NEEDS_REVIEW",
            False,
            "one or more candidates are queued for review (low-confidence extraction "
            "or unresolved document tier) — see the review queue",
        )
    if p_q or q_q or e_q:
        return (
            "UNRESOLVED",
            False,
            "qualified textual presence found (see policy/procedure/evidence spans); "
            "obligation-level comparison against actor/action/trigger/condition is not "
            "yet implemented (P5) — this is NOT a supported-alignment determination",
        )
    return (
        "UNRESOLVED",
        False,
        "no qualified candidates retrieved for this Part — absence is NOT proven; "
        "corpus/search completeness has not been established for this obligation",
    )


@dataclass
class CoverageMatrix:
    effective_on: str
    scope_declared: bool
    cells: list[CoverageCell] = field(default_factory=list)

    def summary(self) -> dict:
        applicable_cells = [c for c in self.cells if c.applies]
        resolved = [c for c in applicable_cells if c.substantively_resolved]
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


def _skip_node(node, has_parts: set) -> bool:
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


def _mapping_endpoint_resolves(mapping: Mapping, sidecar: dict) -> bool:
    """Deterministic endpoint check (P1.3/F04): a mapping is only trustworthy
    if the document it names is actually present in the current ingested
    corpus. Approving a relationship to a document that was later removed, or
    that never existed, must not silently keep supplying a positive verdict."""
    return mapping.internal_document_id in sidecar


def _apply_approved_mappings(cell: CoverageCell, approved: list[Mapping], sidecar: dict) -> None:
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
    document_sidecar: dict | None = None,
) -> CoverageMatrix:
    """Enumerate applicable EFFECTIVE parts and classify each. ``propose(node,
    side)`` with side in {"policy","procedure","evidence"} returns candidate
    spans; approved mappings in ``store`` are authoritative over model
    judgement but must resolve and agree (see ``_apply_approved_mappings``).
    ``document_sidecar`` defaults to the real ingest sidecar; tests may pass
    an explicit dict."""
    if not scope.is_declared:
        raise ValueError(
            "coverage_matrix requires a declared AssetScope — an ungated matrix "
            "produces false gaps for out-of-scope requirements ([GATE] Phase 5)."
        )
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
        superseded = {
            e["dst"] for e in reg.edges if e["rel"] == "SUPERSEDES" and e["src"] == node.standard
        }
        cell.stale_citations = [
            f"{s['section_id']} cites {old} (superseded reference, not necessarily an obsolete implementation)"
            for s in cell.policy_spans + cell.procedure_spans
            for old in superseded
            if re.search(rf"(?<![\w-]){re.escape(old)}(?![\w-])", s["span"])
        ]

        cell.coverage, cell.substantively_resolved, classify_note = _classify(
            cell.policy_spans, cell.procedure_spans, cell.evidence_spans
        )
        cell.note = classify_note
        if cell.stale_citations:
            cell.note += f"; also cites a superseded standard id: {cell.stale_citations}"
        # P1.7: an unresolved conflict must affect the final assessment, not
        # hide behind a positive branch — `_classify` can no longer return a
        # positive verdict at all while conflicts are outstanding, but keep
        # this explicit so a future P5 assessment cannot silently reintroduce
        # the same shortcut.
        if cell.conflicts and cell.coverage not in ("NEEDS_REVIEW", "UNRESOLVED", "NOT_APPLICABLE"):
            cell.coverage = "NEEDS_REVIEW"
            cell.substantively_resolved = False
            cell.note += "; unresolved COMPLIANCE_CONFLICT blocks a positive determination"
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
