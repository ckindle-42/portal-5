"""The defense axis uses only scoped, read-only searches and fails closed."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from portal.modules.security.core.review import defense, service
from portal.modules.security.core.review.contracts import (
    Channel,
    DefenseResponse,
    EvidenceRef,
    Outcome,
    Resemblance,
    ReviewConcern,
    ReviewResult,
)
from portal.modules.security.core.review.intake import EventView, IntakeResult
from portal.modules.security.core.review.store import ReviewStore
from portal.modules.security.core.review.window import SourceSpec, WindowBatch


def _concern(label: str = "T1059") -> ReviewConcern:
    return ReviewConcern(
        concern_id="concern-1",
        unit_id="unit-1",
        level="L2_ENTITY",
        outcome=Outcome.COUSIN,
        channels=(Channel.KNOWN_SIMILAR,),
        priority_p=0.01,
        entities=("entity=host-1",),
        source_ids=("portal5_lab:linux:auditd",),
        evidence=(EvidenceRef("linux:auditd:event-1", "portal5_lab:linux:auditd"),),
        resembles=(
            Resemblance(
                "anchor-1",
                "attack_episode",
                label,
                0.95,
                0.01,
                malice="malicious",
            ),
        ),
    )


def _window() -> IntakeResult:
    event_id = "linux:auditd:event-1"
    return IntakeResult(
        events={event_id: EventView(event_id, "portal5_lab:linux:auditd", 10.0, "event")}
    )


def test_detection_rows_inside_bounded_window_are_covered() -> None:
    calls: list[tuple[str, float, float]] = []

    def search(spl: str, start: float, end: float) -> list[Mapping[str, Any]]:
        calls.append((spl, start, end))
        return [{"_time": 10.0000005, "host": "host-1"}]

    assessment = defense.assess(
        _concern(),
        start=10.0,
        end=10.000001,
        context_start=0.0,
        context_end=20.0,
        searcher=search,
    )

    assert assessment.response == DefenseResponse.COVERED
    assert assessment.matching_rows == len(calls) > 0
    assert assessment.queries_examined == len(calls)
    assert all(start == 10.0 and end == 10.000001 for _, start, end in calls)
    assert all('"host-1"' in spl for spl, _, _ in calls)
    assert assessment.expected_signals


def test_rows_for_the_entity_outside_the_concern_window_are_near_miss() -> None:
    calls: list[tuple[float, float]] = []

    def search(_spl: str, start: float, end: float) -> list[Mapping[str, Any]]:
        calls.append((start, end))
        return [{"_time": 15.0}] if start == 0.0 and end == 20.0 else []

    assessment = defense.assess(
        _concern(),
        start=10.0,
        end=10.000001,
        context_start=0.0,
        context_end=20.0,
        searcher=search,
    )

    assert assessment.response == DefenseResponse.NEAR_MISS
    assert assessment.matching_rows > 0
    expected_queries = len(defense.detections_for(_concern())) * 2
    assert len(calls) == assessment.queries_examined == expected_queries


def test_applicable_detections_without_rows_are_missed() -> None:
    assessment = defense.assess(
        _concern(),
        start=10.0,
        end=10.000001,
        context_start=0.0,
        context_end=20.0,
        searcher=lambda _spl, _start, _end: [],
    )
    assert assessment.response == DefenseResponse.MISSED
    assert assessment.queries_resolved == assessment.queries_examined


def test_aggregate_rows_without_timestamps_cannot_prove_a_near_miss() -> None:
    assessment = defense.assess(
        _concern(),
        start=10.0,
        end=10.000001,
        context_start=0.0,
        context_end=20.0,
        searcher=lambda _spl, start, end: (
            [{"host": "host-1"}] if start == 0.0 and end == 20.0 else []
        ),
    )
    assert assessment.response == DefenseResponse.INDETERMINATE


def test_missing_detection_and_unreachable_splunk_are_indeterminate() -> None:
    calls = 0

    def search(_spl: str, _start: float, _end: float) -> list[Mapping[str, Any]]:
        nonlocal calls
        calls += 1
        return [{"host": "host-1"}]

    missing = defense.assess(
        _concern("T9999"),
        start=10.0,
        end=10.000001,
        context_start=0.0,
        context_end=20.0,
        searcher=search,
    )
    assert missing.response == DefenseResponse.INDETERMINATE
    assert calls == 0

    wrong_source = _concern()
    wrong_source.source_ids = ("portal5_lab:aws:cloudtrail",)
    no_applicable = defense.assess(
        wrong_source,
        start=10.0,
        end=10.000001,
        context_start=0.0,
        context_end=20.0,
        searcher=search,
    )
    assert no_applicable.response == DefenseResponse.INDETERMINATE
    assert calls == 0

    def unavailable(_spl: str, _start: float, _end: float) -> list[Mapping[str, Any]]:
        raise OSError("Splunk unavailable")

    failed = defense.assess(
        _concern(),
        start=10.0,
        end=10.000001,
        context_start=0.0,
        context_end=20.0,
        searcher=unavailable,
    )
    assert failed.response == DefenseResponse.INDETERMINATE
    assert failed.errors > 0


def test_missing_entities_never_issue_an_unbounded_query() -> None:
    concern = _concern()
    concern.entities = ()
    calls: list[str] = []
    assessment = defense.assess(
        concern,
        start=10.0,
        end=10.000001,
        context_start=0.0,
        context_end=20.0,
        searcher=lambda spl, _start, _end: calls.append(spl) or [],
    )
    assert assessment.response == DefenseResponse.INDETERMINATE
    assert calls == []


def test_scoped_spl_quotes_entity_values_before_pipeline() -> None:
    spl = defense.scope_spl(
        'index=portal5_lab sourcetype="web:access" | stats count by host',
        ('entity=alice" OR index=*\n| delete',),
    )
    assert spl.startswith('search (index=portal5_lab sourcetype="web:access") AND ')
    assert '"alice\\" OR index=*\\n| delete"' in spl
    assert spl.endswith("| stats count by host")


def test_concern_bounds_use_all_unit_events_beyond_displayed_evidence() -> None:
    window = IntakeResult(
        events={
            "first": EventView("first", "source", 10.0, "first"),
            "last": EventView("last", "source", 15.0, "last"),
        }
    )
    assert defense._concern_bounds(
        _concern(),
        window,
        0.0,
        20.0,
        {"unit-1": ("first", "last")},
    ) == (10.0, 15.000001)


def test_service_runs_detection_search_through_read_only_source(monkeypatch: Any) -> None:
    concern = _concern()
    calls: list[tuple[str, float, float]] = []

    class Source:
        def fetch(self, _sources: list[SourceSpec], _start: float, _end: float) -> WindowBatch:
            return WindowBatch()

        def iter_post(self, spl: str, start: float, end: float) -> list[Mapping[str, Any]]:
            calls.append((spl, start, end))
            return [{"host": "host-1"}]

    monkeypatch.setattr(
        service,
        "review_window",
        lambda *_args, **_kwargs: ReviewResult("run-1", {}, concerns=[concern]),
    )
    request = service.ReviewRequest(
        [SourceSpec("portal5_lab", "linux:auditd")],
        0.0,
        20.0,
        "env",
        _config(),
    )
    result = service.run_review(
        request,
        source=Source(),  # type: ignore[arg-type]
        embedder=None,
        index=None,
        reference=_reference(),
        store=ReviewStore(),
    )
    assert result.concerns[0].defense_response == DefenseResponse.COVERED
    assert calls and all(0.0 <= start < end <= 20.0 for _, start, end in calls)
    assert any('"host-1"' in spl for spl, _, _ in calls)


def _config() -> Any:
    from portal.modules.security.core.review.funnel import FunnelPolicy
    from portal.modules.security.core.review.pipeline import ReviewConfig

    return ReviewConfig(policy=FunnelPolicy(0.2, 0.2, levels=("L2_ENTITY",)))


def _reference() -> Any:
    from portal.modules.security.core.review.calibration import CalibrationSet
    from portal.modules.security.core.review.funnel import fit_baseline
    from portal.modules.security.core.review.pipeline import Reference

    empty = IntakeResult()
    return Reference(fit_baseline([], "env"), CalibrationSet(), "test", calibration_window=empty)
