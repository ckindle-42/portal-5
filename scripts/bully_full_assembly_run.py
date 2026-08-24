#!/usr/bin/env python3
"""bully_full_assembly_run.py -- F.2: ONE run script that wires all sixteen.

TASK_BULLY_FULL_ASSEMBLY_V1. Ten run scripts existed before this one, never
more than 7/16 modules used together. This script is wiring only: every
stage below calls an existing, already-proven entry point (see the table in
`TASK_BULLY_FULL_ASSEMBLY_V1.md` F.2); nothing here is a new algorithm.
Where an existing script's private helper is the cleanest way to reach a
real live connector (`bully_corpus_hunt_run._live_corpus_range`,
`bully_investigation_run_a6._find_real_anchor_entity`), it is imported and
reused directly -- this arc's own convention (`bully_corpus_hunt_run.py`
already imports `bully_analyst_loop_run`/`bully_loop_milestone_run` this
way) rather than re-derived.

Registered against `full_pipeline.Stage`, which raises at construction if a
stage names a module outside the sixteen `BUILT_MODULES` -- so this script
cannot quietly grow a seventeenth module.

Any seam that does not line up is shimmed HERE, inline, noted in the stage's
`description` as a seam defect -- never "fixed properly" in the module
itself. That temptation is the exact pattern (build before assemble) this
task exists to break.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from portal.modules.security.core.bully import adaptive_scope as ascope  # noqa: E402
from portal.modules.security.core.bully import (
    analyst_loop,  # noqa: E402
    corpus_bed,  # noqa: E402
    correlation,  # noqa: E402
    cousin_inject,  # noqa: E402
    loop_grader,  # noqa: E402
    pyramid,  # noqa: E402
    scoreboard,  # noqa: E402
    series_cousin,  # noqa: E402
    signatures,  # noqa: E402
    unit_outcome,  # noqa: E402
)
from portal.modules.security.core.bully import artifact_graph as ag  # noqa: E402
from portal.modules.security.core.bully import baseline as bl  # noqa: E402
from portal.modules.security.core.bully import behavior_inference as bi  # noqa: E402
from portal.modules.security.core.bully import discovery as disc  # noqa: E402
from portal.modules.security.core.bully import field_roles as fr  # noqa: E402
from portal.modules.security.core.bully import full_pipeline as fp  # noqa: E402
from portal.modules.security.core.bully import inject_plane as ip  # noqa: E402
from portal.modules.security.core.bully import investigation_pivot as pivot  # noqa: E402
from portal.modules.security.core.bully import run_preflight as rpf  # noqa: E402
from portal.modules.security.core.bully import telemetry_behavior as tb  # noqa: E402
from portal.modules.security.core.bully.anchors import Anchor as LibraryAnchor  # noqa: E402
from portal.modules.security.core.bully.anchors import AnchorLibrary  # noqa: E402
from portal.modules.security.core.bully.bots_answer_key import BOTS_ANSWER_KEY  # noqa: E402
from portal.modules.security.core.bully.contracts import new_id  # noqa: E402

ALGORITHM_VERSION = "full-assembly-run-f2-v1"

# The declared (stage name, module) plan -- kept as a module-level constant,
# separate from the callables, so a static check (and F.2's seeded test) can
# assert coverage without executing a single stage or touching a live
# connector.
STAGE_PLAN: tuple[tuple[str, str], ...] = (
    ("resolve_indexes", "corpus_bed"),
    ("discover_index_range", "inject_plane"),
    ("stream_corpus_sample", "corpus_bed"),
    # H.2 (TASK_BULLY_HUNT_SWEEP_V1): moved AFTER the stream, not before it.
    # K.4's fast-proof-first ordering made sense when these stages ran a
    # single capped, entity-pivot investigation; the sweep loop below reads
    # each entry's own window completely and needs `wide_baseline` (set by
    # `stream_corpus_sample`) to score it, so it now reads the corpus rather
    # than running at `records_received: 0`.
    ("investigate_anchors", "investigation_pivot"),
    ("plant_and_measure_cousins", "adaptive_scope"),
    ("infer_field_roles", "field_roles"),
    ("classify_telemetry", "telemetry_behavior"),
    ("infer_universal_behaviors", "behavior_inference"),
    ("build_artifact_graph", "artifact_graph"),
    ("resolve_entities_and_timelines", "correlation"),
    ("fit_baseline", "baseline"),
    ("discover_and_cluster", "discovery"),
    ("series_and_level", "series_cousin"),
    ("level_match", "pyramid"),
    ("grade_to_loop_contract", "loop_grader"),
    ("resolve_unit_outcomes", "unit_outcome"),
    ("raise_and_verdict_concerns", "analyst_loop"),
)

# Every stage downstream of the corpus stream that reads `ctx.get("records")`
# -- the analytical path K.3's starvation_check watches. Derived from
# STAGE_PLAN rather than hardcoded twice: everything after `stream_corpus_
# sample`, which is where "records" is first populated.
ANALYTICAL_STAGES: tuple[str, ...] = tuple(
    name
    for name, _module in STAGE_PLAN[[n for n, _m in STAGE_PLAN].index("stream_corpus_sample") + 1 :]
)

# Checkpoint for `stream_corpus_sample` -- the one stage long enough (hours
# to days) that a kill/interruption must resume, not restart (F.4 finding).
# Small by construction: NormalBaseline's token vocabulary is bounded
# regardless of corpus size (bigrams over ~10 behaviour classes, a handful
# of buckets), so this file stays kilobytes, never gigabytes.
CHECKPOINT_PATH = Path("/tmp/bully_full_assembly_f4_checkpoint.json")
CHECKPOINT_INTERVAL_SECONDS = 120.0

# H.1's 10m-span calibration returned COMMIT (0.9h projected across 27
# entries); this is the default a caller gets without passing
# `--hunt-span-seconds` explicitly. `main()`'s preflight step is the one
# place this should actually be decided from a live calibration, not here.
DEFAULT_HUNT_SPAN_SECONDS = 600.0


class SampledWindowError(RuntimeError):
    """A hunt window read fewer records than the window actually contains.

    H2: a hunt reads its window completely, never a sample of it -- a rare
    planted cousin cannot survive being sampled out. Raising here (rather
    than silently truncating) is deliberate: over budget means narrow the
    span and re-calibrate, never quietly sample the window.
    """


def _serialize_baseline(baseline: bl.NormalBaseline) -> dict[str, Any]:
    return {
        "environment_id": baseline.environment_id,
        "token_counts": {level: dict(counter) for level, counter in baseline._token_counts.items()},
        "fitted_units": dict(baseline._fitted_units),
    }


def _deserialize_baseline(data: dict[str, Any]) -> bl.NormalBaseline:
    from collections import Counter

    baseline = bl.NormalBaseline(environment_id=data.get("environment_id", "full_assembly"))
    for level, counts in (data.get("token_counts") or {}).items():
        baseline._token_counts[level] = Counter(counts)
    for level, n in (data.get("fitted_units") or {}).items():
        baseline._fitted_units[level] = n
    return baseline


def _load_checkpoint() -> dict[str, Any] | None:
    if not CHECKPOINT_PATH.exists():
        return None
    try:
        return json.loads(CHECKPOINT_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _save_checkpoint(data: dict[str, Any]) -> None:
    tmp = CHECKPOINT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(CHECKPOINT_PATH)


# H.3 (TASK_BULLY_HUNT_SWEEP_V1): the hunt loop's own checkpoint state,
# carried in the SAME file as `stream_corpus_sample`'s (merge, not a second
# file) -- prefixed `hunt_*` so the two stages' keys never collide. Before
# H.3 the hunt loop had no checkpoint at all: a death at entry 22 would
# restart at entry 1 and RE-PLANT cousins already shipped, polluting the
# corpus with duplicates (this is what H.1's `resume_roundtrip` preflight
# check and `EntryProgress.already_planted` exist to prevent in the first
# place -- this is what makes that guarantee durable across a process
# restart, not just within one).
#
# Deliberately NOT deleted when the sweep finishes (unlike the stream's own
# checkpoint): `planted_cousins` is the only durable record of which cousin
# ids were shipped into the shared corpus, needed for the documented
# `evidence_origin=corpus:cousin:* | delete` rollback (residual risk in
# TASK_BULLY_HUNT_SWEEP_V1) even after a successful run.
def _save_hunt_checkpoint(progress: rpf.EntryProgress, *, span_seconds: float) -> None:
    existing = _load_checkpoint() or {}
    existing.update(
        {
            "hunt_entries_done": list(progress.entries_done),
            "hunt_planted_cousins": dict(progress.planted_cousins),
            "hunt_results": list(progress.results),
            "hunt_span_seconds": span_seconds,
        }
    )
    _save_checkpoint(existing)


def _load_hunt_checkpoint() -> tuple[rpf.EntryProgress, float] | None:
    data = _load_checkpoint()
    if not data or "hunt_entries_done" not in data:
        return None
    progress = rpf.EntryProgress(
        entries_done=list(data.get("hunt_entries_done", [])),
        planted_cousins=dict(data.get("hunt_planted_cousins", {})),
        results=list(data.get("hunt_results", [])),
    )
    span_seconds = float(data.get("hunt_span_seconds", DEFAULT_HUNT_SPAN_SECONDS))
    return progress, span_seconds


def _action_of(r: dict[str, Any]) -> str | None:
    return tb._dig(r, *tb._FIELD_EVENTCODE) or tb._dig(r, "event_type")


def _entity_of(r: dict[str, Any]) -> list[str]:
    return [str(v) for _k, v in ip._extract_pivot_entities(r) if v]


def _time_of(r: dict[str, Any]) -> float | None:
    ts = r.get("_time")
    return ts if isinstance(ts, (int, float)) else None


def _sourcetype_of(r: dict[str, Any]) -> str:
    return str(r.get("sourcetype") or "")


def _list_sourcetypes(connector: Any, index: str) -> list[tuple[str, int]]:
    """Every distinct sourcetype this index actually carries, via Splunk's
    `metadata` command -- bucket-metadata only, not an event scan (verified
    live: <0.1s on 3 of the 4 corpus indexes, ~6s on the largest)."""
    from portal.modules.security.core.bully.connectors import QueryIntent

    result = connector.read(
        QueryIntent(
            "list sourcetypes for stratified sample",
            seed={"spl": f"| metadata type=sourcetypes index={index}"},
            limit=1000,
        )
    )
    out: list[tuple[str, int]] = []
    for record in result.records:
        fields = record.get("fields", {}) if isinstance(record, dict) else {}
        st = fields.get("sourcetype")
        if not st:
            continue
        try:
            count = int(fields.get("totalCount") or 0)
        except (TypeError, ValueError):
            count = 0
        out.append((str(st), count))
    return out


def _window_count(connector: Any, index: str, start: float, end: float) -> int:
    """Exact event count for one time-bounded window, via `| stats count`
    scoped by the same `earliest`/`latest` the actual read will use -- the
    reference the read is checked against for H2's completeness guarantee."""
    from portal.modules.security.core.bully.connectors import QueryIntent

    result = connector.read(
        QueryIntent(
            "exact count for hunt window completeness check",
            seed={"spl": f"search index={index} | stats count"},
            start=start,
            end=end,
            limit=1,
        )
    )
    if not result.records:
        return 0
    first = result.records[0]
    fields = first.get("fields", {}) if isinstance(first, dict) else {}
    raw = fields.get("count") if isinstance(fields, dict) else None
    if raw is None and isinstance(first, dict):
        raw = first.get("count")
    try:
        return int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        return 0


