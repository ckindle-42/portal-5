"""bully.full_pipeline -- the assembled system, end to end.

**This module adds no capability.** Every part it calls already exists and was
proven in isolation. What has never existed is the assembly.

The evidence for why that matters, counted from the repository:

    ten run scripts, sixteen modules, never more than 7/16 used together

`bully_analyst_loop_run` uses 7. `bully_investigation_run_a6` uses 6 -- a
DIFFERENT 6. Each task in this arc built a module, proved it against a
hand-made fixture, then wired it into a new run script that dropped half of
the previous one. So the system exists as sixteen proven parts and zero
assembled wholes, and every "failure" diagnosed along the way was really the
same failure: the run was too small and too partial to tell us anything, so
the next thing to look at was always another mechanism.

And the scale, against 281,069,416 available records:

    INVESTIGATION_RUN_I6   213,311   (0.076%)
    REAL_TELEMETRY_RUN_T3   79,999
    ADAPTIVE_REACH_RUN_A6   67,545
    CORPUS_BED_RUN_C6       19,999
    six other runs           2,000 - 3,500

Six runs processed 2,000 records -- the same number as before the corpus was
ever connected. The four standing claims (Crogl ingests any source, Bully
finds same/similar, the corpus is the ground, the generator plants cousins in
it) are one sentence repeated four times: **proven in a proxy, never on the
real thing.**

So this is a wiring harness with a single job: run everything that exists,
over the whole corpus, and report what actually happens. It is deliberately
thin -- a stage list, a context object, and honest per-stage accounting -- so
that when a stage fails the failure is attributable to that stage rather than
to the harness.

Two disciplines are encoded here rather than left to prose:

  * **`fix_in_place`** -- a stage that fails records the failure, marks itself
    DEGRADED and the run continues. The rule this arc kept breaking is that a
    mid-run failure became a new module and a new task file, which reset the
    run to 2,000 records. A partial result over 281M records is worth more
    than a clean result over 2,000.
  * **`no_new_capability`** -- the stage registry names the module each stage
    calls. A stage whose module is not one of the sixteen already built is
    refused at registration, so "assemble" cannot quietly become "build".

Pure orchestration (COLD): no grading logic, no model calls, no I/O of its
own. Every stage is an injected callable.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

ALGORITHM_VERSION = "full-pipeline-v1"

# The sixteen modules proven in isolation during this arc. A stage may only be
# registered against one of these: the point of the assembly task is to run
# what exists, not to grow a seventeenth.
BUILT_MODULES: frozenset[str] = frozenset(
    {
        "field_roles",
        "correlation",
        "artifact_graph",
        "baseline",
        "discovery",
        "behavior_inference",
        "series_cousin",
        "pyramid",
        "investigation_pivot",
        "adaptive_scope",
        "telemetry_behavior",
        "corpus_bed",
        "analyst_loop",
        "unit_outcome",
        "loop_grader",
        "inject_plane",
        "run_preflight",
    }
)

STAGE_OK = "OK"
STAGE_DEGRADED = "DEGRADED"
STAGE_SKIPPED = "SKIPPED"


@dataclass
class RunContext:
    """Carries state between stages and records what each one produced.

    Deliberately a plain bag: the harness must not impose a data model on
    modules that already have their own, because a harness-owned schema is
    how an assembly quietly becomes a rewrite.
    """

    data: dict[str, Any] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)

    def put(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def count(self, key: str, n: int = 1) -> None:
        self.counters[key] = self.counters.get(key, 0) + n


@dataclass(frozen=True)
class Stage:
    name: str
    module: str
    run: Callable[[RunContext], Any]
    required: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        if self.module not in BUILT_MODULES:
            raise ValueError(
                f"stage {self.name!r} names module {self.module!r}, which is not one "
                f"of the {len(BUILT_MODULES)} already built. This task assembles what "
                "exists; a new module means a new task, not a new stage."
            )


@dataclass
class StageResult:
    name: str
    module: str
    status: str
    seconds: float
    produced: Any = None
    error: str | None = None
    traceback_head: str | None = None
    records_received: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.name,
            "module": self.module,
            "status": self.status,
            "seconds": round(self.seconds, 3),
            "records_received": self.records_received,
            "error": self.error,
            "traceback_head": self.traceback_head,
        }


@dataclass
class PipelineReport:
    stages: list[StageResult] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def modules_exercised(self) -> tuple[str, ...]:
        return tuple(sorted({s.module for s in self.stages if s.status == STAGE_OK}))

    @property
    def modules_missing(self) -> tuple[str, ...]:
        return tuple(sorted(BUILT_MODULES - set(self.modules_exercised)))

    @property
    def degraded(self) -> tuple[str, ...]:
        return tuple(s.name for s in self.stages if s.status == STAGE_DEGRADED)

    @property
    def integration_fraction(self) -> float:
        return len(self.modules_exercised) / len(BUILT_MODULES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "duration_seconds": round(self.finished_at - self.started_at, 2),
            "n_stages": len(self.stages),
            "modules_built": len(BUILT_MODULES),
            "modules_exercised": list(self.modules_exercised),
            "n_modules_exercised": len(self.modules_exercised),
            "modules_missing": list(self.modules_missing),
            "integration_fraction": round(self.integration_fraction, 4),
            "degraded_stages": list(self.degraded),
            "counters": dict(self.counters),
            "stages": [s.to_dict() for s in self.stages],
        }


def run_pipeline(
    stages: list[Stage],
    ctx: RunContext | None = None,
    *,
    fix_in_place: bool = True,
    on_stage: Callable[[StageResult], None] | None = None,
    records_of: Callable[[RunContext], int] | None = None,
) -> tuple[RunContext, PipelineReport]:
    """Execute every stage, recording what each produced and what it cost.

    With `fix_in_place`, a failing stage is recorded DEGRADED and the run
    continues -- because a partial result over the whole corpus tells us more
    than a clean result over 2,000 records, and because stopping is what turns
    a mid-run failure into another six-phase build task.

    A `required` stage that fails still stops the run: some failures (no
    corpus, no connector) make everything downstream meaningless, and
    continuing would manufacture numbers rather than findings.

    `records_of`, when given, is called against `ctx` immediately BEFORE each
    stage runs and its result recorded as that stage's `records_received`
    (K.2/K.3, TASK_BULLY_SCORER_FEED_V1): a stage completing in ~0s on a
    large run is a starvation signal that stage status alone cannot show --
    F.4 published `integration_fraction 1.0` with every stage OK while the
    analytical path received 63 records of 359,757 streamed. This makes that
    visible per stage instead of only inferable from timing.
    """
    ctx = ctx if ctx is not None else RunContext()
    report = PipelineReport(started_at=time.time())

    for stage in stages:
        received = records_of(ctx) if records_of else None
        t0 = time.time()
        try:
            produced = stage.run(ctx)
            result = StageResult(
                name=stage.name,
                module=stage.module,
                status=STAGE_OK,
                seconds=time.time() - t0,
                produced=produced,
                records_received=received,
            )
        except Exception as exc:  # noqa: BLE001 -- attributing failure is the job
            head = "".join(traceback.format_exc().splitlines(keepends=True)[-4:])
            result = StageResult(
                name=stage.name,
                module=stage.module,
                status=STAGE_DEGRADED,
                seconds=time.time() - t0,
                error=f"{type(exc).__name__}: {exc}",
                traceback_head=head,
                records_received=received,
            )
            if stage.required or not fix_in_place:
                report.stages.append(result)
                report.counters = dict(ctx.counters)
                report.finished_at = time.time()
                if on_stage:
                    on_stage(result)
                return ctx, report
        report.stages.append(result)
        if on_stage:
            on_stage(result)

    report.counters = dict(ctx.counters)
    report.finished_at = time.time()
    return ctx, report


# A stage receiving less than this fraction of the records the stream covered,
# while reporting OK, has been starved regardless of what its status says
# (K.3): F.4's analytical stages all reported OK at 63/359,757 = 0.018%.
MIN_STAGE_RECORDS_FRACTION = 0.01


def starvation_check(
    report: PipelineReport,
    *,
    stream_total: int,
    analytical_stages: tuple[str, ...],
    min_fraction: float = MIN_STAGE_RECORDS_FRACTION,
) -> dict[str, Any]:
    """Did any analytical stage run on a starved input while reporting OK?

    F.4's stage statuses were structurally incapable of showing this --
    all seventeen stages reported OK while the analytical path received one
    sourcetype of 325. `records_received` (this module) plus this check are
    what make a starved stage visible without having to eyeball a 0.0s
    timing column.
    """
    findings: list[dict[str, Any]] = []
    verdict = "PASS"
    by_name = {s.name: s for s in report.stages}
    for name in analytical_stages:
        stage = by_name.get(name)
        if stage is None or stage.status != STAGE_OK:
            continue
        received = stage.records_received or 0
        frac = (received / stream_total) if stream_total else None
        if frac is not None and frac < min_fraction:
            verdict = "FAIL"
            findings.append(
                {
                    "stage": name,
                    "records_received": received,
                    "stream_total": stream_total,
                    "fraction": round(frac, 6),
                    "reason": (
                        f"{name} received {received} of {stream_total} records "
                        f"({frac:.5f}<{min_fraction}) while reporting OK -- starved"
                    ),
                }
            )
    return {"verdict": verdict, "findings": findings, "min_fraction": min_fraction}


def zero_record_claim_guard(
    report: PipelineReport, claim_stage_names: tuple[str, ...]
) -> dict[str, Any]:
    """Which of `claim_stage_names` may NOT source a published claim.

    K.4 published `chain_reach_recall 1.0` from `investigate_anchors`
    while `records_received` for that stage's own inputs was 0 -- a claim
    computed from a stage that never actually ran against real data. A
    stage that reported OK with `records_received == 0` is disqualified: a
    caller building `ClaimEvidence` must null out (never fabricate) any
    field it would have sourced from a disqualified stage.
    """
    by_name = {s.name: s for s in report.stages}
    disqualified: list[str] = []
    for name in claim_stage_names:
        stage = by_name.get(name)
        if stage is None:
            continue
        if stage.status == STAGE_OK and (stage.records_received or 0) == 0:
            disqualified.append(name)
    return {"disqualified_stages": disqualified, "guard_active": True}


# ── reporting against the four standing claims ─────────────────────────────


@dataclass(frozen=True)
class ClaimEvidence:
    """Each of the four claims, answered with a number from THIS run.

    The claims have been restated identically for the whole arc because none
    was ever answered with corpus-scale evidence. Reporting them together, in
    the run's own output, is what makes "proven in a proxy" impossible to
    mistake for "proven".
    """

    crogl_sourcetypes_reviewed: int
    crogl_identity_coverage: float | None
    bully_chain_reach_recall: float | None
    bully_max_pivot_distance: int | None
    corpus_records_processed: int
    corpus_records_available: int
    generator_cousin_recall_at_distance: dict[str, float | None]
    # H.4 (TASK_BULLY_HUNT_SWEEP_V1): Crogl reported as COMPREHENSION, not
    # exposure. `crogl_sourcetypes_reviewed` (above) is "how many sourcetypes
    # this run's stream touched" -- exposure, published in K.4 as
    # `sourcetypes_reviewed: 325`, which reads as breadth achieved. The real
    # comprehension question is narrower: of the sources the SCORER actually
    # sampled, how many did the behavioural inference stage genuinely
    # profile? K.4's own numbers answer this at 5/245 = 0.020 -- a fact its
    # published `sourcetypes_reviewed: 325` obscured entirely. `None` when
    # the source stage is disqualified by `zero_record_claim_guard`.
    crogl_sources_profiled: int | None = None
    crogl_sources_sampled: int | None = None
    # Bully reported FROM THE SWEEP (H.2's widened locate-plant-hunt loop
    # across the whole answer key), not from K.4's single-entry proof. `None`
    # fields mean "the sweep has not run" or "disqualified by the zero-record
    # claim guard" -- never a fabricated 0.
    bully_entries_located: int | None = None
    bully_entries_attempted: int | None = None
    bully_cousins_planted: int | None = None
    bully_cousins_recovered: int | None = None

    @property
    def corpus_fraction(self) -> float | None:
        if not self.corpus_records_available:
            return None
        return self.corpus_records_processed / self.corpus_records_available

    @property
    def crogl_comprehension_fraction(self) -> float | None:
        if not self.crogl_sources_sampled:
            return None
        if self.crogl_sources_profiled is None:
            return None
        return self.crogl_sources_profiled / self.crogl_sources_sampled

    @property
    def bully_floor_recall(self) -> float | None:
        if not self.bully_entries_attempted:
            return None
        if self.bully_entries_located is None:
            return None
        return self.bully_entries_located / self.bully_entries_attempted

    @property
    def bully_cousin_recall(self) -> float | None:
        if not self.bully_cousins_planted:
            return None
        if self.bully_cousins_recovered is None:
            return None
        return self.bully_cousins_recovered / self.bully_cousins_planted

    def to_dict(self) -> dict[str, Any]:
        return {
            "crogl": {
                "sourcetypes_reviewed": self.crogl_sourcetypes_reviewed,
                "identity_coverage": self.crogl_identity_coverage,
                "sources_profiled": self.crogl_sources_profiled,
                "sources_sampled": self.crogl_sources_sampled,
                "comprehension_fraction": (
                    round(self.crogl_comprehension_fraction, 4)
                    if self.crogl_comprehension_fraction is not None
                    else None
                ),
                "claim": "ingests any source",
            },
            "bully": {
                "chain_reach_recall": self.bully_chain_reach_recall,
                "max_pivot_distance": self.bully_max_pivot_distance,
                "entries_located": self.bully_entries_located,
                "entries_attempted": self.bully_entries_attempted,
                "floor_recall": (
                    round(self.bully_floor_recall, 4)
                    if self.bully_floor_recall is not None
                    else None
                ),
                "cousins_planted": self.bully_cousins_planted,
                "cousins_recovered": self.bully_cousins_recovered,
                "cousin_recall": (
                    round(self.bully_cousin_recall, 4)
                    if self.bully_cousin_recall is not None
                    else None
                ),
                "claim": "finds same/similar on a real haystack",
            },
            "corpus": {
                "records_processed": self.corpus_records_processed,
                "records_available": self.corpus_records_available,
                "fraction": (round(self.corpus_fraction, 6) if self.corpus_fraction else None),
                "claim": "the real ground is actually used",
            },
            "generator": {
                "cousin_recall_at_distance": self.generator_cousin_recall_at_distance,
                "claim": "cousins of what is in the corpus, injected into it",
            },
        }


# A run touching less of the corpus than this is another proxy, however clean
# its numbers. Prior best was 0.076%.
MIN_CORPUS_FRACTION = 0.10

# The assembly is the point: a run exercising fewer modules than this has not
# tested the system, only another subset. Prior best was 7/16 = 0.44.
MIN_INTEGRATION_FRACTION = 0.80


def assembly_verdict(
    report: PipelineReport,
    evidence: ClaimEvidence,
    *,
    min_corpus_fraction: float = MIN_CORPUS_FRACTION,
    min_integration: float = MIN_INTEGRATION_FRACTION,
) -> dict[str, Any]:
    """Did this run actually test the assembled system on the real thing?

    Deliberately separate from whether the RESULTS are good. A run may
    legitimately find little; what it may not do is report findings from a
    partial assembly over a token sample as though they described the system.
    """
    reasons: list[str] = []
    verdict = "ASSEMBLED"

    if report.integration_fraction < min_integration:
        verdict = "PARTIAL_ASSEMBLY"
        reasons.append(
            f"integration_fraction_{report.integration_fraction:.2f}<{min_integration}: "
            f"only {len(report.modules_exercised)}/{len(BUILT_MODULES)} modules ran; "
            f"missing {list(report.modules_missing)}"
        )
    frac = evidence.corpus_fraction
    if frac is None or frac < min_corpus_fraction:
        verdict = "PROXY_SCALE" if verdict == "ASSEMBLED" else verdict
        reasons.append(
            f"corpus_fraction_{(frac or 0):.5f}<{min_corpus_fraction}: "
            f"{evidence.corpus_records_processed} of "
            f"{evidence.corpus_records_available} records -- this is another proxy"
        )
    if report.degraded:
        reasons.append(f"degraded_stages:{list(report.degraded)}")

    return {
        "verdict": verdict,
        "reasons": reasons,
        "integration_fraction": round(report.integration_fraction, 4),
        "corpus_fraction": round(frac, 6) if frac else None,
        "modules_exercised": list(report.modules_exercised),
        "modules_missing": list(report.modules_missing),
    }
