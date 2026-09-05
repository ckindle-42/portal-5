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

from collections.abc import Callable
from dataclasses import dataclass, field

from portal.modules.compliance.core.applicability import AssetScope, applicable
from portal.modules.compliance.core.cip_register import Register, RegisterNode
from portal.modules.compliance.core.engine import effective_parts
from portal.modules.compliance.core.mapping_store import MappingStore
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


_COVERAGE = ("FULL", "PARTIAL", "NONE", "NOT_APPLICABLE", "NEEDS_REVIEW")

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
            "substantively_resolved": self.substantively_resolved,
            "policy": [s.get("section_id") for s in self.policy_spans],
            "procedure": [s.get("section_id") for s in self.procedure_spans],
            "evidence": [s.get("section_id") for s in self.evidence_spans],
            "conflicts": self.conflicts,
            "stale_citations": self.stale_citations,
            "note": self.note,
            "retrieval_errors": self.retrieval_errors,
        }


def _locatable(spans: list[dict]) -> list[dict]:
    return [s for s in spans if s.get("locatable")]


def _classify(policy: list[dict], procedure: list[dict], evidence: list[dict]) -> tuple[str, bool]:
    """(coverage token, substantively_resolved). FULL needs a locatable span from
    BOTH the policy and the procedure side."""
    p_loc, q_loc, e_loc = _locatable(policy), _locatable(procedure), _locatable(evidence)
    if p_loc and q_loc:
        return "FULL", True
    if any(s.get("queue_item_id") for s in policy + procedure + evidence):
        return "NEEDS_REVIEW", False
    if p_loc or q_loc:
        return "PARTIAL", True
    if e_loc:
        return "PARTIAL", True  # evidence without policy/procedure text — still substantive
    # candidates were proposed but none substantiated the obligation (a lexical
    # hit, aspirational language, or an off-topic doc) — that is a gap, not an
    # open question. Uncertain relevance was handled above; retrieval failures
    # are handled by _propose_cell before classification.
    return "NONE", True


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
            "full_gaps": [c.requirement_id for c in applicable_cells if c.coverage == "NONE"],
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


def coverage_matrix(
    reg: Register,
    scope: AssetScope,
    effective_on: str,
    propose: ProposeFn,
    store: MappingStore | None = None,
) -> CoverageMatrix:
    """Enumerate applicable EFFECTIVE parts and classify each. ``propose(node,
    side)`` with side in {"policy","procedure","evidence"} returns candidate
    spans; approved mappings in ``store`` short-circuit the proposal."""
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
            cell.from_approved_mapping = True
            cell.coverage = approved[0].coverage  # authoritative over model judgement
            cell.substantively_resolved = cell.coverage != "NEEDS_REVIEW"
            cell.note = f"approved mapping {approved[0].id} by {approved[0].approved_by}"
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

        # stale citation: a span that cites a superseded version of this standard
        superseded = {
            e["dst"] for e in reg.edges if e["rel"] == "SUPERSEDES" and e["src"] == node.standard
        }
        cell.stale_citations = [
            f"{s['section_id']} cites {old} (superseded)"
            for s in cell.policy_spans + cell.procedure_spans
            for old in superseded
            if old in s["span"] or old.rsplit("-", 1)[0] in s["span"]
        ]

        cell.coverage, cell.substantively_resolved = _classify(
            cell.policy_spans, cell.procedure_spans, cell.evidence_spans
        )
        # a span that only satisfies the requirement by citing a retired version
        # is not coverage of the current one
        if cell.stale_citations and cell.coverage in ("FULL", "PARTIAL"):
            cell.coverage = "NONE"
            cell.note = "only match cites a superseded version"
        # a mandatory requirement whose only support is non-binding language is
        # a gap — the deontic conflict is the finding, not a PARTIAL.
        if (
            cell.coverage in ("FULL", "PARTIAL")
            and any(c["kind"] == "deontic" for c in cell.conflicts)
            and not _locatable(cell.evidence_spans)
        ):
            cell.coverage = "NONE"
            cell.note = "only support is non-binding (deontic conflict)"
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
