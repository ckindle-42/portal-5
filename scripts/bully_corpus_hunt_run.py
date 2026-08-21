#!/usr/bin/env python3
"""bully_corpus_hunt_run.py -- C.6: THE LIVE RUN ON THE REAL CORPUS BED.

TASK_BULLY_CORPUS_BED_V1. Every bully run before this one (R.6, W.6, X.6,
Y.6, D.4) read `index=portal5_lab` with a 2,000-row cap and got back only the
`gen:*` synthetic universe it had just written itself -- the generator
manufactured both the haystack and the needles, and the system was measured
against data it authored. This run stands on the REAL bed:

  * **Lane A (BOTS v1/v2/v3)** is the haystack -- real, messy, multi-source,
    at scale, with a published answer key (`bots_answer_key.py`).
  * **Lane B** carries cousins of answer-key-confirmed techniques, injected
    via `cousin_inject.py` (C.5).
  * **Lane C** is unlabelled novelty (not separately driven by this script --
    real background activity already flowing through the lab supplies it).

`corpus_bed.assess_bed(...)` is published FIRST: a run that is not a
haystack (`is_haystack=False`) reports `INVALID` and stops there. Otherwise
this script fits `NormalBaseline` WIDE (every assembled timeline across all
four lanes), refuses to score on an undersized fit
(`baseline.fitted_units_at(...) < corpus_bed.MIN_BASELINE_UNITS`), scores a
truth-aware sample, and publishes floor / product / cost as three separate
numbers -- never averaged (C3):

    floor    known-bad recall against the published answer key (enrichment
             match against an anchor library seeded FROM that answer key)
    product  injected-cousin recall inside the real corpus (did a discovered
             cluster surface the host each cousin shipped under)
    cost     background false-positive rate on real, non-injected activity

Reuses R.6/X.6's generation-free capture/correlation/grading helpers
(imported, not duplicated) -- this script drives its own Lane B injection
(C.5) instead of R.5b's synthetic universe.
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

import bully_analyst_loop_run as x6  # noqa: E402 -- reuse, never re-derive
import bully_loop_milestone_run as r6  # noqa: E402 -- reuse, never re-derive

from portal.modules.security.core.bully import (  # noqa: E402
    baseline as bl,
)
from portal.modules.security.core.bully import (
    config as bully_config,
)
from portal.modules.security.core.bully import (
    corpus_bed,
    correlation,
    cousin_inject,
    telemetry_behavior,
)
from portal.modules.security.core.bully import (
    inject_plane as ip,
)
from portal.modules.security.core.bully import (
    scoreboard as scoreboard_mod,
)
from portal.modules.security.core.bully import (
    scoreboard_conformance as conformance_mod,
)
from portal.modules.security.core.bully import (
    truth_acceptance as ta,
)
from portal.modules.security.core.bully.anchors import AnchorLibrary  # noqa: E402
from portal.modules.security.core.bully.bots_answer_key import BOTS_ANSWER_KEY  # noqa: E402
from portal.modules.security.core.bully.contracts import new_id  # noqa: E402
from portal.modules.security.core.bully.store import Store  # noqa: E402

ALGORITHM_VERSION = "corpus-hunt-run-c6-v1"


def _live_index_counts() -> dict[str, int]:
    """`| stats count` per index -- the real bed assessment, never the
    capped `records_read` size (that would silently reproduce D.4)."""
    from portal.modules.security.core.bully.live_connect import lab_splunk_connector

    counts: dict[str, int] = {}
    for index in corpus_bed.resolve_indexes():
        connector = lab_splunk_connector(index=index)
        counts[index] = ip._index_count(connector, index)
    return counts


def _live_corpus_range(indexes: tuple[str, ...]) -> tuple[float, float]:
    """The REAL discovered time range across every queried index (I5) -- the
    union bound cousins must land inside, never "now"."""
    from portal.modules.security.core.bully.live_connect import lab_splunk_connector

    earliest_candidates: list[float] = []
    latest_candidates: list[float] = []
    for index in indexes:
        connector = lab_splunk_connector(index=index)
        rng = ip.discover_index_range(connector, index)
        if rng.earliest is not None:
            earliest_candidates.append(rng.earliest)
        if rng.latest is not None:
            latest_candidates.append(rng.latest)
    if not earliest_candidates or not latest_candidates:
        raise RuntimeError("could not discover a real time range for any queried index")
    return min(earliest_candidates), max(latest_candidates)


def _seed_anchor_library_from_answer_key() -> AnchorLibrary:
    """Seed ONE anchor per answer-key technique so `disc.enrich` can name a
    discovered cluster against a real, published BOTS technique -- the
    library only enriches AFTER a cluster is found (D.4); it never decides
    what is discovered."""
    lib = AnchorLibrary()
    for entry in BOTS_ANSWER_KEY:
        lib.load_attack_episode(
            source_id="bots_answer_key",
            record=x6._stub_anchor_record(entry.behavioural_spine, entry.technique),
            techniques=(entry.technique,),
        )
    return lib


def _cousin_host(cousin_id: str) -> str:
    return f"corpus-cousin-{cousin_id}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fit-sample-limit", type=int, default=20_000, help="per-index capture cap"
    )
    parser.add_argument("--score-limit", type=int, default=200)
    parser.add_argument("--cousins-per-technique", type=int, default=1)
    parser.add_argument("--dry-run-inject", action="store_true", help="plan cousins, do not ship")
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "docs")
    parser.add_argument("--doc-stem", default="BULLY_CORPUS_BED_RUN_C6_V1")
    args = parser.parse_args()

    started_at = time.time()
    available, reason = ip.lab_available()
    if not available:
        report = {
            "plane": "BLOCKED",
            "reason": f"lab unavailable: {reason}",
            "algorithm_version": ALGORITHM_VERSION,
            "generated_at": time.time(),
        }
        _publish(report, args.out_dir, args.doc_stem)
        print(json.dumps(report, indent=2))
        return 1

    # ---- 1. cheap pre-flight on the corpus itself -- stop before an
    # expensive capture if the corpus can never be a haystack regardless of
    # what this run reads (T.2, TASK_BULLY_REAL_TELEMETRY_V1: assess_bed now
    # requires units_fitted/units_scored, which are not known until step 6,
    # so the full bed assessment happens there; this is a size/lane-only
    # pre-check, not `corpus_bed.assess_bed` itself). ----
    records_available = _live_index_counts()
    total_available = sum(records_available.values())
    lanes_available = {
        lane.lane for lane in corpus_bed.LANES if records_available.get(lane.index, 0) > 0
    }
    if total_available < corpus_bed.MIN_HAYSTACK_RECORDS or "A" not in lanes_available:
        report = {
            "plane": "INVALID",
            "reason": "not_a_haystack",
            "bed_report": {
                "indexes_queried": sorted(records_available),
                "records_available": records_available,
                "records_read": 0,
                "lanes_present": sorted(lanes_available),
                "is_haystack": False,
                "reasons": [
                    "pre_flight: corpus too small or lane A absent -- see records_available"
                ],
            },
            "algorithm_version": ALGORITHM_VERSION,
            "generated_at": time.time(),
        }
        _publish(report, args.out_dir, args.doc_stem)
        print(json.dumps(report, indent=2))
        return 1

    # ---- 2. plan + inject cousins of answer-key-confirmed techniques (C.5) --
    corpus_sourcetypes = tuple(sorted({st for e in BOTS_ANSWER_KEY for st in e.sourcetypes}))
    corpus_earliest, corpus_latest = _live_corpus_range(tuple(records_available))
    cousins = corpus_bed.plan_cousins(
        list(BOTS_ANSWER_KEY),
        corpus_sourcetypes=corpus_sourcetypes,
        per_technique=args.cousins_per_technique,
        corpus_earliest=corpus_earliest,
        corpus_latest=corpus_latest,
    )
    inject_reports = cousin_inject.inject_cousins(
        cousins,
        dry_run=args.dry_run_inject,
        corpus_earliest=corpus_earliest,
        corpus_latest=corpus_latest,
    )
    cousin_host_ids = {_cousin_host(c.cousin_id) for c in cousins}

    if not args.dry_run_inject:
        time.sleep(5.0)  # let HEC-shipped cousin events land before capture

    # ---- 3. capture across EVERY lane, streamed by index (C.3) ----
    capture = ip.capture_records(sample_limit=args.fit_sample_limit)
    if capture.plane != "live" or not capture.records:
        report = {
            "plane": "BLOCKED",
            "reason": f"capture unavailable or empty: {capture.reason or 'zero records'}",
            "bed_report": capture.bed_report.to_dict() if capture.bed_report else None,
            "algorithm_version": ALGORITHM_VERSION,
            "generated_at": time.time(),
            "inject_reports": [r.to_dict() for r in inject_reports],
        }
        _publish(report, args.out_dir, args.doc_stem)
        print(json.dumps(report, indent=2))
        return 1

    # ---- 4. correlation: entity resolution + truth-aware timeline assembly
    # (Y.3) -- priority given to entities carrying a cousin-injected host ----
    captured_records = [r6._parse_raw_kv(r) for r in capture.records]
    observations = r6._extract_identifier_observations(captured_records)
    entities, value_to_id = correlation.resolve_entities(observations)

    # ---- classifier health, measured on what this run ACTUALLY captured
    # (T3, TASK_BULLY_REAL_TELEMETRY_V1) -- coverage on synthetic held-out
    # data says nothing about real telemetry, which is what C.6's published
    # `learned_coverage: 0.963` did while every real verb read `unknown`. ----
    def _sourcetype_of(rec: dict[str, Any]) -> str:
        sid = str(rec.get("__source_id") or "")
        return (
            sid.split(":", 1)[1]
            if sid.startswith("lab-splunk:")
            else str(rec.get("sourcetype") or "")
        )

    classifier_coverage = telemetry_behavior.coverage_report(
        [(rec, _sourcetype_of(rec)) for rec in captured_records]
    )

    by_artifact_index: dict[str, dict[str, Any]] = {}
    for src, group in r6._group_by_source(captured_records).items():
        for idx, rec in enumerate(group):
            by_artifact_index[f"{src}:{idx}"] = rec

    def _entity_values_for(art_key: str) -> list[str]:
        rec = by_artifact_index.get(art_key, {})
        return [v for v in rec.values() if isinstance(v, str) and v in value_to_id]

    canonical_by_entity_id: dict[str, str] = {}
    cousin_id_by_entity_id: dict[str, str] = {}
    for eid, ent in entities.items():
        canonical_by_entity_id[eid] = ent.canonical
        for alias in (ent.canonical, *ent.aliases):
            if alias in cousin_host_ids:
                cousin_id_by_entity_id[eid] = alias.removeprefix("corpus-cousin-")
                break

    priority_entity_ids = frozenset(cousin_id_by_entity_id)
    identity_to_class = dict.fromkeys(cousin_host_ids, "unknown_cousin")

    timelines = correlation.assemble_timelines(
        [{"_key": k, **v} for k, v in by_artifact_index.items()],
        entities,
        value_to_id,
        artifact_entity_values=lambda a: _entity_values_for(a["_key"]),
        artifact_time=lambda a: None,
        artifact_id=lambda a: a["_key"],
        artifact_source=lambda a: str(a.get("__source_id") or "unknown"),
        priority_entity_ids=priority_entity_ids,
    )
    fit_timelines = timelines
    score_timelines = timelines[: args.score_limit]

    # ---- 5. entity-resolution quality on REAL cross-source identities --
    # the metric the synthetic universe could never produce (D.4's
    # 2,212-entities-from-2,000-records signature of self-authored data). ----
    cross_source_entities = 0
    for eid in entities:
        sources = {
            str(by_artifact_index[a].get("__source_id") or "unknown")
            for t in timelines
            if t.entity.entity_id == eid
            for a in t.artifact_ids
        }
        if len(sources) > 1:
            cross_source_entities += 1
    entity_resolution_quality = {
        "n_captured_records": len(capture.records),
        "n_resolved_entities": len(entities),
        "entities_per_record": round(len(entities) / len(capture.records), 4)
        if capture.records
        else None,
        "cross_source_entities": cross_source_entities,
        "cross_source_entity_fraction": round(cross_source_entities / len(entities), 4)
        if entities
        else None,
    }

    # ---- 6. FIT WIDE -- one baseline from every assembled timeline ----
    classifier = None
    fit_units = x6._build_units(fit_timelines, by_artifact_index, classifier)
    baseline = bl.NormalBaseline(environment_id="c6:corpus-bed")
    baseline.fit(list(fit_units.values()))
    fitted_at_level = baseline.fitted_units_at("L4_WINDOW")

    # ---- bed_report FINAL -- the real records_read/units_fitted/units_scored
    # are only known here (T.2, TASK_BULLY_REAL_TELEMETRY_V1: assess_bed's
    # units_fitted/units_scored are required, so this is the single call this
    # run's PUBLISHED bed_report/bed_acceptance are computed from -- never the
    # records_read=0 placeholder the pre-flight check above used). ----
    bed = corpus_bed.assess_bed(
        records_available,
        records_read=len(capture.records),
        units_fitted=fitted_at_level,
        units_scored=len(score_timelines),
    )
    if not bed.is_haystack:
        report = {
            "plane": "INVALID",
            "reason": "not_a_haystack",
            "bed_report": bed.to_dict(),
            "capture": capture.to_dict(),
            "algorithm_version": ALGORITHM_VERSION,
            "generated_at": time.time(),
        }
        _publish(report, args.out_dir, args.doc_stem)
        print(json.dumps(report, indent=2))
        return 1

    if fitted_at_level < corpus_bed.MIN_BASELINE_UNITS:
        report = {
            "plane": "BLOCKED",
            "reason": (
                f"baseline_undersized: fitted_units_at('L4_WINDOW')={fitted_at_level} "
                f"< corpus_bed.MIN_BASELINE_UNITS={corpus_bed.MIN_BASELINE_UNITS}"
            ),
            "bed_report": bed.to_dict(),
            "capture": capture.to_dict(),
            "algorithm_version": ALGORITHM_VERSION,
            "generated_at": time.time(),
        }
        _publish(report, args.out_dir, args.doc_stem)
        print(json.dumps(report, indent=2))
        return 1

    # ---- 7. SCORE NARROW -- discovery-first, single cycle (no maturation
    # loop -- C.6 is about floor/product/cost against a real bed, not
    # verdict write-back) ----
    anchor_library = _seed_anchor_library_from_answer_key()
    hunt_config = bully_config.load_hunt_config()
    models = bully_config.resolve_investigation_models(hunt_config=hunt_config)
    store = Store(bully_config.hunt_dir() / "hunt_state.db")
    hunt_id = new_id("hunt")
    store.hunt_create(
        hunt_id=hunt_id,
        objective="C.6 live hunt on the real corpus bed",
        neighborhood_scope="lab-corpus-bed",
        authorization_ref="operator:bully-c6",
        config_version="c6-corpus-bed",
        role_snapshot=models,
        budgets={},
    )
    notify_counter = [0]
    x6._register_anchor_stub_signatures(store, anchor_library)
    rows, _concerns, _sigs, meta = x6._grade_cycle(
        score_timelines,
        by_artifact_index,
        classifier,
        anchor_library,
        store,
        hunt_id,
        1,
        identity_to_class,
        notify_counter,
        baseline,
    )

    # `entities` on each cluster carries raw resolved entity VALUES -- real
    # field content pulled straight out of the real corpus (IPs, hostnames,
    # and occasionally free-text values a source system embedded, up to and
    # including a token-looking string caught live by this repo's
    # pre-commit secret scan). This report is committed to git, so raw
    # corpus content is never published -- `n_distinct_entities` already
    # carries the count this report needs.
    for cluster in meta["cousin_clusters"]:
        cluster.pop("entities", None)

    scoreboard_records = store.scoreboard_records_for_hunt(hunt_id)
    scoreboard_result = scoreboard_mod.update(hunt_id, scoreboard_records)
    known_benign_rows_total = store.known_state_count(kind="known_benign")
    store.close()

    scored_by_assessment = {r["assessment_id"]: r for r in scoreboard_result["records"]}
    for row in rows:
        scored = scored_by_assessment.get(row["assessment_id"])
        if scored is not None:
            row.update(scored)

    # ---- 8. floor / product / cost -- three separate numbers ----
    resembled_techniques = {
        cl["enrichment"]["resembles_technique"]
        for cl in meta["cousin_clusters"]
        if cl["enrichment"].get("resembles_technique")
    }
    floor_hit = sum(1 for e in BOTS_ANSWER_KEY if e.technique in resembled_techniques)

    recovered_cousin_ids: set[str] = set()
    for row in rows:
        cid = cousin_id_by_entity_id.get(row["entity_id"])
        if cid and row.get("concern_raised"):
            recovered_cousin_ids.add(cid)
    cousin_total = len(cousins)
    cousin_hit = len(recovered_cousin_ids)

    background_rows = [r for r in rows if r["implant_class_ground_truth"] == "background"]
    background_flagged = sum(1 for r in background_rows if r["concern_raised"])

    acceptance = corpus_bed.bed_acceptance(
        answer_key_hit=floor_hit,
        answer_key_total=len(BOTS_ANSWER_KEY),
        cousin_hit=cousin_hit,
        cousin_total=cousin_total,
        background_flagged=background_flagged,
        background_total=len(background_rows),
        bed=bed,
    )

    per_transformation: dict[str, dict[str, int]] = {}
    for cousin in cousins:
        bucket = per_transformation.setdefault(cousin.transformation, {"total": 0, "recovered": 0})
        bucket["total"] += 1
        if cousin.cousin_id in recovered_cousin_ids:
            bucket["recovered"] += 1
    per_transformation_recovery = {
        t: {**v, "recall": round(v["recovered"] / v["total"], 4) if v["total"] else None}
        for t, v in per_transformation.items()
    }

    # ---- 9. degeneracy / selection / poisoning (Y.1/Y.3 machinery, reused) --
    degeneracy = ta.degeneracy_check(rows).to_dict()
    implant_entity_ids = set(cousin_id_by_entity_id)
    scored_entity_ids = {r["entity_id"] for r in rows}
    selection = ta.selection_report(
        n_implants_shipped=sum(r.n_events for r in inject_reports),
        implant_entity_ids=implant_entity_ids,
        selected_entity_ids=scored_entity_ids,
    )
    poisoning = ta.poisoning_report([])  # no scripted verdicts issued this run

    resembles_nothing_clusters = [
        c for c in meta["cousin_clusters"] if c["enrichment"]["resembles_nothing"]
    ]

    report: dict[str, Any] = {
        "plane": "live",
        "grader_entry_point": meta["grader_entry_point"],
        "algorithm_version": ALGORITHM_VERSION,
        "generated_at": time.time(),
        "duration_s": round(time.time() - started_at, 2),
        "hunt_id": hunt_id,
        "bed_report": bed.to_dict(),
        "bed_acceptance": acceptance.to_dict(),
        "answer_key": [e.to_dict() for e in BOTS_ANSWER_KEY],
        "cousins_injected": [c.to_dict() for c in cousins],
        "inject_reports": [r.to_dict() for r in inject_reports],
        "per_transformation_cousin_recovery": per_transformation_recovery,
        "capture": capture.to_dict(),
        "correlation": {
            "n_observations": len(observations),
            "n_resolved_entities": len(entities),
            "n_timelines_fit": len(fit_timelines),
            "n_timelines_scored": len(score_timelines),
            "baseline_fitted_units_l4_window": fitted_at_level,
        },
        "entity_resolution_quality": entity_resolution_quality,
        "classifier_coverage_report": classifier_coverage.to_dict(),
        "discovery": {
            "discovery_report": meta["discovery_report"],
            "cousin_clusters": meta["cousin_clusters"],
            "n_resembles_nothing_clusters": len(resembles_nothing_clusters),
        },
        "degeneracy_check": degeneracy,
        "selection_report": selection.to_dict(),
        "poisoning_report": poisoning.to_dict(),
        "notifications_dispatched": notify_counter[0],
        "scoreboard": {k: v for k, v in scoreboard_result.items() if k != "records"},
        "correctness_axis_provenance": {"known_benign_rows_total": known_benign_rows_total},
        "per_row": rows,
    }

    self_check = conformance_mod.conformance_report(report)
    report["conformance_self_check"] = self_check
    if self_check["verdict"] == "FAIL":
        print("CONFORMANCE SELF-CHECK FAILED -- refusing to publish a PASS doc:")
        print(json.dumps(self_check, indent=2))

    if degeneracy["verdict"] == "FAIL":
        print("DEGENERACY CHECK FAILED -- reporting as measured, not tuning thresholds:")
        print(json.dumps(degeneracy, indent=2))

    _publish(report, args.out_dir, args.doc_stem)
    print(json.dumps({k: v for k, v in report.items() if k != "per_row"}, indent=2, default=str))
    return 0


def _publish(report: dict[str, Any], out_dir: Path, doc_stem: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{doc_stem}.json"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md_path = out_dir / f"{doc_stem}.md"
    md_path.write_text(_render_md(report, doc_stem), encoding="utf-8")


def _render_md(report: dict[str, Any], doc_stem: str) -> str:
    if report.get("plane") in ("BLOCKED", "INVALID"):
        return (
            f"# {doc_stem}\n\n**plane:** {report['plane']}\n\n**reason:** {report.get('reason')}\n\n"
            f"```json\n{json.dumps(report, indent=2, default=str)}\n```\n"
        )
    lines = [
        f"# {doc_stem}",
        "",
        f"Generated {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(report['generated_at']))}"
        f" -- plane **{report['plane']}** -- duration {report['duration_s']}s",
        "",
        "## Bed report (is this a real haystack?) -- published FIRST",
        "",
        f"```json\n{json.dumps(report['bed_report'], indent=2)}\n```",
        "",
        "## Bed acceptance -- floor / product / cost, never averaged",
        "",
        f"```json\n{json.dumps(report['bed_acceptance'], indent=2)}\n```",
        "",
        "## Per-transformation cousin recovery",
        "",
        f"```json\n{json.dumps(report['per_transformation_cousin_recovery'], indent=2)}\n```",
        "",
        "## Entity resolution quality (real cross-source identities)",
        "",
        f"```json\n{json.dumps(report['entity_resolution_quality'], indent=2)}\n```",
        "",
        "## Classifier coverage (measured on records THIS run captured)",
        "",
        f"```json\n{json.dumps(report['classifier_coverage_report'], indent=2)}\n```",
        "",
        "## Discovery",
        "",
        f"```json\nDiscovery report: {json.dumps(report['discovery']['discovery_report'], indent=2)}\n```",
        f"- Clusters resembling nothing: {report['discovery']['n_resembles_nothing_clusters']}",
        "",
        "## Degeneracy check",
        "",
        f"```json\n{json.dumps(report['degeneracy_check'], indent=2)}\n```",
        "",
        "## Selection report (did injected cousins reach the grader)",
        "",
        f"```json\n{json.dumps(report['selection_report'], indent=2)}\n```",
        "",
        "## Poisoning report (no scripted verdicts issued this run)",
        "",
        f"```json\n{json.dumps(report['poisoning_report'], indent=2)}\n```",
        "",
        f"## Scoreboard.update() contract -- {report['conformance_self_check']['verdict']}",
        "",
        f"```json\n{json.dumps(report['scoreboard'], indent=2)}\n```",
        "",
        "## Conformance self-check",
        "",
        f"```json\n{json.dumps(report['conformance_self_check'], indent=2)}\n```",
        "",
        "## Correlation",
        "",
        f"```json\n{json.dumps(report['correlation'], indent=2)}\n```",
        "",
        "## Residual risks",
        "",
        "- BOTS is finite and pre-labelled -- it proves floor and cousin recovery but "
        "cannot prove discovery of genuine novelty; Lane C (Caldera/ART) carries that "
        "claim separately and is not separately driven by this script.",
        "- The published answer key here is a small curated subset of BOTS's full, "
        "far larger official answer key -- floor recall is bounded by what this "
        "module actually encodes, not by everything BOTS documents.",
        "- Background false-positive rate against BOTS is an upper bound on error, "
        "not a count of mistakes: BOTS contains real, undocumented activity a "
        "'false positive' here may in fact be a genuine finding.",
        "- Injected cousins are synthetic inside real data; their realism bounds the "
        "product claim (see `cousins_injected` for the injection recipe).",
        "",
        "## Full per-row data",
        "",
        f"```json\n{json.dumps(report['per_row'], indent=2, default=str)}\n```",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
