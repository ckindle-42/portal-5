"""Leave-one-family-out libraries use product intake units and fail on seeded leakage."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from portal.modules.security.core.bully.artifact_graph import GradeableUnit
from portal.modules.security.core.review.intake import EventView, IntakeResult, IntakeUnit
from portal.modules.security.core.review_eval.folds import (
    FoldLeakError,
    assert_no_probe_leak,
    build_leave_one_family_out,
)


def intake(event_id: str) -> IntakeResult:
    unit = GradeableUnit(
        unit_id=f"unit-{event_id}",
        level="L2_ENTITY",
        artifact_ids=(f"artifact-{event_id}",),
        entities=(f"host={event_id}",),
        action_classes=("auth",),
        edge_kinds=(),
        span_seconds=0.0,
        structural_signature={"class_sequence": ["auth"]},
        vocabulary=("logon",),
        source_ids=("botsv3:wineventlog:security",),
    )
    result = IntakeResult()
    result.events[event_id] = EventView(event_id, "botsv3:wineventlog:security", 1.0, "evidence")
    result.units.append(
        IntakeUnit(unit, (event_id,), unit.source_ids, ("logon",), "sources: event")
    )
    return result


def test_each_family_fold_uses_only_the_other_families_product_units() -> None:
    folds = build_leave_one_family_out({"a": intake("event-a"), "b": intake("event-b")})
    fold_a = folds["a"]
    assert fold_a.probe_event_ids == frozenset({"event-a"})
    assert fold_a.library_event_ids == frozenset({"event-b"})
    assert len(fold_a.anchors) == 1
    assert fold_a.anchors[0].record["family"] == "b"
    assert fold_a.anchors[0].record["event_ids"] == ["event-b"]
    assert_no_probe_leak(fold_a.anchors, fold_a.probe_event_ids)


def test_leak_guard_fails_on_a_seeded_probe_event() -> None:
    leaked = SimpleNamespace(
        anchor_id="seeded-leak",
        record={"event_ids": ["probe-event", "library-event"]},
    )
    with pytest.raises(FoldLeakError, match="leaked 1 event id"):
        assert_no_probe_leak([leaked], {"probe-event"})


def test_leak_guard_fails_closed_when_anchor_has_no_event_receipt() -> None:
    unreceipted = SimpleNamespace(anchor_id="no-receipt", record={"family": "library"})
    with pytest.raises(FoldLeakError, match="lacks source event ids"):
        assert_no_probe_leak([unreceipted], set())
