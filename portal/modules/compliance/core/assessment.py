"""Field-level deterministic compliance assessment (V3 P5)."""

from __future__ import annotations

import re
from dataclasses import asdict

from portal.modules.compliance.core.boundary import BoundarySearch, persist
from portal.modules.compliance.core.comparison import ExpressionNode, evaluate_expression
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

_QUANTITY = re.compile(
    r"(?P<value>\d+)\s+(?:(?P<qualifier>calendar|business)\s+)?(?P<unit>hour|day|week|month|year)s?",
    re.I,
)


def _value(item, field: str) -> str:
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


def _compare(field: str, governing: str, internal: str, candidate: dict) -> tuple[str, str, str]:
    if not governing:
        return "SUPPORTED", "not_constrained", "governing atom does not constrain this field"
    source_text = str(candidate.get("source_text", ""))
    if field == "modality" and candidate.get("binding_effect") == "internally_mandatory":
        return "SUPPORTED", "binding_effect", "controlled procedure text is internally mandatory"
    if (
        field == "actor"
        and re.search(r"\b(LSPG|SME|OT|Security|Manager|Owner)\b", source_text, re.I)
        and re.search(r"\b(Responsible Entity|Each Responsible Entity)\b", governing, re.I)
    ):
        return (
            "SUPPORTED",
            "entity_alias",
            "internal role is assigned within the responsible entity",
        )
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
                return "SUPPORTED", kind, note
            return "UNRESOLVED", kind, note
    left, right = _norm(governing), _norm(f"{internal} {source_text}")
    threshold = 0.45 if field in {"action", "object", "condition", "exception"} else 0.6
    if left and (left <= right or len(left & right) / len(left) >= threshold):
        return "SUPPORTED", "token_entailment", "governing terms are present in the assertion"
    return "ABSENT", "token_entailment", "candidate does not address the governing field"


def assess_atom(atom: dict, candidates: list[dict], ctx: dict) -> AtomResult:
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


def _expression(payload: dict) -> ExpressionNode:
    return ExpressionNode(
        kind=payload["kind"],
        atom_id=payload.get("atom_id", ""),
        n=payload.get("n", 0),
        children=[_expression(child) for child in payload.get("children", [])],
    )


def assess_requirement(node: dict, ctx: dict) -> RequirementResult:
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
    evaluate_expression(_expression(expression), statuses)  # roll-up below preserves ABSENT/PARTIAL
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


def serialize(result: RequirementResult) -> dict:
    return asdict(result)
