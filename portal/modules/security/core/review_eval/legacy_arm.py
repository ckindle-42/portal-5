"""review_eval.legacy_arm -- the only adapter around the shipped legacy discovery defaults."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any

from portal.modules.security.core.bully import artifact_graph, baseline, discovery
from portal.modules.security.core.review.contracts import (
    Channel,
    EvidenceRef,
    Outcome,
    ReviewConcern,
    ReviewResult,
    StageReceipt,
)
from portal.modules.security.core.review.intake import build_window_units


def run_legacy_funnel(
    records_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    environment_id: str,
) -> ReviewResult:
    """Run old graph/unit caps and discovery thresholds exactly as shipped.

    ``artifact_graph.enumerate_units`` and ``discovery.discover`` are intentionally called
    without overrides. No legacy constant is calibrated, tuned, or modified in this adapter.
    The result is projected into the same ``ReviewResult`` concern shape as ``review_d0``.
    """
    started = time.time()
    units: list[artifact_graph.GradeableUnit] = []
    insufficient: list[str] = []
    for source_id, records in sorted(records_by_source.items()):
        source_records = [
            {**record, "__source_id": source_id}
            for record in records
            if isinstance(record, Mapping)
        ]
        graph = artifact_graph.build_graph(source_records, source_id=source_id)
        if graph.insufficient_view:
            insufficient.append(source_id)
        units.extend(artifact_graph.enumerate_units(graph))

    fitted = baseline.NormalBaseline(environment_id=environment_id)
    fitted.fit(units)
    discovered, discovery_report = discovery.discover(units, fitted)
    product_window = build_window_units(records_by_source)
    unit_events = {unit.unit.unit_id: unit.event_ids for unit in product_window.units}
    result = ReviewResult(
        run_id=f"legacy-{int(started)}",
        fingerprint={
            "arm": "legacy_funnel",
            "baseline_units": str(fitted.fitted_units),
            "legacy_unit_cap": str(artifact_graph.MAX_UNITS_PER_LEVEL),
        },
    )
    result.receipts.append(StageReceipt("legacy.units", len(units), len(units)))
    result.receipts.append(
        StageReceipt("legacy.discovery", len(units), len(discovered), str(discovery_report))
    )
    result.degraded.extend(
        f"legacy source has insufficient view: {source}" for source in insufficient
    )
    for candidate in discovered:
        event_ids = unit_events.get(candidate.unit_id, ())
        result.concerns.append(
            ReviewConcern(
                concern_id=f"legacy-{candidate.unit_id}",
                unit_id=candidate.unit_id,
                level=candidate.level,
                outcome=Outcome.NOVEL,
                channels=(Channel.UNUSUAL,),
                priority_p=1.0 - candidate.salience,
                entities=candidate.entities,
                evidence=tuple(
                    EvidenceRef(event_id=event_id, source_id=event_id.rsplit(":", 1)[0])
                    for event_id in event_ids[:200]
                ),
                brief=(
                    f"legacy discovery: remarkability={candidate.remarkability:.4f}; "
                    f"cohesion={candidate.cohesion:.4f}"
                ),
            )
        )
    result.receipts.append(StageReceipt("legacy.output", len(discovered), len(result.concerns)))
    result.started_at = started
    result.finished_at = time.time()
    return result
