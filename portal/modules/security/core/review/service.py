"""review.service -- the only harness entry point into the synchronous product path."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass

from .contracts import ReviewResult, StageReceipt
from .intake import build_window_units
from .knowledge import AnchorIndex, Embedder
from .pipeline import JudgeFn, Reference, ReviewConfig, review_window
from .reference import stale
from .wall import assert_label_free
from .window import SourceSpec, WindowSource


@dataclass(frozen=True)
class ReviewRequest:
    sources: Sequence[SourceSpec]
    start: float
    end: float
    environment_id: str
    config: ReviewConfig


def run_review(
    request: ReviewRequest,
    *,
    source: WindowSource,
    embedder: Embedder | None,
    index: AnchorIndex | None,
    reference: Reference,
    config: ReviewConfig | None = None,
    judge: JudgeFn | None = None,
) -> ReviewResult:
    """Fetch, intake, and review a complete request; source or embedding errors propagate."""
    if request.end <= request.start:
        raise ValueError("request.end must be greater than request.start")
    chosen_config = config or request.config
    batch = source.fetch(request.sources, request.start, request.end)
    for source_id, records in batch.records_by_source.items():
        for ordinal, record in enumerate(records):
            assert_label_free(record, where=f"review-service:{source_id}:{ordinal}")

    if index is not None:
        if embedder is None:
            raise ValueError("an anchor index requires its embedder")
        if index.embedder_id != embedder.identity:
            raise ValueError("anchor index and embedder identities disagree")
        stale_keys = stale(reference, embedder.identity)
        if stale_keys:
            raise ValueError(f"reference has stale embedder calibrations: {stale_keys}")

    intake = build_window_units(batch.records_by_source)
    notes = list(batch.degraded)
    intake.receipts.append(
        StageReceipt(
            name="window.fetch",
            examined=batch.expected,
            resolved=batch.fetched,
            note="; ".join(notes),
        )
    )
    result = review_window(
        intake,
        reference=reference,
        index=index,
        embedder=embedder,
        config=chosen_config,
        judge=judge,
    )
    result.degraded.extend(notes)
    source_digest = hashlib.sha256(
        json.dumps(sorted(spec.source_id for spec in request.sources)).encode("utf-8")
    ).hexdigest()[:16]
    result.fingerprint.update(
        {
            "environment": request.environment_id,
            "window": f"{request.start:.6f}:{request.end:.6f}",
            "sources": source_digest,
            "expected_events": str(batch.expected),
            "fetched_events": str(batch.fetched),
        }
    )
    return result
