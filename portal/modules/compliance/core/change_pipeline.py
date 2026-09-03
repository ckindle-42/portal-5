"""Change pipeline (T4 Phases 2, 4, 5, 6).

T3 answers *"where are our gaps today."* This answers *"what just changed and
what you now have to do about it."* A gap is a static property of today's
register against today's policy; a change is a **delta between two register
states**, propagated through the mapping edges to the policy sections that have
to move.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from portal.modules.compliance.core.applicability import AssetScope, applicable
from portal.modules.compliance.core.cip_register import Register
from portal.modules.compliance.core.mapping_store import MappingStore
from portal.modules.compliance.core.register_diff import DiffRow, diff_standard, diff_summary


def _node_by_id(reg: Register, node_id: str):
    return next((n for n in reg.nodes if n.id == node_id), None)


# ── Phase 2: impact traversal ──────────────────────────────────────────────
@dataclass
class ImpactRow:
    diff: dict
    changed_part: str
    applies: bool
    applicability_reason: str
    mapped_sections: list[dict] = field(default_factory=list)
    prior_verdicts_now_unverified: list[str] = field(default_factory=list)
    classification: str = "work"  # "work" | "informational"

    def to_dict(self) -> dict:
        return {
            "changed_part": self.changed_part,
            "change_type": self.diff["change_type"],
            "sub_type": self.diff["sub_type"],
            "old_span": self.diff["old_span"],
            "new_span": self.diff["new_span"],
            "applies": self.applies,
            "classification": self.classification,
            "mapped_sections": self.mapped_sections,
            "prior_verdicts_now_unverified": self.prior_verdicts_now_unverified,
        }


def impact_report(
    old: Register,
    new: Register,
    standard_base: str,
    scope: AssetScope,
    store: MappingStore | None = None,
) -> dict:
    """For each substantive diff row: traverse the mapping store to the policy /
    procedure sections that implemented the affected Part, note the prior
    coverage verdict (now unverified), and gate on applicability — a change to a
    Part outside the asset scope is **informational**, not work."""
    if not scope.is_declared:
        raise ValueError("impact_report needs a declared AssetScope ([GATE] Phase 5)")
    store = store or MappingStore()
    rows = diff_standard(old, new, standard_base)
    out: list[ImpactRow] = []
    examined = resolved = 0

    for r in rows:
        d = r.to_dict()
        if not d["substantive"]:
            continue
        examined += 1
        # the affected Part id in the NEW register (or old for a removal)
        part_id = r.part_id_new or r.part_id_old
        node = _node_by_id(new, part_id) or _node_by_id(old, part_id)
        applies, reason = (
            applicable(node.applicable_systems, scope) if node else (True, "part not in register")
        )
        ir = ImpactRow(
            diff=d,
            changed_part=part_id,
            applies=applies,
            applicability_reason=reason,
            classification="work" if applies else "informational",
        )
        for m in store.all_for(r.part_id_old) + (
            store.all_for(r.part_id_new) if r.part_id_new != r.part_id_old else []
        ):
            ir.mapped_sections.append(
                {
                    "document_id": m.internal_document_id,
                    "section_id": m.section_id,
                    "prior_coverage": m.coverage,
                    "approved_by": m.approved_by or "(unapproved)",
                    "now": "UNVERIFIED — the Part it implements changed",
                }
            )
            if m.is_approved:
                ir.prior_verdicts_now_unverified.append(
                    f"{m.internal_document_id} {m.section_id}: was {m.coverage}"
                )
        if ir.applies and (ir.mapped_sections or not node):
            resolved += 1
        elif not ir.applies:
            resolved += 1  # informational is a substantive result
        out.append(ir)

    return {
        "standard": standard_base,
        "diff_summary": diff_summary(rows),
        # examined apart from substantively resolved (Bully GP)
        "examined": examined,
        "substantively_resolved": resolved,
        "impact_rows": [ir.to_dict() for ir in out],
        "work_items": sum(1 for ir in out if ir.classification == "work"),
        "informational": sum(1 for ir in out if ir.classification == "informational"),
    }


# ── Phase 4: mapping validity + coverage invalidation ─────────────────────
def expire_mappings(store: MappingStore, rows: list[DiffRow], supersession_date: str) -> dict:
    """For every mapping whose target Part is superseded or language-changed by
    the transition: close its ``valid_to`` and create the successor mapping as
    ``NEEDS_REVIEW`` — **never carrying the prior verdict forward.**"""
    affected_parts: dict[str, str] = {}  # old_id -> new_id (or "" for removal)
    for r in rows:
        if not r.to_dict()["substantive"]:
            continue
        if r.change_type in ("RENUMBERED", "LANGUAGE_CHANGED", "TIMELINE_CHANGED", "PART_REMOVED"):
            affected_parts[r.part_id_old or r.part_id_new] = r.part_id_new

    expired, successors = [], []
    for m in list(store._rows):
        if m.requirement_id not in affected_parts or not m.is_approved:
            continue
        m.valid_to = supersession_date
        expired.append(m.id)
        new_id = affected_parts[m.requirement_id]
        if new_id:
            succ = store.propose(
                new_id,
                m.internal_document_id,
                m.section_id,
                "NEEDS_REVIEW",  # verdict NOT inherited
                relationship=m.relationship,
                valid_from=supersession_date,
            )
            succ.confidence = 0.0
            succ.source = "successor_of_expired"
            successors.append(succ.id)
    store._save()
    return {
        "supersession_date": supersession_date,
        "n_expired": len(expired),
        "expired_mapping_ids": expired,
        "n_successors_needs_review": len(successors),
        "successor_ids": successors,
        "rule": "a mapping never inherits a verdict across a language change",
    }


def coverage_delta_for_transition(before: dict, after: dict) -> dict:
    """Compare two coverage-matrix summaries for the affected subset and report
    which cells moved (FULL -> PARTIAL, FULL -> NONE, ...)."""
    b = {c["requirement_id"]: c["coverage"] for c in before.get("cells", [])}
    a = {c["requirement_id"]: c["coverage"] for c in after.get("cells", [])}
    moves = [
        {"requirement_id": k, "from": b[k], "to": a[k]}
        for k in sorted(b.keys() & a.keys())
        if b[k] != a[k]
    ]
    return {"n_moved": len(moves), "moves": moves}


# ── Phase 5: prospective analysis ─────────────────────────────────────────
def prospective_report(reg: Register, scope: AssetScope, as_of: str) -> dict:
    """*"What must we prepare for, and by when."* Future-effective content is
    tagged and MUST NOT be returned by a "today" query — that segregation is the
    caller's contract; here every row is explicitly marked prospective."""
    from portal.modules.compliance.core.engine import future_effective_parts

    fut = future_effective_parts(reg, as_of)
    rows = []
    for n in fut:
        applies, reason = (
            applicable(n.applicable_systems, scope)
            if scope.is_declared
            else (True, "scope undeclared")
        )
        rows.append(
            {
                "requirement_id": n.id,
                "prospective": True,  # never a "today" obligation
                "enforcement_date": n.valid_from
                or "SEE Implementation Plan — verify, do not infer",
                "applies_to_scope": applies,
                "applicability_reason": reason,
                "verbatim_text": n.verbatim_text,
                "lead_time_note": "policy sections mapped to this Part will need revision before "
                f"{n.valid_from or 'the enforcement date'}",
            }
        )
    return {
        "as_of": as_of,
        "n_future_effective": len(rows),
        "answers": '"what must we prepare for, and by when"',
        "segregation": "every row marked prospective:true — MUST NOT reach a 'what must we do today' answer",
        "rows": rows,
    }


