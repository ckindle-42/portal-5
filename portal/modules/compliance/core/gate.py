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

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from portal.modules.compliance.core.applicability import AssetScope, applicability_state
from portal.modules.compliance.core.constraints import (
    CONSTRAINT_KINDS,
    Quantity,
    compare_constraint,
)
from portal.modules.compliance.core.determination import (
    AlignmentRecord,
    AlignmentResult,
    AssessmentContext,
    AssessmentRequest,
    CandidateRecord,
    ConstraintBinding,
    GoverningBundle,
)
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
    # ── aligned-gate additions (reading architecture §4) ────────────────────
    excluded: list[dict[str, Any]] = field(default_factory=list)
    unknowns: list[dict[str, Any]] = field(default_factory=list)
    binding_outcomes: list[dict[str, Any]] = field(default_factory=list)
    acquisition_completeness: str = "UNKNOWN"
    governing_fingerprint: str = ""

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
            "excluded": self.excluded,
            "unknowns": self.unknowns,
            "binding_outcomes": self.binding_outcomes,
            "acquisition_completeness": self.acquisition_completeness,
            "governing_fingerprint": self.governing_fingerprint,
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


# ── aligned gate (reading architecture §4) ──────────────────────────────────
# The aligned gate consumes an already prepared AlignmentResult and the pinned
# candidate set. Semantic selection happened in obligation_alignment; this
# module only assembles the authoritative packet and runs the reviewed
# arithmetic over model-selected, source-verified operands. It never picks a
# candidate by word overlap, folder, candidate order or first number.

_BINDING_UNITS = ("hour", "day", "week", "month", "year")
_EXCLUDED_FUNCTIONS = ("DEFINITION", "AUTHORITY_RECORD", "CROSS_REFERENCE_TABLE", "CONTENTS")
_ACTOR_PATTERNS = (
    re.compile(r"\bResponsible Entity\b", re.I),
    re.compile(
        r"\b(?:each|the)\s+([A-Z][A-Za-z0-9&'\- ]{2,60}?)\s+"
        r"(?:shall|must|will|is required to)\b"
    ),
)
_APPROVER_PATTERN = re.compile(
    r"approved\s+by\s+(?:the\s+)?([A-Z][A-Za-z0-9&'\- ]+?)"
    r"(?:\s+or\s+(?:their\s+)?delegate|\s*[.,;]|\s*$)"
)
_VOCAB_CACHE: list[Any] = []


def compare_aligned(binding: ConstraintBinding, link: AlignmentRecord) -> tuple[str, str]:
    """Deterministic arithmetic over one source-verified SAME binding.

    Rejects any operand that is not carried by a SAME link whose population is
    not DISJOINT, then defers to the reviewed ``compare_constraint``. An
    INCOMPARABLE result is uncertainty, never a contradiction."""
    if link.relation != "SAME":
        return "INCOMPARABLE", f"link relation is {link.relation}, not source-verified SAME"
    if link.population_overlap == "DISJOINT":
        return "INCOMPARABLE", "populations are disjoint — different obligations, no arithmetic"
    if binding.link_id != link.link_id:
        return "INCOMPARABLE", "binding link_id does not match the alignment record"
    if binding.governing_slice_id not in link.governing_slice_ids:
        return "INCOMPARABLE", "governing operand is not a cited slice of the SAME link"
    if binding.candidate_slice_id not in link.candidate_slice_ids:
        return "INCOMPARABLE", "candidate operand is not a cited slice of the SAME link"
    governing = _binding_quantity(binding.governing_quantity)
    internal = _binding_quantity(binding.internal_quantity)
    if governing is None or internal is None:
        return "INCOMPARABLE", "one or both bound quantities is missing or ill-formed"
    if binding.constraint_kind not in CONSTRAINT_KINDS:
        return "INCOMPARABLE", f"unknown constraint kind {binding.constraint_kind!r}"
    return compare_constraint(binding.constraint_kind, governing, internal)


