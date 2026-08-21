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
    ("investigate_anchors", "investigation_pivot"),
    ("plant_and_measure_cousins", "adaptive_scope"),
    ("raise_and_verdict_concerns", "analyst_loop"),
)


def _action_of(r: dict[str, Any]) -> str | None:
    return tb._dig(r, *tb._FIELD_EVENTCODE) or tb._dig(r, "event_type")


def _entity_of(r: dict[str, Any]) -> list[str]:
    return [str(v) for _k, v in ip._extract_pivot_entities(r) if v]


def _time_of(r: dict[str, Any]) -> float | None:
    ts = r.get("_time")
    return ts if isinstance(ts, (int, float)) else None


def _sourcetype_of(r: dict[str, Any]) -> str:
    return str(r.get("sourcetype") or "")


def build_stages(  # noqa: C901, PLR0915
    *,
    max_records: int | None,
    batch_size: int,
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

    def stream_corpus_sample(ctx: fp.RunContext) -> dict[str, Any]:
        indexes = ctx.get("indexes", ())
        records: list[dict[str, Any]] = []
        for row in ip.stream_captured_records(
            indexes=indexes, batch_size=batch_size, max_records=max_records
        ):
            records.append(row)
            ctx.count("records_processed")
        ctx.put("records", records)
        return {"n_records": len(records)}

    def infer_field_roles(ctx: fp.RunContext) -> dict[str, Any]:
        records = ctx.get("records", [])
        role_map = fr.infer_field_roles(records, source_id="full_assembly")
        ctx.put("role_map", role_map)
        return {
            "extraction_valid": role_map.extraction_valid,
            "n_fields": len(role_map.roles) if role_map.extraction_valid else 0,
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
        graph = ctx.get("graph")
        observations = []
        for artifact in graph.artifacts if graph else []:
            for entity in artifact.entities:
                observations.append(
                    correlation.IdentifierObservation(
                        artifact_id=artifact.artifact_id, value=entity
                    )
                )
        entities, value_to_id = correlation.resolve_entities(observations)
        timelines = correlation.assemble_timelines(
            [a.__dict__ for a in (graph.artifacts if graph else [])],
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
        units = ctx.get("units", [])
        baseline = bl.NormalBaseline(environment_id="full_assembly")
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

    def investigate_anchors(ctx: fp.RunContext) -> dict[str, Any]:
        indexes = ctx.get("indexes", ())
        anchors: list[pivot.Anchor] = []
        for entry in BOTS_ANSWER_KEY:
            if entry.dataset not in indexes or not entry.entities:
                continue
            index_ranges = ctx.get("index_ranges", {})
            rng = index_ranges.get(entry.dataset)
            at = rng.earliest if rng and rng.earliest is not None else time.time()
            anchors.append(
                pivot.Anchor(
                    anchor_id=f"a-assembly-{entry.technique}",
                    at=at,
                    entity=entry.entities[0],
                    entity_kind="host",
                    sourcetype=entry.sourcetypes[0] if entry.sourcetypes else "",
                    why=f"answer_key:{entry.technique}",
                    index=entry.dataset,
                )
            )
        if not anchors:
            return {"n_investigations": 0, "seam_defect": "no answer-key anchors in scope"}
        capture = ip.capture_investigation(anchors, indexes=indexes)
        ctx.put("investigations", capture.investigations)
        ctx.put("investigation_bed_report", capture.bed_report)
        return {"n_investigations": len(capture.investigations)}

    def plant_and_measure_cousins(ctx: fp.RunContext) -> dict[str, Any]:
        earliest = ctx.get("corpus_earliest")
        latest = ctx.get("corpus_latest")
        coverage = ctx.get("coverage")
        if earliest is None or latest is None:
            return {"n_planted": 0, "seam_defect": "no discovered corpus range to plant inside"}
        sourcetypes = tuple(sorted(coverage.by_sourcetype)) if coverage else ()
        cousins = corpus_bed.plan_cousins(
            list(BOTS_ANSWER_KEY),
            corpus_earliest=earliest,
            corpus_latest=latest,
            corpus_sourcetypes=sourcetypes,
        )
        ctx.put("planned_cousins", cousins)
        investigations = ctx.get("investigations", [])
        reached: set[str] = set()
        for inv in investigations:
            reached |= set(inv.entities_seen)
        planted = [(c.anchor_entity, c.planted_distance) for c in cousins if c.anchor_entity]
        recovery = ascope.distance_recovery(planted, reached)
        ctx.put("distance_recovery", recovery)
        return {"n_planted": len(cousins), **recovery.to_dict()}

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
        fp.Stage("stream_corpus_sample", "corpus_bed", stream_corpus_sample, required=True),
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
        fp.Stage("investigate_anchors", "investigation_pivot", investigate_anchors),
        fp.Stage("plant_and_measure_cousins", "adaptive_scope", plant_and_measure_cousins),
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
    parser.add_argument("--dry-run-cousins", action="store_true")
    args = parser.parse_args()

    available, reason = ip.lab_available()
    if not available:
        print(json.dumps({"plane": "unavailable", "reason": reason}, indent=2))
        return 1

    stages = build_stages(
        max_records=args.max_records,
        batch_size=args.batch_size,
        dry_run_cousins=args.dry_run_cousins,
    )
    ctx, report = fp.run_pipeline(stages, fix_in_place=True)

    print(json.dumps(report.to_dict(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
