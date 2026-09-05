"""Proposed-change scenarios (P6.6 / design §7.3 / Q12).

A scenario evaluates a proposed patch to ONE targeted obligation against
today's governing register, without writing to the mapping store or any
persisted document — the patch text is injected only as an in-memory
candidate span for this one evaluation. This is the bounded, deterministic
half of what Q12 asks for: "before/after documented alignment... against
current and relevant future obligations."

What this does NOT do (design §6.2/§6.3's bounded-LLM territory, not
attempted this session): draft the replacement language itself, evaluate
free-text semantic equivalence, or produce the full ordered implementation
plan (owner/training/rollback). It answers a narrower, honestly-scoped
question: does injecting this exact proposed text change whether the
obligation-atom/candidate layer can see qualified evidence for it, per the
SAME qualification rule (`coverage._qualified`) the live engine already uses
— never a compliance verdict, since that is P5's unbuilt comparison engine.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.cip_register import Register
from portal.modules.compliance.core.coverage import ProposeFn, coverage_matrix
from portal.modules.compliance.core.mapping_store import MappingStore
from portal.modules.compliance.core.temporal import now_iso


@dataclass
class ChangeScenario:
    scenario_id: str
    target_node_id: str
    patch_text: str
    rationale: str
    scope_note: str
    planned_effective_date: str | None
    created_at: str = field(default_factory=now_iso)


def _patched_propose(real_propose: ProposeFn, target_node_id: str, patch_text: str) -> ProposeFn:
    """Wraps a real proposer so that, for ``target_node_id`` only, an
    additional synthetic candidate carrying ``patch_text`` is injected on the
    procedure side — never written to any store, never affecting any other
    Part's evaluation."""

    def wrapped(node, side: str) -> list[dict]:
        candidates = list(real_propose(node, side))
        if node.id == target_node_id and side == "procedure":
            candidates.append(
                {
                    "document_id": "SCENARIO-PROPOSED-PATCH",
                    "section_id": f"scenario:{target_node_id}",
                    "span": patch_text,
                    "text": patch_text,
                    "anchor_verified": True,
                    "relevant": True,
                    "locatable": True,
                }
            )
        return candidates

    return wrapped


def evaluate_scenario(
    scenario: ChangeScenario,
    reg: Register,
    scope: AssetScope,
    effective_on: str,
    real_propose: ProposeFn,
    mapping_store: MappingStore | None = None,
) -> dict:
    """Before/after comparison for one targeted obligation. Returns both
    cells' full dict form plus an explicit ``qualification_changed`` flag —
    the one thing this deterministic evaluator can honestly claim. A caller
    wanting a full documented-alignment verdict still needs P5's comparison
    engine, not yet implemented; this never fabricates one."""
    target_reg = Register(
        nodes=[n for n in reg.nodes if n.id == scenario.target_node_id], edges=reg.edges
    )
    if not target_reg.nodes:
        return {"error": f"target_node_id not found in register: {scenario.target_node_id}"}

    before_mx = coverage_matrix(target_reg, scope, effective_on, real_propose, mapping_store)
    after_mx = coverage_matrix(
        target_reg,
        scope,
        effective_on,
        _patched_propose(real_propose, scenario.target_node_id, scenario.patch_text),
        mapping_store,
    )
    before_cell = before_mx.cells[0].to_dict() if before_mx.cells else None
    after_cell = after_mx.cells[0].to_dict() if after_mx.cells else None

    return {
        "scenario_id": scenario.scenario_id,
        "target_node_id": scenario.target_node_id,
        "rationale": scenario.rationale,
        "planned_effective_date": scenario.planned_effective_date,
        "before": before_cell,
        "after": after_cell,
        "qualification_changed": bool(before_cell)
        and bool(after_cell)
        and before_cell["coverage"] != after_cell["coverage"],
        "note": "This compares QUALIFICATION signal only (does the candidate layer see "
        "evidence for this obligation) — never a documented-alignment verdict, which "
        "requires P5's obligation-atom comparison engine (not implemented). A patch "
        "that changes qualification still requires SME review before it means anything.",
    }


def new_scenario(
    target_node_id: str,
    patch_text: str,
    rationale: str,
    scope_note: str = "",
    planned_effective_date: str | None = None,
) -> ChangeScenario:
    return ChangeScenario(
        scenario_id=uuid.uuid4().hex[:12],
        target_node_id=target_node_id,
        patch_text=patch_text,
        rationale=rationale,
        scope_note=scope_note,
        planned_effective_date=planned_effective_date,
    )