def run_aligned_gate(
    request: AssessmentRequest,
    alignment: AlignmentResult,
    context: AssessmentContext,
) -> GateResult:
    """Assemble the council packet from the authoritative Part and alignment."""
    governing = request.governing
    governing_ref = (governing.ref if governing else "") or request.requirement_id
    scope = request.scope if request.scope is not None else AssetScope()
    applic, reason = applicability_state(_applicable_systems_text(governing), scope)
    subject = _derive_actor(governing)
    pairs = [
        (record, binding)
        for record in alignment.records
        if record.relation == "SAME"
        for binding in record.constraint_bindings
    ]
    if applic == "DOES_NOT_APPLY":
        return GateResult(
            actor_cu_id=governing_ref,
            applicability=applic,
            applicability_reason=reason,
            gated_out=True,
            cu=_governing_cu(governing, governing_ref, subject, None),
            reference_closure=[],
            exception_clauses=_exception_clauses(governing),
            notes=["gated out before judgment — never scored ABSENT (task §1.2)"],
            acquisition_completeness=_completeness(request),
            governing_fingerprint=governing.fingerprint if governing else "",
        )

    scalar = _scalar_results(pairs)
    quantities = [b.governing_quantity for _, b in pairs]
    single_quantity = quantities[0] if len(pairs) == 1 else None
    candidates, excluded, unknowns = _aligned_candidates(
        alignment, request.candidate_set, subject, scalar
    )
    outcomes = _binding_results(pairs)
    notes = _aligned_notes(alignment, excluded, unknowns, applic)
    return GateResult(
        actor_cu_id=governing_ref,
        applicability=applic,
        applicability_reason=reason,
        gated_out=False,
        cu=_governing_cu(governing, governing_ref, subject, single_quantity),
        reference_closure=_reference_closure(governing),
        exception_clauses=_exception_clauses(governing),
        candidates=candidates,
        backstop_surplus=[],
        notes=notes,
        excluded=excluded,
        unknowns=unknowns,
        binding_outcomes=outcomes,
        acquisition_completeness=_completeness(request),
        governing_fingerprint=governing.fingerprint if governing else "",
    )


