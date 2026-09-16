"""Enumeration over the declared population (SUBSTRATE_PROPERTIES_V1 P6.1).

Property 3: gaps come from enumeration over the requirement register, not from
asking. Its retrieval-side twin is this module: the primitive that reads a
whole declared population straight from the canonical store and emits the
boundary receipt that says what was eligible, what was examined, and what is
missing — the receipt an absence claim rests on.

One implementation, three consumers: ``assessment_source.acquire_exhaustively``
(reduced to a caller of this), file B's ``core.closure`` population, and file
D's ``compliance_orphans``. A population you can name is the thing all three
need, and a population named three ways is the duplication this module exists
to prevent.
"""

from __future__ import annotations

from typing import Any

#: The full requirement-side population: everything the join says belongs to a
#: requirement, in every relation. A narrower call asks for less on purpose.
ALL_RELATIONS = ("governing", "measure", "applicable_systems", "technical_basis")


def population_for_requirement(
    repo: Any,
    ref: str,
    *,
    relations: tuple[str, ...] = ALL_RELATIONS,
    valid_at: str = "",
    proximity_fallback: Any = None,
) -> dict[str, Any]:
    """The sections constituting one requirement, BY IDENTITY where possible.

    ONE_REGULATORY_EXTRACTION_V1 P4.2. Before the join there was no way to
    retrieve *the sections constituting R2 Part 2.2*, so the reading path
    gathered by heading-path proximity — not because proximity is a principle,
    but because it was the only option available. Where
    ``requirement_sections`` has an anchor, the population is now the join, and
    ``population_method`` says ``"join"``.

    Where it does not, ``proximity_fallback`` (a zero-argument callable
    returning section rows) still runs, and ``population_method`` says
    ``"proximity"`` — **named, never silently substituted**. An absence claim
    resting on a proximity guess has to be visibly weaker than one resting on
    the join, or the two get treated as the same evidence.

    The operator-side sections the existing link walk contributes are unioned
    in by the caller: both sides as before, only the regulatory side's
    derivation changes.
    """
    rows = repo.sections_for_requirement(ref, relations=relations, valid_at=valid_at)
    if rows:
        return {
            "ref": ref,
            "population_method": "join",
            "relations": list(relations),
            "section_ids": list(dict.fromkeys(str(r["section_id"]) for r in rows)),
            "rows": rows,
            "detail": (f"{len(rows)} section-relation pair(s) anchored to {ref!r} by exact match"),
        }
    misses = [m for m in repo.anchor_misses() if str(m["requirement_id"]) == ref]
    fallback_rows = list(proximity_fallback() or []) if proximity_fallback else []
    return {
        "ref": ref,
        "population_method": "proximity",
        "relations": list(relations),
        "section_ids": [str(r.get("section_id", "")) for r in fallback_rows],
        "rows": fallback_rows,
        "unanchored": misses,
        "detail": (
            f"{ref!r} is not anchored into the captured revision"
            + (f" ({misses[0]['reason']})" if misses else "")
            + " — this population was gathered by heading-path proximity, which is a "
            "weaker basis than the join and is reported as such"
        ),
    }


def declared_population(
    repo: Any,
    *,
    jurisdiction: str,
    kb_id: str = "",
    scope_sections: list[str] | None = None,
) -> dict[str, Any]:
    """Every canonical section of one jurisdiction, resolved verbatim, with the
    boundary receipt over it.

    The declared population is whatever the store says it is —
    ``section_index.build_plan`` over the jurisdiction, optionally narrowed to
    ``scope_sections`` (one standard, one requirement's neighbourhood). A
    section that cannot yield verbatim text is in the receipt's omissions with
    its reason, never dropped silently: an enumeration that silently omits part
    of the declared population cannot support an absence claim, which is the
    whole reason it exists.

    Returns ``{jurisdiction, kb_id, sections, boundary_receipt,
    examined_sections}`` where ``sections`` maps ``section_id → the canonical
    entry (verbatim text, provenance, authority tier)``.
    """
    from portal.modules.compliance.core import section_index

    plan = section_index.build_plan(repo, jurisdiction=jurisdiction, kb_id=kb_id)
    scope = list(scope_sections) if scope_sections is not None else plan.eligible_sections
    resolved = section_index.resolve_sections(repo, scope)
    receipt = section_index.boundary_receipt(repo, plan, scope_sections=scope)
    receipt["examined_sections"] = sorted(set(scope) & set(resolved))
    receipt["omissions"] = sorted(set(scope) - set(receipt["examined_sections"]))
    receipt["complete"] = bool(receipt["eligible_sections"]) and not receipt["omissions"]
    return {
        "jurisdiction": jurisdiction,
        "kb_id": plan.kb_id,
        "sections": resolved,
        "examined_sections": receipt["examined_sections"],
        "boundary_receipt": receipt,
    }
