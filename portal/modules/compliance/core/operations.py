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

import hashlib
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from portal.modules.compliance.core import assessment_source
from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.assessment import assess_part
from portal.modules.compliance.core.council import SeatFn
from portal.modules.compliance.core.determination import (
    AssessmentContext,
    AssessmentRequest,
    AssessmentResult,
    CandidateRecord,
    CandidateSet,
    CorpusSnapshot,
    ScenarioEdit,
    ScenarioOverlay,
    SourceSlice,
)
from portal.modules.compliance.core.engine import parse_iso_date
from portal.modules.compliance.core.policy_graph import PolicyGraph, build_policy_graph
from portal.modules.compliance.core.vocabulary_bridge import PolicyVocabulary

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
    # ── reading-architecture projection fields (additive; §4/§6) ────────────
    # ``judge`` is now a thin adapter over ``assessment.assess_part``, so the
    # canonical assessment identity and its documentary/evidence detail travel
    # on the same projection. Existing field names above are unchanged.
    assessment_id: str = ""
    documentary_coverage: str = ""
    coverage: str = ""
    applicability: str = ""
    covered: list[Any] = field(default_factory=list)
    gaps: list[Any] = field(default_factory=list)
    uncertainties: list[Any] = field(default_factory=list)


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
    status: str  # proposed | VALIDATED | FAILED_VALIDATION | BLOCKED_MISSING_FACT
    closes_fields: list[str]
    rejudged: Determination | None
    weakens: list[str]
    diff_against_current: str
    # ── additive, honest-status fields (reading architecture §5) ────────────
    before: Determination | None = None
    assessment_id: str = ""
    virtual_fingerprint: str = ""
    closed_gaps: list[str] = field(default_factory=list)
    unclosed_gaps: list[str] = field(default_factory=list)
    affected_parts: list[str] = field(default_factory=list)
    unknown_dependencies: list[str] = field(default_factory=list)
    missing_facts: list[str] = field(default_factory=list)
    closure_limited: bool = False
    note: str = ""


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
    org_commitments: list[dict[str, Any]] | None = None,
    seats: list[dict[str, str]],
    policy_graph: PolicyGraph | None = None,
    vocab: PolicyVocabulary | None = None,
    seat_fn: SeatFn | None = None,
    retrieval_hits: list[dict[str, Any]] | None = None,
    reference_texts: dict[str, str] | None = None,
    quorum: float = 0.66,
    context: AssessmentContext | None = None,
    request: AssessmentRequest | None = None,
    kb_id: str = "operator_corpus",
    effective_on: str = "",
    known_at: str = "",
) -> Determination:
    """Thin adapter to the one shared assessment service (brief §6).

    ``judge`` no longer owns a gate/council orchestration of its own: it
    resolves the single Part's :class:`AssessmentRequest`, calls
    ``assessment.assess_part`` and projects the canonical
    :class:`AssessmentResult` into the existing :class:`Determination` shape,
    carrying the assessment id, documentary coverage, covered commitments,
    gaps and uncertainty detail. ``org_commitments``/``retrieval_hits``/
    ``reference_texts``/``vocab`` are retained for call compatibility; the
    substantive candidate set is now the pinned retrieval set, not a
    keyword-filtered graph list.
    """
    graph = policy_graph or build_policy_graph()
    ctx = context or AssessmentContext(
        seats=list(seats or []),
        quorum=quorum,
        seat_fn=seat_fn,
        policy_graph=graph,
        kb_id=kb_id,
    )
    req = _resolve_request(
        actor_cu_id,
        request=request,
        scope=scope,
        kb_id=kb_id,
        policy_graph=graph,
        effective_on=effective_on,
        known_at=known_at,
        seat_fn=seat_fn,
        org_commitments=org_commitments,
        retrieval_hits=retrieval_hits,
    )
    return _project_determination(actor_cu_id, assess_part(req, ctx))


def _build_request(
    target_ref: str,
    *,
    scope: AssetScope | None,
    kb_id: str,
    policy_graph: PolicyGraph | None,
    effective_on: str,
    known_at: str,
    snapshot: Any = None,
) -> AssessmentRequest:
    """Resolve one Part's request through the source adapter.

    The caller-supplied :class:`AssetScope` is authoritative (the adapter only
    knows ``scope_text``/corpus derivation); it is attached after assembly so a
    declared scope is never silently replaced by a derived one.
    """
    request = assessment_source.build_assessment_request(
        target_ref,
        kb_id=kb_id,
        effective_on=effective_on,
        known_at=known_at,
        policy_graph=policy_graph,
    )
    if scope is not None:
        request.scope = scope
    if snapshot is not None:
        request.snapshot = snapshot
    return request


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _commitment_candidate(c: dict[str, Any], seq: int) -> CandidateRecord:
    text = str(c.get("text", ""))
    cid = str(c.get("commitment_id") or f"candidate-{seq}")
    doc = str(c.get("document_id") or "controlled")
    return CandidateRecord(
        candidate_id=cid,
        document_id=doc,
        chunk_id=str(c.get("chunk_id") or cid),
        text=text,
        locator=str(c.get("section_id") or ""),
        source_slice=SourceSlice(
            slice_id=f"cand-{cid}",
            ref=cid,
            document_id=doc,
            revision_hash=_sha(text),
            chunk_id=str(c.get("chunk_id") or cid),
            text=text,
            char_start=0,
            char_end=len(text),
            role="candidate",
        ),
    )