# A hunt window this large would mean the span calibration (H.1) was never
# run or was ignored -- a hard ceiling, not a tuning knob, so a caller
# cannot quietly widen it away from the calibrated span.
MAX_WINDOW_READ_RECORDS = 500_000


def _read_window_completely(
    connector: Any, index: str, start: float, end: float
) -> list[dict[str, Any]]:
    """Read every record in `[start, end)` for `index` -- no `dedup`, no
    per-sourcetype cap (H2). The window's true count is fetched first
    (`_window_count`) and compared against what the actual read returns;
    a mismatch means the read was truncated -- sampled, not complete -- and
    `SampledWindowError` is raised rather than silently proceeding on a
    partial window. A rare planted cousin cannot survive a sampled window,
    which is the entire reason this function exists instead of reusing
    `investigation_pivot.investigate`'s capped, entity-pivot search."""
    from portal.modules.security.core.bully.connectors import QueryIntent

    true_count = _window_count(connector, index, start, end)
    result = connector.read(
        QueryIntent(
            f"complete window read {index} [{start},{end})",
            seed={"spl": f"search index={index}"},
            start=start,
            end=end,
            limit=max(true_count, 1) if true_count else MAX_WINDOW_READ_RECORDS,
        )
    )
    schemas: set[str] = set()
    rows: list[dict[str, Any]] = []
    for record in result.records:
        tagged = ip._tag_captured_record(record, index=index, schemas=schemas)
        if tagged is not None:
            rows.append(tagged)
    if true_count and len(rows) < true_count:
        raise SampledWindowError(
            f"{index} window [{start},{end}) read {len(rows)} of {true_count} known "
            "records -- sampled, not complete; narrow the span and re-calibrate"
        )
    return rows