# ── Phase 6: drafted revisions [GATE] ────────────────────────────────────
def draft_revisions(impact: dict, *, mode: str = "specification_only") -> dict:
    """``[GATE]`` — does the engine draft policy language, or only specify what
    must change? Default and only-implemented mode: **(a) specification only** —
    output *what* must change and *why*, with both verbatim spans, and let an SME
    write the language. Modes (b)/(c) are the operator's decision (report, do not
    choose)."""
    if mode != "specification_only":
        raise NotImplementedError(
            "modes (b) draft-as-proposal and (c) draft-into-revision are the "
            "operator's [GATE] decision — not implemented. See ENGINE gate report."
        )
    specs = []
    for ir in impact["impact_rows"]:
        if ir["classification"] != "work":
            continue
        for sec in ir["mapped_sections"]:
            specs.append(
                {
                    "policy_section": f"{sec['document_id']} {sec['section_id']}",
                    "motivated_by": ir["changed_part"],
                    "change_type": ir["change_type"],
                    "old_requirement_span": ir["old_span"],
                    "new_requirement_span": ir["new_span"],
                    "prior_coverage": sec["prior_coverage"],
                    "what_must_change": "the section must be re-assessed against the NEW requirement "
                    "span and re-approved; the prior verdict does not carry forward",
                    "drafted_replacement": None,  # (a): an SME writes the language
                }
            )
    return {
        "gate": "does the engine draft policy language, or only specify what must change?",
        "mode": mode,
        "options": {
            "a": "specification only — output what/why with both spans; SME writes it (implemented)",
            "b": "draft as proposal — generate replacement text, permanently marked proposal",
            "c": "draft into a tracked revision workflow",
        },
        "recommendation": "report to operator; (a) is the capability with no new risk surface. "
        "A draft reads as finished work and is accepted more uncritically than a gap statement; "
        "granite-4.1-8b was demoted from this persona for fabricating regulatory requirements.",
        "n_sections_needing_revision": len(specs),
        "specifications": specs,
    }
