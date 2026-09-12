"""Field-level deterministic compliance assessment (V3 P5)."""

from __future__ import annotations

import logging
import re
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