def build_stages(  # noqa: C901, PLR0915
    *,
    max_records: int | None,
    batch_size: int,
    per_sourcetype_cap: int,
    dry_run_cousins: bool,
    hunt_span_seconds: float = DEFAULT_HUNT_SPAN_SECONDS,
    hunt_time_budget_seconds: float | None = None,
    hunt_progress: rpf.EntryProgress | None = None,
    on_entry_done: Callable[[rpf.EntryProgress, dict[str, Any]], None] | None = None,
) -> list[fp.Stage]:
    """Build the real stage list. Every `run` callable below reads its
    inputs from `ctx` (produced by an earlier stage) and writes its outputs
    back to `ctx` -- the harness owns no schema of its own (F.1)."""

    def resolve_indexes(ctx: fp.RunContext) -> tuple[str, ...]:
        indexes = corpus_bed.resolve_indexes()
        ctx.put("indexes", indexes)
        return indexes

    def discover_index_range(ctx: fp.RunContext) -> dict[str, Any]:
        from portal.modules.security.core.bully.live_connect import lab_splunk_connector

        indexes = ctx.get("indexes", ())
        ranges: dict[str, Any] = {}
        earliest_all: list[float] = []
        latest_all: list[float] = []
        for index in indexes:
            connector = lab_splunk_connector(index=index)
            rng = ip.discover_index_range(connector, index)
            ranges[index] = rng
            if rng.earliest is not None:
                earliest_all.append(rng.earliest)
            if rng.latest is not None:
                latest_all.append(rng.latest)
        ctx.put("index_ranges", ranges)
        if earliest_all and latest_all:
            ctx.put("corpus_earliest", min(earliest_all))
            ctx.put("corpus_latest", max(latest_all))
        return {"n_indexes": len(ranges)}

    def stream_corpus_sample(ctx: fp.RunContext) -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915
        """Fit WIDE, score NARROW (corpus_bed's own doctrine, C.6) -- STRATIFIED
        by sourcetype, not sequential by volume (operator finding, second F.4
        redesign): `NormalBaseline` fits over a small, BOUNDED vocabulary
        (behaviour-class bigrams, entity-role tags, size/span buckets, edge-
        kind mixes -- a few hundred distinct tokens total). A sequential walk
        through one index's raw record volume before moving to the next
        cannot guarantee that vocabulary sees every real event TYPE the
        corpus carries, and pays for redundant volume within a dominant
        sourcetype instead. This pulls up to `per_sourcetype_cap` records
        from EVERY distinct sourcetype in EVERY index (`_list_sourcetypes`,
        a fast bucket-metadata query, not an event scan), so the fit
        converges on genuine event-type diversity in minutes to low hours
        rather than days of largely repetitive volume.

        This deliberately trades away F.4's literal `corpus_fraction >= 0.10`
        floor (raw records processed / records available) for something the
        raw-volume metric never measured: sourcetype/event-type COVERAGE.
        `assembly_verdict` (F.1) will grade this `PROXY_SCALE` on the
        corpus_fraction number alone, and that is reported as the headline,
        not hidden -- `n_sourcetypes_covered`/`n_sourcetypes_available` is
        published alongside it as the metric this run actually optimized
        for, and the trade-off is on the record in the published doc.

        Interruption is caught HERE, not left to propagate (first F.4
        finding): a `required=True` stage that raises stops the WHOLE
        pipeline per F.1's fix-in-place contract. RESUMABLE (second F.4
        finding): progress checkpoints to `CHECKPOINT_PATH` every
        `CHECKPOINT_INTERVAL_SECONDS`, now at (index, sourcetype)
        granularity, and a subsequent run resumes from the next
        not-yet-covered sourcetype instead of restarting."""
        indexes = list(ctx.get("indexes", ()))
        checkpoint = _load_checkpoint()
        resuming = bool(checkpoint) and checkpoint.get("all_indexes") == indexes
        if resuming:
            baseline = _deserialize_baseline(checkpoint)
            covered: set[tuple[str, str]] = {
                (pair[0], pair[1]) for pair in checkpoint.get("covered", [])
            }
            processed_before = int(checkpoint.get("records_processed", 0))
        else:
            baseline = bl.NormalBaseline(environment_id="full_assembly")
            covered = set()
            processed_before = 0
        for _ in range(processed_before):
            ctx.count("records_processed")

        from portal.modules.security.core.bully import score_sample as ss

        sample = ss.StratifiedSample()
        interrupted_reason: str | None = None
        last_checkpoint_at = time.time()
        connectors: dict[str, Any] = {}

        def _connector(index: str) -> Any:
            if index not in connectors:
                from portal.modules.security.core.bully.live_connect import lab_splunk_connector

                connectors[index] = lab_splunk_connector(index=index)
            return connectors[index]

        def _fit_batch(rows: list[dict[str, Any]]) -> None:
            if not rows:
                return
            graph = ag.build_graph(rows, source_id="full_assembly")
            units = ag.enumerate_units(graph)
            baseline.fit(units)

        def _checkpoint() -> None:
            _save_checkpoint(
                {
                    "all_indexes": indexes,
                    "covered": [list(pair) for pair in covered],
                    "records_processed": ctx.counters.get("records_processed", 0),
                    **_serialize_baseline(baseline),
                }
            )

        n_sourcetypes_available = 0
        current: tuple[str, str] | None = None
        try:
            for index in indexes:
                sourcetypes = _list_sourcetypes(_connector(index), index)
                n_sourcetypes_available += len(sourcetypes)
                for sourcetype, _count in sourcetypes:
                    current = (index, sourcetype)
                    if current in covered:
                        continue
                    from portal.modules.security.core.bully.connectors import QueryIntent

                    result = _connector(index).read(
                        QueryIntent(
                            f"stratified sample {index}/{sourcetype}",
                            seed={
                                "spl": (
                                    f'search index={index} sourcetype="{sourcetype}" '
                                    f"| head {per_sourcetype_cap}"
                                )
                            },
                            limit=per_sourcetype_cap,
                        )
                    )
                    schemas: set[str] = set()
                    batch: list[dict[str, Any]] = []
                    for record in result.records:
                        tagged = ip._tag_captured_record(record, index=index, schemas=schemas)
                        if tagged is not None:
                            batch.append(tagged)
                    for _ in batch:
                        ctx.count("records_processed")
                    if batch:
                        _fit_batch(batch)
                        sample.extend(batch, sourcetype_of=_sourcetype_of)
                    covered.add(current)
                    current = None
                    if (
                        max_records is not None
                        and ctx.counters.get("records_processed", 0) >= max_records
                    ):
                        raise StopIteration  # noqa: TRY301 -- deliberate early-exit, not an error
                    if time.time() - last_checkpoint_at >= CHECKPOINT_INTERVAL_SECONDS:
                        _checkpoint()
                        last_checkpoint_at = time.time()
        except StopIteration:
            pass
        except Exception as exc:  # noqa: BLE001 -- absorb here so the run continues
            interrupted_reason = f"{type(exc).__name__}: {exc}"
            try:
                _checkpoint()
            except Exception:  # noqa: BLE001 -- best-effort; never mask the interruption
                pass

        finished_all = len(covered) >= n_sourcetypes_available and interrupted_reason is None
        if finished_all and CHECKPOINT_PATH.exists():
            CHECKPOINT_PATH.unlink(missing_ok=True)

        ctx.put("records", sample.records())
        ctx.put("wide_baseline", baseline)
        sample_report = sample.report()
        verdict = ss.scorer_input_verdict(sample_report, len(covered))
        result: dict[str, Any] = {
            "n_records_wide_fit": ctx.counters.get("records_processed", 0),
            "wide_fitted_units": baseline.fitted_units,
            "resumed_from_checkpoint": resuming,
            "n_sourcetypes_covered": len(covered),
            "n_sourcetypes_available": n_sourcetypes_available,
            "sample_report": sample_report,
            "scorer_input_verdict": verdict,
            "coverage_note": (
                "this run optimizes sourcetype/event-type coverage, not raw corpus "
                "volume -- corpus_fraction will read low against F.4's literal 0.10 "
                "floor by design (operator decision); see stage docstring"
            ),
        }
        if interrupted_reason:
            result["seam_defect"] = (
                f"corpus stream interrupted, continuing (checkpoint saved for "
                f"resume): {interrupted_reason}"
            )
        return result

    def infer_field_roles(ctx: fp.RunContext) -> dict[str, Any]:
        records = ctx.get("records", [])
        role_map = fr.infer_field_roles(records, source_id="full_assembly")
        ctx.put("role_map", role_map)
        return {
            "extraction_valid": role_map.extraction_valid,
            "n_fields": len(role_map.profiles) if role_map.extraction_valid else 0,
        }

    def classify_telemetry(ctx: fp.RunContext) -> dict[str, Any]:
        records = ctx.get("records", [])
        coverage_input = [(r, _sourcetype_of(r)) for r in records]
        coverage = tb.coverage_report(coverage_input)
        ctx.put("coverage", coverage)
        return coverage.to_dict() if hasattr(coverage, "to_dict") else {}

    def infer_universal_behaviors(ctx: fp.RunContext) -> dict[str, Any]:
        records = ctx.get("records", [])
        profiles = bi.profile_actions(
            records,
            action_of=_action_of,
            entity_of=_entity_of,
            time_of=_time_of,
            sourcetype_of=_sourcetype_of,
        )
        behaviors = bi.infer_behaviors(profiles)
        report = bi.inference_report(profiles, behaviors)
        ctx.put("behavior_profiles", profiles)
        ctx.put("inferred_behaviors", behaviors)
        return report

    def build_artifact_graph(ctx: fp.RunContext) -> dict[str, Any]:
        records = ctx.get("records", [])
        role_map = ctx.get("role_map")
        graph = ag.build_graph(records, source_id="full_assembly", role_map=role_map)
        units = ag.enumerate_units(graph)
        ctx.put("graph", graph)
        ctx.put("units", units)
        return {"n_artifacts": len(graph.artifacts), "n_units": len(units)}

    def resolve_entities_and_timelines(ctx: fp.RunContext) -> dict[str, Any]:
        # `graph.artifacts` is a dict keyed by artifact_id -- iterating it
        # directly yields the KEYS (strings), not the Artifact values.
        graph = ctx.get("graph")
        artifacts = list(graph.artifacts.values()) if graph else []
        observations = []
        for artifact in artifacts:
            for entity in artifact.entities:
                observations.append(
                    correlation.IdentifierObservation(
                        value=entity,
                        field_path="entities",
                        source_id=artifact.source_id,
                        artifact_id=artifact.artifact_id,
                    )
                )
        entities, value_to_id = correlation.resolve_entities(observations)
        timelines = correlation.assemble_timelines(
            [a.__dict__ for a in artifacts],
            entities,
            value_to_id,
            artifact_entity_values=lambda a: list(a.get("entities") or ()),
            artifact_time=lambda a: a.get("timestamp"),
            artifact_id=lambda a: a.get("artifact_id", ""),
            artifact_source=lambda a: a.get("source_id", ""),
        )
        ctx.put("entities", entities)
        ctx.put("timelines", timelines)
        return {"n_entities": len(entities), "n_timelines": len(timelines)}

    def fit_baseline(ctx: fp.RunContext) -> dict[str, Any]:
        # The WIDE fit already happened incrementally across the whole
        # streamed corpus in `stream_corpus_sample` -- fitting again here
        # from only the last batch would throw away exactly the "fit wide"
        # discipline this run exists to prove. This stage's job is to also
        # fold in the last batch's own units (already inside the wide fit
        # only if it landed on a batch boundary) so `discover_and_cluster`
        # always scores narrow against a baseline that has seen its own
        # scoring units at least once.
        baseline = ctx.get("wide_baseline") or bl.NormalBaseline(environment_id="full_assembly")
        units = ctx.get("units", [])
        if units:
            baseline.fit(units)
        ctx.put("baseline", baseline)
        return {"fitted_units": baseline.fitted_units}

    def discover_and_cluster(ctx: fp.RunContext) -> dict[str, Any]:
        units = ctx.get("units", [])
        baseline = ctx.get("baseline")
        discoveries, report = disc.discover(units, baseline)
        clusters = disc.find_cousin_clusters(discoveries)
        ctx.put("discoveries", discoveries)
        ctx.put("cousin_clusters", clusters)
        return {**report, "n_clusters": len(clusters)}

    def series_and_level(ctx: fp.RunContext) -> dict[str, Any]:
        timelines = ctx.get("timelines", [])
        known_library: list[series_cousin.BehaviouralSeries] = []
        observed_series = []
        for timeline in timelines:
            logs = getattr(timeline, "events", None) or []
            series = series_cousin.series_from_logs(
                f"series-{getattr(timeline, 'entity_id', new_id('e'))}",
                logs,
                action_of=_action_of,
                sourcetype_of=_sourcetype_of,
            )
            observed_series.append(series)
        idf = series_cousin.build_idf(known_library)
        decisions = [
            series_cousin.decide_cousin(s, known_library, idf=idf) for s in observed_series
        ]
        ctx.put("observed_series", observed_series)
        ctx.put("series_decisions", decisions)
        return {"n_series": len(observed_series)}

    def level_match(ctx: fp.RunContext) -> dict[str, Any]:
        # `cluster.shared_shape` already carries behavioural CLASS tokens
        # (telemetry_behavior's alphabet, e.g. "auth"/"escalate"), not raw
        # verbs -- so each feature is built directly at L3_BEHAVIOR rather
        # than through `level_feature`, which re-derives the class from a
        # raw verb via `classify_behavior` and would double-classify an
        # already-classified token.
        clusters = ctx.get("cousin_clusters", [])
        matches = []
        for cluster in clusters:
            subject_features = [
                pyramid.LeveledFeature(
                    token=token, role="ACTION", level=pyramid.L3_BEHAVIOR, behavior_class=token
                )
                for token in cluster.shared_shape
            ]
            matches.append(pyramid.match_level(subject_features, subject_features))
        ctx.put("level_matches", matches)
        return {"n_matches": len(matches)}

    def grade_to_loop_contract(ctx: fp.RunContext) -> dict[str, Any]:
        observed_series = ctx.get("observed_series", [])
        units = ctx.get("units", [])
        if not observed_series or not units:
            return {"assessments": 0, "seam_defect": "no observed series or units to grade"}
        assessments = []
        for series, unit in zip(observed_series, units, strict=False):
            telemetry_view = {
                "action_sequence": list(unit.vocabulary),
                "event_graph": dict(unit.structural_signature),
                "telemetry_shape": {"edge_kinds": list(unit.edge_kinds)},
                "context_topology": {"target_host": unit.entities[0] if unit.entities else None},
            }
            signature = signatures.build_signature({"target_host": None}, telemetry_view)
            assessments.append(
                loop_grader.build_cousin_assessment_from_series(signature, series, [])
            )
        ctx.put("cousin_assessments", assessments)
        return {"assessments": len(assessments)}

    def resolve_unit_outcomes_stage(ctx: fp.RunContext) -> dict[str, Any]:
        units = ctx.get("units", [])
        baseline = ctx.get("baseline")
        library_anchors = ctx.get("library_anchors", [])
        outcomes = unit_outcome.resolve_unit_outcomes(units, library_anchors, baseline)
        ctx.put("unit_outcomes", outcomes)
        return {
            "n_outcomes": len(outcomes),
            "by_outcome": {
                o: sum(1 for u in outcomes if u.outcome == o) for o in {u.outcome for u in outcomes}
            },
        }

    def _anchor_for(entry: Any, ctx: fp.RunContext) -> pivot.Anchor:
        index_ranges = ctx.get("index_ranges", {})
        rng = index_ranges.get(entry.dataset)
        at = rng.earliest if rng and rng.earliest is not None else time.time()
        return pivot.Anchor(
            anchor_id=f"a-assembly-{entry.technique}",
            at=at,
            entity=entry.entities[0],
            entity_kind="host",
            sourcetype=entry.sourcetypes[0] if entry.sourcetypes else "",
            why=f"answer_key:{entry.technique}",
            index=entry.dataset,
        )

    def _hunt_entry(
        entry: Any, ctx: fp.RunContext, *, span_seconds: float, progress: rpf.EntryProgress
    ) -> dict[str, Any]:
        """One full turn of the intact locate-plant-hunt loop (H1: never
        split into a floor pass and a cousin pass) for a single answer-key
        entry: read this entry's own window COMPLETELY (H2), locate the
        documented activity in it, and -- only if located -- plant a
        cousin derived from what was actually found and re-hunt the SAME
        window to measure recovery. A resumed run never re-plants
        (`progress.already_planted`): `corpus_bed.plan_cousins` is a pure
        function of (entry, window), so the cousin spec is reproduced
        deterministically to measure recovery without re-shipping it."""
        from portal.modules.security.core.bully.live_connect import lab_splunk_connector

        t0 = time.time()
        anchor = _anchor_for(entry, ctx)
        half = span_seconds / 2.0
        corpus_earliest = ctx.get("corpus_earliest")
        corpus_latest = ctx.get("corpus_latest")
        start = anchor.at - half
        end = anchor.at + half
        if corpus_earliest is not None:
            start = max(start, corpus_earliest)
        if corpus_latest is not None:
            end = min(end, corpus_latest)
        if end <= start:
            end = start + span_seconds

        connector = lab_splunk_connector(index=entry.dataset)
        records = _read_window_completely(connector, entry.dataset, start, end)

        entities_seen = {v for r in records for _k, v in ip._extract_pivot_entities(r) if v}
        located = bool(records) and anchor.entity in entities_seen

        graph = ag.build_graph(records, source_id="hunt_sweep") if records else None
        units = ag.enumerate_units(graph) if graph is not None else []

        result: dict[str, Any] = {
            "technique": entry.technique,
            "dataset": entry.dataset,
            "located": located,
            "cousin_planted": False,
            "cousin_id": None,
            "cousin_recovered": None,
            "distance": None,
            "records_read": len(records),
            "units": len(units),
            "seconds": round(time.time() - t0, 2),
        }
        if not located:
            return result

        already_planted_id = progress.already_planted(entry.technique)
        sourcetypes = tuple(sorted({_sourcetype_of(r) for r in records}))
        cousins = corpus_bed.plan_cousins(
            [entry],
            corpus_earliest=start,
            corpus_latest=end,
            corpus_sourcetypes=sourcetypes,
            per_technique=1,
        )
        cousin = cousins[0] if cousins else None
        if cousin is None:
            result["seconds"] = round(time.time() - t0, 2)
            return result

        if already_planted_id is None:
            inject_reports = cousin_inject.inject_cousins(
                cousins,
                index=entry.dataset,
                corpus_earliest=start,
                corpus_latest=end,
                dry_run=dry_run_cousins,
            )
            progress.planted_cousins[entry.technique] = cousin.cousin_id
            if not dry_run_cousins and any(r.ok for r in inject_reports):
                time.sleep(5.0)  # let HEC-shipped events land before recovery capture

        recovery_records = _read_window_completely(connector, entry.dataset, start, end)
        reached = {v for r in recovery_records for _k, v in ip._extract_pivot_entities(r) if v}
        recovery = ascope.distance_recovery(
            [(cousin.anchor_entity, cousin.planted_distance)], reached
        )
        recovered = bool(recovery.by_distance.get(cousin.planted_distance, {}).get("reached"))
        result.update(
            cousin_planted=True,
            cousin_id=cousin.cousin_id,
            cousin_recovered=recovered,
            distance=cousin.planted_distance,
            seconds=round(time.time() - t0, 2),
        )
        return result

    def investigate_anchors(ctx: fp.RunContext) -> dict[str, Any]:
        """H2 (TASK_BULLY_HUNT_SWEEP_V1): sweeps EVERY in-scope answer-key
        entry with the intact locate-plant-hunt loop, widened from K.4's
        proof that deliberately stopped at the first hit. The loop itself
        does not split (H1): `_hunt_entry` locates, plants (only if
        located), and re-hunts in one call per entry, before this stage
        moves to the next entry. `plant_and_measure_cousins` below is a
        reporting seam, not a second pass over the corpus -- `STAGE_PLAN`
        names two stages, so this stage populates `ctx["entry_progress"]`
        and the other stage re-surfaces its cousin-facing numbers from the
        SAME sweep run here; there is exactly one loop over the corpus."""
        indexes = ctx.get("indexes", ())
        candidates = [e for e in BOTS_ANSWER_KEY if e.dataset in indexes and e.entities]
        span_seconds = hunt_span_seconds
        if hunt_progress is not None:
            # A caller that hands in an explicit progress object (tests,
            # or a caller wiring its own resume) always wins over disk.
            progress = hunt_progress
        else:
            # H.3: a process restart resumes from CHECKPOINT_PATH's own
            # `hunt_*` keys, not from entry 1 -- the failure H.1's
            # `resume_roundtrip` preflight check exists to catch before a
            # long run ever starts.
            loaded = _load_hunt_checkpoint()
            if loaded is not None:
                progress, span_seconds = loaded
            else:
                progress = rpf.EntryProgress()
        time_budget = hunt_time_budget_seconds
        ctx.put("entry_progress", progress)
        started = time.time()
        for entry in candidates:
            if progress.already_done(entry.technique):
                continue
            if time_budget is not None and (time.time() - started) >= time_budget:
                # H5: a time budget caps entries ATTEMPTED, never the read
                # within one -- checked only BETWEEN entries, never mid-read.
                continue
            result = _hunt_entry(entry, ctx, span_seconds=span_seconds, progress=progress)
            progress.record(entry.technique, result)
            # H.3: checkpoint AND publish after every entry -- a death at
            # entry 19 must yield 19 measurements, not zero (H4).
            _save_hunt_checkpoint(progress, span_seconds=span_seconds)
            if on_entry_done is not None:
                on_entry_done(progress, result)
        progress.entries_not_attempted = [
            e.technique for e in candidates if not progress.already_done(e.technique)
        ]
        n_located = sum(1 for r in progress.results if r.get("located"))
        return {
            "n_entries_in_scope": len(candidates),
            "n_entries_attempted": len(progress.entries_done),
            "n_entries_not_attempted": len(progress.entries_not_attempted),
            "n_located": n_located,
            "floor_recall": (
                round(n_located / len(progress.results), 4) if progress.results else None
            ),
            "span_seconds": span_seconds,
        }

    def plant_and_measure_cousins(ctx: fp.RunContext) -> dict[str, Any]:
        """The cousin/recovery-facing view of the SAME sweep
        `investigate_anchors` just ran -- see that stage's docstring for
        why this is not a second pass over the corpus. Reads
        `ctx["entry_progress"]`, already fully populated."""
        progress = ctx.get("entry_progress")
        if progress is None:
            return {
                "n_planted": 0,
                "seam_defect": "investigate_anchors did not populate entry_progress",
            }
        d = progress.to_dict()
        by_distance: dict[int, dict[str, int]] = {}
        for r in progress.results:
            if not r.get("cousin_planted"):
                continue
            dist = r.get("distance") or 0
            slot = by_distance.setdefault(dist, {"total": 0, "reached": 0})
            slot["total"] += 1
            if r.get("cousin_recovered"):
                slot["reached"] += 1
        recovery = ascope.DistanceRecovery(by_distance=by_distance)
        ctx.put("distance_recovery", recovery)
        return {
            "n_planted": d["n_cousins_planted"],
            "n_recovered": d["n_cousins_recovered"],
            "cousin_recall": d["cousin_recall"],
            "dry_run": dry_run_cousins,
            **recovery.to_dict(),
        }

    def raise_and_verdict_concerns(ctx: fp.RunContext) -> dict[str, Any]:
        outcomes = ctx.get("unit_outcomes", [])
        concerns = []
        for outcome in outcomes:
            concern = analyst_loop.raise_concern(
                assessment_id=new_id("assembly"),
                entity_id=(outcome.unit.entities[0] if outcome.unit.entities else "unknown"),
                relationship=outcome.outcome,
                should_escalate=outcome.outcome in unit_outcome.CONCERN_OUTCOMES,
            )
            if concern is not None:
                concerns.append(concern)
        ctx.put("concerns", concerns)
        return {"n_concerns": len(concerns)}

    stages = [
        fp.Stage("resolve_indexes", "corpus_bed", resolve_indexes, required=True),
        fp.Stage("discover_index_range", "inject_plane", discover_index_range, required=True),
        # Fast proof first: targeted, entity/time-scoped queries against
        # known answer-key anchors, not a corpus walk -- see STAGE_PLAN.
        fp.Stage("investigate_anchors", "investigation_pivot", investigate_anchors),
        fp.Stage("plant_and_measure_cousins", "adaptive_scope", plant_and_measure_cousins),
        # NOT required (F.4 finding): this stage internally absorbs its own
        # interruption and always returns a real, if partial, result -- see
        # its docstring. Marking it required would still abort the whole
        # 16-stage run on any OTHER unexpected exception here.
        fp.Stage("stream_corpus_sample", "corpus_bed", stream_corpus_sample),
        fp.Stage("infer_field_roles", "field_roles", infer_field_roles),
        fp.Stage("classify_telemetry", "telemetry_behavior", classify_telemetry),
        fp.Stage("infer_universal_behaviors", "behavior_inference", infer_universal_behaviors),
        fp.Stage("build_artifact_graph", "artifact_graph", build_artifact_graph),
        fp.Stage("resolve_entities_and_timelines", "correlation", resolve_entities_and_timelines),
        fp.Stage("fit_baseline", "baseline", fit_baseline),
        fp.Stage("discover_and_cluster", "discovery", discover_and_cluster),
        fp.Stage("series_and_level", "series_cousin", series_and_level),
        fp.Stage("level_match", "pyramid", level_match),
        fp.Stage("grade_to_loop_contract", "loop_grader", grade_to_loop_contract),
        fp.Stage("resolve_unit_outcomes", "unit_outcome", resolve_unit_outcomes_stage),
        fp.Stage("raise_and_verdict_concerns", "analyst_loop", raise_and_verdict_concerns),
    ]
    _ = (LibraryAnchor, AnchorLibrary)  # reserved for cousin write-back seam
    return stages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="docs")
    parser.add_argument("--doc-stem", default="BULLY_FULL_ASSEMBLY_RUN_F4_V1")
    parser.add_argument("--max-records", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=10_000)
    parser.add_argument("--per-sourcetype-cap", type=int, default=2_000)
    parser.add_argument("--dry-run-cousins", action="store_true")
    parser.add_argument(
        "--hunt-span-seconds",
        type=float,
        default=DEFAULT_HUNT_SPAN_SECONDS,
        help="H.1: the span a preflight calibration returned COMMIT for. Never "
        "widen this past what was actually calibrated -- narrow it and "
        "re-calibrate instead.",
    )
    parser.add_argument(
        "--hunt-time-budget-seconds",
        type=float,
        default=None,
        help="H5: caps entries ATTEMPTED, never the read within one entry.",
    )
    args = parser.parse_args()

    # `ip.lab_available()` also gates on the DC/SRV attack-simulation VMs
    # answering AD ports -- irrelevant to reading the already-indexed BOTS
    # corpus or injecting a cousin via HEC, both of which only need Splunk
    # itself. Gating the WHOLE run on it would abort a genuine corpus hunt
    # over an unrelated subsystem being down; the credential check below is
    # the real precondition for streaming. `investigate_anchors`/
    # `plant_and_measure_cousins` no longer route through that gate at all
    # (F.4 finding: it made a live anchor find structurally impossible in
    # this environment, not just slow) -- see `_hunt_entry`/
    # `_read_window_completely`.
    if not os.environ.get("LAB_SPLUNK_PASSWORD"):
        print(
            json.dumps({"plane": "unavailable", "reason": "LAB_SPLUNK_PASSWORD not set"}, indent=2)
        )
        return 1

    # H.3/H4: the run doc was previously written only after every stage
    # completed, so a death at hour 20 produced nothing. `out_dir` is
    # created up front so `_on_entry_done` can publish a partial sweep doc
    # -- readable at ANY point -- after every entry, not only at the end.
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    partial_path = out_dir / f"{args.doc_stem}_PARTIAL.json"

    def _on_entry_done(progress: rpf.EntryProgress, result: dict[str, Any]) -> None:
        tmp = partial_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "last_entry": result,
                    "entry_progress": progress.to_dict(),
                    "published_at": time.time(),
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        tmp.replace(partial_path)

    stages = build_stages(
        max_records=args.max_records,
        batch_size=args.batch_size,
        per_sourcetype_cap=args.per_sourcetype_cap,
        dry_run_cousins=args.dry_run_cousins,
        hunt_span_seconds=args.hunt_span_seconds,
        hunt_time_budget_seconds=args.hunt_time_budget_seconds,
        on_entry_done=_on_entry_done,
    )

    # Print EACH stage's result as it completes (F.4 finding): a run whose
    # expensive stage can take hours must not stay silent until the very
    # end -- there is no way to tell a resolved fast-proof from a stalled
    # run otherwise. `full_pipeline.run_pipeline` already threads an
    # `on_stage` callback for exactly this.
    def _on_stage(result: fp.StageResult) -> None:
        print(
            json.dumps(
                {"stage_complete": result.to_dict(), "produced": result.produced},
                indent=2,
                default=str,
            ),
            flush=True,
        )

    ctx, report = fp.run_pipeline(
        stages,
        fix_in_place=True,
        on_stage=_on_stage,
        records_of=lambda c: len(c.get("records", [])),
    )

    published = _build_published_report(ctx, report, indexes=corpus_bed.resolve_indexes())
    print(json.dumps({"final_report": published}, indent=2, default=str))

    (out_dir / f"{args.doc_stem}.json").write_text(
        json.dumps(published, indent=2, default=str), encoding="utf-8"
    )
    (out_dir / f"{args.doc_stem}.md").write_text(
        _render_md(published, args.doc_stem), encoding="utf-8"
    )
    return 0