def _hit_candidate(h: dict[str, Any], seq: int) -> CandidateRecord:
    return _commitment_candidate(
        {
            "commitment_id": h.get("candidate_id") or h.get("chunk_id") or f"hit-{seq}",
            "document_id": h.get("document_id") or h.get("source_file"),
            "chunk_id": h.get("chunk_id") or h.get("section_id"),
            "section_id": h.get("section_id"),
            "text": h.get("text") or h.get("span") or "",
        },
        seq,
    )


def _controlled_request(
    target_ref: str,
    *,
    scope: AssetScope | None,
    kb_id: str,
    policy_graph: PolicyGraph | None,
    effective_on: str,
    known_at: str,
    org_commitments: list[dict[str, Any]] | None,
    retrieval_hits: list[dict[str, Any]] | None,
) -> AssessmentRequest:
    """A caller-supplied candidate set (a controlled harness), never retrieval.

    Used only when the caller injects its own transport: a test/harness owns
    the candidate list, so the shared service must not reach the live store.
    Production callers omit ``seat_fn`` and get the pinned retrieval request.
    """
    governing = assessment_source.resolve_governing_bundle(target_ref, policy_graph=policy_graph)
    records: list[CandidateRecord] = []
    for seq, c in enumerate(org_commitments or []):
        records.append(_commitment_candidate(c, seq))
    for seq, h in enumerate(retrieval_hits or []):
        records.append(_hit_candidate(h, seq))
    snapshot = CorpusSnapshot(
        snapshot_id="", kb_id=kb_id, acquisition_mode="EXPLICIT_SET", completeness="UNKNOWN"
    )
    fingerprint = _sha("EXPLICIT_SET|" + "|".join(record.candidate_id for record in records))
    snapshot.fingerprint = fingerprint
    snapshot.snapshot_id = f"snap-{fingerprint[:20]}"
    return AssessmentRequest(
        requirement_id=target_ref,
        kb_id=kb_id,
        scope=scope,
        governing=governing,
        snapshot=snapshot,
        candidate_set=CandidateSet(
            records=records,
            acquisition_receipt={"acquisition_mode": "EXPLICIT_SET", "completeness": "UNKNOWN"},
        ),
        effective_on=effective_on,
        known_at=known_at,
    )


def _resolve_request(
    target_ref: str,
    *,
    request: AssessmentRequest | None,
    scope: AssetScope | None,
    kb_id: str,
    policy_graph: PolicyGraph | None,
    effective_on: str,
    known_at: str,
    seat_fn: SeatFn | None,
    org_commitments: list[dict[str, Any]] | None,
    retrieval_hits: list[dict[str, Any]] | None,
) -> AssessmentRequest:
    if request is not None:
        return request
    if seat_fn is not None and (org_commitments is not None or retrieval_hits is not None):
        return _controlled_request(
            target_ref,
            scope=scope,
            kb_id=kb_id,
            policy_graph=policy_graph,
            effective_on=effective_on,
            known_at=known_at,
            org_commitments=org_commitments,
            retrieval_hits=retrieval_hits,
        )
    return _build_request(
        target_ref,
        scope=scope,
        kb_id=kb_id,
        policy_graph=policy_graph,
        effective_on=effective_on,
        known_at=known_at,
    )


_DETERMINATION_BY_COUNCIL = {
    "SUPPORTED": "SUPPORTED",
    "PARTIAL": "PARTIAL",
    "CONTRADICTED": "CONTRADICTED",
    "ABSENT": "ABSENT",
}
_DETERMINATION_BY_COVERAGE = {
    "FULL": "SUPPORTED",
    "PARTIAL": "PARTIAL",
    "NONE": "ABSENT",
    "NOT_APPLICABLE": "NOT_APPLICABLE",
}


