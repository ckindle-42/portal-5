"""The six operations (TASK_COMPLIANCE_REASONING_V6 P6).

The twelve operator questions are compositions of six primitives, not twelve
pipelines. Each has a typed contract; none calls a model on un-pre-analyzed
input; ``propose`` always re-runs ``judge`` on its own output.

| op        | deterministic part                                   | model part |
| --------- | ---------------------------------------------------- | ---------- |
| resolve   | interval selection, premise attach, meta-CU gating,  | (none —    |
|           | reference closure, CU decomposition                  |  structure) |
| trace     | graph traversal, cycle handling, budget, frontier    | none       |
| judge     | the gate; constraint arithmetic; quorum              | listwise   |
|           |                                                      | council +  |
|           |                                                      | exception  |
| diff      | text delta, lineage, affected-set closure            | change-    |
|           |                                                      | type class |
| norms     | permission-branch enumeration, constraint direction  | branch     |
|           |                                                      | choice     |
| propose   | re-running judge on the proposal; plan skeleton      | drafting   |

Model calls are injected (``seat_fn`` / ``draft_fn``); defaults talk to Ollama.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.council import SeatFn, run_council
from portal.modules.compliance.core.engine import parse_iso_date
from portal.modules.compliance.core.gate import run_gate
from portal.modules.compliance.core.policy_graph import PolicyGraph, build_policy_graph
from portal.modules.compliance.core.vocabulary_bridge import PolicyVocabulary, derive_vocabulary

# ── the change taxonomy (diff) ────────────────────────────────────────────
CHANGE_TYPES = (
    "NEW_DUTY",
    "TIGHTENED",
    "RELAXED",
    "SCOPE_CHANGE",
    "RECORDKEEPING_CHANGE",
    "EVIDENCE_CHANGE",
    "DEFINITION_CHANGE",
    "REFERENCE_CHANGE",
    "RENUMBER_ONLY",
    "EDITORIAL_ONLY",
)
_NO_REVIEW_WORK = ("RENUMBER_ONLY", "EDITORIAL_ONLY")


@dataclass
class GoverningSet:
    ref: str
    valid_at: str
    enforceable: bool
    actor_cus: list[dict[str, Any]]
    premises: list[dict[str, Any]]
    meta_cus: list[dict[str, Any]]
    reference_closure: list[str]
    label: str  # "current" | "historical" | "future" | "unknown_effectivity"


@dataclass
class Paths:
    start: str
    direction: str
    nodes: list[str]
    edges: list[dict[str, Any]]
    frontier: list[str]  # nodes reached at the budget edge, not expanded
    budget_hit: bool


@dataclass
class Determination:
    anchor: str
    determination: str
    finding_type: str
    citations: list[str]
    council_votes: dict[str, int]
    dissent: list[str]
    sme_decision_kind: str
    gate_gated_out: bool
    rationale: str


@dataclass
class NormativeProfile:
    ref: str
    branches: list[dict[str, Any]]  # permitted alternatives with selection conditions
    chosen_branch: str
    direction: str  # constraint direction where a quantity exists
    classification: str  # MORE_RESTRICTIVE | EQUIVALENT | LESS_RESTRICTIVE | INCOMPARABLE | ""
    intent: dict[str, Any]  # {"source": "policy_decisions:<id>"} or {"code": "U07_INTENT_UNKNOWN"}


@dataclass
class ProposePackage:
    target_ref: str
    replacement_text: str
    status: str  # always "proposed"
    closes_fields: list[str]
    rejudged: Determination | None
    weakens: list[str]
    diff_against_current: str


# ── resolve ────────────────────────────────────────────────────────────────


def resolve(
    ref: str,
    *,
    valid_at: str,
    known_at: str = "",
    scope: AssetScope | None = None,
    policy_graph: PolicyGraph | None = None,
) -> GoverningSet:
    parse_iso_date(valid_at, field="valid_at")
    g = policy_graph or build_policy_graph()
    scope = scope or AssetScope()
    nodes = [n for n in g.nodes if n.id == ref or n.id.startswith(ref + " ")]
    if not nodes:
        return GoverningSet(ref, valid_at, False, [], [], [], [], "unknown_effectivity")

    from portal.modules.compliance.core.cip_register import Register
    from portal.modules.compliance.core.engine import _is_enforceable_at

    reg_by_id = {n.id: n for n in Register.load().nodes}
    actor_cus, premises, meta_cus, ref_closure = [], [], [], set()
    label = "current"
    for n in nodes:
        rn = reg_by_id.get(n.id)
        enf = _is_enforceable_at(rn, valid_at) if rn else False
        if rn and not enf:
            label = "historical" if (rn.valid_to and rn.valid_to <= valid_at) else "future"
        entry = {"id": n.id, "text": n.verbatim_text, "type": n.node_type, "cu": n.cu}
        if n.node_type == "actor_cu":
            actor_cus.append(entry)
            for e in g.edges:
                if e["rel"] == "REFERS_TO" and e["src"] == n.id and e["dst"]:
                    ref_closure.add(e["dst"])
            meta_cus.extend(
                {"id": m, "text": next((x.verbatim_text for x in g.nodes if x.id == m), "")}
                for m in n.gated_by
            )
        elif n.node_type == "meta_cu":
            meta_cus.append(entry)
        else:
            premises.append(entry)
    # attach referenced actor-CU text as premises the reader needs
    for rc in sorted(ref_closure):
        node = next((x for x in g.nodes if x.id == rc), None)
        if node:
            premises.append({"id": rc, "text": node.verbatim_text, "type": "reference"})
    enforceable = any(
        _is_enforceable_at(reg_by_id[n["id"]], valid_at) for n in actor_cus if n["id"] in reg_by_id
    )
    return GoverningSet(
        ref=ref,
        valid_at=valid_at,
        enforceable=enforceable,
        actor_cus=actor_cus,
        premises=premises,
        meta_cus=[dict(t) for t in {tuple(sorted(m.items())) for m in meta_cus}],
        reference_closure=sorted(ref_closure),
        label=label,
    )


# ── trace ──────────────────────────────────────────────────────────────────


def trace(
    start: str,
    *,
    direction: str = "both",
    depth: int = 3,
    edge_types: tuple[str, ...] = (),
    policy_graph: PolicyGraph | None = None,
    org_edges: list[dict[str, Any]] | None = None,
    max_edges: int = 500,
) -> Paths:
    g = policy_graph or build_policy_graph()
    all_edges = list(g.edges) + list(org_edges or [])
    if edge_types:
        all_edges = [e for e in all_edges if e["rel"] in edge_types]
    fwd: dict[str, list[dict]] = {}
    rev: dict[str, list[dict]] = {}
    for e in all_edges:
        fwd.setdefault(e["src"], []).append(e)
        rev.setdefault(e["dst"], []).append(e)

    seen = {start}
    out_edges: list[dict] = []
    frontier: list[str] = []
    budget_hit = False
    q: deque[tuple[str, int]] = deque([(start, 0)])
    while q:
        node, d = q.popleft()
        if d >= depth:
            continue
        nbrs: list[dict] = []
        if direction in ("forward", "both"):
            nbrs += fwd.get(node, [])
        if direction in ("reverse", "both"):
            nbrs += rev.get(node, [])
        for e in nbrs:
            other = e["dst"] if e["src"] == node else e["src"]
            if not other:
                continue
            if len(out_edges) >= max_edges:
                budget_hit = True
                if other not in seen:
                    frontier.append(other)  # reached at the cutoff, not expanded
                continue
            out_edges.append(e)
            if other not in seen:
                seen.add(other)
                q.append((other, d + 1))
    return Paths(
        start=start,
        direction=direction,
        nodes=sorted(seen),
        edges=out_edges,
        frontier=sorted(set(frontier)),
        budget_hit=budget_hit,
    )


# ── judge ──────────────────────────────────────────────────────────────────


def judge(
    actor_cu_id: str,
    *,
    scope: AssetScope,
    org_commitments: list[dict[str, Any]],
    seats: list[dict[str, str]],
    policy_graph: PolicyGraph | None = None,
    vocab: PolicyVocabulary | None = None,
    seat_fn: SeatFn | None = None,
    retrieval_hits: list[dict[str, Any]] | None = None,
    reference_texts: dict[str, str] | None = None,
    quorum: float = 0.66,
) -> Determination:
    """The gate ALWAYS runs before the council (Y08). One listwise call per
    anchor; a second override call if the decision is unmet."""
    g = policy_graph or build_policy_graph()
    v = vocab or derive_vocabulary(g)
    gate_result = run_gate(actor_cu_id, g, v, scope, org_commitments, retrieval_hits)
    if gate_result.gated_out:
        return Determination(
            anchor=actor_cu_id,
            determination="NOT_APPLICABLE",
            finding_type="",
            citations=[actor_cu_id],
            council_votes={},
            dissent=[],
            sme_decision_kind="",
            gate_gated_out=True,
            rationale=gate_result.applicability_reason,
        )
    packet = gate_result.to_council_packet()
    if not reference_texts:
        reference_texts = {
            n.id: n.verbatim_text for n in g.nodes if n.id in gate_result.reference_closure
        }
    cr = run_council(packet, seats, seat_fn=seat_fn, quorum=quorum, reference_texts=reference_texts)
    return Determination(
        anchor=actor_cu_id,
        determination=cr.determination,
        finding_type=cr.finding_type,
        citations=cr.citations or [actor_cu_id],
        council_votes=cr.votes,
        dissent=cr.dissent,
        sme_decision_kind=cr.sme_decision_kind,
        gate_gated_out=False,
        rationale=cr.rationale,
    )


# ── diff ───────────────────────────────────────────────────────────────────

_REGISTER_TYPE_MAP = {
    "PART_ADDED": "NEW_DUTY",
    "PART_REMOVED": "RELAXED",
    "RENUMBERED": "RENUMBER_ONLY",
    "LANGUAGE_CHANGED": "TIGHTENED",  # refined below by cues
}


def diff(rev_a: str, rev_b: str, *, classify_fn: Any | None = None) -> list[dict[str, Any]]:
    """Text delta + lineage (deterministic) then a change-type per row. The
    model classifies ambiguous LANGUAGE_CHANGED rows; the rest are structural."""
    from portal.modules.compliance.core.cip_register import Register
    from portal.modules.compliance.core.register_diff import diff_standard

    reg = Register.load()
    base = rev_a.rsplit("-", 1)[0]
    a = Register(nodes=[n for n in reg.nodes if n.standard == rev_a], edges=reg.edges)
    b = Register(nodes=[n for n in reg.nodes if n.standard == rev_b], edges=reg.edges)
    rows = diff_standard(a, b, base)
    out = []
    for r in rows:
        d = r.to_dict()
        ct = _REGISTER_TYPE_MAP.get(d["change_type"], "EDITORIAL_ONLY")
        if d["change_type"] == "LANGUAGE_CHANGED":
            ct = _classify_language_change(d, classify_fn)
        d["taxonomy_type"] = ct
        d["creates_review_work"] = ct not in _NO_REVIEW_WORK
        out.append(d)
    return out


def _classify_language_change(d: dict[str, Any], classify_fn: Any | None) -> str:
    old, new = d.get("old_span", ""), d.get("new_span", "")
    low_new, low_old = new.lower(), old.lower()
    if d.get("sub_type") == "cosmetic":
        return "EDITORIAL_ONLY"
    if any(k in low_new for k in ("retain", "retention", "record")) != any(
        k in low_old for k in ("retain", "retention", "record")
    ):
        return "RECORDKEEPING_CHANGE"
    if "evidence" in low_new or "measure" in low_new:
        return "EVIDENCE_CHANGE"
    if any(
        k in low_new for k in ("applicable systems", "high impact", "medium impact", "low impact")
    ):
        return "SCOPE_CHANGE"
    if "cip-" in low_new and "cip-" not in low_old:
        return "REFERENCE_CHANGE"
    import re

    def _num(t: str) -> list[int]:
        return [
            int(x) for x in re.findall(r"\b(\d+)\s+(?:calendar|business)?\s*(?:day|month|year)", t)
        ]

    on, nn = _num(low_old), _num(low_new)
    if on and nn:
        return "TIGHTENED" if min(nn) < min(on) else "RELAXED"
    if classify_fn is not None:
        try:
            guess = str(classify_fn(old, new)).upper().strip()
            if guess in CHANGE_TYPES:
                return guess
        except Exception:  # noqa: BLE001
            pass
    return "TIGHTENED"


# ── norms ──────────────────────────────────────────────────────────────────

_PERMISSION_CUES = ("may include", "may be", "one or more of the following", "either", " or ")


def norms(
    actor_cu_id: str,
    internal_quantities: list[dict[str, Any]] | None = None,
    *,
    policy_graph: PolicyGraph | None = None,
    policy_decisions: dict[str, dict[str, Any]] | None = None,
) -> NormativeProfile:
    g = policy_graph or build_policy_graph()
    node = next((n for n in g.nodes if n.id == actor_cu_id), None)
    if node is None:
        raise ValueError(f"{actor_cu_id!r} not in policy graph")
    text = node.verbatim_text
    branches = []
    low = text.lower()
    for cue in _PERMISSION_CUES:
        i = low.find(cue)
        if i >= 0:
            branches.append({"cue": cue.strip(), "text": text[i : i + 160], "char_start": i})
    q = node.cu.get("constraint", {}).get("quantity") if node.cu else None
    direction = q.get("direction", "") if q else ""
    classification = ""
    if q and internal_quantities:
        from portal.modules.compliance.core.constraints import Quantity, compare_constraint

        kind = "max_interval" if direction in ("max_interval", "max_elapsed") else "min_retention"
        gov = Quantity(q["value"], q["unit"], q.get("qualifier"))
        outs = set()
        for iq in internal_quantities:
            try:
                res, _ = compare_constraint(
                    kind, gov, Quantity(iq["value"], iq["unit"], iq.get("qualifier"))
                )
                outs.add(res)
            except ValueError:
                outs.add("INCOMPARABLE")
        classification = (
            "MORE_RESTRICTIVE"
            if outs == {"MORE_RESTRICTIVE"}
            else "LESS_RESTRICTIVE"
            if "LESS_RESTRICTIVE" in outs
            else "EQUIVALENT"
            if outs == {"EQUIVALENT"}
            else "INCOMPARABLE"
        )
    pd = (policy_decisions or {}).get(actor_cu_id)
    intent = (
        {"source": f"policy_decisions:{pd['id']}", "intentional": pd.get("intentional")}
        if pd
        else {"code": "U07_INTENT_UNKNOWN", "control_id": actor_cu_id}
    )
    return NormativeProfile(
        ref=actor_cu_id,
        branches=branches,
        chosen_branch="",  # filled by the model part in the planner
        direction=direction,
        classification=classification,
        intent=intent,
    )


# ── propose ────────────────────────────────────────────────────────────────


def propose(
    target_ref: str,
    unmet_fields: list[str],
    draft_text: str,
    *,
    scope: AssetScope,
    org_commitments: list[dict[str, Any]],
    seats: list[dict[str, str]],
    seat_fn: SeatFn | None = None,
    policy_graph: PolicyGraph | None = None,
) -> ProposePackage:
    """A proposal is NEVER emitted without being re-judged by the same gate +
    council that found the problem (task §3, rule 2)."""
    g = policy_graph or build_policy_graph()
    # re-judge: the proposed text becomes the sole candidate commitment
    proposed_commitment = {
        "commitment_id": f"proposed:{target_ref}",
        "document_id": "proposed",
        "standard_folder": next(
            (n.standard.rsplit("-", 1)[0] for n in g.nodes if n.id == target_ref), ""
        ),
        "actor": "Responsible Entity",
        "text": draft_text,
    }
    rejudged = judge(
        target_ref,
        scope=scope,
        org_commitments=[*org_commitments, proposed_commitment],
        seats=seats,
        policy_graph=g,
        seat_fn=seat_fn,
    )
    weakens: list[str] = []
    if rejudged.determination in ("PARTIAL", "CONTRADICTED", "ABSENT", "ESCALATE"):
        weakens.append(
            f"proposal does not close {target_ref}: re-judgment returned {rejudged.determination}"
        )
    return ProposePackage(
        target_ref=target_ref,
        replacement_text=draft_text,
        status="proposed",
        closes_fields=list(unmet_fields) if rejudged.determination == "SUPPORTED" else [],
        rejudged=rejudged,
        weakens=weakens,
        diff_against_current="",
    )
