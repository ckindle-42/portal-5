"""Proposed-change scenarios (P6.6 / design §7.3 / Q12).

A scenario evaluates a proposed edit to ONE targeted Part against a pinned
snapshot: the same snapshot is assessed *before*, the edit is materialised as an
exact :class:`ScenarioOverlay` over that snapshot, and the resulting virtual
document state is assessed *after* through the **same** shared
``assessment.assess_part`` service. The actual corpus, mappings and approved
decisions are never mutated — the proposed text lives only in the virtual
request for this one evaluation.

What this does NOT do: it does not draft the replacement language itself, and it
does not decide a compliance verdict outside the shared service. Before and
after share the same scope/effective-date semantics; a planned future effective
date is carried as an explicit label, never silently treated as today.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from portal.modules.compliance.core import assessment_source
from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.assessment import assess_part
from portal.modules.compliance.core.change_plan import build as build_change_plan
from portal.modules.compliance.core.cip_register import Register
from portal.modules.compliance.core.determination import (
    AssessmentContext,
    AssessmentRequest,
    ScenarioEdit,
    ScenarioOverlay,
)
from portal.modules.compliance.core.mapping_store import MappingStore
from portal.modules.compliance.core.temporal import now_iso


@dataclass
class ChangeScenario:
    scenario_id: str
    target_node_id: str
    patch_text: str
    rationale: str
    scope_note: str
    planned_effective_date: str | None
    created_at: str = field(default_factory=now_iso)
    #: exact REPLACE/ADD edits; when absent the bare ``patch_text`` is treated
    #: as an explicitly ADDITIVE scenario (labelled), never a silent replacement.
    overlay: ScenarioOverlay | None = None


def evaluate_scenario(
    scenario: ChangeScenario,
    reg: Register,
    scope: AssetScope,
    effective_on: str,
    real_propose: Any | None = None,
    mapping_store: MappingStore | None = None,
    *,
    context: AssessmentContext | None = None,
    request: AssessmentRequest | None = None,
    kb_id: str = "operator_corpus",
) -> dict[str, Any]:
    """Return isolated before/after assessments over one pinned snapshot.

    ``real_propose`` is accepted for caller compatibility; retrieval now flows
    through the source adapter's single pinned acquisition, so it is not used.
    A hermetic caller injects ``request`` and ``context``.
    """
    node = next((n for n in reg.nodes if n.id == scenario.target_node_id), None)
    if node is None:
        return {"error": f"target_node_id not found in register: {scenario.target_node_id}"}

    if context is None and request is None:
        # Legacy no-context callers (and hermetic unit tests) must never reach a
        # live model/retrieval. Production passes an explicit context+request.
        ctx = _hermetic_context()
        base = _hermetic_request(scenario.target_node_id, scope, effective_on)
    else:
        ctx = context or _default_context(kb_id, scope, effective_on)
        base = request or _base_request(scenario.target_node_id, scope, effective_on, kb_id)
    if base.snapshot is None:
        return {
            "error": "scenario requires a pinned corpus snapshot",
            "scenario_id": scenario.scenario_id,
        }

    overlay = scenario.overlay or _legacy_overlay(scenario, base)
    before = assess_part(base, ctx)
    try:
        virtual = assessment_source.materialize_overlay(base, overlay)
    except ValueError as exc:
        return {
            "error": str(exc),
            "scenario_id": scenario.scenario_id,
            "target_node_id": scenario.target_node_id,
            "before_assessment_id": before.assessment_id,
        }
    after = assess_part(virtual, ctx)

    before_coverage = before.documentary_coverage
    after_coverage = after.documentary_coverage
    return {
        "scenario_id": scenario.scenario_id,
        "target_node_id": scenario.target_node_id,
        "rationale": scenario.rationale,
        "planned_effective_date": scenario.planned_effective_date,
        "temporal_label": "planned_future" if scenario.planned_effective_date else "current",
        "scope_basis": base.scope_basis,
        "snapshot_fingerprint": base.snapshot.fingerprint,
        "virtual_fingerprint": virtual.snapshot.fingerprint if virtual.snapshot else "",
        "before_assessment_id": before.assessment_id,
        "after_assessment_id": after.assessment_id,
        "before": asdict(before),
        "after": asdict(after),
        "coverage_before": before_coverage,
        "coverage_after": after_coverage,
        "determination_changed": before_coverage != after_coverage,
        "qualification_changed": before_coverage != after_coverage,
        "weakening": _is_weakening(before_coverage, after_coverage),
        "affected_obligation": node.id,
        "change_plan": build_change_plan({"target_node_id": node.id}),
        "note": "Shared-service before/after over one pinned snapshot; the proposed "
        "text is not written to the effective corpus or any approved mapping.",
    }


def _default_context(kb_id: str, scope: AssetScope, effective_on: str) -> AssessmentContext:
    from portal.modules.compliance.core.runtime_config import build_assessment_context

    return build_assessment_context(kb_id, scope, effective_on, "", None)


def _hermetic_context() -> AssessmentContext:
    """A network-free context: the alignment/report transports return empty
    strings, so the assessment resolves UNRESOLVED without a live call."""
    return AssessmentContext(
        seats=[],
        seat_fn=lambda model, system, user: "",
        report_fn=lambda model, system, user: "",
    )


def _hermetic_request(
    target_node_id: str, scope: AssetScope, effective_on: str
) -> AssessmentRequest:
    """A pinned request with an empty explicit candidate set — no retrieval."""
    from portal.modules.compliance.core.assessment_source import resolve_governing_bundle
    from portal.modules.compliance.core.determination import CandidateSet, CorpusSnapshot

    return AssessmentRequest(
        requirement_id=target_node_id,
        scope=scope,
        effective_on=effective_on,
        governing=resolve_governing_bundle(target_node_id),
        candidate_set=CandidateSet(),
        snapshot=CorpusSnapshot(
            snapshot_id="legacy-hermetic",
            kb_id="legacy",
            acquisition_mode="EXPLICIT_SET",
            completeness="UNKNOWN",
            fingerprint="legacy-hermetic",
        ),
    )


def _base_request(
    target_node_id: str, scope: AssetScope, effective_on: str, kb_id: str
) -> AssessmentRequest:
    request = assessment_source.build_assessment_request(
        target_node_id,
        kb_id=kb_id,
        effective_on=effective_on,
    )
    request.scope = scope
    return request


def _legacy_overlay(scenario: ChangeScenario, base: AssessmentRequest) -> ScenarioOverlay:
    """A bare legacy patch string defaults to ADD and is labelled as such."""
    edit = ScenarioEdit(
        operation="ADD",
        target_document=scenario.target_node_id,
        target_section="scenario-proposed",
        new_text=scenario.patch_text,
        label="legacy-add",
    )
    return ScenarioOverlay(
        base_snapshot_fingerprint=base.snapshot.fingerprint if base.snapshot else "",
        edits=[edit],
    )


_SEVERITY = {"FULL": 3, "PARTIAL": 2, "NONE": 1, "NEEDS_REVIEW": 1, "UNRESOLVED": 0}


def _is_weakening(before: str, after: str) -> bool:
    return _SEVERITY.get(after, 0) < _SEVERITY.get(before, 0)


def new_scenario(
    target_node_id: str,
    patch_text: str,
    rationale: str,
    scope_note: str = "",
    planned_effective_date: str | None = None,
    overlay: ScenarioOverlay | None = None,
) -> ChangeScenario:
    return ChangeScenario(
        scenario_id=uuid.uuid4().hex[:12],
        target_node_id=target_node_id,
        patch_text=patch_text,
        rationale=rationale,
        scope_note=scope_note,
        planned_effective_date=planned_effective_date,
        overlay=overlay,
    )
