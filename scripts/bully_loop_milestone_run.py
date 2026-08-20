#!/usr/bin/env python3
"""bully_loop_milestone_run.py -- R.6: run the reintegrated LOOP, live, end to end.

Not the intake sidecar -- the orchestrated loop. Per
docs/DESIGN_BULLY_LOOP_REINTEGRATION_V1.md and the master doc's Reintegration
& Pyramid section (2026-08-20): the standalone script is a loop CALLER, never
a second pipeline. This script:

1. Drives R.5a (real-tooling chains against the agent-controlled lab) and
   R.5b (the procedurally-generated schema-agnostic source universe, shipped
   to the live index via HEC) -- both halves of the event generator.
2. Captures the blended universal telemetry back out of the lab's Splunk
   (broad index, all sourcetypes) via the existing `inject_plane.capture_records`.
3. Runs entity resolution + cross-source timeline assembly (correlation.py),
   builds a behavioural series per timeline (pyramid + the learned
   classifier), and decides cousinhood by sequence alignment
   (series_cousin.py) against a known-technique library built from R.5b's
   sealed cousin specs.
4. Grades through `loop_grader.build_cousin_assessment_from_series` -- the
   SAME CousinAssessment DTO `orchestrator._analyzing` emits -- and records
   every assessment through the real `Store`/`scoreboard` organs, runs the
   real investigation arm on bubbled cousins, and drafts a handoff detection
   for operator-confirmed ones.
5. Publishes docs/BULLY_LOOP_MILESTONE_RUN_R6_V1.{md,json}.

A genuine environment blocker (lab unreachable, HEC unauthenticated, zero
capture) is reported BLOCKED with its reason -- synthetic data is never
presented as a live loop run (R4).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from portal.modules.security.core.bully import (  # noqa: E402
    behavior_classifier,
    correlation,
    field_roles,
    loop_grader,
    series_cousin,
    universe,
)
from portal.modules.security.core.bully import (
    config as bully_config,
)
from portal.modules.security.core.bully import (
    handoff as handoff_mod,
)
from portal.modules.security.core.bully import (
    inject_plane as ip,
)
from portal.modules.security.core.bully import (
    investigation as investigation_mod,
)
from portal.modules.security.core.bully import (
    scoreboard as scoreboard_mod,
)
from portal.modules.security.core.bully import (
    scoreboard_conformance as conformance_mod,
)
from portal.modules.security.core.bully import (
    signatures as signatures_mod,
)
from portal.modules.security.core.bully.contracts import DecisionEvent, new_id
from portal.modules.security.core.bully.store import Store
from portal.modules.security.core.episode import Episode
from portal.modules.security.core.siem import hec_ship

ALGORITHM_VERSION = "loop-milestone-run-r6-v1"

# The 4 transformations the exit gate requires at minimum, +DOWNLEVEL always
# present. SCATTER (cross-source identity realization) is prose-described in
# TASK_BULLY_LOOP_REINTEGRATION_V1's R.5b but is NOT implemented in the
# universe.py payload as delivered -- reported as a residual, not fabricated.
_COUSIN_SPINE = ("auth", "enumerate", "escalate", "collect")
_COUSIN_TRANSFORMATIONS = (
    universe.TRANSFORMATIONS
)  # 5: REVOCABULARY/REIDENTITY/REORDER_MINOR/RESCHEMA/DOWNLEVEL

# Real-telemetry seed examples (well-known Windows Security/Sysmon EventCodes
# and Linux auditd types this lab actually emits) so the R.5c classifier,
# fit ONLY on universe.py's synthetic realizations, also transfers to the
# genuine captured telemetry -- without this, a naive-Bayes model trained
# purely on invented `gen:*` sources has no real-world grounding and
# classifies real EventCodes essentially at random.
_REAL_TELEMETRY_SEED: list[tuple[str, str]] = [
    ("4624", "auth"),
    ("4625", "auth"),
    ("4648", "auth"),
    ("4672", "escalate"),
    ("4688", "execute"),
    ("4697", "persist"),
    ("4698", "persist"),
    ("4720", "persist"),
    ("4732", "escalate"),
    ("4769", "auth"),
    ("4776", "auth"),
    ("1", "execute"),  # sysmon process create
    ("3", "lateral"),  # sysmon network connect
    ("11", "collect"),  # sysmon file create
    ("SERVICE_STOP", "destroy"),
    ("SERVICE_START", "persist"),
    ("USER_LOGIN", "auth"),
    ("USER_LOGOUT", "auth"),
    ("SYSCALL", "execute"),
    ("CRED_ACQ", "auth"),
]


def _blocked(reason: str, *, partial: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "plane": "BLOCKED",
        "reason": reason,
        "algorithm_version": ALGORITHM_VERSION,
        "generated_at": time.time(),
        **(partial or {}),
    }


def _run_r5a(dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"plane": "skipped", "reason": "--dry-run-generate"}
    report = ip.generate_labelled_activity()
    return report.to_dict()


def _run_r5b(n_sources: int, background_n: int, seed: int) -> universe.UniverseLot:
    cousins = [
        {
            "parent_family": f"priv-esc-{t.lower()}",
            "parent_technique": "T1078",
            "behavioural_spine": list(_COUSIN_SPINE),
            "transformation": t,
            "chain_id": f"universe-cousin-{t.lower()}",
        }
        for t in _COUSIN_TRANSFORMATIONS
    ]
    return universe.build_universe(
        n_sources=n_sources, background_n=background_n, cousins=cousins, seed=seed
    )


def _ship_universe_via_hec(lot: universe.UniverseLot, *, dry_run: bool) -> dict[str, Any]:
    by_source: dict[str, list[dict[str, Any]]] = {}
    times_by_source: dict[str, list[float]] = {}
    for e in lot.events:
        by_source.setdefault(e["source_id"], []).append(e["event"])
        times_by_source.setdefault(e["source_id"], []).append(e["time"])

    results = {}
    for source_id, events in by_source.items():
        result = hec_ship.ship_batch(
            events,
            sourcetype=source_id,
            host="bully-universe-r6",
            event_times=times_by_source[source_id],
            dry_run=dry_run,
            evidence_origin="bully_loop_milestone_run_r6",
        )
        results[source_id] = result
    return {
        "n_sources_shipped": len(by_source),
        "n_events_shipped": sum(len(v) for v in by_source.values()),
        "all_ok": all(r.get("ok") for r in results.values()),
        "per_source_ok": {k: bool(v.get("ok")) for k, v in results.items()},
    }


_RAW_KV = re.compile(
    r"""(?P<key>[A-Za-z_][A-Za-z0-9_.]*)=(?:"(?P<qval>[^"]*)"|'(?P<sqval>[^']*)'|(?P<val>\S+))"""
)


