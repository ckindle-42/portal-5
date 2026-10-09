"""Service integration for analyst write-back, replay, and calibration isolation."""

from __future__ import annotations

import pytest

from portal.modules.security.core.review import calibration, funnel, intake, pipeline, service
from portal.modules.security.core.review.contracts import Verdict
from portal.modules.security.core.review.store import ReviewStore
from portal.modules.security.core.review.window import InMemoryWindowSource, SourceSpec

from ._fakes import HashEmbedder, linux_records, web_records, windows_records


def _fixture() -> tuple[
    dict[str, list[dict[str, object]]],
    intake.IntakeResult,
    InMemoryWindowSource,
    service.ReviewRequest,
    pipeline.Reference,
]:
    specs = [
        SourceSpec("memory", "wineventlog"),
        SourceSpec("memory", "web:access"),
        SourceSpec("memory", "linux:audit"),
    ]
    records_by_source = {
        specs[0].source_id: [dict(item) for item in windows_records(80, seed=5)],
        specs[1].source_id: [dict(item) for item in web_records(80, seed=6)],
        specs[2].source_id: [dict(item) for item in linux_records(80, seed=7)],
    }
    for records in records_by_source.values():
        for index, record in enumerate(records):
            record["_time"] = float(index)
    training = intake.build_window_units(records_by_source)
    policy = funnel.FunnelPolicy(0.2, 0.2, levels=("L2_ENTITY",))
    baseline = funnel.fit_baseline([unit.unit for unit in training.units], "memory-env")
    null = calibration.CalibrationSet()
    null.put(
        calibration.fit_calibration(
            funnel.CHANNEL_UNUSUAL,
            "L2_ENTITY",
            [-1.0] * 40,
            0.2,
            basis="test_benign_slice",
        )
    )
    reference = pipeline.Reference(
        baseline,
        null,
        "test_benign_slice",
        calibration_window=training,
    )
    request = service.ReviewRequest(
        specs, 0.0, 80.0, "memory-env", pipeline.ReviewConfig(policy=policy)
    )
    return (
        records_by_source,
        training,
        InMemoryWindowSource(records_by_source, partition_seconds=40),
        request,
        reference,
    )


def _outcomes(result: pipeline.ReviewResult) -> list[tuple[str, str, float]]:
    return sorted(
        (item.unit_id, item.outcome.value, item.priority_p)
        for item in [*result.concerns, *result.suppressed]
    )


def test_service_persists_runs_exposes_verdict_queue_and_replays_as_of() -> None:
    _records, _training, source, request, reference = _fixture()
    store = ReviewStore()

    first = service.run_review(
        request,
        source=source,
        embedder=None,
        index=None,
        reference=reference,
        store=store,
    )
    assert first.concerns
    assert service.queue(store=store)

    concern_id = first.concerns[0].concern_id
    service.record_verdict(
        concern_id,
        Verdict.NOTHING,
        actor="analyst:test",
        store=store,
        at=first.finished_at + 1.0,
    )
    assert all(item.concern_id != concern_id for item in service.queue(store=store))
    assert not service.contradictions(store=store)

    replay = service.run_review(
        request,
        source=source,
        embedder=None,
        index=None,
        reference=reference,
        store=store,
        as_of=first.finished_at,
    )
    assert replay.fingerprint["knowledge_anchors"] == "0"
    assert _outcomes(replay) == _outcomes(first)


def test_benign_verdict_anchor_events_are_excluded_from_calibration_null(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _records, training, source, request, reference = _fixture()
    store = ReviewStore()
    first = service.run_review(
        request,
        source=source,
        embedder=None,
        index=None,
        reference=reference,
        store=store,
    )
    concern_id = first.concerns[0].concern_id
    writeback = service.record_verdict(
        concern_id,
        Verdict.NOTHING,
        actor="analyst:test",
        store=store,
        at=first.finished_at + 1.0,
    )
    assert writeback.anchor_id is not None

    observed: dict[str, intake.IntakeResult] = {}
    original = service.build_reference

    def capture_reference(
        benign: intake.IntakeResult,
        *,
        policy: funnel.FunnelPolicy,
        index: object,
        embedder: object,
        environment_id: str,
        basis: str = "benign_slice",
    ) -> pipeline.Reference:
        observed["calibration"] = benign
        return original(
            benign,
            policy=policy,
            index=index,  # type: ignore[arg-type]
            embedder=embedder,  # type: ignore[arg-type]
            environment_id=environment_id,
            basis=basis,
        )

    monkeypatch.setattr(service, "build_reference", capture_reference)
    second = service.run_review(
        request,
        source=source,
        embedder=HashEmbedder(),
        index=None,
        reference=reference,
        store=store,
        as_of=first.finished_at + 2.0,
        calibration_window=training,
    )

    anchor = next(row for row in store.anchors() if row.anchor_id == writeback.anchor_id)
    anchor_events = set(anchor.record["event_ids"])
    calibration_events = set(observed["calibration"].events)
    assert anchor_events.isdisjoint(calibration_events)
    receipt = next(row for row in second.receipts if row.name == "knowledge.calibration_null")
    assert receipt.examined == len(training.units)
    assert receipt.resolved < receipt.examined