def _project_determination(anchor: str, result: AssessmentResult) -> Determination:
    """Project the canonical result, dropping no evidence the old shape carried."""
    council = dict(result.council_result or {})
    decision = str(council.get("determination", ""))
    if result.coverage == "NOT_APPLICABLE":
        determination = "NOT_APPLICABLE"
    elif decision in _DETERMINATION_BY_COUNCIL:
        determination = _DETERMINATION_BY_COUNCIL[decision]
    elif decision in ("ESCALATE", "INSUFFICIENT"):
        determination = "UNRESOLVED"
    else:
        determination = _DETERMINATION_BY_COVERAGE.get(result.documentary_coverage, "UNRESOLVED")
    citations = list(council.get("citations") or [])
    if not citations:
        citations = [str(s.get("ref", "")) for s in result.selected_source_slices if s.get("ref")]
    return Determination(
        anchor=anchor,
        determination=determination,
        finding_type=str(council.get("finding_type", "")),
        citations=citations or [anchor],
        council_votes=dict(council.get("votes") or {}),
        dissent=list(council.get("dissent") or []),
        sme_decision_kind=("S04_INTERPRETATION_DISPUTE" if decision == "ESCALATE" else ""),
        gate_gated_out=result.coverage == "NOT_APPLICABLE",
        rationale=str(council.get("rationale", "")) or result.unresolved_code,
        assessment_id=result.assessment_id,
        documentary_coverage=result.documentary_coverage,
        coverage=result.coverage,
        applicability=result.applicability,
        covered=list(result.covered),
        gaps=list(result.gaps),
        uncertainties=list(result.uncertainties),
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
    draft_text: str = "",
    *,
    scope: AssetScope | None = None,
    org_commitments: list[dict[str, Any]] | None = None,
    seats: list[dict[str, str]] | None = None,
    seat_fn: SeatFn | None = None,
    policy_graph: PolicyGraph | None = None,
    overlay: ScenarioOverlay | None = None,
    context: AssessmentContext | None = None,
    request: AssessmentRequest | None = None,
    affected_requests: list[AssessmentRequest] | None = None,
    kb_id: str = "operator_corpus",
    effective_on: str = "",
    known_at: str = "",
    quorum: float = 0.66,
) -> ProposePackage:
    """Re-judge a proposed edit as a virtual document state.

    The proposal is never self-certifying: it is materialised as a
    :class:`ScenarioOverlay` over the pinned snapshot and re-judged through the
    same ``assessment.assess_part`` service that found the gap. A closing draft
    requires after-assessment ``documentary_coverage == "FULL"``; a
    non-closing draft keeps the gap with ``FAILED_VALIDATION``. Missing factual
    values (no pinned snapshot, no resolving edit target, an undeclared scope)
    produce ``BLOCKED_MISSING_FACT`` — operators, dates and installed controls
    are never invented. Draft validation never mutates the actual assessment or
    any approved mapping.
    """
    graph = policy_graph or build_policy_graph()
    ctx = context or AssessmentContext(
        seats=list(seats or []),
        quorum=quorum,
        seat_fn=seat_fn,
        policy_graph=graph,
        kb_id=kb_id,
    )
    base = _resolve_request(
        target_ref,
        request=request,
        scope=scope,
        kb_id=kb_id,
        policy_graph=graph,
        effective_on=effective_on,
        known_at=known_at,
        seat_fn=seat_fn,
        org_commitments=org_commitments,
        retrieval_hits=None,
    )
    if base.snapshot is None:
        return _blocked(target_ref, draft_text, ["a pinned corpus snapshot"])
    overlay = overlay or _legacy_overlay(target_ref, draft_text, base)
    if overlay is None or not overlay.edits:
        return _blocked(target_ref, draft_text, ["a resolving edit target"])

    before = assess_part(base, ctx)
    try:
        virtual = assessment_source.materialize_overlay(base, overlay)
    except ValueError as exc:
        return _failed(target_ref, draft_text, before, [str(exc)])

    after = assess_part(virtual, ctx)
    weakens: list[str] = []
    unknown: list[str] = []
    weakened = _weakened_dependencies(base, overlay, affected_requests or [], ctx)
    weakens.extend(weakened["weakened"])
    unknown.extend(weakened["unknown"])

    if before.unresolved_code in ("U05_SCOPE_UNDECLARED", "U02_MISSING_GOVERNING_SOURCE"):
        gap = before.missing_fact.get("requirement_id") or before.unresolved_code
        return _blocked(target_ref, draft_text, [str(gap)], before=before)

    if after.documentary_coverage != "FULL" or weakens:
        if after.documentary_coverage != "FULL":
            weakens.append(
                f"proposal does not close {target_ref}: re-judgment returned "
                f"{after.documentary_coverage}"
            )
        return _failed(
            target_ref,
            draft_text,
            before,
            weakens,
            after=after,
            virtual=virtual,
            unclosed=[g.gap_id for g in after.gaps] or list(unmet_fields),
            unknown=unknown,
        )

    note = "validated by overlay re-judgment through assessment.assess_part"
    if unknown:
        note += "; closure is limited — dependency coverage unknown for " + ", ".join(
            sorted(unknown)
        )
    elif not affected_requests:
        note += (
            "; closure is limited to the target Part — no dependency assessment requests supplied"
        )
    return ProposePackage(
        target_ref=target_ref,
        replacement_text=draft_text,
        status="VALIDATED",
        closes_fields=list(unmet_fields),
        rejudged=_project_determination(target_ref, after),
        weakens=[],
        diff_against_current="",
        before=_project_determination(target_ref, before),
        assessment_id=after.assessment_id,
        virtual_fingerprint=virtual.snapshot.fingerprint if virtual.snapshot else "",
        closed_gaps=[g.gap_id for g in before.gaps],
        unclosed_gaps=[],
        affected_parts=list(getattr(virtual, "affected_parts", []) or []),
        unknown_dependencies=sorted(unknown),
        missing_facts=[],
        closure_limited=bool(unknown) or not affected_requests,
        note=note,
    )