def _build_published_report(
    ctx: fp.RunContext, report: fp.PipelineReport, *, indexes: tuple[str, ...]
) -> dict[str, Any]:
    """Assemble F.4's required publication shape: `assembly_verdict` FIRST
    (F.1's own harness never trusted to run itself -- this is the one call
    site that actually invokes it), `ClaimEvidence` for the four standing
    claims, `bed_acceptance` (required by `corpus_bed.require_bed_
    acceptance`), and every stage's own output, so a reader never has to
    reconstruct what happened from raw stdout."""
    stage_by_name = {s.name: s for s in report.stages}

    records_available: dict[str, int] = {}
    for index in indexes:
        try:
            from portal.modules.security.core.bully.live_connect import lab_splunk_connector

            records_available[index] = ip._index_count(lab_splunk_connector(index=index), index)
        except Exception:  # noqa: BLE001 -- a failed count must not block publication
            records_available[index] = 0
    total_available = sum(records_available.values())

    stream_produced = getattr(stage_by_name.get("stream_corpus_sample"), "produced", None) or {}
    role_map = ctx.get("role_map")
    recovery = ctx.get("distance_recovery")
    investigations = ctx.get("investigations", [])
    found_entry = ctx.get("found_anchor_entry")

    evidence = fp.ClaimEvidence(
        crogl_sourcetypes_reviewed=stream_produced.get("n_sourcetypes_covered", 0),
        crogl_identity_coverage=(role_map.entity_coverage if role_map else None),
        bully_chain_reach_recall=(recovery.recall_at(0) if recovery else None),
        bully_max_pivot_distance=(recovery.max_reached_distance if recovery else None),
        corpus_records_processed=ctx.counters.get("records_processed", 0),
        corpus_records_available=total_available,
        generator_cousin_recall_at_distance=(
            {str(h): recovery.recall_at(h) for h in recovery.by_distance} if recovery else {}
        ),
    )
    verdict = fp.assembly_verdict(report, evidence)

    # bed_acceptance (A5, required by corpus_bed.require_bed_acceptance):
    # floor_known_recall here means "did the search-until-first-match design
    # confirm at least one answer-key technique live", NOT "what fraction of
    # all 27 techniques recovered" -- this run stops at the first hit by
    # design (operator instruction), so scoring against all candidates tried
    # would be a denominator of 1 and a trivial 100%. Denominator is the
    # full in-scope answer-key candidate count instead, so the number reads
    # honestly as "confirmed 1 of N", not as an inflated recall figure.
    n_candidates = len([e for e in BOTS_ANSWER_KEY if e.dataset in indexes and e.entities])
    n_hit = 1 if investigations and investigations[0].events else 0
    cousins = ctx.get("planned_cousins", [])
    cousin_reached = sum(
        h.get("reached", 0) for h in (recovery.by_distance.values() if recovery else [])
    )
    bed_report = corpus_bed.assess_bed(
        records_available,
        records_read=evidence.corpus_records_processed,
        units_fitted=stream_produced.get("wide_fitted_units", 0),
        units_scored=len(ctx.get("units", [])),
    )
    acceptance = corpus_bed.bed_acceptance(
        answer_key_hit=n_hit,
        answer_key_total=n_candidates,
        cousin_hit=cousin_reached,
        cousin_total=len(cousins),
        background_flagged=0,
        background_total=0,
        bed=bed_report,
    )

    # scoreboard.update() (W.2/W.5, TASK_BULLY_SCOREBOARD_CONFORMANCE_V1):
    # every published run must report the real correctness axis
    # (trust_mean_rank/false_flag_count) computed from scoreboard.update(),
    # not a proxy recall/coverage figure alone -- CI's DT/DV checks enforce
    # this repo-wide. `grade_to_loop_contract` already produces real
    # CousinAssessment rows (module=loop_grader, one of the sixteen); this
    # scores them through the real contract rather than inventing a second
    # scoring path.
    cousin_assessments = ctx.get("cousin_assessments", [])
    scoreboard_rows = [
        {
            "assessment_id": a.assessment_id,
            "relationship": a.relationship,
            "defense_response": a.defense_response,
            "composite": a.composite,
            "candidate_state": None,
            "known_benign": False,
        }
        for a in cousin_assessments
    ]
    scoreboard_row = scoreboard.update("full_assembly_f4", scoreboard_rows)

    # starvation_check (K.3, TASK_BULLY_SCORER_FEED_V1): a stage completing
    # in ~0s on a large run is a starvation signal stage status cannot show
    # by itself (F.4: all seventeen stages reported OK at 63/359,757
    # records). Compared against the stream's own record total, not the
    # scorer sample's, so this is a genuine cross-check on K.1/K.2's fix.
    starvation = fp.starvation_check(
        report,
        stream_total=stream_produced.get("n_records_wide_fit", 0),
        analytical_stages=ANALYTICAL_STAGES,
    )

    return {
        "assembly_verdict": verdict,
        "claim_evidence": evidence.to_dict(),
        "bed_acceptance": acceptance.to_dict(),
        "bed_report": bed_report.to_dict(),
        "scoreboard": scoreboard_row,
        "starvation_check": starvation,
        "found_anchor_technique": found_entry.technique if found_entry else None,
        "found_anchor_dataset": found_entry.dataset if found_entry else None,
        "pipeline_report": report.to_dict(),
        "stage_outputs": {s.name: s.produced for s in report.stages},
    }


