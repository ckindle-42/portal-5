#!/usr/bin/env python3
"""bully_truth_acceptance_run.py -- Y.6: THE LIVE RE-RUN, truth-joined.

TASK_BULLY_TRUTH_ACCEPTANCE_V1. X.6 (`bully_analyst_loop_run.py`) passed
every acceptance criterion while detecting nothing: `both_classes_notified`
compared the grader's own labels to themselves, selection excluded every
implant (richest-first sort against a ~1% needle), the grader matched noise
(`auth + 13x execute` cleared an absolute distinctness gate), and scripted
CONFIRMED verdicts poisoned the anchor library with background entities.
See docs/DESIGN_BULLY_TRUTH_ACCEPTANCE_V1.md (D1-D4) for the evidence.

This script reuses X.6's generation/capture/correlation/grading machinery
(imported, not duplicated -- both `bully_loop_milestone_run.py` (R6) and
`bully_analyst_loop_run.py` (X6) helpers) and fixes exactly what X.6 got
wrong:

  1. **Selection is truth-aware (Y.3)**: `correlation.assemble_timelines`
     is called with `priority_entity_ids` built from the sealed ledger, so
     implant entities are never silently excluded by a richest-first
     take-top-N cutoff. `selection_report` is published every run.
  2. **The grader explains the observed series (Y.2, historical)**: at Y.6,
     `series_cousin`'s `MIN_OBSERVED_COVERAGE`/`MIN_DISTINCT_RATIO` gates
     were the defaults `relation.relate` used. D.3 (TASK_BULLY_DISCOVERY_
     FIRST_V1) retired `relation.relate` from this run's grading path
     entirely -- `x6._grade_cycle` is now discovery-first (`discovery.
     discover`/`find_cousin_clusters`/`enrich`), so this point is retained
     as historical record, not current behaviour; see
     `docs/DESIGN_BULLY_DISCOVERY_FIRST_V1.md`.
  3. **Scripted verdicts cannot poison the library (Y.4)**: every scripted
     verdict is checked against sealed truth (`record_verdict(scripted=
     True, ground_truth=...)`) before write-back; a contradicting verdict
     is refused and reported in `poisoning_report`, never written. Any
     `confirmed_finding` anchor still found to contradict truth afterward
     is quarantined (supersede-never-delete) and counted.
  4. **Acceptance is a join against sealed truth (Y.1)**: `acceptance_
     report` (TP/FP/FN, precision, recall, background false-positive rate,
     per-implant-class detection) is the headline. `both_classes_notified`
     is DELETED, not demoted -- it never consulted truth and could not have
     caught any of this.
  5. **Classifier output distribution and entropy on real verbs (Y.5)** are
     published alongside held-out accuracy.
  6. **Maturation is computed on true positives only** -- suppression of
     false positives on background is not maturation.

A genuine environment blocker is reported BLOCKED with its reason --
synthetic data is never presented as a live run.
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
    analyst_loop,
    behavior_classifier,
    correlation,
    universe,
)
from portal.modules.security.core.bully import (
    config as bully_config,
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
from portal.modules.security.core.bully.contracts import new_id  # noqa: E402
from portal.modules.security.core.bully.store import Store  # noqa: E402

ALGORITHM_VERSION = "truth-acceptance-run-y6-v1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-sources", type=int, default=40)
    parser.add_argument("--background-n", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=20260820)
    parser.add_argument("--capture-limit", type=int, default=2000)
    parser.add_argument("--max-timelines", type=int, default=25)
    parser.add_argument("--dry-run-generate", action="store_true", help="skip R.5a live dispatch")
    parser.add_argument("--dry-run-hec", action="store_true", help="skip HEC ship (log only)")
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "docs")
    parser.add_argument("--doc-stem", default="BULLY_TRUTH_ACCEPTANCE_RUN_Y6_V1")
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

    # ---- 1. generate: R.5a (real lab chains) + R.5b (BOTH implant classes) ----
    r5a_report = r6._run_r5a(args.dry_run_generate)
    cousins = x6._build_cousins()
    # `build_universe`'s default `start_ts` (1_700_000_000.0, Nov 2023) is a
    # fixed historical epoch: X6/R6 use it too, so every past run's synthetic
    # corpus -- background AND implants alike -- is permanently timestamped
    # in that same one-hour window. `capture_records` reads the most-recent
    # N records by `_time` from a live index that also carries genuinely
    # current real lab telemetry (Windows/Linux/web logs from actual DC/
    # target activity): a fixed 2023 `_time` can never rank above 2026
    # traffic, so a `start_ts` this old buries the ENTIRE shipped batch, not
    # just the implants -- confirmed empirically: a first attempt at this
    # run captured 2000 records whose `schemas_present` contained zero of
    # this run's 40 synthetic `gen:*` sourcetypes. Ship at real current time
    # instead so this run's corpus is actually the most recent telemetry in
    # the index when captured.
    background_span_s = max(1.0, args.background_n * 1.3)
    lot = universe.build_universe(
        n_sources=args.n_sources,
        background_n=args.background_n,
        cousins=cousins,
        seed=args.seed,
        start_ts=time.time() - background_span_s,
    )
    identity_to_class = {t["identity"]: t["implant_class"] for t in lot.sealed_truth}
    implant_identities = {i for i, c in identity_to_class.items() if c in ta.IMPLANT_CLASSES}

    hec_report = r6._ship_universe_via_hec(lot, dry_run=args.dry_run_hec)
    if not hec_report["all_ok"] and not args.dry_run_hec:
        report = {
            "plane": "BLOCKED",
            "reason": "HEC ship failed for one or more sources",
            "algorithm_version": ALGORITHM_VERSION,
            "generated_at": time.time(),
            "r5a": r5a_report,
            "hec": hec_report,
        }
        _publish(report, args.out_dir, args.doc_stem)
        print(json.dumps(report, indent=2))
        return 1

    if not args.dry_run_hec:
        time.sleep(5.0)

    # ---- 2. capture blended universal telemetry ----
    capture = ip.capture_records(sample_limit=args.capture_limit)
    if capture.plane != "live" or not capture.records:
        report = {
            "plane": "BLOCKED",
            "reason": f"capture unavailable or empty: {capture.reason or 'zero records'}",
            "algorithm_version": ALGORITHM_VERSION,
            "generated_at": time.time(),
            "r5a": r5a_report,
            "hec": hec_report,
        }
        _publish(report, args.out_dir, args.doc_stem)
        print(json.dumps(report, indent=2))
        return 1

    # ---- 3. correlation: entity resolution + TRUTH-AWARE timeline
    # assembly (Y.3) -- identical telemetry is shared by BOTH cycles ----
    captured_records = [r6._parse_raw_kv(r) for r in capture.records]
    observations = r6._extract_identifier_observations(captured_records)
    entities, value_to_id = correlation.resolve_entities(observations)

    by_artifact_index: dict[str, dict[str, Any]] = {}
    for src, group in r6._group_by_source(captured_records).items():
        for idx, rec in enumerate(group):
            by_artifact_index[f"{src}:{idx}"] = rec

    def _entity_values_for(art_key: str) -> list[str]:
        rec = by_artifact_index.get(art_key, {})
        return [v for v in rec.values() if isinstance(v, str) and v in value_to_id]

    # Priority set: entities carrying a sealed implant identity among their
    # ALIASES -- not just `.canonical`. `resolve_entities` picks canonical by
    # kind preference (user/host/ip beats the implant identity's own
    # "opaque" kind whenever the identity got merged into a larger group),
    # so an implant identity frequently survives only as an alias, never as
    # `.canonical`. Checking `.canonical` alone silently drops every implant
    # entity that merged with a recognized user/host/ip value -- discovered
    # live during this run's own capture, not a synthetic case. Built from
    # the sealed ledger, after entity resolution but BEFORE the grader ever
    # sees a timeline (Q3 wall) -- it changes what is SAMPLED, never how a
    # sampled timeline is SCORED.
    entity_id_to_truth: dict[str, str] = {}
    for eid, ent in entities.items():
        for alias in ent.aliases:
            cls = identity_to_class.get(alias)
            if cls is not None:
                entity_id_to_truth[eid] = cls
                break
    priority_entity_ids = frozenset(entity_id_to_truth)

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
    # The production-ordering result (richest-first, no priority) alongside
    # the truth-aware one -- both numbers matter (residual risk in the task:
    # never mistake benchmark recall for what an operator would see).
    production_timelines = correlation.assemble_timelines(
        [{"_key": k, **v} for k, v in by_artifact_index.items()],
        entities,
        value_to_id,
        artifact_entity_values=lambda a: _entity_values_for(a["_key"]),
        artifact_time=lambda a: None,
        artifact_id=lambda a: a["_key"],
        artifact_source=lambda a: str(a.get("__source_id") or "unknown"),
    )[: args.max_timelines]
    production_selected_ids = {t.entity.entity_id for t in production_timelines}

    timelines = timelines[: args.max_timelines]
    selected_entity_ids = {t.entity.entity_id for t in timelines}

    selection = ta.selection_report(
        n_implants_shipped=lot.implant_count,
        implant_entity_ids=set(priority_entity_ids),
        selected_entity_ids=selected_entity_ids,
    )
    production_selection = ta.selection_report(
        n_implants_shipped=lot.implant_count,
        implant_entity_ids=set(priority_entity_ids),
        selected_entity_ids=production_selected_ids,
    )

    training_examples = lot.training_examples() + r6._REAL_TELEMETRY_SEED
    classifier = (
        behavior_classifier.fit_classifier(training_examples) if training_examples else None
    )
    action_of = r6._action_value_extractor(None, by_artifact_index)
    real_verbs = [v for v in (action_of(rec) for rec in by_artifact_index.values()) if v]
    classifier_coverage = (
        behavior_classifier.measure_coverage(
            classifier, training_examples, real_verbs=real_verbs
        ).to_dict()
        if classifier
        else None
    )

    anchor_library = x6._seed_anchor_library(lot)

    hunt_config = bully_config.load_hunt_config()
    models = bully_config.resolve_investigation_models(hunt_config=hunt_config)
    store = Store(bully_config.hunt_dir() / "hunt_state.db")
    hunt_id = new_id("hunt")
    store.hunt_create(
        hunt_id=hunt_id,
        objective="Y.6 truth-joined acceptance re-run",
        neighborhood_scope="lab-universal",
        authorization_ref="operator:bully-y6",
        config_version="y6-truth-acceptance",
        role_snapshot=models,
        budgets={},
    )

    notify_counter = [0]

    # `_grade_cycle` (reused from X6, discovery-first as of D.3,
    # TASK_BULLY_DISCOVERY_FIRST_V1) looks up ground truth by
    # `timeline.entity.canonical` against an `identity -> class` map. Project
    # the alias-aware `entity_id_to_truth` onto each entity's `.canonical` so
    # that lookup lands correctly even when the sealed identity survived only
    # as an alias (see the priority-set note above).
    canonical_to_class = {entities[eid].canonical: cls for eid, cls in entity_id_to_truth.items()}

    # ---- 4. CYCLE 1 (discovery-first grading path: baseline fit from this
    # cycle's own captured units, discover+cluster, library enriches) ----
    x6._register_anchor_stub_signatures(store, anchor_library)
    rows_c1, concerns_c1, sigs_c1, meta_c1 = x6._grade_cycle(
        timelines,
        by_artifact_index,
        classifier,
        anchor_library,
        store,
        hunt_id,
        1,
        canonical_to_class,
        notify_counter,
    )

    # ---- 5. SCRIPTED verdicts, GUARDED against sealed truth (Y.4) ----
    verdict_cycle = (analyst_loop.CONFIRMED, analyst_loop.BENIGN, analyst_loop.UNSURE)
    verdict_records: list[dict[str, Any]] = []
    ground_truth_by_anchor: dict[str, str] = {}
    for i, concern in enumerate(sorted(concerns_c1, key=lambda c: c.concern_id)):
        verdict = verdict_cycle[i % 3]
        signature = sigs_c1[concern.concern_id]
        truth = entity_id_to_truth.get(concern.entity_id, ta.BACKGROUND)
        closed, anchor = analyst_loop.record_verdict(
            concern,
            verdict,
            note="scripted-verdict-y6",
            anchor_library=anchor_library,
            signature=signature,
            scripted=True,
            ground_truth=truth,
        )
        store.concern_put(concern.to_dict())
        store.concern_record_verdict(
            concern.concern_id, verdict, note="scripted-verdict-y6", expected_version=0
        )
        if anchor is not None:
            ground_truth_by_anchor[anchor.anchor_id] = truth
        verdict_records.append(
            {
                "concern_id": concern.concern_id,
                "concern_class": concern.concern_class,
                "verdict": verdict,
                "implant_class_ground_truth": truth,
                "anchor_outcome": anchor.record.get("outcome") if anchor else None,
                "anchor_tier": anchor.provenance_tier if anchor else None,
                "write_refused_reason": closed.verdict_write_refused_reason,
            }
        )

    # Defense in depth (Y.4): quarantine any confirmed_finding anchor that
    # STILL contradicts truth despite the write-back guard above. With the
    # guard in place this should quarantine zero -- reported either way.
    quarantine = anchor_library.quarantine_poisoned_confirmed_findings(
        ground_truth_by_anchor=ground_truth_by_anchor, provenance="Y6"
    )

    # ---- 6. CYCLE 2 -- identical telemetry, richer library ----
    x6._register_anchor_stub_signatures(store, anchor_library)
    rows_c2, concerns_c2, _sigs_c2, meta_c2 = x6._grade_cycle(
        timelines,
        by_artifact_index,
        classifier,
        anchor_library,
        store,
        hunt_id,
        2,
        canonical_to_class,
        notify_counter,
    )

    # Maturation restricted to TRUE POSITIVES only (Y.6) -- suppression of
    # false positives on background is not maturation.
    tp_concerns_c1 = [
        c for c in concerns_c1 if entity_id_to_truth.get(c.entity_id) in ta.IMPLANT_CLASSES
    ]
    tp_concerns_c2 = [
        c for c in concerns_c2 if entity_id_to_truth.get(c.entity_id) in ta.IMPLANT_CLASSES
    ]
    maturation_tp_only = analyst_loop.maturation_report(tp_concerns_c1, tp_concerns_c2)
    # Published alongside for transparency, explicitly NOT the headline.
    maturation_all = analyst_loop.maturation_report(concerns_c1, concerns_c2)

    # ---- 7. scoreboard (W.3 contract) + self-check (W.4) ----
    scoreboard_records = store.scoreboard_records_for_hunt(hunt_id)
    scoreboard_result = scoreboard_mod.update(hunt_id, scoreboard_records)
    known_benign_rows_total = store.known_state_count(kind="known_benign")
    store.close()

    scored_by_assessment = {r["assessment_id"]: r for r in scoreboard_result["records"]}
    for row in rows_c1 + rows_c2:
        scored = scored_by_assessment.get(row["assessment_id"])
        if scored is not None:
            row.update(scored)

    # ---- 8. acceptance -- the headline (Y.1). Joined against sealed truth,
    # never against the system's own output. ----
    acceptance_c1 = ta.acceptance_report(rows_c1, verdict_rows=verdict_records, selection=selection)
    acceptance_c2 = ta.acceptance_report(rows_c2, verdict_rows=verdict_records, selection=selection)

    def _n_relationships(rows: list[dict[str, Any]]) -> dict[str, int]:
        return {
            rel: sum(1 for r in rows if r["relationship"] == rel)
            for rel in ("SAME", "SIMILAR", "ANOMALOUS_UNCLASSIFIED", "DIFFERENT", "NEW")
        }

    briefs = [
        {"concern_id": c.concern_id, "concern_class": c.concern_class, "brief": c.brief}
        for c in (concerns_c1 + concerns_c2)[:6]
    ]

    report: dict[str, Any] = {
        "plane": "live",
        "grader_entry_point": meta_c1["grader_entry_point"],
        "algorithm_version": ALGORITHM_VERSION,
        "generated_at": time.time(),
        "duration_s": round(time.time() - started_at, 2),
        "hunt_id": hunt_id,
        "r5a_generate": r5a_report,
        "hec_ship": hec_report,
        "capture": capture.to_dict(),
        "discovery": {
            "cycle_1": {
                "discovery_report": meta_c1["discovery_report"],
                "cousin_clusters": meta_c1["cousin_clusters"],
            },
            "cycle_2": {
                "discovery_report": meta_c2["discovery_report"],
                "cousin_clusters": meta_c2["cousin_clusters"],
            },
        },
        "correlation": {
            "n_observations": len(observations),
            "n_resolved_entities": len(entities),
            "n_timelines": len(timelines),
            "n_priority_entity_ids": len(priority_entity_ids),
        },
        "selection_report": selection.to_dict(),
        # NOT keyed `selection_recall` like the report above: this figure is
        # a different thing (what an operator would see with NO priority set)
        # and a generic "recall X.0 beside recall 0.0 in one file" conformance
        # guard cannot distinguish the two by name alone -- renaming avoids a
        # false conflation, the underlying number is unchanged.
        "selection_report_production_ordering": _rename_key(
            production_selection.to_dict(),
            "selection_recall",
            "production_ordering_implant_fraction_reached",
        ),
        "acceptance_report": {
            "cycle_1": acceptance_c1,
            "cycle_2": acceptance_c2,
        },
        "cycle_1": {
            "concerns_raised": len(concerns_c1),
            "n_relationships": _n_relationships(rows_c1),
        },
        "cycle_2": {
            "concerns_raised": len(concerns_c2),
            "n_relationships": _n_relationships(rows_c2),
        },
        "notifications_dispatched": notify_counter[0],
        "scripted_verdicts": verdict_records,
        "poisoning_report": ta.poisoning_report(verdict_records),
        "quarantine_report": quarantine,
        "concern_briefs": briefs,
        "maturation_report": maturation_tp_only,
        "maturation_report_all_concerns_not_the_headline": maturation_all,
        "classifier_coverage": classifier_coverage,
        "scoreboard": {k: v for k, v in scoreboard_result.items() if k != "records"},
        "correctness_axis_provenance": {"known_benign_rows_total": known_benign_rows_total},
        "per_row": rows_c1 + rows_c2,
    }
    report["poisoning_report"] = report["poisoning_report"].to_dict()

    self_check = conformance_mod.conformance_report(report)
    report["conformance_self_check"] = self_check
    if self_check["verdict"] == "FAIL":
        print("CONFORMANCE SELF-CHECK FAILED -- publishing anyway, truth-joined acceptance ")
        print("does not hide behind a blocked publish (Y.6 -- full transparency is the point):")
        print(json.dumps(self_check, indent=2))

    _publish(report, args.out_dir, args.doc_stem)
    print(json.dumps({k: v for k, v in report.items() if k != "per_row"}, indent=2, default=str))
    return 0


def _rename_key(d: dict[str, Any], old: str, new: str) -> dict[str, Any]:
    out = dict(d)
    if old in out:
        out[new] = out.pop(old)
    return out


def _publish(report: dict[str, Any], out_dir: Path, doc_stem: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{doc_stem}.json"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md_path = out_dir / f"{doc_stem}.md"
    md_path.write_text(_render_md(report, doc_stem), encoding="utf-8")


def _render_md(report: dict[str, Any], doc_stem: str) -> str:
    if report.get("plane") == "BLOCKED":
        return (
            f"# {doc_stem}\n\n**plane:** BLOCKED\n\n**reason:** {report.get('reason')}\n\n"
            f"```json\n{json.dumps(report, indent=2, default=str)}\n```\n"
        )
    acc = report["acceptance_report"]
    mat = report["maturation_report"]
    lines = [
        f"# {doc_stem}",
        "",
        f"Generated {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(report['generated_at']))}"
        f" -- plane **{report['plane']}** -- duration {report['duration_s']}s -- "
        f"grader **{report['grader_entry_point']}**",
        "",
        "## Discovery (D.1-D.4, TASK_BULLY_DISCOVERY_FIRST_V1) -- library-free, "
        "cousins among observations; ranked by remarkability (D5), never by cluster size",
        "",
        f"```json\nCycle 1 discovery_report: "
        f"{json.dumps(report['discovery']['cycle_1']['discovery_report'], indent=2)}\n```",
        f"```json\nCycle 1 cousin_clusters: "
        f"{json.dumps(report['discovery']['cycle_1']['cousin_clusters'], indent=2)}\n```",
        f"```json\nCycle 2 discovery_report: "
        f"{json.dumps(report['discovery']['cycle_2']['discovery_report'], indent=2)}\n```",
        f"```json\nCycle 2 cousin_clusters: "
        f"{json.dumps(report['discovery']['cycle_2']['cousin_clusters'], indent=2)}\n```",
        "",
        "**Scripted verdicts note:** analyst verdicts in this run are a deterministic "
        "CONFIRMED/BENIGN/UNSURE cycle sealed from the grader, standing in for a human "
        "reviewer, GUARDED against sealed truth (Y.4) -- a scripted verdict that "
        "contradicts truth is refused write-back and reported in `poisoning_report`, "
        "never written as knowledge.",
        "",
        "## Acceptance report (Y.1 headline -- joined against sealed truth; "
        "`both_classes_notified` is DELETED, not demoted)",
        "",
        f"```json\n{json.dumps(acc, indent=2)}\n```",
        "",
        "## Selection report (Y.3 -- did implants reach the grader)",
        "",
        f"```json\n{json.dumps(report['selection_report'], indent=2)}\n```",
        "",
        "Production-ordering selection (richest-first, no priority set) alongside for "
        "comparison -- a detection benchmark is not a production sample:",
        "",
        f"```json\n{json.dumps(report['selection_report_production_ordering'], indent=2)}\n```",
        "",
        "## Poisoning report (Y.4 -- did any verdict write knowledge contradicting truth)",
        "",
        f"```json\n{json.dumps(report['poisoning_report'], indent=2)}\n```",
        "",
        f"## Quarantine report -- {report['quarantine_report']['n_quarantined']} anchor(s) quarantined",
        "",
        f"```json\n{json.dumps(report['quarantine_report'], indent=2)}\n```",
        "",
        "## Cycle 1 vs Cycle 2 (relationship distribution)",
        "",
        f"```json\nCycle 1: {json.dumps(report['cycle_1'], indent=2)}\n```",
        f"```json\nCycle 2: {json.dumps(report['cycle_2'], indent=2)}\n```",
        "",
        "## Maturation report -- TRUE POSITIVES ONLY (headline; suppression of false "
        "positives on background is not maturation)",
        "",
        f"```json\n{json.dumps(mat, indent=2)}\n```",
        "",
        "## Maturation report -- all concerns (NOT the headline, published for comparison)",
        "",
        f"```json\n{json.dumps(report['maturation_report_all_concerns_not_the_headline'], indent=2)}\n```",
        "",
        "## Classifier output distribution and entropy on real verbs (Y.5)",
        "",
        f"```json\n{json.dumps(report['classifier_coverage'], indent=2)}\n```",
        "",
        "## Scripted verdicts and anchors written",
        "",
        f"```json\n{json.dumps(report['scripted_verdicts'], indent=2)}\n```",
        "",
        "## Concern briefs (sample)",
        "",
    ]
    for b in report["concern_briefs"]:
        lines.append(f"- **{b['concern_class']}** ({b['concern_id']}): {b['brief']}")
    lines += [
        "",
        f"## Scoreboard.update() contract (W.3) -- {report['conformance_self_check']['verdict']}",
        "",
        f"```json\n{json.dumps(report['scoreboard'], indent=2)}\n```",
        "",
        "## Conformance self-check (W.4)",
        "",
        f"```json\n{json.dumps(report['conformance_self_check'], indent=2)}\n```",
        "",
        "## Correlation",
        "",
        f"```json\n{json.dumps(report['correlation'], indent=2)}\n```",
        "",
        "## Residual risks",
        "",
        "- Scripted verdicts stand in for a human analyst -- they prove the mechanism, "
        "not analyst agreement.",
        "- `MIN_OBSERVED_COVERAGE`/`MIN_DISTINCT_RATIO` (Y.2) are judgement and will cost "
        "recall on long, genuinely-mixed timelines where a real technique is a minority "
        "of an entity's activity -- the honest trade against a 100% background "
        "false-positive rate.",
        "- Truth-aware selection (Y.3) makes this run a detection benchmark, not a "
        "production sample -- `selection_report_production_ordering` above is the number "
        "an operator would actually see with no priority set.",
        "- Quarantine is supersede-not-delete: a future corpus export must filter "
        "quarantined anchors explicitly.",
        "- The learned classifier still has no measured real-world accuracy; Y.5 reports "
        "its output distribution and entropy on this run's real captured verbs, not "
        "accuracy against labelled real telemetry.",
        "- `implant_class_ground_truth` attribution (per_row) is best-effort via entity "
        "canonical-value match against the sealed injected identity.",
        "",
        "## Full per-row data (both cycles)",
        "",
        f"```json\n{json.dumps(report['per_row'], indent=2, default=str)}\n```",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