def _blocked(
    target_ref: str,
    draft_text: str,
    missing: list[str],
    *,
    before: AssessmentResult | None = None,
) -> ProposePackage:
    return ProposePackage(
        target_ref=target_ref,
        replacement_text=draft_text,
        status="BLOCKED_MISSING_FACT",
        closes_fields=[],
        rejudged=None,
        weakens=[],
        diff_against_current="",
        before=_project_determination(target_ref, before) if before else None,
        missing_facts=missing,
        note="cannot validate: missing " + "; ".join(missing),
    )


def _failed(
    target_ref: str,
    draft_text: str,
    before: AssessmentResult,
    weakens: list[str],
    *,
    after: AssessmentResult | None = None,
    virtual: AssessmentRequest | None = None,
    unclosed: list[str] | None = None,
    unknown: list[str] | None = None,
) -> ProposePackage:
    rejudged = _project_determination(target_ref, after) if after else None
    return ProposePackage(
        target_ref=target_ref,
        replacement_text=draft_text,
        status="FAILED_VALIDATION",
        closes_fields=[],
        rejudged=rejudged,
        weakens=list(weakens),
        diff_against_current="",
        before=_project_determination(target_ref, before),
        assessment_id=after.assessment_id if after else "",
        virtual_fingerprint=virtual.snapshot.fingerprint if virtual and virtual.snapshot else "",
        unclosed_gaps=list(unclosed or []),
        unknown_dependencies=sorted(unknown or []),
        closure_limited=bool(unknown),
        note="virtual state retained as a failed proposal; the actual gap is unchanged",
    )


def _legacy_overlay(
    target_ref: str, draft_text: str, base: AssessmentRequest
) -> ScenarioOverlay | None:
    """A bare draft string is an explicitly ADDITIVE scenario, never a silent
    replacement of an existing rule (brief §5)."""
    if base.snapshot is None:
        return None
    edit = ScenarioEdit(
        operation="ADD",
        target_document=target_ref,
        target_section="proposed",
        new_text=draft_text,
        label="legacy-add",
    )
    return ScenarioOverlay(base_snapshot_fingerprint=base.snapshot.fingerprint, edits=[edit])


_SEVERITY = {"FULL": 3, "PARTIAL": 2, "NONE": 1, "NEEDS_REVIEW": 1, "UNRESOLVED": 0}


def _coverage_rank(value: str) -> int:
    return _SEVERITY.get(value, 0)


def _weakened_dependencies(
    base: AssessmentRequest,
    overlay: ScenarioOverlay,
    affected_requests: list[AssessmentRequest],
    ctx: AssessmentContext,
) -> dict[str, list[str]]:
    """Re-judge declared dependency Parts and flag a previously supported duty
    that the overlay weakens. A dependency that cannot be re-materialised is
    reported as unknown — never silently treated as safe."""
    weakened: list[str] = []
    unknown: list[str] = []
    for dep in affected_requests:
        if dep.requirement_id == base.requirement_id:
            continue
        try:
            dep_virtual = assessment_source.materialize_overlay(dep, overlay)
        except ValueError:
            unknown.append(dep.requirement_id)
            continue
        dep_before = assess_part(dep, ctx)
        dep_after = assess_part(dep_virtual, ctx)
        if _coverage_rank(dep_after.documentary_coverage) < _coverage_rank(
            dep_before.documentary_coverage
        ):
            weakened.append(
                f"{dep.requirement_id}: {dep_before.documentary_coverage} -> "
                f"{dep_after.documentary_coverage}"
            )
    return {"weakened": weakened, "unknown": unknown}