def _parse_raw_kv(record: dict[str, Any]) -> dict[str, Any]:
    """Splunk's search API hands back the RAW event text under `_raw`
    (`EventCode=1 Account=AR-WIN-3\\Administrator ...`), not parsed fields --
    everything else on the wrapper (`_bkt`/`_cd`/`_indextime`/`sourcetype`/
    `host`/...) is Splunk's own metadata, not the event's payload. Without
    parsing `_raw`, field-role inference and entity resolution only ever see
    metadata and miss the real payload entirely -- the actual bottleneck a
    genuinely live capture hits that a fixture never would. Merges parsed
    `key=value` pairs (quoted or bare) into the record; unparseable/free-text
    `_raw` is left as-is (still available as a PAYLOAD-role fallback)."""
    raw = record.get("_raw")
    if not isinstance(raw, str) or not raw:
        return record
    merged = dict(record)
    for m in _RAW_KV.finditer(raw):
        key = m.group("key")
        value = m.group("qval") or m.group("sqval") or m.group("val")
        if key not in merged and value:
            merged[key] = value
    return merged


def _extract_identifier_observations(
    records: list[dict[str, Any]],
) -> list[correlation.IdentifierObservation]:
    """Build IdentifierObservations from the captured pool via field-role
    inference per source, so entity resolution operates only on ENTITY-role
    values -- never attack labels (Q3)."""
    by_source: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        sid = str(r.get("__source_id") or "unknown")
        by_source.setdefault(sid, []).append(r)

    observations: list[correlation.IdentifierObservation] = []
    for source_id, source_records in by_source.items():
        role_map = field_roles.infer_field_roles(source_records, source_id=source_id)
        if not role_map.entity_fields:
            continue
        for idx, rec in enumerate(source_records):
            artifact_id = f"{source_id}:{idx}"
            for field_name in role_map.entity_fields:
                value = rec.get(field_name)
                if isinstance(value, str) and value:
                    observations.append(
                        correlation.IdentifierObservation(
                            value=value,
                            field_path=field_name,
                            source_id=source_id,
                            artifact_id=artifact_id,
                        )
                    )
    return observations


