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
from portal.modules.compliance.core.tiers import Span, detect_conflicts

_COVERAGE = ("FULL", "PARTIAL", "NONE", "NOT_APPLICABLE", "NEEDS_REVIEW")

# what a proposer returns per side: [{"document_id", "section_id", "span",
# "locatable": bool}]  — `locatable` is True only when a deterministic checker
# re-found `span` verbatim in the cited document.
ProposeFn = Callable[[RegisterNode, str], list[dict]]


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
        }


def _locatable(spans: list[dict]) -> list[dict]:
    return [s for s in spans if s.get("locatable")]


def _classify(policy: list[dict], procedure: list[dict], evidence: list[dict]) -> tuple[str, bool]:
    """(coverage token, substantively_resolved). FULL needs a locatable span from
    BOTH the policy and the procedure side."""
    p_loc, q_loc, e_loc = _locatable(policy), _locatable(procedure), _locatable(evidence)
    if p_loc and q_loc:
        return "FULL", True
    if p_loc or q_loc:
        return "PARTIAL", True
    if e_loc:
        return "PARTIAL", True  # evidence without policy/procedure text — still substantive
    # candidates were proposed but none substantiated the obligation (a lexical
    # hit, aspirational language, or an off-topic doc) — that is a gap, not an
    # open question. NEEDS_REVIEW is reserved for an approved-mapping row that
    # says so.
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
    # skip an R-level node only when the same R has extracted Parts (then the
    # Parts carry the judgement); an R with no Parts (CIP-012, CIP-013, ...) is
    # itself the unit of coverage.
    has_parts = {(n.standard, n.requirement) for n in nodes if n.granularity == "part"}

    for node in nodes:
        if node.granularity == "requirement" and (node.standard, node.requirement) in has_parts:
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

        cell.policy_spans = propose(node, "policy")
        cell.procedure_spans = propose(node, "procedure")
        cell.evidence_spans = propose(node, "evidence")

        # tier conflict: the standard node is the Tier-0 span; every proposed
        # policy/procedure span is Tier 2/3. detect_conflicts never reconciles.
        spans = [Span(node.verbatim_text, tier=0, citation=node.id, doc_class="standard")]
        for s in cell.policy_spans:
            spans.append(Span(s["span"], tier=2, citation=s["section_id"], doc_class="policy"))
        for s in cell.procedure_spans:
            spans.append(Span(s["span"], tier=3, citation=s["section_id"], doc_class="procedure"))
        cell.conflicts = [c.to_dict() for c in detect_conflicts(spans, obligation=node.id)]

        # stale citation: a span that cites a superseded version of this standard
        superseded = {
            e["dst"] for e in reg.edges if e["rel"] == "SUPERSEDES" and e["src"] == node.standard
        }
        for s in cell.policy_spans + cell.procedure_spans:
            for old in superseded:
                if old in s["span"] or old.rsplit("-", 1)[0] in s["span"]:
                    cell.stale_citations.append(f"{s['section_id']} cites {old} (superseded)")

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
