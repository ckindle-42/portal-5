"""Durable analyst runtime, checkable evidence, and embedder-change repair."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import httpx
import pytest

from portal.modules.security.core.review import funnel, intake, pipeline, service
from portal.modules.security.core.review.contracts import Claim, JudgeRecord, ReviewConcern, Verdict
from portal.modules.security.core.review.knowledge import AnchorIndex, Embedder
from portal.modules.security.core.review.pipeline import JudgeFn
from portal.modules.security.core.review.service import ReviewRuntime
from portal.modules.security.core.review.window import SplunkWindowSource

from ._fakes import HashEmbedder
from .test_service_knowledge import _fixture


class NamedHashEmbedder(Embedder):
    def __init__(self, identity: str) -> None:
        self.identity = identity

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return HashEmbedder().embed(texts)


def _runtime_for_fixture(
    review_dir: Path,
    *,
    judge: JudgeFn | None = None,
) -> tuple[ReviewRuntime, service.ReviewRequest, intake.IntakeResult]:
    records, training, source, request, reference = _fixture()
    runtime = ReviewRuntime(
        source=source,
        embedder=None,
        index=None,
        reference=reference,
        config=request.config,
        environment_id=request.environment_id,
        review_dir=review_dir,
        judge=judge,
        calibration_records_by_source=records,
        splunk_health=lambda: {"reachable": True, "indexes": {"portal5_lab": 281}},
        reasoning_model_probe=lambda: ["reasoner:test"],
    )
    return runtime, request, training


def test_runtime_lifecycle_explain_verdict_and_doctor(tmp_path: Path) -> None:
    _records, training, source, request, reference = _fixture()

    def judge(concern: ReviewConcern, window: intake.IntakeResult) -> JudgeRecord:
        event_id = concern.evidence[0].event_id
        text = window.events[event_id].text
        return JudgeRecord(
            model="reasoner:test",
            verdict=Verdict.UNSURE,
            claims=(Claim("The event shows a checkable process activity.", (event_id,), text),),
        )

    runtime = ReviewRuntime(
        source=source,
        embedder=None,
        index=None,
        reference=reference,
        config=request.config,
        environment_id=request.environment_id,
        review_dir=tmp_path,
        judge=judge,
        splunk_health=lambda: {"reachable": True, "indexes": {"portal5_lab": 281}},
        reasoning_model_probe=lambda: ["reasoner:test"],
    )
    try:
        run_id = runtime.start(request)
        runtime.worker.join(run_id, timeout=10)
        status = runtime.status(run_id)
        assert status is not None and status.status.value == "COMPLETE"
        result = runtime.result(run_id)
        assert result is not None and result["run_id"] == run_id
        assert result["concerns"]

        concern_id = str(result["concerns"][0]["concern_id"])
        explanation = runtime.explain(concern_id)
        claim = explanation["claims"][0]
        event_id = claim["evidence_ids"][0]
        assert explanation["events"][event_id]["text"] == claim["quote"]
        assert explanation["events"][event_id]["text"]
        assert len(runtime.queue()) > 0
        runtime.verdict(concern_id, Verdict.SOMETHING, actor="analyst:test")
        assert all(item.concern_id != concern_id for item in runtime.queue())

        health = runtime.doctor()
        assert health["splunk"] == {"reachable": True, "indexes": {"portal5_lab": 281}}
        assert health["reasoning_models"]["models"] == ["reasoner:test"]
        assert health["last_run"]["status"] == "COMPLETE"
        assert health["databases"]["runs"]["ok"] is True
        assert health["databases"]["verdicts"]["ok"] is True
        assert training.events
    finally:
        runtime.close()


def test_explain_includes_concern_evidence_without_reader_claims(tmp_path: Path) -> None:
    runtime, request, _training = _runtime_for_fixture(tmp_path)
    try:
        run_id = runtime.start(request)
        runtime.worker.join(run_id, timeout=10)
        status = runtime.status(run_id)
        assert status is not None and status.status.value == "COMPLETE"
        result = runtime.result(run_id)
        assert result is not None and result["concerns"]

        concern = result["concerns"][0]
        concern_id = str(concern["concern_id"])
        expected_ids = {
            str(item["event_id"]) for item in concern["evidence"] if item.get("event_id")
        }
        explanation = runtime.explain(concern_id)

        assert explanation["claims"] == []
        assert set(explanation["events"]) == expected_ids
        assert all(event["text"] for event in explanation["events"].values())
    finally:
        runtime.close()


def test_stale_embedder_refuses_run_then_doctor_reprojects_and_recalibrates(
    tmp_path: Path,
) -> None:
    records, training, source, request, _old_reference = _fixture()
    old_embedder = NamedHashEmbedder("hash-bow;dim=256;identity=old")
    new_embedder = NamedHashEmbedder("hash-bow;dim=256;identity=new")
    policy = request.config.policy
    anchor_unit = next(unit for unit in training.units if unit.unit.level == "L2_ENTITY")
    cards = pipeline.anchors_from_units(
        [anchor_unit],
        kind="advisory",
        label="known-pattern",
        malice="unknown",
        prefix="runtime",
    )
    from portal.modules.security.core.review.knowledge import cards_from_anchors

    old_index = AnchorIndex.build(cards_from_anchors(cards), old_embedder)
    stale_reference = pipeline.build_reference(
        training,
        policy=policy,
        index=old_index,
        embedder=old_embedder,
        environment_id=request.environment_id,
    )
    assert stale_reference.calibrations.stale_for(old_embedder.identity) == []
    similar = stale_reference.calibrations.get(funnel.CHANNEL_SIMILAR, "L2_ENTITY")
    assert similar is not None and similar.embedder_id == old_embedder.identity

    runtime = ReviewRuntime(
        source=source,
        embedder=new_embedder,
        index=old_index,
        reference=stale_reference,
        config=request.config,
        environment_id=request.environment_id,
        review_dir=tmp_path,
        calibration_records_by_source=records,
        splunk_health=lambda: {"reachable": True, "indexes": {"portal5_lab": 281}},
        reasoning_model_probe=lambda: ["reasoner:test"],
    )
    try:
        with pytest.raises(ValueError, match="review doctor --fix"):
            runtime.start(request)

        before = runtime.doctor()
        assert before["embedder"]["stale_calibrations"] == ["known_similar|L2_ENTITY"]
        repaired = runtime.doctor(fix=True)
        assert repaired["fix"]["applied"] is True
        assert repaired["embedder"]["stale_calibrations"] == []
        assert repaired["embedder"]["anchor_index_stale"] is False
        fixed = runtime.reference.calibrations.get(funnel.CHANNEL_SIMILAR, "L2_ENTITY")
        assert fixed is not None and fixed.embedder_id == new_embedder.identity
        assert (tmp_path / "reference" / "default.json").is_file()
        assert (tmp_path / "calibration_slice.json").is_file()
        run_id = runtime.start(request)
        runtime.worker.join(run_id, timeout=10)
        status = runtime.status(run_id)
        assert status is not None and status.status.value in {"COMPLETE", "FAILED"}
    finally:
        runtime.close()


def test_startup_marks_prior_queued_work_interrupted(tmp_path: Path) -> None:
    runtime, _request, _training = _runtime_for_fixture(tmp_path)
    pending_id = runtime.run_store.create({"legacy": True})
    runtime.close()

    resumed, _request, _training = _runtime_for_fixture(tmp_path)
    try:
        assert resumed.interrupted_at_startup == 1
        status = resumed.status(pending_id)
        assert status is not None and status.status.value == "INTERRUPTED"
    finally:
        resumed.close()


def test_runtime_uses_exact_instruction_for_stale_calibration(tmp_path: Path) -> None:
    records, training, source, request, _reference = _fixture()
    old = NamedHashEmbedder("identity=old")
    current = NamedHashEmbedder("identity=current")
    anchor_unit = next(unit for unit in training.units if unit.unit.level == "L2_ENTITY")
    from portal.modules.security.core.review.knowledge import cards_from_anchors

    index = AnchorIndex.build(
        cards_from_anchors(
            pipeline.anchors_from_units(
                [anchor_unit],
                kind="advisory",
                label="known-pattern",
                malice="unknown",
                prefix="instruction",
            )
        ),
        old,
    )
    reference = pipeline.build_reference(
        training,
        policy=request.config.policy,
        index=index,
        embedder=old,
        environment_id=request.environment_id,
    )
    assert reference.calibrations.get(funnel.CHANNEL_SIMILAR, "L2_ENTITY") is not None
    runtime = ReviewRuntime(
        source=source,
        embedder=current,
        index=index,
        reference=reference,
        config=request.config,
        environment_id=request.environment_id,
        review_dir=tmp_path,
        calibration_records_by_source=records,
    )
    try:
        with pytest.raises(ValueError) as exc:
            runtime.start(request)
        assert service.STALE_CALIBRATION_INSTRUCTION in str(exc.value)
    finally:
        runtime.close()


def test_splunk_health_reports_index_and_event_counts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/services/data/indexes"
        return httpx.Response(
            200,
            json={
                "entry": [
                    {"name": "botsv3", "content": {"totalEventCount": "123"}},
                    {"name": "empty_index", "content": {}},
                ]
            },
        )

    source = SplunkWindowSource(
        url="https://splunk.test:8089",
        user="analyst",
        password="secret",
        transport=httpx.MockTransport(handler),
    )
    assert source.health() == {
        "reachable": True,
        "index_count": 2,
        "indexes": {"botsv3": 123, "empty_index": None},
    }