def _aligned_candidates(
    alignment: AlignmentResult,
    candidate_set: Any,
    subject: str,
    scalar: dict[str, tuple[str, str]],
) -> tuple[list[CandidateAssessment], list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[CandidateAssessment] = []
    excluded: list[dict[str, Any]] = []
    unknowns: list[dict[str, Any]] = []
    for record in alignment.records:
        if _substantive(record):
            candidates.append(_build_aligned_candidate(record, candidate_set, subject, scalar))
            continue
        entry = _trace_entry(record)
        excluded.append(entry)
        if record.relation == "UNKNOWN":
            unknowns.append(entry)
    return candidates, excluded, unknowns


def _build_aligned_candidate(
    record: AlignmentRecord,
    candidate_set: Any,
    subject: str,
    scalar: dict[str, tuple[str, str]],
) -> CandidateAssessment:
    candidate: CandidateRecord | None = (
        candidate_set.by_id(record.candidate_ref) if candidate_set else None
    )
    text = candidate.text if candidate else ""
    aligned, note = _actor_alignment_note(text, subject)
    outcome, quantity_note = scalar.get(record.candidate_ref, ("", ""))
    doc_name = (candidate.document_id if candidate else "") or record.document_id
    stable = record.candidate_ref or record.link_id
    return CandidateAssessment(
        # Carry both the human-readable document name (so a seat's citation of
        # "B22.txt" resolves in the council allowlist) and the stable id.
        commitment_id=f"{doc_name} {stable}".strip() if doc_name else stable,
        document_id=candidate.document_id if candidate else "",
        text=text,
        source="aligned",
        actor_aligned=aligned,
        actor_note=note,
        quantity_outcome=outcome,
        quantity_note=quantity_note,
    )


def _binding_results(
    pairs: list[tuple[AlignmentRecord, ConstraintBinding]],
) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for record, binding in pairs:
        result, explanation = compare_aligned(binding, record)
        outcomes.append(
            {
                "link_id": record.link_id,
                "binding_id": binding.binding_id,
                "governing_slice_id": binding.governing_slice_id,
                "candidate_slice_id": binding.candidate_slice_id,
                "result": result,
                "explanation": explanation,
            }
        )
    return outcomes


def _scalar_results(
    pairs: list[tuple[AlignmentRecord, ConstraintBinding]],
) -> dict[str, tuple[str, str]]:
    # the legacy scalar is populated only for one unambiguous aligned constraint
    if len(pairs) != 1:
        return {}
    record, binding = pairs[0]
    return {record.candidate_ref: compare_aligned(binding, record)}


def _governing_cu(
    governing: GoverningBundle | None,
    ref: str,
    subject: str,
    quantity: dict[str, Any] | None,
) -> dict[str, Any]:
    part_text = governing.part_text if governing else ""
    lead_in = governing.lead_in if governing else ""
    constraint: dict[str, Any] = {"text": part_text or lead_in or ref}
    if quantity:
        constraint["quantity"] = quantity
    return {
        "ref": ref,
        "verbatim_text": part_text,
        "lead_in": lead_in,
        "subject": {"text": subject},
        "constraint": constraint,
        "condition": _exception_clauses(governing),
        "definitions": list(governing.definitions) if governing else [],
        "references": list(governing.references) if governing else [],
        "source_slice_ids": [s.slice_id for s in governing.source_slices] if governing else [],
    }


def _reference_closure(governing: GoverningBundle | None) -> list[str]:
    if governing is None:
        return []
    refs: list[str] = []
    for collection in (governing.references, governing.definitions):
        for item in collection or []:
            if not isinstance(item, dict):
                continue
            ref = item.get("ref") or item.get("logical_id") or ""
            if ref:
                refs.append(str(ref))
    seen: set[str] = set()
    out: list[str] = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            out.append(ref)
    return out


def _exception_clauses(governing: GoverningBundle | None) -> list[dict[str, Any]]:
    if governing is None:
        return []
    out: list[dict[str, Any]] = []
    for collection in (governing.definitions, governing.references, governing.meta):
        for item in collection or []:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind", "")).lower()
            role = str(item.get("role", "")).lower()
            if kind == "exception" or role == "exception":
                out.append({"ref": str(item.get("ref", "")), "text": str(item.get("text", ""))})
    return out


def _substantive(record: AlignmentRecord) -> bool:
    if record.source_function in _EXCLUDED_FUNCTIONS:
        return False
    if record.relation == "SAME":
        return True
    return record.relation == "UNKNOWN" and record.source_function == "OPERATIVE_COMMITMENT"


def _exclusion_reason(record: AlignmentRecord) -> str:
    if record.relation == "DIFFERENT":
        return "alignment read DIFFERENT — not reinserted as a substantive candidate"
    if record.source_function in _EXCLUDED_FUNCTIONS:
        return f"non-operative source function {record.source_function} — not substantive"
    return "not a substantive operative commitment"


def _trace_entry(record: AlignmentRecord) -> dict[str, Any]:
    return {
        "link_id": record.link_id,
        "candidate_ref": record.candidate_ref,
        "relation": record.relation,
        "source_function": record.source_function,
        "rationale": record.rationale,
        "missing_facts": list(record.missing_facts),
        "reason": _exclusion_reason(record),
    }


def _aligned_notes(
    alignment: AlignmentResult,
    excluded: list[dict[str, Any]],
    unknowns: list[dict[str, Any]],
    applic: str,
) -> list[str]:
    notes: list[str] = []
    if not alignment.valid:
        notes.append(f"alignment was not valid: {alignment.failure}")
    if excluded:
        notes.append(f"{len(excluded)} record(s) excluded from the substantive candidate list")
    if unknowns:
        notes.append(f"{len(unknowns)} unresolved potentially-operative record(s) retained")
    if applic != "APPLIES":
        notes.append(f"applicability is {applic} — the packet is provisional")
    return notes


def _applicable_systems_text(governing: GoverningBundle | None) -> str:
    if governing is None:
        return ""
    for item in governing.meta or []:
        if isinstance(item, dict):
            for key in ("applicable_systems", "applicable_systems_text", "applies_to"):
                value = item.get(key)
                if value:
                    return str(value)
    return ""


def _completeness(request: AssessmentRequest) -> str:
    return request.snapshot.completeness if request.snapshot else "UNKNOWN"


def _derive_actor(governing: GoverningBundle | None) -> str:
    lead_in = governing.lead_in if governing else ""
    part_text = governing.part_text if governing else ""
    actor = _leading_actor(lead_in) or _leading_actor(part_text)
    approver = _exception_approver(part_text)
    if actor and approver and approver.lower() in actor.lower():
        actor = ""
    return actor or "Responsible Entity"


def _leading_actor(text: str) -> str:
    if not text:
        return ""
    match = _ACTOR_PATTERNS[0].search(text)
    if match:
        return "Responsible Entity"
    match = _ACTOR_PATTERNS[1].search(text)
    if match:
        return match.group(1).strip()
    return ""


def _exception_approver(text: str) -> str:
    if not text:
        return ""
    match = _APPROVER_PATTERN.search(text)
    return match.group(1).strip() if match else ""


def _actor_alignment_note(text: str, subject: str) -> tuple[bool, str]:
    if not subject:
        return True, "no governing actor supplied"
    actor = _leading_actor(text)
    if not actor:
        return True, "candidate actor not resolved independently"
    try:
        from portal.modules.compliance.core.vocabulary_bridge import (
            align_actor,
            derive_vocabulary,
        )

        if not _VOCAB_CACHE:
            _VOCAB_CACHE.append(derive_vocabulary())
        result = align_actor(actor, subject, _VOCAB_CACHE[0])
        return bool(result.aligned), result.note
    except Exception:  # noqa: BLE001 - a display annotation never fails the gate
        return True, "vocabulary bridge unavailable"


def _binding_quantity(value: dict[str, Any] | None) -> Quantity | None:
    if not isinstance(value, dict):
        return None
    raw_number = value.get("value")
    if raw_number is None:
        return None
    try:
        number = int(raw_number)
    except (TypeError, ValueError):
        return None
    unit = str(value.get("unit", "")).lower().rstrip("s")
    if unit not in _BINDING_UNITS:
        return None
    qualifier = value.get("qualifier")
    norm = str(qualifier).lower() if qualifier else None
    if norm not in (None, "calendar", "business"):
        norm = None
    return Quantity(number, unit, norm)
