"""The shared assessment entry points (IMPLEMENTATION_BRIEF_COMPLIANCE_READING).

``assess_requirement`` expands one requirement reference (e.g. ``"CIP-007-6 R2"``)
into its Parts and runs the single authoritative ``assessment.assess_part``
service for each. Gaps, analyze, scenarios, proposals and the asynchronous run
worker all call through here, so the same input produces the same engine,
fingerprint and verdict regardless of which MCP tool asked.
"""

from __future__ import annotations

from typing import Any

from portal.modules.compliance.core.assessment import assess_part
from portal.modules.compliance.core.assessment_source import (
    build_assessment_request,
    build_corpus_snapshot,
)
from portal.modules.compliance.core.cip_register import Register
from portal.modules.compliance.core.determination import (
    AssessmentContext,
    AssessmentRequest,
    AssessmentResult,
    ScenarioOverlay,
)
from portal.modules.compliance.core.scope_derive import derive_scope

__all__ = ["part_ids", "assess_requirement", "build_requests"]


def part_ids(requirement_id: str) -> list[str]:
    """Every register Part under a requirement reference, in stable order."""
    reg = Register.load()
    exact = [n.id for n in reg.nodes if n.id == requirement_id]
    if exact:
        return exact
    parts = sorted(
        n.id for n in reg.nodes if n.granularity == "part" and n.id.startswith(requirement_id + " ")
    )
    if parts:
        return parts
    # fall back to an R-level node when it has no extracted Parts
    return sorted(n.id for n in reg.nodes if n.id.startswith(requirement_id))


def _resolve_scope(kb_id: str, scope_text: str, scope: Any, conditional: bool) -> tuple[Any, str]:
    if scope is not None:
        return scope, ("conditional" if conditional else "actual")
    if scope_text:
        from portal.modules.compliance.core.applicability import parse_scope_declaration

        return parse_scope_declaration(scope_text), ("conditional" if conditional else "actual")
    derived, _meta = derive_scope(kb_id)
    return derived, "actual"


def build_requests(
    requirement_id: str,
    *,
    kb_id: str = "operator_corpus",
    org_id: str = "default",
    scope_text: str = "",
    scope: Any = None,
    effective_on: str = "",
    known_at: str = "",
    conditional_scope: bool = False,
    top_k: int = 15,
    arbiter_fn: Any = None,
    overlay: ScenarioOverlay | None = None,
    policy_graph: Any = None,
    snapshot: Any = None,
) -> list[AssessmentRequest]:
    resolved_scope, basis = _resolve_scope(kb_id, scope_text, scope, conditional_scope)
    shared_snapshot = snapshot or build_corpus_snapshot(kb_id)
    requests: list[AssessmentRequest] = []
    for pid in part_ids(requirement_id):
        request = build_assessment_request(
            pid,
            kb_id=kb_id,
            scope_text=scope_text,
            effective_on=effective_on,
            known_at=known_at,
            org_id=org_id,
            conditional_scope=conditional_scope,
            top_k=top_k,
            arbiter_fn=arbiter_fn,
            policy_graph=policy_graph,
        )
        # The adapter resolves scope from scope_text; an explicit AssetScope (or
        # a scope derived here) is the authority, so override after construction.
        request.scope = resolved_scope
        request.snapshot = shared_snapshot
        request.scope_basis = basis
        if overlay is not None:
            from portal.modules.compliance.core.assessment_source import materialize_overlay

            request = materialize_overlay(request, overlay)
        requests.append(request)
    return requests


def assess_requirement(
    requirement_id: str,
    context: AssessmentContext,
    *,
    kb_id: str = "operator_corpus",
    org_id: str = "default",
    scope_text: str = "",
    scope: Any = None,
    effective_on: str = "",
    known_at: str = "",
    conditional_scope: bool = False,
    top_k: int = 15,
    overlay: ScenarioOverlay | None = None,
    policy_graph: Any = None,
    snapshot: Any = None,
    on_result: Any = None,
) -> list[AssessmentResult]:
    """Assess every Part under ``requirement_id`` through the shared service.

    ``on_result(result)`` is called after each Part is persisted so a run worker
    can stream progress; it must not alter the result.
    """
    results: list[AssessmentResult] = []
    for request in build_requests(
        requirement_id,
        kb_id=kb_id,
        org_id=org_id,
        scope_text=scope_text,
        scope=scope,
        effective_on=effective_on,
        known_at=known_at,
        conditional_scope=conditional_scope,
        top_k=top_k,
        overlay=overlay,
        policy_graph=policy_graph,
        snapshot=snapshot,
    ):
        context.repository = context.repository
        result = assess_part(request, context)
        results.append(result)
        if on_result is not None:
            on_result(result)
    return results