# Behavioural spine each R.5a live-chain family maps to, by MITRE tactic
# semantics (the same domain knowledge pyramid.py's deterministic table
# encodes). Without these, the known library would ONLY contain R.5b's
# synthetic priv-esc cousins, so the real lab activity generated by R.5a
# could never grade SAME/SIMILAR against anything -- the library must cover
# both generator halves, not just one.
_R5A_FAMILY_SPINE: dict[str, tuple[str, ...]] = {
    "discovery": ("enumerate",),
    "credential_access_asrep": ("auth", "collect"),
    "credential_access_kerberoast": ("auth", "collect"),
    "credential_access_dcsync": ("auth", "escalate", "collect"),
    "network_service_scan": ("enumerate",),
    "account_discovery": ("enumerate",),
    "lateral_movement": ("auth", "execute"),
    "credential_access_spray": ("auth",),
}


def _build_known_library(lot: universe.UniverseLot) -> list[series_cousin.BehaviouralSeries]:
    library = []
    for sealed in lot.sealed_truth:
        library.append(
            series_cousin.BehaviouralSeries(
                series_id=sealed["chain_id"],
                spine=tuple(sealed["behavioural_spine"]),
                n_logs=sealed["n_steps"],
                technique=sealed["technique"],
            )
        )
    for chain in ip._LIVE_CHAINS:
        spine = _R5A_FAMILY_SPINE.get(chain["family"])
        if not spine:
            continue
        library.append(
            series_cousin.BehaviouralSeries(
                series_id=chain["chain_id"],
                spine=spine,
                n_logs=len(chain["steps"]),
                technique=chain["technique"],
            )
        )
    return library


def _record_decision(
    store: Store, hunt_id: str, subject_id: str, rationale: str, data: dict
) -> None:
    store.record_decision(
        DecisionEvent(
            event_id=new_id("dec"),
            hunt_id=hunt_id,
            iteration_id=None,
            actor="system:bully_loop_milestone_run",
            kind="grade",
            subject_id=subject_id,
            rationale=rationale,
            data=data,
            recorded_at=time.time(),
        )
    )


