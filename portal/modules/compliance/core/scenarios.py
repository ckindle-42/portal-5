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
from portal.modules.compliance.core.assessment import assess_requirement, serialize
from portal.modules.compliance.core.boundary import BoundarySearch, build_queries
from portal.modules.compliance.core.change_plan import build as build_change_plan
from portal.modules.compliance.core.cip_register import Register
from portal.modules.compliance.core.coverage import ProposeFn, _qualified
from portal.modules.compliance.core.mapping_store import MappingStore
from portal.modules.compliance.core.obligations import decompose
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
    """Return isolated before/after determinations and a change package."""
    target_reg = Register(
        nodes=[n for n in reg.nodes if n.id == scenario.target_node_id], edges=reg.edges
    )
    if not target_reg.nodes:
        return {"error": f"target_node_id not found in register: {scenario.target_node_id}"}

    node = target_reg.nodes[0]
    atom = decompose(node.id, node.verbatim_text, anchor_ids=[node.id])[0].to_record()
    atom_id = atom["atom_id"]
    model = {"node_id": node.id, "atoms": [atom], "expression_id": f"expr:{node.id}"}
    raw_before = []
    for side in ("policy", "procedure", "evidence"):
        raw_before.extend(_qualified(real_propose(node, side)))
    before_candidates = []
    for index, row in enumerate(raw_before):
        parsed = decompose(f"candidate:{index}", row.get("span", ""))[0].to_record()
        parsed["anchor_id"] = row.get("section_id", "")
        before_candidates.append(parsed)
    proposed = decompose("scenario-proposal", scenario.patch_text)[0].to_record()
    proposed["anchor_id"] = f"scenario:{node.id}"
    # A patch is replacement text for the targeted section, not an additive
    # supplement. Keeping the old assertion would make weakening impossible
    # to detect because the still-present old text would continue to satisfy it.
    after_candidates = [proposed]
    boundary = BoundarySearch(
        node.id, build_queries(node.id, atom), "live-proposer", "runtime", len(raw_before)
    )
    context = {"valid_at": effective_on, "applicability": "APPLIES", "boundary": boundary}
    before_result = assess_requirement(
        model, {**context, "candidates": {atom_id: before_candidates}}
    )
    after_result = assess_requirement(model, {**context, "candidates": {atom_id: after_candidates}})
    before_cell, after_cell = serialize(before_result), serialize(after_result)

    return {
        "scenario_id": scenario.scenario_id,
        "target_node_id": scenario.target_node_id,
        "rationale": scenario.rationale,
        "planned_effective_date": scenario.planned_effective_date,
        "before": before_cell,
        "after": after_cell,
        "determination_changed": before_result.determination != after_result.determination,
        "qualification_changed": before_result.determination != after_result.determination,
        "weakening": before_result.determination == "SUPPORTED"
        and after_result.determination != "SUPPORTED",
        "affected_obligation": node.id,
        "change_plan": build_change_plan({"target_node_id": node.id}),
        "note": "Isolated deterministic assessment; proposed text is not written to the effective graph.",
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
