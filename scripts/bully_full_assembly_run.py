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
    # Fast proof FIRST (targeted, entity/time-scoped queries -- not a
    # corpus walk), ahead of the uncapped wide fit below: a live run
    # showed the wide fit alone can run for many hours, and gating "does
    # the assembled loop actually work" behind that grind defeats the
    # point of checking early.
    ("investigate_anchors", "investigation_pivot"),
    ("plant_and_measure_cousins", "adaptive_scope"),
    ("stream_corpus_sample", "corpus_bed"),
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

# Checkpoint for `stream_corpus_sample` -- the one stage long enough (hours
# to days) that a kill/interruption must resume, not restart (F.4 finding).
# Small by construction: NormalBaseline's token vocabulary is bounded
# regardless of corpus size (bigrams over ~10 behaviour classes, a handful
# of buckets), so this file stays kilobytes, never gigabytes.
CHECKPOINT_PATH = Path("/tmp/bully_full_assembly_f4_checkpoint.json")
CHECKPOINT_INTERVAL_SECONDS = 120.0


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


def build_stages(  # noqa: C901, PLR0915
    *,
    max_records: int | None,
    batch_size: int,
    per_sourcetype_cap: int,
    dry_run_cousins: bool,
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

        last_batch: list[dict[str, Any]] = []
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
                        last_batch = batch
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

        ctx.put("records", last_batch)
        ctx.put("wide_baseline", baseline)
        result: dict[str, Any] = {
            "n_records_wide_fit": ctx.counters.get("records_processed", 0),
            "n_records_last_batch": len(last_batch),
            "wide_fitted_units": baseline.fitted_units,
            "resumed_from_checkpoint": resuming,
            "n_sourcetypes_covered": len(covered),
            "n_sourcetypes_available": n_sourcetypes_available,
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

    def _investigate_anchors_directly(
        anchors: list[pivot.Anchor], indexes: tuple[str, ...], ctx: fp.RunContext
    ) -> list[pivot.Investigation]:
        """Mirrors `inject_plane.capture_investigation`'s own query/execute
        logic, MINUS its `lab_available()` gate (F.4 finding, seam defect
        shimmed here per F.2's own doctrine, not fixed in the module): that
        gate requires the DC/SRV attack-simulation VMs to answer AD ports,
        which is irrelevant to reading the already-indexed historical BOTS
        corpus around an anchor -- this only needs Splunk, already verified
        reachable. Routing through the real gate meant `investigate_anchors`
        could never find anything in this environment no matter how long it
        searched, independent of whether the corpus itself held a match."""
        from portal.modules.security.core.bully.connectors import QueryIntent
        from portal.modules.security.core.bully.live_connect import lab_splunk_connector

        connectors = {idx: lab_splunk_connector(index=idx) for idx in indexes}
        index_ranges = ctx.get("index_ranges", {})

        def execute(query: Any) -> list[dict[str, Any]]:
            connector = connectors[query.index]
            result = connector.read(
                QueryIntent(
                    "anchor-pivot investigation",
                    start=query.earliest,
                    end=query.latest,
                    entities=(query.entity,),
                )
            )
            schemas: set[str] = set()
            out: list[dict[str, Any]] = []
            for record in result.records:
                tagged = ip._tag_captured_record(record, index=query.index, schemas=schemas)
                if tagged is not None:
                    out.append(tagged)
            return out

        investigations = []
        for anchor in anchors:
            rng = index_ranges.get(anchor.index)
            inv = pivot.investigate(
                anchor,
                list(indexes),
                execute,
                ip._extract_pivot_entities,
                corpus_earliest=rng.earliest if rng else None,
                corpus_latest=rng.latest if rng else None,
            )
            investigations.append(inv)
        return investigations

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

    def investigate_anchors(ctx: fp.RunContext) -> dict[str, Any]:
        """Search the answer key's real anchors ONE AT A TIME and stop at
        the FIRST that produces a genuine finding (a live investigation
        that actually captured events) -- proving the investigation loop
        works against the real corpus without exhaustively investigating
        all 27 entries. `n_answer_key_entries_tried` publishes how much of
        the key had to be searched, so a run finding nothing after trying
        all of them reads as a real negative, not a truncated one."""
        indexes = ctx.get("indexes", ())
        candidates = [e for e in BOTS_ANSWER_KEY if e.dataset in indexes and e.entities]
        tried = 0
        for entry in candidates:
            anchor = _anchor_for(entry, ctx)
            invs = _investigate_anchors_directly([anchor], (entry.dataset,), ctx)
            tried += 1
            if invs and len(invs[0].events) > 0:
                ctx.put("investigations", invs)
                ctx.put("found_anchor_entry", entry)
                ctx.put("found_anchor", anchor)
                return {
                    "n_investigations": len(invs),
                    "n_events": len(invs[0].events),
                    "n_answer_key_entries_tried": tried,
                    "found_technique": entry.technique,
                    "found_dataset": entry.dataset,
                }
        return {
            "n_investigations": 0,
            "n_answer_key_entries_tried": tried,
            "n_answer_key_entries_available": len(candidates),
            "seam_defect": "searched every in-scope answer-key anchor, none captured a live event",
        }

    def plant_and_measure_cousins(ctx: fp.RunContext) -> dict[str, Any]:
        """Narrow proof, not a corpus-wide sweep: once `investigate_anchors`
        found ONE real anchor with real events, plant exactly ONE cousin of
        THAT technique, ship it live (unless `--dry-run-cousins`), let it
        land, then re-run the SAME anchor's investigation to measure
        whether the chain that just proved itself real can also recover an
        injected cousin next to it."""
        entry = ctx.get("found_anchor_entry")
        anchor = ctx.get("found_anchor")
        earliest = ctx.get("corpus_earliest")
        latest = ctx.get("corpus_latest")
        if entry is None or anchor is None or earliest is None or latest is None:
            return {
                "n_planted": 0,
                "seam_defect": "no anchor found by investigate_anchors to test a cousin against",
            }
        # `coverage` (telemetry_behavior's sourcetype breakdown) comes from
        # `classify_telemetry`, which runs AFTER this stage now that the
        # fast proof is sequenced ahead of the wide fit -- so this reads
        # sourcetypes from the found investigation's OWN captured events
        # instead, which is available here and arguably more relevant (only
        # sourcetypes this specific anchor's investigation actually saw).
        investigations = ctx.get("investigations", [])
        sourcetypes = tuple(sorted({st for inv in investigations for st in inv.sourcetypes}))
        cousins = corpus_bed.plan_cousins(
            [entry],
            corpus_earliest=earliest,
            corpus_latest=latest,
            corpus_sourcetypes=sourcetypes,
            per_technique=1,
        )
        ctx.put("planned_cousins", cousins)
        inject_reports = cousin_inject.inject_cousins(
            cousins,
            index=entry.dataset,
            corpus_earliest=earliest,
            corpus_latest=latest,
            dry_run=dry_run_cousins,
        )
        if not dry_run_cousins and any(r.ok for r in inject_reports):
            time.sleep(5.0)  # let HEC-shipped events land before recovery capture
        recovery_investigations = _investigate_anchors_directly([anchor], (entry.dataset,), ctx)
        reached: set[str] = set()
        for inv in recovery_investigations:
            reached |= set(inv.entities_seen)
        planted = [(c.anchor_entity, c.planted_distance) for c in cousins if c.anchor_entity]
        recovery = ascope.distance_recovery(planted, reached)
        ctx.put("distance_recovery", recovery)
        return {
            "n_planted": len(cousins),
            "dry_run": dry_run_cousins,
            "inject_reports": [r.to_dict() for r in inject_reports],
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
    _ = (dry_run_cousins, LibraryAnchor, AnchorLibrary)  # reserved for cousin write-back seam
    return stages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="docs")
    parser.add_argument("--doc-stem", default="BULLY_FULL_ASSEMBLY_RUN_F4_V1")
    parser.add_argument("--max-records", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=10_000)
    parser.add_argument("--per-sourcetype-cap", type=int, default=2_000)
    parser.add_argument("--dry-run-cousins", action="store_true")
    args = parser.parse_args()

    # `ip.lab_available()` also gates on the DC/SRV attack-simulation VMs
    # answering AD ports -- irrelevant to reading the already-indexed BOTS
    # corpus or injecting a cousin via HEC, both of which only need Splunk
    # itself. Gating the WHOLE run on it would abort a genuine corpus hunt
    # over an unrelated subsystem being down; the credential check below is
    # the real precondition for streaming. `investigate_anchors`/
    # `plant_and_measure_cousins` no longer route through that gate at all
    # (F.4 finding: it made a live anchor find structurally impossible in
    # this environment, not just slow) -- see `_investigate_anchors_directly`.
    if not os.environ.get("LAB_SPLUNK_PASSWORD"):
        print(
            json.dumps({"plane": "unavailable", "reason": "LAB_SPLUNK_PASSWORD not set"}, indent=2)
        )
        return 1

    stages = build_stages(
        max_records=args.max_records,
        batch_size=args.batch_size,
        per_sourcetype_cap=args.per_sourcetype_cap,
        dry_run_cousins=args.dry_run_cousins,
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

    ctx, report = fp.run_pipeline(stages, fix_in_place=True, on_stage=_on_stage)

    print(json.dumps({"final_report": report.to_dict()}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