def _synthetic_episode_for_timeline(timeline: correlation.EntityTimeline) -> Episode:
    return Episode(
        episode_id=f"ep-r6-{uuid.uuid4().hex[:12]}",
        scenario=f"loop-milestone-r6:{timeline.entity.kind}",
        target_host=timeline.entity.canonical,
        started_at=time.time(),
        red_status="RED_LANDED",
        telemetry_status="TELEMETRY_INDEXED" if timeline.is_cross_source else "TELEMETRY_OBSERVED",
        detection_status="DETECTION_NOT_RUN",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-sources", type=int, default=40)
    parser.add_argument("--background-n", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=20260820)
    parser.add_argument("--capture-limit", type=int, default=2000)
    parser.add_argument("--max-timelines", type=int, default=25)
    parser.add_argument("--max-investigations", type=int, default=5)
    parser.add_argument("--dry-run-generate", action="store_true", help="skip R.5a live dispatch")
    parser.add_argument("--dry-run-hec", action="store_true", help="skip HEC ship (log only)")
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "docs")
    parser.add_argument(
        "--doc-stem",
        default="BULLY_LOOP_MILESTONE_RUN_R6_V1",
        help="output filename stem (no extension) for the published .json/.md",
    )
    args = parser.parse_args()

    started_at = time.time()
    available, reason = ip.lab_available()
    if not available:
        report = _blocked(f"lab unavailable: {reason}")
        _publish(report, args.out_dir, args.doc_stem)
        print(json.dumps(report, indent=2))
        return 1

    # ---- 1. generate: R.5a + R.5b ----
    r5a_report = _run_r5a(args.dry_run_generate)
    lot = _run_r5b(args.n_sources, args.background_n, args.seed)
    hec_report = _ship_universe_via_hec(lot, dry_run=args.dry_run_hec)
    if not hec_report["all_ok"] and not args.dry_run_hec:
        report = _blocked(
            "HEC ship failed for one or more sources",
            partial={"r5a": r5a_report, "hec": hec_report},
        )
        _publish(report, args.out_dir, args.doc_stem)
        print(json.dumps(report, indent=2))
        return 1

    # give the indexer a moment before we capture back
    if not args.dry_run_hec:
        time.sleep(5.0)

    # ---- 2. capture blended universal telemetry ----
    capture = ip.capture_records(sample_limit=args.capture_limit)
    if capture.plane != "live" or not capture.records:
        report = _blocked(
            f"capture unavailable or empty: {capture.reason or 'zero records'}",
            partial={"r5a": r5a_report, "hec": hec_report},
        )
        _publish(report, args.out_dir, args.doc_stem)
        print(json.dumps(report, indent=2))
        return 1

    # ---- 3. correlation: entity resolution + timeline assembly ----
    captured_records = [_parse_raw_kv(r) for r in capture.records]
    observations = _extract_identifier_observations(captured_records)
    entities, value_to_id = correlation.resolve_entities(observations)

    by_artifact_index: dict[str, dict[str, Any]] = {}
    for src, group in _group_by_source(captured_records).items():
        for idx, rec in enumerate(group):
            by_artifact_index[f"{src}:{idx}"] = rec

    def _entity_values_for(art_key: str) -> list[str]:
        rec = by_artifact_index.get(art_key, {})
        return [v for v in rec.values() if isinstance(v, str) and v in value_to_id]

    timelines = correlation.assemble_timelines(
        [{"_key": k, **v} for k, v in by_artifact_index.items()],
        entities,
        value_to_id,
        artifact_entity_values=lambda a: _entity_values_for(a["_key"]),
        artifact_time=lambda a: None,
        artifact_id=lambda a: a["_key"],
        artifact_source=lambda a: str(a.get("__source_id") or "unknown"),
    )
    timelines = timelines[: args.max_timelines]

    # ---- 4. learned classifier (R.5c), fit on this run's sealed truth
    #      PLUS the real-telemetry seed, so the model has real-world
    #      grounding and not just synthetic-universe grounding. ----
    training_examples = lot.training_examples() + _REAL_TELEMETRY_SEED
    classifier = (
        behavior_classifier.fit_classifier(training_examples) if training_examples else None
    )
    coverage_before_after = (
        behavior_classifier.measure_coverage(classifier, training_examples).to_dict()
        if classifier
        else None
    )

    known_library = _build_known_library(lot)

    # ---- 5. grade every timeline via series alignment, through the loop ----
    hunt_config = bully_config.load_hunt_config()
    models = bully_config.resolve_investigation_models(hunt_config=hunt_config)

    store = Store(bully_config.hunt_dir() / "hunt_state.db")
    hunt_id = new_id("hunt")
    store.hunt_create(
        hunt_id=hunt_id,
        objective="R.6 loop reintegration milestone run",
        neighborhood_scope="lab-universal",
        authorization_ref="operator:bully-r6",
        config_version="r6-milestone",
        role_snapshot=models,
        budgets={},
    )

    # `reference_signature_id` on cousin_assessments FKs to
    # behavior_signatures.signature_id -- each known-library anchor needs a
    # (thin, stub) signature row so a series-alignment grade's anchor_id can
    # be recorded, not just carried in `explanation`.
    for known in known_library:
        stub = signatures_mod.BehaviorSignature(
            signature_id=known.series_id,
            episode_ref=known.series_id,
            signature_algorithm_version=signatures_mod.SIGNATURE_ALGORITHM_VERSION,
            input_manifest_hash=known.series_id,
            canonical_fingerprint=known.series_id,
            action_sequence=list(known.spine),
            attack_mappings=[{"technique_id": known.technique}] if known.technique else [],
            completeness=1.0,
            present_dimensions=("action_sequence",),
        )
        store.record_signature(stub)

    graded: list[dict[str, Any]] = []
    bubbled_trace: list[dict[str, Any]] = []
    investigations_run = 0
    handoffs_drafted = 0

    for timeline in timelines:
        action_of = _action_value_extractor(timeline, by_artifact_index)
        observed_series = series_cousin.series_from_logs(
            f"observed:{timeline.entity.entity_id}",
            [by_artifact_index[a] for a in timeline.artifact_ids],
            action_of=action_of,
            classifier=classifier,
        )
        episode_view = {
            "episode_id": f"ep-r6-{timeline.entity.entity_id}",
            "target_host": timeline.entity.canonical,
        }
        signature = signatures_mod.build_signature(
            episode_view,
            {"action_sequence": list(observed_series.spine)},
            behavior_classifier=classifier,
        )
        assessment = loop_grader.build_cousin_assessment_from_series(
            signature, observed_series, known_library
        )
        store.record_signature(signature)
        store.record_cousin(assessment)
        _record_decision(
            store,
            hunt_id,
            assessment.assessment_id,
            f"R6_series_grade relationship={assessment.relationship}",
            {"entity_id": timeline.entity.entity_id, "n_sources": timeline.n_sources},
        )
        row = {
            "assessment_id": assessment.assessment_id,
            "entity_id": timeline.entity.entity_id,
            "is_cross_source": timeline.is_cross_source,
            "n_sources": timeline.n_sources,
            "relationship": assessment.relationship,
            "match_level": assessment.explanation.get("match_level", ""),
            "robustness": assessment.explanation.get("robustness", 0.0),
        }
        graded.append(row)

        if assessment.relationship in ("SIMILAR", "ANOMALOUS_UNCLASSIFIED") and (
            investigations_run < args.max_investigations
        ):
            episode = _synthetic_episode_for_timeline(timeline)
            try:
                inv_result = investigation_mod.run_arm(episode, models=models, dry_run=False)
                investigations_run += 1
                trace_entry = {
                    "entity_id": timeline.entity.entity_id,
                    "relationship": assessment.relationship,
                    "match_level": row["match_level"],
                    "investigation_verdict": inv_result.verdict,
                }
                if inv_result.verdict == "CONFIRMED" and handoffs_drafted < args.max_investigations:
                    technique_id = (
                        assessment.reference_signature_id
                        and next(
                            (
                                k.technique
                                for k in known_library
                                if k.series_id == assessment.reference_signature_id
                            ),
                            None,
                        )
                    ) or "T1078"
                    draft = handoff_mod.draft_generalization(
                        technique_id,
                        signatures_mod.reference_record_fields(signature),
                        {"spl": "", "distinguishing_features": {}},
                    )
                    handoffs_drafted += 1
                    trace_entry["handoff_draft"] = {
                        "technique_id": technique_id,
                        "has_spl": bool(draft.get("spl")),
                    }
                bubbled_trace.append(trace_entry)
            except Exception as exc:  # honest degrade, never crash the run (I-14)
                bubbled_trace.append(
                    {
                        "entity_id": timeline.entity.entity_id,
                        "relationship": assessment.relationship,
                        "investigation_error": f"{type(exc).__name__}: {exc}",
                    }
                )

    # ---- 5b. score: feed the instrument its REAL inputs (W.2). candidate_state
    # and known_benign come from store.scoreboard_records_for_hunt, which
    # left-joins every graded assessment with its latest BIN candidate row
    # and its known_state known_benign flag -- never hardcoded nulls. ----
    scoreboard_records = store.scoreboard_records_for_hunt(hunt_id)
    scoreboard_result = scoreboard_mod.update(hunt_id, scoreboard_records)
    scored_by_assessment = {r["assessment_id"]: r for r in scoreboard_result["records"]}

    # Residual risk (task exit criteria): trust_mean_rank/false_flag_count can
    # be PRESENT yet UNINFORMATIVE -- trust_mean_rank never sees a candidate
    # if BIN was never driven for this hunt, and false_flag_count is
    # structurally zero if known_state is empty. Publish the provenance
    # counts beside the axes so a zero is never misread as "none found".
    n_candidates_driven = sum(1 for r in scoreboard_records if r["candidate_state"] is not None)
    known_benign_rows_total = store.known_state_count(kind="known_benign")
    for row in graded:
        scored = scored_by_assessment.get(row["assessment_id"])
        if scored is not None:
            row.update(scored)

    store.close()

    # ---- 6. metrics ----
    n_graded = len(graded)
    n_anomalous = sum(1 for g in graded if g["relationship"] == "ANOMALOUS_UNCLASSIFIED")
    n_similar = sum(1 for g in graded if g["relationship"] == "SIMILAR")
    n_same = sum(1 for g in graded if g["relationship"] == "SAME")
    n_cross_source = sum(1 for g in graded if g["is_cross_source"])
    level_dist: dict[str, int] = {}
    for g in graded:
        level_dist[g["match_level"] or "none"] = level_dist.get(g["match_level"] or "none", 0) + 1

    report = {
        "plane": "live",
        "algorithm_version": ALGORITHM_VERSION,
        "generated_at": time.time(),
        "duration_s": round(time.time() - started_at, 2),
        "hunt_id": hunt_id,
        "r5a_generate": r5a_report,
        "r5b_universe": {
            "n_sources": len(lot.shapes),
            "info_levels": sorted({s.info_level for s in lot.shapes}),
            "naming_conventions": sorted({s.naming for s in lot.shapes}),
            "benign_count": lot.benign_count,
            "implant_count": lot.implant_count,
            "needle_to_hay_ratio": round(
                lot.implant_count / (lot.benign_count + lot.implant_count), 4
            ),
            "transformations": list(_COUSIN_TRANSFORMATIONS),
            "scatter_implemented": False,
        },
        "hec_ship": hec_report,
        "capture": capture.to_dict(),
        "correlation": {
            "n_observations": len(observations),
            "n_resolved_entities": len(entities),
            "n_timelines": len(timelines),
            "n_cross_source_timelines": n_cross_source,
            "cross_source_share": round(n_cross_source / n_graded, 4) if n_graded else 0.0,
        },
        "classifier_coverage_before_after": coverage_before_after,
        # The literal `scoreboard.update()` return -- catch_rate, trust_mean_rank,
        # discovery_total, discovery_mean, false_flag_count (W.3). Never a proxy
        # ratio invented in this script; `scoreboard_conformance.check_run`
        # enforces this contract in CI (W.5).
        "scoreboard": {k: v for k, v in scoreboard_result.items() if k != "records"},
        # Provenance for the correctness axis (residual risk, task exit
        # criteria): present-but-uninformative is distinguishable from a
        # genuine measurement only with these counts alongside it.
        "correctness_axis_provenance": {
            "candidates_driven_for_hunt": n_candidates_driven,
            "known_benign_rows_total": known_benign_rows_total,
        },
        "grade_distribution": {
            "n_graded": n_graded,
            "n_anomalous_unclassified": n_anomalous,
            "n_similar": n_similar,
            "n_same": n_same,
            "pyramid_level_distribution": level_dist,
        },
        "investigation": {
            "investigations_run": investigations_run,
            "handoffs_drafted": handoffs_drafted,
            "bubbled_trace": bubbled_trace,
        },
        "per_row": graded,
    }

    # ---- 7. self-check: a run may not publish a headline it would itself
    # reject (W.4). Refuse to write a PASS doc if the guard FAILs. ----
    self_check = conformance_mod.conformance_report(report)
    report["conformance_self_check"] = self_check
    if self_check["verdict"] == "FAIL":
        print("CONFORMANCE SELF-CHECK FAILED -- refusing to publish a PASS doc:")
        print(json.dumps(self_check, indent=2))
        return 1

    _publish(report, args.out_dir, args.doc_stem)
    print(json.dumps({k: v for k, v in report.items() if k != "per_row"}, indent=2))
    return 0


