"""bully.run_preflight -- fail in seconds, not in hours.

A long run is only worth starting if it cannot already be known to be
invalid. This module exists because the arithmetic of the 27-entry hunt says
a span choice nobody calibrated is the difference between a one-hour run and
a twenty-nine-hour one, measured from K.4's own numbers:

    K.4 measured: 38,040 records -> 971 units, clustering 770.6s (O(n^2)),
                  read throughput ~950 rec/s, 39.2 records per unit

    botsv3 at ~84,583 rec/hr:
        5m  window ->    180 units ->    34s/entry -> 27 entries =  0.3h
       10m  window ->    360 units ->   121s/entry -> 27 entries =  0.9h
       20m  window ->    719 units ->   452s/entry -> 27 entries =  3.4h
       60m  window ->  2,158 units -> 3,894s/entry -> 27 entries = 29.2h

Clustering is quadratic in units, so the span is not a free parameter -- it
is the whole cost model. And botsv2 is roughly 4x botsv3's density, so a span
that is cheap on one index is expensive on another.

Four preconditions this checks, each cheap, each capable of invalidating a
run before it starts:

  1. **Anchors resolve.** An answer-key entry whose entities are not present
     in its index will burn a window discovering that. A term search per
     entry answers it in seconds.
  2. **The plant path round-trips.** If HEC writes silently fail or land
     outside the window, every cousin measurement is void -- and that is
     indistinguishable, after the fact, from a system that failed to find
     them.
  3. **Resume round-trips.** The existing checkpoint covers only
     `stream_corpus_sample`; the hunt loop has none. A mechanism must be
     proven before it is depended on, or a death at entry 22 silently
     restarts at entry 1 -- re-planting cousins and polluting the corpus
     with duplicates.
  4. **The span projection is under budget**, calibrated on ONE real entry
     rather than assumed.

The calibration step is the important one and is deliberately empirical:
run a single entry end to end, measure the units and clustering seconds it
actually produced, project to the full entry count, and only then commit.
Projection from K.4's constants is the starting guess; the measured entry is
the decision.

Pure computation and gating (COLD). Probe callables are injected; this module
performs no I/O of its own.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

ALGORITHM_VERSION = "run-preflight-v1"

# Measured in K.4 and used only as the OPENING projection; the calibration
# entry replaces these with observed values.
K4_RECORDS_PER_UNIT = 39.2
K4_UNITS = 971
K4_CLUSTER_SECONDS = 770.6
K4_READ_RECORDS_PER_SECOND = 950.0

# A run longer than this should be a deliberate decision, not a surprise.
DEFAULT_BUDGET_HOURS = 4.0


def project_entry_seconds(
    units: float,
    records: float,
    *,
    cluster_seconds_at_ref: float = K4_CLUSTER_SECONDS,
    ref_units: float = K4_UNITS,
    read_rps: float = K4_READ_RECORDS_PER_SECOND,
) -> dict[str, float]:
    """Cost of one hunt entry. Clustering is quadratic in units -- that term
    dominates everything else past a few hundred units, which is why span
    sizing decides the run length."""
    read = records / read_rps if read_rps else 0.0
    cluster = cluster_seconds_at_ref * (units / ref_units) ** 2 if ref_units else 0.0
    return {
        "read_seconds": round(read, 1),
        "cluster_seconds": round(cluster, 1),
        "total_seconds": round(read + cluster, 1),
    }


@dataclass(frozen=True)
class SpanCalibration:
    """The decision to commit, made from ONE measured entry."""

    span_seconds: float
    index: str
    measured_records: int
    measured_units: int
    measured_cluster_seconds: float
    measured_total_seconds: float
    n_entries: int
    projected_total_hours: float
    budget_hours: float
    verdict: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_seconds": self.span_seconds,
            "index": self.index,
            "measured_records": self.measured_records,
            "measured_units": self.measured_units,
            "measured_cluster_seconds": round(self.measured_cluster_seconds, 1),
            "measured_total_seconds": round(self.measured_total_seconds, 1),
            "n_entries": self.n_entries,
            "projected_total_hours": round(self.projected_total_hours, 2),
            "budget_hours": self.budget_hours,
            "records_per_unit": (
                round(self.measured_records / self.measured_units, 1)
                if self.measured_units
                else None
            ),
            "verdict": self.verdict,
            "reasons": list(self.reasons),
        }


def calibrate_span(
    *,
    span_seconds: float,
    index: str,
    measured_records: int,
    measured_units: int,
    measured_cluster_seconds: float,
    measured_total_seconds: float,
    n_entries: int,
    budget_hours: float = DEFAULT_BUDGET_HOURS,
) -> SpanCalibration:
    """Project the full run from one measured entry and decide.

    `NARROW_SPAN` is the correct response to an over-budget projection --
    never sampling the window. A sampled hunt window cannot contain a rare
    thing, which is the failure this whole line of work exists to remove.
    """
    projected_hours = (measured_total_seconds * n_entries) / 3600.0
    reasons: list[str] = []
    verdict = "COMMIT"
    if projected_hours > budget_hours:
        verdict = "NARROW_SPAN"
        factor = (budget_hours / projected_hours) ** 0.5  # cost ~ units^2 ~ span^2
        reasons.append(
            f"projected_{projected_hours:.1f}h>{budget_hours}h at span "
            f"{span_seconds / 60:.0f}m -- narrow the span by ~{factor:.2f}x and "
            "re-calibrate; do NOT sample the window"
        )
    if measured_units == 0:
        verdict = "INVALID"
        reasons.append("calibration_entry_produced_no_units: the window is empty or unreadable")
    if measured_records == 0:
        verdict = "INVALID"
        reasons.append("calibration_entry_read_no_records")
    return SpanCalibration(
        span_seconds=span_seconds,
        index=index,
        measured_records=measured_records,
        measured_units=measured_units,
        measured_cluster_seconds=measured_cluster_seconds,
        measured_total_seconds=measured_total_seconds,
        n_entries=n_entries,
        projected_total_hours=projected_hours,
        budget_hours=budget_hours,
        verdict=verdict,
        reasons=tuple(reasons),
    )


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    passed: bool
    detail: str
    seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "seconds": round(self.seconds, 2),
        }


@dataclass(frozen=True)
class PreflightReport:
    checks: tuple[PreflightCheck, ...]
    calibration: SpanCalibration | None = None

    @property
    def passed(self) -> bool:
        ok = all(c.passed for c in self.checks)
        if self.calibration is not None:
            ok = ok and self.calibration.verdict == "COMMIT"
        return ok

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.checks if not c.passed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "passed": self.passed,
            "failures": list(self.failures),
            "checks": [c.to_dict() for c in self.checks],
            "calibration": self.calibration.to_dict() if self.calibration else None,
        }


def check_anchors_resolve(
    entries: list[Any],
    probe: Callable[[Any], int],
    *,
    min_resolved: int = 1,
) -> PreflightCheck:
    """Each answer-key entry's entities must actually exist in its index.

    An entry that resolves nothing will consume a full hunt window to
    discover it. Answering this with a term search per entry costs seconds
    and turns an hours-long discovery into a preflight line.
    """
    resolved = 0
    unresolved: list[str] = []
    for e in entries:
        try:
            hits = probe(e)
        except Exception as exc:  # noqa: BLE001 -- a probe failure is a finding
            hits = 0
            unresolved.append(f"{getattr(e, 'technique', '?')}:{type(exc).__name__}")
            continue
        if hits > 0:
            resolved += 1
        else:
            unresolved.append(str(getattr(e, "technique", "?")))
    return PreflightCheck(
        name="anchors_resolve",
        passed=resolved >= min_resolved,
        detail=(
            f"{resolved}/{len(entries)} entries resolve to present entities; "
            f"unresolved={unresolved[:8]}"
        ),
    )


def check_plant_roundtrip(
    plant: Callable[[], str],
    read_back: Callable[[str], int],
    cleanup: Callable[[str], None],
) -> PreflightCheck:
    """Plant one probe event, read it back, remove it.

    A silently failing write makes every cousin measurement void, and after
    the fact that is indistinguishable from a system that simply did not find
    them. Proving the path costs one event.
    """
    marker = ""
    try:
        marker = plant()
        found = read_back(marker)
        ok = found > 0
        detail = f"probe event {marker!r} read back: {found} hit(s)"
    except Exception as exc:  # noqa: BLE001
        ok = False
        detail = f"plant/read-back failed: {type(exc).__name__}: {exc}"
    finally:
        if marker:
            with contextlib.suppress(Exception):  # best effort
                cleanup(marker)
    return PreflightCheck(name="plant_roundtrip", passed=ok, detail=detail)


def check_resume_roundtrip(
    save: Callable[[dict[str, Any]], None],
    load: Callable[[], dict[str, Any] | None],
) -> PreflightCheck:
    """Write a checkpoint, reload it, confirm it survives.

    The existing checkpoint covers only the wide fit; the hunt loop has none.
    A resume that has never been exercised is not a resume -- and an
    unproven one means a death at entry 22 restarts at entry 1, re-planting
    cousins and leaving duplicates in the corpus.
    """
    probe = {"__preflight__": True, "entries_done": ["__probe__"], "planted": {}}
    try:
        save(probe)
        back = load() or {}
        ok = back.get("entries_done") == ["__probe__"]
        detail = f"checkpoint round-trip {'ok' if ok else 'MISMATCH'}: {str(back)[:120]}"
    except Exception as exc:  # noqa: BLE001
        ok = False
        detail = f"checkpoint round-trip failed: {type(exc).__name__}: {exc}"
    return PreflightCheck(name="resume_roundtrip", passed=ok, detail=detail)


def check_claim_guard(guard: Callable[[], bool]) -> PreflightCheck:
    """The zero-record-claim guard must be wired before the run, not after.

    K.4 published `chain_reach_recall 1.0` from a stage that received zero
    records. A guard that only runs at report time cannot prevent the hours
    spent producing an unpublishable number.
    """
    try:
        ok = bool(guard())
        detail = "zero-record-claim guard active" if ok else "guard NOT wired"
    except Exception as exc:  # noqa: BLE001
        ok = False
        detail = f"guard check failed: {type(exc).__name__}: {exc}"
    return PreflightCheck(name="claim_guard_wired", passed=ok, detail=detail)


def preflight(
    checks: list[PreflightCheck], calibration: SpanCalibration | None = None
) -> PreflightReport:
    return PreflightReport(checks=tuple(checks), calibration=calibration)


# ── per-entry progress, so a death is not a wasted run ─────────────────────


@dataclass
class EntryProgress:
    """Per-entry state, checkpointed and published INCREMENTALLY.

    The run doc is currently written only after every stage completes, so a
    death at hour 20 produces nothing. Writing each entry's result as it
    finishes means a run that dies at entry 19 still yields 19 measurements
    -- which is what makes a long run un-wastable.
    """

    entries_done: list[str] = field(default_factory=list)
    entries_not_attempted: list[str] = field(default_factory=list)
    planted_cousins: dict[str, str] = field(default_factory=dict)
    results: list[dict[str, Any]] = field(default_factory=list)

    def record(self, technique: str, result: dict[str, Any]) -> None:
        self.entries_done.append(technique)
        self.results.append({"technique": technique, **result})

    def already_done(self, technique: str) -> bool:
        return technique in self.entries_done

    def already_planted(self, technique: str) -> str | None:
        """A resumed run must not re-plant: duplicates pollute the corpus and
        inflate recovery."""
        return self.planted_cousins.get(technique)

    def to_dict(self) -> dict[str, Any]:
        located = sum(1 for r in self.results if r.get("located"))
        recovered = sum(1 for r in self.results if r.get("cousin_recovered"))
        planted = sum(1 for r in self.results if r.get("cousin_planted"))
        return {
            "n_done": len(self.entries_done),
            "n_not_attempted": len(self.entries_not_attempted),
            "entries_done": list(self.entries_done),
            "entries_not_attempted": list(self.entries_not_attempted),
            "n_located": located,
            "n_cousins_planted": planted,
            "n_cousins_recovered": recovered,
            "floor_recall": (round(located / len(self.results), 4) if self.results else None),
            "cousin_recall": (round(recovered / planted, 4) if planted else None),
            "results": list(self.results),
        }
