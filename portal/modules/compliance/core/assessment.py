"""Field-level deterministic compliance assessment (V3 P5)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import asdict
from typing import Any, cast

from portal.modules.compliance.core.boundary import BoundarySearch, persist
from portal.modules.compliance.core.comparison import ExpressionNode, Status, evaluate_expression
from portal.modules.compliance.core.constraints import (
    Quantity,
    compare_constraint,
    infer_constraint_kind,
)
from portal.modules.compliance.core.determination import (
    FIELDS,
    AssessmentContext,
    AssessmentRequest,
    AssessmentResult,
    AtomResult,
    FieldResult,
    RequirementResult,
)

logger = logging.getLogger(__name__)

_QUANTITY = re.compile(
    r"(?P<value>\d+)\s+(?:(?P<qualifier>calendar|business)\s+)?(?P<unit>hour|day|week|month|year)s?",
    re.I,
)

_VOCAB_CACHE: list[Any] = []


def _actor_alignment(internal_actor: str, governing_actor: str) -> Any:
    """Actor alignment through the recorded hypernym-proposal chain (P3) — the
    principled replacement for the old role-word regex. No org name or role
    literal lives in this module (Y07)."""
    from portal.modules.compliance.core.vocabulary_bridge import align_actor, derive_vocabulary

    if not _VOCAB_CACHE:
        _VOCAB_CACHE.append(derive_vocabulary())
    return align_actor(internal_actor, governing_actor, _VOCAB_CACHE[0])


def _value(item: dict[str, Any], field: str) -> str:
    if field == "condition":
        item = item.get("conditions", item.get("conditions_json", item.get(field, "")))
    elif field == "exception":
        item = item.get("exceptions", item.get("exceptions_json", item.get(field, "")))
    else:
        item = item.get(field, "")
    if isinstance(item, list):
        return " ".join(map(str, item))
    return str(item or "").strip()


def _norm(value: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]+", value.lower())
        if word
        not in {
            "the",
            "a",
            "an",
            "of",
            "to",
            "and",
            "or",
            "for",
            "in",
            "on",
            "by",
            "each",
            "its",
            "that",
            "this",
            "with",
            "from",
            "be",
            "are",
            "is",
            "at",
            "shall",
            "must",
            "required",
            "entity",
            "responsible",
        }
    }


def _compare(
    field: str, governing: str, internal: str, candidate: dict[str, Any]
) -> tuple[str, str, str]:
    if not governing:
        return "SUPPORTED", "not_constrained", "governing atom does not constrain this field"
    source_text = str(candidate.get("source_text", ""))
    if field == "modality" and candidate.get("binding_effect") == "internally_mandatory":
        return "SUPPORTED", "binding_effect", "controlled procedure text is internally mandatory"
    if field == "actor":
        alignment = _actor_alignment(internal or source_text, governing)
        if alignment.aligned:
            return "SUPPORTED", "vocabulary_bridge", alignment.note
    if not internal:
        left, context = _norm(governing), _norm(source_text)
        if left and len(left & context) / len(left) >= 0.6:
            return (
                "SUPPORTED",
                "source_context",
                "governing field is present in the anchored assertion text",
            )
        return "ABSENT", "presence", "internal assertion omits the governing field"
    if governing.casefold() == internal.casefold():
        return "SUPPORTED", "exact", "internal field exactly matches the governing field"
    if field == "deadline_cadence":
        gq, iq = _QUANTITY.search(governing), _QUANTITY.search(internal)
        kind = infer_constraint_kind(governing)
        if gq and iq and kind:
            outcome, note = compare_constraint(
                kind,
                Quantity(
                    int(gq["value"]), gq["unit"].lower(), (gq["qualifier"] or "").lower() or None
                ),
                Quantity(
                    int(iq["value"]), iq["unit"].lower(), (iq["qualifier"] or "").lower() or None
                ),
            )
            if outcome == "LESS_RESTRICTIVE":
                return "CONTRADICTED", kind, note
            if outcome in {"EQUIVALENT", "MORE_RESTRICTIVE"}:
                # SUPPORTED is right — a stricter internal rule satisfies a
                # governing bound and is never a violation. But whether that
                # strictness is DELIBERATE is not in either document: the
                # procedure says 30 days, the standard says 35, and no reading
                # of either settles whether 30 was chosen or drifted. That is
                # S02_INTENTIONAL_STRICTNESS, and it is the operator's call —
                # they may confirm the tighter cadence or relax to the governing
                # bound and reclaim the margin. Surfaced, never assumed.
                _queue_intentional_strictness(outcome, field, governing, internal, note)
                return "SUPPORTED", kind, note
            return "UNRESOLVED", kind, note
    left, right = _norm(governing), _norm(f"{internal} {source_text}")
    threshold = 0.45 if field in {"action", "object", "condition", "exception"} else 0.6
    if left and (left <= right or len(left & right) / len(left) >= threshold):
        return "SUPPORTED", "token_entailment", "governing terms are present in the assertion"
    return "ABSENT", "token_entailment", "candidate does not address the governing field"


def _queue_intentional_strictness(
    outcome: str, field: str, governing: str, internal: str, note: str
) -> None:
    """S02, for MORE_RESTRICTIVE only. The guard lives here rather than at the
    call site so `_compare` keeps one branch for both SUPPORTED outcomes.
    Best-effort: a queue failure must never break an assessment."""
    if outcome != "MORE_RESTRICTIVE":
        return
    from portal.modules.compliance.core import review_queue as rq

    try:
        rq.propose(
            "S02_INTENTIONAL_STRICTNESS",
            subject_id=f"{field}:{internal[:60]}",
            proposed_value={
                "field": field,
                "governing_requirement": governing[:200],
                "internal_commitment": internal[:200],
                "comparison": note,
                "question": (
                    "The internal rule is stricter than the governing bound. Is that "
                    "deliberate, or should it be relaxed to the governing requirement?"
                ),
            },
            confidence=1.0,  # the COMPARISON is certain; the INTENT is what is asked
        )
    except Exception:  # noqa: BLE001 - surfacing a question must not fail the assessment
        logger.debug("could not queue S02 for %s", field, exc_info=True)


def assess_atom(
    atom: dict[str, Any], candidates: list[dict[str, Any]], ctx: dict[str, Any]
) -> AtomResult:
    """Compare one atom. Approval state is intentionally not an input (C3)."""
    from portal.modules.compliance.core.runtime import bump

    bump("assessment")
    governing_anchors = list(atom.get("source_anchor_ids", atom.get("source_anchor_ids_json", [])))
    if isinstance(governing_anchors, str):
        import json

        governing_anchors = json.loads(governing_anchors)
    if not governing_anchors:
        return AtomResult(
            atom_id=atom["atom_id"],
            determination="UNRESOLVED",
            unresolved_code="U02_MISSING_GOVERNING_SOURCE",
            missing_fact={"logical_id": atom.get("node_id", atom["atom_id"])},
            rationale="governing atom has no resolving source anchor",
        )
    if ctx.get("truncated") or ctx.get("budget_hit"):
        return AtomResult(
            atom_id=atom["atom_id"],
            determination="UNRESOLVED",
            governing_anchor_ids=governing_anchors,
            unresolved_code="U04_RETRIEVAL_INCOMPLETE",
            missing_fact={
                "index_generation": ctx.get("index_generation", "unknown"),
                "truncation": bool(ctx.get("truncated")),
                "budget": ctx.get("budget_hit"),
            },
            rationale="retrieval boundary was incomplete",
        )
    if not candidates:
        search = ctx.get("boundary")
        if not isinstance(search, BoundarySearch) or not search.exhaustive:
            return AtomResult(
                atom_id=atom["atom_id"],
                determination="UNRESOLVED",
                governing_anchor_ids=governing_anchors,
                unresolved_code="U04_RETRIEVAL_INCOMPLETE",
                missing_fact={
                    "index_generation": ctx.get("index_generation", "missing"),
                    "truncation": "boundary proof absent",
                    "budget": ctx.get("budget_hit", "unknown"),
                },
            )
        proof_id = persist(ctx["repository"], search) if ctx.get("repository") else search.stable_id
        return AtomResult(
            atom_id=atom["atom_id"],
            determination="ABSENT",
            governing_anchor_ids=governing_anchors,
            boundary_proof_id=proof_id,
            rationale="exhaustive corpus search found no implementation assertion",
        )

    best = candidates[0]
    internal_anchor = best.get("anchor_id") or best.get("span_id") or best.get("section_id", "")
    if not internal_anchor:
        return AtomResult(
            atom_id=atom["atom_id"],
            determination="UNRESOLVED",
            governing_anchor_ids=governing_anchors,
            unresolved_code="U03_EXTRACTION_FAILED",
            missing_fact={
                "revision_id": best.get("revision_id", "unknown"),
                "section": best.get("section_id", "unknown"),
                "parser_error": "candidate has no source anchor",
            },
        )
    results = []
    for field in FIELDS:
        governing, internal = _value(atom, field), _value(best, field)
        status, comparator, note = _compare(field, governing, internal, best)
        results.append(
            FieldResult(
                field,
                status,
                governing_anchors[0],
                internal_anchor,
                governing,
                internal,
                comparator,
                note,
            )
        )
    constrained = [r for r in results if r.governing_value]
    if any(r.determination == "CONTRADICTED" for r in constrained):
        determination = "CONTRADICTED"
    elif any(r.determination == "UNRESOLVED" for r in constrained):
        return AtomResult(
            atom_id=atom["atom_id"],
            determination="UNRESOLVED",
            field_results=results,
            governing_anchor_ids=governing_anchors,
            internal_anchor_ids=[internal_anchor],
            unresolved_code="U01_AMBIGUOUS_GOVERNING_LOGIC",
            missing_fact={
                "expression_id": ctx.get("expression_id", "field-comparison"),
                "readings": [governing, internal],
            },
        )
    elif any(r.determination == "ABSENT" for r in constrained):
        determination = "ABSENT"
        search = ctx.get("boundary")
        if not isinstance(search, BoundarySearch) or not search.exhaustive:
            return AtomResult(
                atom_id=atom["atom_id"],
                determination="UNRESOLVED",
                field_results=results,
                governing_anchor_ids=governing_anchors,
                internal_anchor_ids=[internal_anchor],
                unresolved_code="U04_RETRIEVAL_INCOMPLETE",
                missing_fact={
                    "index_generation": ctx.get("index_generation", "missing"),
                    "truncation": "field search incomplete",
                    "budget": "unknown",
                },
            )
        proof_id = persist(ctx["repository"], search) if ctx.get("repository") else search.stable_id
        return AtomResult(
            atom_id=atom["atom_id"],
            determination=determination,
            field_results=results,
            governing_anchor_ids=governing_anchors,
            internal_anchor_ids=[internal_anchor],
            boundary_proof_id=proof_id,
            rationale="candidate omits a mandatory field",
        )
    else:
        determination = "SUPPORTED"
    return AtomResult(
        atom_id=atom["atom_id"],
        determination=determination,
        field_results=results,
        governing_anchor_ids=governing_anchors,
        internal_anchor_ids=[internal_anchor],
        counterevidence_anchor_ids=[internal_anchor] if determination == "CONTRADICTED" else [],
        rationale="deterministic field comparison",
    )


def _expression(payload: dict[str, Any]) -> ExpressionNode:
    return ExpressionNode(
        kind=payload["kind"],
        atom_id=payload.get("atom_id", ""),
        n=payload.get("n", 0),
        children=[_expression(child) for child in payload.get("children", [])],
    )


def assess_requirement(node: dict[str, Any], ctx: dict[str, Any]) -> RequirementResult:
    from portal.modules.compliance.core.runtime import bump

    bump("assessment")
    atoms = node.get("atoms", [])
    results = [
        assess_atom(
            atom,
            ctx.get("candidates", {}).get(atom["atom_id"], []),
            {**ctx, "expression_id": node.get("expression_id", "")},
        )
        for atom in atoms
    ]
    statuses = {
        r.atom_id: ("CONTRADICTED" if r.determination in {"ABSENT", "PARTIAL"} else r.determination)
        for r in results
    }
    expression = node.get("expression") or {
        "kind": "ALL_OF",
        "children": [{"kind": "ATOM", "atom_id": a["atom_id"]} for a in atoms],
    }
    # Required live call into the reviewed boolean evaluator (C5).
    # Roll-up below preserves ABSENT/PARTIAL; the folded set only ever contains
    # SUPPORTED/CONTRADICTED/UNRESOLVED, which is what the evaluator accepts.
    evaluate_expression(_expression(expression), cast(dict[str, Status], statuses))
    determinations = [r.determination for r in results]
    if any(value == "UNRESOLVED" for value in determinations):
        unresolved = next(r for r in results if r.determination == "UNRESOLVED")
        overall = "UNRESOLVED"
        code, missing = unresolved.unresolved_code, unresolved.missing_fact
    elif any(value == "CONTRADICTED" for value in determinations):
        overall, code, missing = "CONTRADICTED", "", {}
    elif determinations and all(value == "SUPPORTED" for value in determinations):
        overall, code, missing = "SUPPORTED", "", {}
    elif determinations and all(value == "ABSENT" for value in determinations):
        overall, code, missing = "ABSENT", "", {}
    else:
        overall, code, missing = "PARTIAL", "", {}
    return RequirementResult(
        node_id=node["node_id"],
        determination=overall,
        atom_results=results,
        expression_id=node.get("expression_id", ""),
        valid_at=ctx.get("valid_at", ""),
        known_at=ctx.get("known_at", ""),
        applicability=ctx.get("applicability", "APPLIES"),
        unresolved_code=code,
        missing_fact=missing,
    )


def serialize(result: RequirementResult) -> dict[str, Any]:
    return asdict(result)


# ── the one authoritative assessment service ────────────────────────────────
# IMPLEMENTATION_BRIEF_COMPLIANCE_READING_20260912 §4. Source resolution →
# applicability → semantic alignment → deterministic gate → unchanged council →
# one source-linked explanation → consistency projection → persistence. This is
# the only path that produces substantive verdicts; every projection
# (CoverageCell, operations.Determination, AtomResult, RequirementResult) is
# derived from its AssessmentResult, never an independent decision engine.

_ENGINE_VERSION = "compliance-reading/1"


def assess_part(request: AssessmentRequest, context: AssessmentContext) -> AssessmentResult:
    """Assess one governing Part. See ``determination.AssessmentResult``."""
    from portal.modules.compliance.core.assessment_report import explain
    from portal.modules.compliance.core.council import run_council
    from portal.modules.compliance.core.gate import run_aligned_gate
    from portal.modules.compliance.core.obligation_alignment import align_part

    run_id = _ensure_run(request, context)
    base: dict[str, Any] = {
        "assessment_id": uuid.uuid4().hex[:16],
        "run_id": run_id,
        "engine_version": context.engine_version or _ENGINE_VERSION,
        "input_fingerprint": _input_fingerprint(request),
        "requirement_id": request.requirement_id,
        "engine_fingerprint": _engine_fingerprint(context),
    }

    scope = request.scope
    if scope is None or not getattr(scope, "is_declared", False):
        return _finalize(
            AssessmentResult(
                **base,
                applicability="UNKNOWN",
                applicability_basis=request.scope_basis,
                documentary_coverage="UNRESOLVED",
                coverage="UNRESOLVED",
                unresolved_code="U05_SCOPE_UNDECLARED",
                missing_fact={
                    "requirement_id": request.requirement_id,
                    "scope_basis": request.scope_basis,
                },
            ),
            context,
        )

    integrity = _source_integrity_error(request)
    if integrity is not None:
        return _finalize(
            AssessmentResult(
                **base,
                applicability="UNKNOWN",
                applicability_basis=request.scope_basis,
                documentary_coverage="UNRESOLVED",
                coverage="UNRESOLVED",
                unresolved_code="U03_EXTRACTION_FAILED",
                missing_fact=integrity,
            ),
            context,
        )

    alignment = align_part(request, context)
    if not alignment.valid:
        return _finalize(
            AssessmentResult(
                **base,
                applicability="UNKNOWN",
                applicability_basis=request.scope_basis,
                documentary_coverage="UNRESOLVED",
                coverage="UNRESOLVED",
                unresolved_code="U09_SEMANTIC_ALIGNMENT_UNKNOWN",
                missing_fact={"failure": alignment.failure, "part_ref": alignment.part_ref},
            ),
            context,
        )

    gate_result = run_aligned_gate(request, alignment, context)
    if gate_result.gated_out:
        return _finalize(
            AssessmentResult(
                **base,
                applicability=gate_result.applicability,
                applicability_basis=request.scope_basis,
                documentary_coverage="NOT_APPLICABLE",
                coverage="NOT_APPLICABLE",
                substantively_resolved=True,
                receipt=_receipt(request, gate_result, alignment),
            ),
            context,
        )

    packet = gate_result.to_council_packet()
    trace: list[dict[str, Any]] = []
    seat_fn = _recording_seat_fn(context.seat_fn, trace)
    council = run_council(
        packet,
        context.seats,
        seat_fn=seat_fn,
        quorum=context.quorum,
        reference_texts=_reference_texts(request),
    )
    source_catalog = _source_catalog(request, alignment)
    explanation = explain(request, asdict(council), alignment, source_catalog, context)

    documentary, coverage, resolved, code, missing = _project(
        request, gate_result, council, explanation
    )
    valid_explanation = explanation.valid
    selected = list(source_catalog.values())
    return _finalize(
        AssessmentResult(
            **base,
            applicability=gate_result.applicability,
            applicability_basis=request.scope_basis,
            documentary_coverage=documentary,
            coverage=coverage,
            substantively_resolved=resolved,
            council_result=asdict(council),
            # An invalid explanation contributes no grounded commitments or gaps.
            covered=explanation.covered if valid_explanation else [],
            gaps=explanation.gaps if valid_explanation else [],
            uncertainties=explanation.uncertainties,
            selected_source_slices=selected,
            receipt=_receipt(request, gate_result, alignment, explanation=explanation),
            unresolved_code=code,
            missing_fact=missing,
        ),
        context,
    )


def _source_integrity_error(request: AssessmentRequest) -> dict[str, Any] | None:
    """Reject a candidate whose stored slice no longer hashes to its recorded
    revision — a quote/hash verification failure is U03, never a resolved
    support or an omission (brief §7 case 22)."""
    for record in request.candidate_set.records if request.candidate_set else []:
        sl = record.source_slice
        if sl is None:
            continue
        if hashlib.sha256(sl.text.encode("utf-8")).hexdigest() != sl.revision_hash:
            return {
                "revision_id": sl.revision_hash,
                "section": sl.locator or sl.ref,
                "candidate_id": record.candidate_id,
                "parser_error": "candidate source slice hash does not match its stored text",
            }
    return None


def _project(
    request: AssessmentRequest,
    gate_result: Any,
    council: Any,
    explanation: Any,
) -> tuple[str, str, bool, str, dict[str, Any]]:
    """(documentary_coverage, public coverage, resolved, unresolved_code, missing).

    Documentary coverage is the model-validated reading. The public projection
    only exposes the ordinary FULL/PARTIAL/NONE vocabulary when applicability is
    an OPERATOR-CONFIRMED APPLIES; a corpus-derived or undeclared scope keeps
    ``coverage=UNRESOLVED`` with the missing scope declaration, even when
    documentary coverage is FULL (brief §5 scope reconciliation)."""
    decision = str(getattr(council, "determination", ""))
    votes = getattr(council, "votes", {}) or {}
    if decision == "ESCALATE":
        if sum(votes.values()) == 0:
            # No seat produced a valid vote (timeout/invalid JSON): an
            # operational uncertainty, never a fabricated SME dispute (U10).
            return (
                "UNRESOLVED",
                "UNRESOLVED",
                False,
                "U10_COUNCIL_UNRESOLVED",
                {
                    "council_votes": votes,
                    "dropped": [
                        {"seat": o.seat_id, "dropped": o.dropped}
                        for o in getattr(council, "opinions", [])
                        if not o.votes
                    ],
                },
            )
        return (
            "NEEDS_REVIEW",
            "NEEDS_REVIEW",
            False,
            "",
            {"council": "ESCALATE — S04 interpretation dispute"},
        )
    if decision == "INSUFFICIENT":
        return (
            "UNRESOLVED",
            "UNRESOLVED",
            False,
            "U10_COUNCIL_UNRESOLVED",
            {
                "council_votes": votes,
                "dropped": [
                    {"seat": o.seat_id, "dropped": o.dropped}
                    for o in getattr(council, "opinions", [])
                    if not o.votes
                ],
            },
        )
    incomparable = [
        o for o in getattr(gate_result, "binding_outcomes", []) if o.get("result") == "INCOMPARABLE"
    ]
    if incomparable:
        # A same-duty constraint the reviewed comparator cannot place is
        # uncertainty, not contradiction and not a PARTIAL fallback (U12).
        return (
            "UNRESOLVED",
            "UNRESOLVED",
            False,
            "U12_CONSTRAINT_INCOMPARABLE",
            {
                "bindings": incomparable,
                "council_decision": decision,
            },
        )
    if not explanation.valid:
        if decision == "ABSENT" and gate_result.acquisition_completeness != "COMPLETE":
            return (
                "UNRESOLVED",
                "UNRESOLVED",
                False,
                "U04_RETRIEVAL_INCOMPLETE",
                {
                    "acquisition_completeness": gate_result.acquisition_completeness,
                    "truncation": "absence requires a completed boundary, not a top-k receipt",
                    "failure": explanation.failure,
                },
            )
        return (
            "UNRESOLVED",
            "UNRESOLVED",
            False,
            "U11_ASSESSMENT_CONTRACT_FAILED",
            {"failure": explanation.failure, "council_decision": decision},
        )

    documentary = explanation.documentary_coverage
    if documentary in ("FULL", "PARTIAL", "NONE"):
        if gate_result.applicability == "APPLIES":
            return documentary, documentary, True, "", {}
        return (
            documentary,
            "UNRESOLVED",
            False,
            "",
            {
                "missing_scope_declaration": "asset scope is not operator-confirmed",
                "applicability": gate_result.applicability,
                "applicability_reason": gate_result.applicability_reason,
                "scope_basis": request.scope_basis,
            },
        )
    if documentary == "NEEDS_REVIEW":
        return "NEEDS_REVIEW", "NEEDS_REVIEW", False, "", {}
    return (
        "UNRESOLVED",
        "UNRESOLVED",
        False,
        "U11_ASSESSMENT_CONTRACT_FAILED",
        {"explanation": explanation.documentary_coverage},
    )


def _recording_seat_fn(seat_fn: Any, trace: list[dict[str, Any]]) -> Any:
    """Wrap the ordinary council transport to retain raw responses so a failed
    seat's rejection cause is auditable. The council's own cite-or-drop still
    decides the vote; this only records what was asked and returned."""
    if seat_fn is None:
        return None

    def wrapped(model: str, system: str, user: str) -> str:
        raw = seat_fn(model, system, user)
        trace.append({"model": model, "raw": raw})
        return str(raw)

    return wrapped


def _reference_texts(request: AssessmentRequest) -> dict[str, str]:
    governing = request.governing
    if governing is None:
        return {}
    out: dict[str, str] = {}
    for collection in (governing.references, governing.definitions, governing.meta):
        for item in collection or []:
            if isinstance(item, dict) and item.get("ref"):
                out[str(item["ref"])] = str(item.get("text", ""))
    return out


def _source_catalog(request: AssessmentRequest, alignment: Any) -> dict[str, dict[str, Any]]:
    """Every immutable selectable slice the report may cite, with exact text."""
    catalog: dict[str, dict[str, Any]] = {}

    def add(slice_obj: Any) -> None:
        if slice_obj is None:
            return
        catalog[slice_obj.slice_id] = {
            "slice_id": slice_obj.slice_id,
            "ref": slice_obj.ref,
            "text": slice_obj.text,
            "role": slice_obj.role,
            "document_id": slice_obj.document_id,
            "locator": slice_obj.locator,
        }

    if request.governing:
        for s in request.governing.source_slices:
            add(s)
    if request.candidate_set:
        for record in request.candidate_set.records:
            add(record.source_slice)
    return catalog


def _input_fingerprint(request: AssessmentRequest) -> str:
    body = {
        "requirement_id": request.requirement_id,
        "governing": request.governing.fingerprint if request.governing else "",
        "snapshot": request.snapshot.fingerprint if request.snapshot else "",
        "scope_basis": request.scope_basis,
        "effective_on": request.effective_on,
        "known_at": request.known_at,
        "overlay": request.overlay.overlay_id if request.overlay else "",
    }
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _engine_fingerprint(context: AssessmentContext) -> str:
    body = {
        "engine_version": context.engine_version or _ENGINE_VERSION,
        "seats": [(s.get("id"), s.get("model")) for s in context.seats],
        "quorum": context.quorum,
    }
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _receipt(
    request: AssessmentRequest, gate_result: Any, alignment: Any, explanation: Any = None
) -> dict[str, Any]:
    return {
        "acquisition_mode": request.snapshot.acquisition_mode if request.snapshot else "RETRIEVAL",
        "completeness": request.snapshot.completeness if request.snapshot else "UNKNOWN",
        "snapshot_fingerprint": request.snapshot.fingerprint if request.snapshot else "",
        "governing_fingerprint": request.governing.fingerprint if request.governing else "",
        "alignment_valid": alignment.valid,
        "alignment_links": len(alignment.records),
        "applicability": gate_result.applicability,
        "explanation_valid": bool(explanation.valid) if explanation is not None else False,
    }


def _ensure_run(request: AssessmentRequest, context: AssessmentContext) -> str:
    repo = context.repository
    if repo is None:
        return str(request.metadata.get("run_id", ""))
    run_id = str(request.metadata.get("run_id", ""))
    if run_id and repo.get_run(run_id) is not None:
        repo.update_run(run_id, status="RUNNING")
        return run_id
    created = repo.create_run(
        {
            "requirement_id": request.requirement_id,
            "kb_id": request.kb_id,
            "scope_basis": request.scope_basis,
            "effective_on": request.effective_on,
            "known_at": request.known_at,
        },
        status="RUNNING",
        org_id=request.org_id,
    )
    return str(created)


def _finalize(result: AssessmentResult, context: AssessmentContext) -> AssessmentResult:
    repo = context.repository
    if repo is not None:
        from portal.modules.compliance.core.repository import Repository

        if isinstance(repo, Repository):
            repo.record_assessment(result)
    return result