def _group_by_source(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        sid = str(r.get("__source_id") or "unknown")
        out.setdefault(sid, []).append(r)
    return out


def _action_value_extractor(
    timeline: correlation.EntityTimeline, by_artifact_index: dict[str, Any]
):
    def action_of(_log: dict[str, Any]) -> str:
        # `_log` here is the raw captured record itself (series_from_logs
        # iterates `logs` positionally), already `_raw`-parsed. EventCode/
        # EventID/type are the real action markers for windows:security/
        # sysmon/linux:auditd; fall back to generic action-ish keys, then
        # any string value.
        for key in (
            "EventCode",
            "EventID",
            "type",
            "event",
            "action",
            "op",
            "cmd",
            "message",
        ):
            if key in _log and isinstance(_log[key], str):
                return _log[key]
        for value in _log.values():
            if isinstance(value, str) and value:
                return value
        return ""

    return action_of


def _publish(report: dict[str, Any], out_dir: Path, doc_stem: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{doc_stem}.json"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    md_path = out_dir / f"{doc_stem}.md"
    md_path.write_text(_render_md(report, doc_stem), encoding="utf-8")


def _render_md(report: dict[str, Any], doc_stem: str) -> str:
    if report.get("plane") == "BLOCKED":
        return (
            f"# {doc_stem}\n\n"
            f"**plane:** BLOCKED\n\n**reason:** {report.get('reason')}\n\n"
            f"```json\n{json.dumps(report, indent=2, default=str)}\n```\n"
        )
    sb = report["scoreboard"]
    gd = report["grade_distribution"]
    corr = report["correlation"]
    inv = report["investigation"]
    lines = [
        f"# {doc_stem}",
        "",
        f"Generated {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(report['generated_at']))}"
        f" -- plane **{report['plane']}** -- duration {report['duration_s']}s",
        "",
        "## Headline: the loop scoreboard (scoreboard.update() contract, W.3)",
        "",
        f"- catch_rate: {sb['catch_rate']}",
        f"- **trust_mean_rank (correctness axis)**: {sb['trust_mean_rank']}",
        f"- discovery_total / discovery_mean: {sb['discovery_total']} / {sb['discovery_mean']}",
        f"- **false_flag_count (correctness axis)**: {sb['false_flag_count']}",
        "",
        "### Correctness axis provenance (present-but-uninformative check)",
        "",
        f"- Candidates driven through BIN for this hunt: "
        f"{report['correctness_axis_provenance']['candidates_driven_for_hunt']} "
        f"(0 means trust_mean_rank reflects only HONEST_ANOMALY catches, never a "
        f"PROMOTED/KILLED/DISPROVED operator verdict)",
        f"- known_state 'known_benign' rows (live, any hunt): "
        f"{report['correctness_axis_provenance']['known_benign_rows_total']} "
        f"(0 means false_flag_count={sb['false_flag_count']} is structurally zero -- "
        f"no known-benign subject existed to be falsely flagged -- not evidence of zero false flags)",
        "",
        f"## Conformance self-check: {report['conformance_self_check']['verdict']}"
        " (scoreboard_conformance.check_run, W.4)",
        "",
        f"```json\n{json.dumps(report['conformance_self_check'], indent=2)}\n```",
        "",
        "## Grade distribution (relationship counts -- NOT the scoreboard)",
        "",
        f"- Graded: {gd['n_graded']} entity timelines",
        f"- ANOMALOUS_UNCLASSIFIED (the product, bubbled to analyst): {gd['n_anomalous_unclassified']}",
        f"- SIMILAR (behavioural cousin): {gd['n_similar']}",
        f"- SAME (known behaviour): {gd['n_same']}",
        f"- Pyramid level distribution: {gd['pyramid_level_distribution']}",
        "",
        "## Correlation (cross-source entity timelines)",
        "",
        f"- Resolved entities: {corr['n_resolved_entities']} from {corr['n_observations']} identifier observations",
        f"- Timelines graded: {corr['n_timelines']}, cross-source: {corr['n_cross_source_timelines']}"
        f" ({corr['cross_source_share']})",
        "",
        "## Investigation & handoff",
        "",
        f"- Investigations run (real model call): {inv['investigations_run']}",
        f"- Handoff drafts produced: {inv['handoffs_drafted']}",
        "",
        "### Bubbled-cousin trace",
        "",
    ]
    for entry in inv["bubbled_trace"][:10]:
        lines.append(f"- {json.dumps(entry, default=str)}")
    lines += [
        "",
        "## R.5b universe",
        "",
        f"```json\n{json.dumps(report['r5b_universe'], indent=2)}\n```",
        "",
        "## R.5c classifier coverage (before/after)",
        "",
        f"```json\n{json.dumps(report['classifier_coverage_before_after'], indent=2)}\n```",
        "",
        "## Residual risks / known gaps in this run",
        "",
        "- SCATTER transformation (cross-source identity realization) is "
        "prose-described in the task but not implemented in universe.py as "
        "delivered; not exercised in this run.",
        "- R.5b's synthetic cousins are each realized within ONE target "
        "source shape, so R.5b does not itself exercise cross-source entity "
        "stitching -- that signal comes from R.5a's real multi-sourcetype "
        "lab telemetry (Windows/DNS/cloud identity representations of one "
        "principal).",
        "",
        "## Full per-row data",
        "",
        f"```json\n{json.dumps(report['per_row'], indent=2, default=str)}\n```",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
