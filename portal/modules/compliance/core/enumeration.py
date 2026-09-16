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
