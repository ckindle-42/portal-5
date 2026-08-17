"""Reproducible planner proof over the live source catalog."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .connectors import QueryIntent
from .data_plane import DataPlane, InvestigationPlan


def _plan_dict(plan: InvestigationPlan) -> dict[str, Any]:
    return {
        "seed_id": plan.seed_id,
        "source_order": list(plan.source_order),
        "decisions": [
            {
                "source_id": decision.source_id,
                "selected": decision.selected,
                "reasons": list(decision.reasons),
            }
            for decision in plan.decisions
        ],
    }


def planner_proof(plane: DataPlane) -> dict[str, Any]:
    telemetry_plan = plane.plan(
        "seed-live-telemetry",
        QueryIntent(
            "investigate indexed entity activity",
            seed={"required_capabilities": ("queryable_in_place", "entity_identity")},
        ),
    )
    coverage_plan = plane.plan(
        "seed-response-coverage",
        QueryIntent(
            "measure response-axis coverage",
            seed={"required_capabilities": ("label_basis", "semantic_text")},
        ),
    )
    telemetry = _plan_dict(telemetry_plan)
    coverage = _plan_dict(coverage_plan)
    telemetry_sources = set(telemetry_plan.source_order)
    coverage_sources = set(coverage_plan.source_order)
    report = {
        "telemetry": telemetry,
        "coverage": coverage,
        "materially_different": telemetry_sources != coverage_sources,
        "catalog_version": plane.catalog.version,
    }
    report["proof_hash"] = hashlib.sha256(
        json.dumps(report, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return report
