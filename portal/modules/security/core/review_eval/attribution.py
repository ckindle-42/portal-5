"""review_eval.attribution -- where the truth is lost, stage by stage.

Root cause this exists for: on 2026-10-08 a day of grader tuning (B1, F1, T1) targeted a stage
that was not binding. The one instrument that mattered (B1.1) showed 558 of 988 blind probes
retrieved NO truth-related candidate at all, so no grader change could ever find them. The
tuning was not clumsy; the system simply had no per-stage ceiling, so nothing said WHERE the
loss was.

Every evaluation therefore reports a *truth ledger*: for each independently sourced truth item,
the last stage it survived. The binding stage is the stage that loses the most items (ties go to
the earliest, since an upstream loss caps everything downstream). A change is admissible only
against the binding stage; ``decisions.problems`` enforces it.

Stages, in order:

  window     the item's events were fetched into the window
  unit       some unit contains one of its events (a source was not blind; units formed)
  candidate  that unit was flagged by the funnel
  retrieved  the correct known anchor (twin-aware) was among the top-k (known / cousin classes)
  read       the reader did not dismiss it
  raised     it reached the analyst queue within the workload budget

``last_stage`` is the representation on purpose: a trace cannot claim a later stage without the
earlier ones, so the ledger cannot be inconsistent.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from portal.modules.security.core.review.contracts import ReviewConcern, ReviewResult
from portal.modules.security.core.review_eval.metrics import twin_aware_hit

if TYPE_CHECKING:
    from portal.modules.security.core.review.intake import IntakeResult
    from portal.modules.security.core.review_eval.truth import TruthItem

STAGES: tuple[str, ...] = ("window", "unit", "candidate", "retrieved", "read", "raised")


class AttributionError(ValueError):  # noqa: N818 -- the name is the contract
    """The truth ledger cannot be built from these traces."""


@dataclass(frozen=True)
class TruthTrace:
    item_id: str
    klass: str
    last_stage: str | None  # the last stage survived; None = lost before the window


@dataclass(frozen=True)
class StageCount:
    stage: str
    reached: int
    lost_here: int


@dataclass(frozen=True)
class Ledger:
    total: int
    stages: tuple[StageCount, ...]
    binding: str  # "" when nothing was lost

    def to_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "binding": self.binding,
            "stages": [
                {"stage": c.stage, "reached": c.reached, "lost_here": c.lost_here}
                for c in self.stages
            ],
        }


def traces_for(
    result: ReviewResult,
    window: IntakeResult,
    truth: Sequence[TruthItem],
    *,
    workload_b: int | None = None,
    twin_groups: Mapping[str, str] | None = None,
) -> list[TruthTrace]:
    """Map independently sourced truth through fetched events, units, and the analyst queue.

    ``window`` is the product intake result built from the exact ``WindowBatch`` passed through
    the service. ``workload_b`` limits the queue by the product's ranked concerns; a missing B
    means the full queue is visible. Novel classes have no expected anchor and are handled by
    the caller's per-class ``skip={"novel": {"retrieved"}}`` ledger rule.
    """
    if workload_b is not None and workload_b < 0:
        raise ValueError("workload_b must be non-negative")
    active = list(result.concerns)
    candidates = [*active, *result.suppressed]
    candidate_units = {concern.unit_id for concern in candidates}
    active_units = {concern.unit_id for concern in active}
    ranked = sorted(active, key=lambda concern: (concern.priority_p, concern.concern_id))
    budget = len(ranked) if workload_b is None else min(workload_b, len(ranked))
    raised_units = {concern.unit_id for concern in ranked[:budget]}
    concerns_by_unit = _concerns_by_unit(candidates)
    unit_ids_by_event = _unit_ids_by_event(window)
    available_events = set(window.events)
    twins = twin_groups or {}
    return [
        TruthTrace(
            item.item_id,
            item.klass,
            _trace_last_stage(
                item,
                available_events,
                unit_ids_by_event,
                candidate_units,
                concerns_by_unit,
                active_units,
                raised_units,
                twins,
            ),
        )
        for item in truth
    ]


def _unit_ids_by_event(window: IntakeResult) -> dict[str, set[str]]:
    units_by_event: dict[str, set[str]] = {}
    for unit in window.units:
        for event_id in unit.event_ids:
            units_by_event.setdefault(event_id, set()).add(unit.unit.unit_id)
    return units_by_event


def _concerns_by_unit(concerns: Sequence[ReviewConcern]) -> dict[str, list[ReviewConcern]]:
    by_unit: dict[str, list[ReviewConcern]] = {}
    for concern in concerns:
        by_unit.setdefault(concern.unit_id, []).append(concern)
    return by_unit


def _has_expected_anchor(
    unit_id: str,
    expected_anchors: set[str],
    concerns_by_unit: Mapping[str, Sequence[ReviewConcern]],
    twin_groups: Mapping[str, str],
) -> bool:
    return any(
        twin_aware_hit(match.anchor_id, expected_anchors, twin_groups)
        for concern in concerns_by_unit.get(unit_id, [])
        for match in concern.resembles
    )


def _trace_last_stage(
    item: TruthItem,
    available_events: set[str],
    unit_ids_by_event: Mapping[str, set[str]],
    candidate_units: set[str],
    concerns_by_unit: Mapping[str, Sequence[ReviewConcern]],
    active_units: set[str],
    raised_units: set[str],
    twin_groups: Mapping[str, str],
) -> str | None:
    fetched = set(item.event_ids) & available_events
    last: str | None = "window" if fetched else None
    unit_ids = {unit for event_id in fetched for unit in unit_ids_by_event.get(event_id, set())}
    if unit_ids:
        last = "unit"
    flagged = unit_ids & candidate_units
    if flagged:
        last = "candidate"
    expected_anchors = set(item.anchor_ids)
    if expected_anchors and any(
        _has_expected_anchor(unit_id, expected_anchors, concerns_by_unit, twin_groups)
        for unit_id in flagged
    ):
        last = "retrieved"
    read = flagged & active_units
    if read:
        last = "read"
    if read & raised_units:
        last = "raised"
    return last


def _rank(stage: str | None) -> int:
    if stage is None:
        return -1
    if stage not in STAGES:
        raise AttributionError(f"unknown stage {stage!r}; expected one of {STAGES}")
    return STAGES.index(stage)


def ledger(traces: Sequence[TruthTrace], *, skip: Collection[str] = ()) -> Ledger:
    """``skip`` lists stages that do not apply (a novel item has no anchor to retrieve)."""
    if not traces:
        raise AttributionError("a ledger needs truth items; an empty set proves nothing")
    unknown = set(skip) - set(STAGES)
    if unknown:
        raise AttributionError(f"cannot skip unknown stages {sorted(unknown)}")
    ranks = [_rank(t.last_stage) for t in traces]
    counts: list[StageCount] = []
    previous = len(traces)
    for stage in (s for s in STAGES if s not in skip):
        reached = sum(1 for r in ranks if r >= STAGES.index(stage))
        counts.append(StageCount(stage, reached, previous - reached))
        previous = reached
    worst = max(counts, key=lambda c: (c.lost_here, -STAGES.index(c.stage)))
    return Ledger(len(traces), tuple(counts), worst.stage if worst.lost_here > 0 else "")


def by_class(
    traces: Sequence[TruthTrace], *, skip: Mapping[str, Collection[str]] | None = None
) -> dict[str, Ledger]:
    classes = sorted({t.klass for t in traces})
    return {
        k: ledger([t for t in traces if t.klass == k], skip=(skip or {}).get(k, ()))
        for k in classes
    }


def render_markdown(ledgers: Mapping[str, Ledger]) -> str:
    lines = [
        "| class | items | " + " | ".join(STAGES) + " | binding |",
        "|---|---|" + "---|" * (len(STAGES) + 1),
    ]
    for name, led in sorted(ledgers.items()):
        reached = {c.stage: str(c.reached) for c in led.stages}
        cells = [reached.get(s, "n/a") for s in STAGES]
        lines.append(
            f"| {name} | {led.total} | " + " | ".join(cells) + f" | {led.binding or '-'} |"
        )
    return "\n".join(lines) + "\n"