def _render_md(published: dict[str, Any], doc_stem: str) -> str:
    verdict = published["assembly_verdict"]
    evidence = published["claim_evidence"]
    acceptance = published["bed_acceptance"]
    sb = published["scoreboard"]
    pr = published["pipeline_report"]
    starv = published["starvation_check"]
    lines = [
        f"# {doc_stem}",
        "",
        f"## assembly_verdict: **{verdict['verdict']}**",
        "",
        f"- integration_fraction: {verdict['integration_fraction']} "
        f"({len(verdict['modules_exercised'])}/16 modules)",
        f"- corpus_fraction: {verdict['corpus_fraction']}",
        f"- modules_missing: {verdict['modules_missing']}",
        f"- degraded_stages: {pr['degraded_stages']}",
        f"- reasons: {verdict['reasons']}",
        "",
        "## The four standing claims, answered by THIS run",
        "",
        f"```json\n{json.dumps(evidence, indent=2)}\n```",
        "",
        "## bed_acceptance (A5)",
        "",
        f"```json\n{json.dumps(acceptance, indent=2)}\n```",
        "",
        "## scoreboard.update() -- the correctness axis (W.2)",
        "",
        f"- trust_mean_rank: {sb.get('trust_mean_rank')}",
        f"- false_flag_count: {sb.get('false_flag_count')}",
        f"```json\n{json.dumps({k: v for k, v in sb.items() if k != 'records'}, indent=2)}\n```",
        "",
        f"- found_anchor: {published['found_anchor_technique']} "
        f"({published['found_anchor_dataset']})",
        "",
        f"## starvation_check (K.3): **{starv['verdict']}**",
        "",
        f"```json\n{json.dumps(starv, indent=2)}\n```",
        "",
        "## Per-stage timings, records received, and outputs",
        "",
    ]
    for s in pr["stages"]:
        lines.append(
            f"- **{s['stage']}** ({s['module']}) -- {s['status']}, {s['seconds']}s, "
            f"records_received={s['records_received']}"
        )
        if s["error"]:
            lines.append(f"  - error: {s['error']}")
    lines += [
        "",
        f"Total duration: {pr['duration_seconds']}s",
        "",
        "## Full stage outputs",
        "",
        f"```json\n{json.dumps(published['stage_outputs'], indent=2, default=str)}\n```",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
