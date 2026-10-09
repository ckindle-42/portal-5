"""review.service -- the only harness entry point into the synchronous product path."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass

from . import defense, verdicts
from .contracts import ReviewResult, StageReceipt, Verdict
from .intake import IntakeResult, build_window_units
from .knowledge import AnchorCard, AnchorIndex, Embedder
from .pipeline import (
    JudgeFn,
    Reference,
    ReviewConfig,
    build_reference,
    review_window,
)
from .reference import stale
from .store import ReviewStore, StoredConcern
from .wall import assert_label_free
from .window import SourceSpec, WindowSource

DEFAULT_READER: JudgeFn | None = None
DEFAULT_STORE = ReviewStore()


@dataclass(frozen=True)
class ReviewRequest:
    sources: Sequence[SourceSpec]
    start: float
    end: float
    environment_id: str
    config: ReviewConfig


def disjoint_calibration_slice(
    benign: IntakeResult, excluded_event_ids: set[str] | frozenset[str]
) -> IntakeResult:
    """Remove every calibration unit that contains an event used by a verdict anchor."""
    excluded = set(excluded_event_ids)
    units = [unit for unit in benign.units if not excluded.intersection(unit.event_ids)]
    event_ids = {event_id for unit in units for event_id in unit.event_ids}
    removed = len(benign.units) - len(units)
    receipts = list(benign.receipts)
    receipts.append(
        StageReceipt(
            name="knowledge.calibration_null",
            examined=len(benign.units),
            resolved=len(units),
            note=f"excluded {removed} units overlapping verdict-derived benign anchor events",
        )
    )
    return IntakeResult(
        units=units,
        events={key: value for key, value in benign.events.items() if key in event_ids},
        receipts=receipts,
        blind_sources=list(benign.blind_sources),
    )


def _combined_index(
    static_index: AnchorIndex | None,
    learned_cards: Sequence[AnchorCard],
    embedder: Embedder | None,
) -> AnchorIndex | None:
    if not learned_cards:
        return static_index
    if embedder is None:
        raise ValueError("stored verdict anchors require their configured embedder")
    cards: list[AnchorCard] = []
    seen: set[str] = set()
    for card in [*(static_index.cards if static_index is not None else []), *learned_cards]:
        if card.anchor_id not in seen:
            cards.append(card)
            seen.add(card.anchor_id)
    return AnchorIndex.build(cards, embedder)


def run_review(  # noqa: PLR0912 -- this is the sole path orchestration boundary.
    request: ReviewRequest,
    *,
    source: WindowSource,
    embedder: Embedder | None,
    index: AnchorIndex | None,
    reference: Reference,
    config: ReviewConfig | None = None,
    judge: JudgeFn | None = DEFAULT_READER,
    store: ReviewStore | None = None,
    as_of: float | None = None,
    calibration_window: IntakeResult | None = None,
    defense_search: defense.ReadOnlySearcher | None = None,
) -> ReviewResult:
    """Run the deterministic default path, with replayable verdict knowledge and write-back."""
    if request.end <= request.start:
        raise ValueError("request.end must be greater than request.start")
    chosen_config = config or request.config
    active_store = store if store is not None else DEFAULT_STORE

    if index is not None:
        if embedder is None:
            raise ValueError("an anchor index requires its embedder")
        if index.embedder_id != embedder.identity:
            raise ValueError("anchor index and embedder identities disagree")

    learned_rows = active_store.anchors(as_of=as_of)
    learned_cards = verdicts.cards_from_store(active_store, as_of=as_of)
    combined_index = _combined_index(index, learned_cards, embedder)
    chosen_reference = reference
    calibration_source = calibration_window or reference.calibration_window
    calibration_slice: IntakeResult | None = None

    if learned_cards:
        if calibration_source is None:
            raise ValueError(
                "stored verdict anchors require the recorded benign calibration window"
            )
        if embedder is None or combined_index is None:
            raise ValueError("stored verdict anchors require an embedder for recalibration")
        benign_event_ids = {
            str(event_id)
            for anchor in learned_rows
            if anchor.malice == "benign"
            for event_id in anchor.record.get("event_ids", [])
        }
        calibration_slice = disjoint_calibration_slice(calibration_source, benign_event_ids)
        chosen_reference = build_reference(
            calibration_slice,
            policy=chosen_config.policy,
            index=combined_index,
            embedder=embedder,
            environment_id=request.environment_id,
            basis=reference.basis,
        )

    if combined_index is not None:
        if embedder is None:
            raise ValueError("an anchor index requires its embedder")
        stale_keys = stale(chosen_reference, embedder.identity)
        if stale_keys:
            raise ValueError(f"reference has stale embedder calibrations: {stale_keys}")

    batch = source.fetch(request.sources, request.start, request.end)
    for source_id, records in batch.records_by_source.items():
        for ordinal, record in enumerate(records):
            assert_label_free(record, where=f"review-service:{source_id}:{ordinal}")

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
        reference=chosen_reference,
        index=combined_index,
        embedder=embedder,
        config=chosen_config,
        judge=judge,
    )
    searcher = defense_search or defense.source_searcher(source)
    defense_receipt, defense_errors = defense.apply_to_result(
        result,
        intake,
        request_start=request.start,
        request_end=request.end,
        searcher=searcher,
    )
    result.receipts.append(defense_receipt)
    if defense_errors:
        result.degraded.append(
            f"defense searches had {defense_errors} error(s); affected responses are INDETERMINATE"
        )
    result.degraded.extend(notes)
    if calibration_slice is not None and calibration_source is not None:
        null_receipt = calibration_slice.receipts[-1]
        result.receipts.append(null_receipt)

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
            "knowledge_as_of": "current" if as_of is None else f"{as_of:.6f}",
            "knowledge_anchors": str(len(learned_cards)),
        }
    )
    verdicts.persist_run(active_store, result, intake)
    return result


def record_verdict(
    concern_id: str,
    verdict: Verdict,
    *,
    actor: str,
    store: ReviewStore = DEFAULT_STORE,
    note: str = "",
    scripted: bool = False,
    at: float | None = None,
) -> verdicts.WriteBack:
    """Record an analyst verdict and write the resulting knowledge anchor back to the store."""
    return verdicts.record_verdict(
        store,
        concern_id,
        verdict,
        actor=actor,
        note=note,
        scripted=scripted,
        at=at,
    )


def queue(*, store: ReviewStore = DEFAULT_STORE, limit: int | None = None) -> list[StoredConcern]:
    """Return concerns awaiting an analyst verdict."""
    return store.queue() if limit is None else store.queue(limit=limit)


def contradictions(*, store: ReviewStore = DEFAULT_STORE) -> list[dict[str, object]]:
    """Return reversals and disagreements in the recorded review knowledge."""
    return verdicts.contradictions(store)
