"""The gate (TASK_COMPLIANCE_REASONING_V6 P4).

Structural reasoning the models should never be asked to do. **No model call
happens in this module.** Given one actor-CU and the operator's declared asset
scope, the gate produces a *constrained, pre-analyzed problem* for the council:

  1. meta-CU applicability — evaluated FIRST (``applicability.applicability_state``
     over the gating meta-CUs). ``DOES_NOT_APPLY`` short-circuits: the CU is
     gated out, never handed to the council, never scored ABSENT.
  2. actor alignment — every candidate commitment's actor is resolved against
     the CU's ``subject`` through the vocabulary bridge (recorded chain).
  3. reference / exception closure — the CU's REFERS_TO closure plus its own
     ``condition`` clauses of kind ``exception``, computed by traversal.
  4. constraint arithmetic — where the CU carries a parsed quantity, every
     candidate's quantity is compared with ``constraints.compare_constraint``
     (direction-aware: max_interval vs min_retention).
  5. candidate plan — assembled from the organization graph by structured
     filter (standard folder + vocabulary overlap), with retrieval hits as a
     ranking aid and recall backstop whose *surplus* is reported, never
     silently unioned.

The gate always runs before the council (Y08).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from portal.modules.compliance.core.applicability import AssetScope, applicability_state
from portal.modules.compliance.core.constraints import Quantity, compare_constraint
from portal.modules.compliance.core.policy_graph import PolicyGraph
from portal.modules.compliance.core.vocabulary_bridge import PolicyVocabulary, align_actor

_UNIT_ALIASES = {
    "minute": "minute",
    "hour": "hour",
    "day": "day",
    "week": "week",
    "month": "month",
    "year": "year",
}
# a council packet must fit the smallest seat's context — real gate output
# otherwise reaches ~16k tokens with 100+ loosely-matched candidates
_MAX_STRUCTURED_CANDIDATES = 15


@dataclass
class CandidateAssessment:
    commitment_id: str
    document_id: str
    text: str
    source: str  # "structured_filter" | "retrieval_backstop"
    actor_aligned: bool
    actor_note: str
    quantity_outcome: str  # "" | EQUIVALENT | MORE_RESTRICTIVE | LESS_RESTRICTIVE | INCOMPARABLE
    quantity_note: str


@dataclass
class GateResult:
    actor_cu_id: str
    applicability: str  # APPLIES | DOES_NOT_APPLY | UNKNOWN | CONFLICTED
    applicability_reason: str
    gated_out: bool
    cu: dict[str, Any]
    reference_closure: list[str]
    exception_clauses: list[dict[str, Any]]
    candidates: list[CandidateAssessment] = field(default_factory=list)
    backstop_surplus: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_council_packet(self) -> dict[str, Any]:
        """The structured-JSON packet the council seat receives — a
        pre-analyzed problem, never raw text (P5)."""
        return {
            "governing_unit": {"ref": self.actor_cu_id, **self.cu},
            "applicability": {"state": self.applicability, "reason": self.applicability_reason},
            "reference_closure": self.reference_closure,
            "exception_clauses": self.exception_clauses,
            "candidates": [asdict(c) for c in self.candidates],
            "backstop_surplus": self.backstop_surplus,
        }


def _quantity_from_parsed(q: dict[str, Any] | None) -> tuple[Quantity | None, str]:
    if not q:
        return None, ""
    unit = _UNIT_ALIASES.get(q.get("unit", ""), q.get("unit", ""))
    direction = q.get("direction", "")
    kind = (
        "max_interval"
        if direction in ("max_interval", "max_elapsed")
        else ("min_retention" if direction == "min_interval" else "")
    )
    if not unit or unit not in ("hour", "day", "week", "month", "year") or not kind:
        return None, ""
    return Quantity(int(q["value"]), unit, q.get("qualifier") or None), kind


_QTY_TOKEN = None


def _extract_internal_quantity(text: str) -> Quantity | None:
    import re

    global _QTY_TOKEN
    if _QTY_TOKEN is None:
        _QTY_TOKEN = re.compile(
            r"(\d+)\s+(?:(calendar|business)\s+)?(hour|day|week|month|year)s?", re.I
        )
    m = _QTY_TOKEN.search(text)
    if not m:
        return None
    return Quantity(int(m.group(1)), m.group(3).lower(), (m.group(2) or "").lower() or None)


def run_gate(
    actor_cu_id: str,
    policy_graph: PolicyGraph,
    vocab: PolicyVocabulary,
    scope: AssetScope,
    org_commitments: list[dict[str, Any]],
    retrieval_hits: list[dict[str, Any]] | None = None,
) -> GateResult:
    """Produce the pre-analyzed problem for one actor-CU. No model calls."""
    node = next((n for n in policy_graph.nodes if n.id == actor_cu_id), None)
    if node is None or node.node_type != "actor_cu":
        raise ValueError(f"{actor_cu_id!r} is not an actor_cu in the policy graph")

    # 1. applicability — meta-CUs first
    applic, reason = applicability_state(node.applicable_systems, scope)
    cu = node.cu
    if applic == "DOES_NOT_APPLY":
        return GateResult(
            actor_cu_id=actor_cu_id,
            applicability=applic,
            applicability_reason=reason,
            gated_out=True,
            cu=cu,
            reference_closure=[],
            exception_clauses=[],
            notes=["gated out before judgment — never scored ABSENT (task §1.2)"],
        )

    # 3. reference + exception closure by traversal
    ref_closure = sorted(
        {
            e["dst"]
            for e in policy_graph.edges
            if e["rel"] == "REFERS_TO" and e["src"] == actor_cu_id and e["dst"]
        }
    )
    exception_clauses = [c for c in cu.get("condition", []) if c.get("kind") == "exception"]

    gov_q, gov_kind = _quantity_from_parsed(cu.get("constraint", {}).get("quantity"))
    subject_text = cu.get("subject", {}).get("text", "")

    # 5. candidate plan — structured filter, then retrieval backstop
    structured: list[dict[str, Any]] = []
    std = node.standard.rsplit("-", 1)[0]  # "CIP-007"
    strong_terms = {t.lower() for t in vocab.strong_terms()}
    cu_terms = {
        w.lower()
        for w in (cu.get("constraint", {}).get("text", "") + " " + node.verbatim_text).split()
        if len(w) > 3
    }
    scored: list[tuple[int, dict[str, Any]]] = []
    for c in org_commitments:
        folder_ok = c.get("standard_folder", "") in ("", std)
        overlap = len({t for t in cu_terms if t in c.get("text", "").lower()})
        term_hit = bool(cu_terms & {w.lower() for w in c.get("text", "").split()} & strong_terms)
        if folder_ok and (overlap >= 3 or term_hit):
            scored.append((overlap + (2 if term_hit else 0), c))
    # rank by overlap and cap — a council packet must stay inside the seat's
    # context (real gate packets otherwise reach ~16k tokens with 100+
    # loosely-matched candidates); the surplus below the cap is disclosed.
    scored.sort(key=lambda t: -t[0])
    structured = [c for _, c in scored[:_MAX_STRUCTURED_CANDIDATES]]
    dropped_for_budget = len(scored) - len(structured)

    structured_ids = {c["commitment_id"] for c in structured}
    backstop = []
    for h in retrieval_hits or []:
        if h.get("commitment_id") not in structured_ids:
            backstop.append(h)

    candidates: list[CandidateAssessment] = []
    for c, src in [(c, "structured_filter") for c in structured] + [
        (c, "retrieval_backstop") for c in backstop
    ]:
        align = align_actor(c.get("actor", "") or subject_text, subject_text, vocab)
        q_outcome, q_note = "", ""
        if gov_q and gov_kind:
            iq = _extract_internal_quantity(c.get("text", ""))
            if iq:
                q_outcome, q_note = compare_constraint(gov_kind, gov_q, iq)
        candidates.append(
            CandidateAssessment(
                commitment_id=c.get("commitment_id", ""),
                document_id=c.get("document_id", ""),
                text=c.get("text", ""),
                source=src,
                actor_aligned=align.aligned,
                actor_note=align.note,
                quantity_outcome=q_outcome,
                quantity_note=q_note,
            )
        )

    notes = []
    if backstop:
        notes.append(
            f"{len(backstop)} retrieval-backstop candidate(s) not found by the structured "
            "filter — surplus reported for investigation, not silently unioned (task §P4)"
        )
    if dropped_for_budget:
        notes.append(
            f"{dropped_for_budget} lower-ranked structured candidate(s) held below the "
            f"{_MAX_STRUCTURED_CANDIDATES}-candidate packet cap — disclosed, not silently dropped"
        )
    return GateResult(
        actor_cu_id=actor_cu_id,
        applicability=applic,
        applicability_reason=reason,
        gated_out=False,
        cu=cu,
        reference_closure=ref_closure,
        exception_clauses=exception_clauses,
        candidates=candidates,
        backstop_surplus=[c.get("commitment_id", "") for c in backstop],
        notes=notes,
    )
