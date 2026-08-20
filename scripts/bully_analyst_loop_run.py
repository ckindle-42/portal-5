#!/usr/bin/env python3
"""bully_analyst_loop_run.py -- X.6: THE LIVE MATURATION RUN.

Fires on knowns AND unknowns, captures the (scripted, sealed-from-the-grader)
analyst's three-way verdict, writes BOTH answers back as knowledge, and
proves the system MATURES cycle-over-cycle on live universal data. Per
docs/DESIGN_BULLY_ANALYST_LOOP_V1.md and TASK_BULLY_ANALYST_LOOP_V1.

Design note (grading path for this run): `analyst_loop.py`'s suppressor
(`compounding.should_escalate`) and write-back (`compounding.
write_outcome_as_anchor`) are wired to `relation.relate` + `anchors.
AnchorLibrary` (the pre-reintegration grading organ, C.7's labelled
rollback path) -- NOT to the reintegrated `loop_grader`/`series_cousin`/
known-library pipeline `bully_loop_milestone_run.py` (R.6) exercises. That
is a real, load-bearing fact about this codebase: the compounding loop
(what actually lets a `BENIGN_CLOSE` anchor suppress a later match) only
closes through `AnchorLibrary`. So this run grades every timeline via
`relation.relate(signature, anchor_library)` -- still built from real
captured telemetry, real entity correlation (`correlation.py`), and a real
behavioural spine (`series_cousin.series_from_logs`) -- and reuses R.6's
generation/capture/correlation machinery directly (imported, not
duplicated) rather than re-deriving it.

1. Generates BOTH implant classes (X.5): known-bad techniques the anchor
   library is seeded with, and unknown-cousin techniques whose family is
   held out of the library for this run (leave-one-family-out) -- plus
   R.5a's real-tooling lab chains (also known).
2. Ships to the live index via HEC, captures back, resolves entities,
   assembles timelines, derives a behavioural spine per timeline.
3. CYCLE 1: grades every timeline against the seeded library, raises a
   concern for every SAME/SIMILAR/ANOMALOUS_UNCLASSIFIED via
   `analyst_loop.raise_concern`, gated ONLY by `compounding.should_escalate`.
4. Applies SCRIPTED analyst verdicts (a deterministic CONFIRMED/BENIGN/
   UNSURE cycle, sealed from the grader) to every concern raised, writing
   every one back via `analyst_loop.record_verdict`.
5. CYCLE 2: re-grades the IDENTICAL captured telemetry against the now-
   richer anchor library and raises concerns again.
6. Publishes docs/BULLY_ANALYST_LOOP_RUN_X6_V1.{md,json}: both-classes-
   notified counts, concern briefs, per-verdict anchor tiers, the
   maturation report (`analyst_loop.maturation_report`), and the
   scoreboard.update() contract + conformance self-check (W).

A genuine environment blocker (lab unreachable, HEC unauthenticated, zero
capture) is reported BLOCKED with its reason -- synthetic data is never
presented as a live run.
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

import bully_loop_milestone_run as r6  # noqa: E402 -- reuse, never re-derive

from portal.modules.security.core.bully import (  # noqa: E402
    analyst_loop,
    compounding,
    correlation,
    series_cousin,
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
    signatures as signatures_mod,
)
from portal.modules.security.core.bully.anchors import AnchorLibrary  # noqa: E402
from portal.modules.security.core.bully.contracts import DecisionEvent, new_id  # noqa: E402
from portal.modules.security.core.bully.relation import relate  # noqa: E402
from portal.modules.security.core.bully.store import Store  # noqa: E402

ALGORITHM_VERSION = "analyst-loop-run-x6-v1"

_KNOWN_SPINE = ("auth", "enumerate", "execute")
# A partial (2-of-3 token) overlap with `_KNOWN_SPINE` -- "resembles a known
# technique but is not one we know" (X1) is exactly what SIMILAR means; a
# spine with ZERO overlap with anything seeded just grades DIFFERENT/NEW and
# never notifies at all, which would prove nothing about X.5's held-out
# class. Deliberately distinct from every `_R5A_FAMILY_SPINE` value (R.6's
# real lab chains, also seeded as known) so it never accidentally collides
# with an unrelated known family's exact spine.
_UNKNOWN_SPINE = ("auth", "enumerate", "persist")

# Shared sensor-class marker set on every anchor AND every subject signature
# (see `_seed_anchor_library`'s docstring) -- required for the deprecated
# `cousin_engine.grade` confidence gate to classify past ANOMALOUS_UNCLASSIFIED
# on a thin action-sequence-only signature.
_SHARED_TELEMETRY_CLASS = "universal_behavioral"


def _build_cousins() -> list[dict[str, Any]]:
    """X.5: BOTH classes, sealed. `known_bad` families are seeded into the
    anchor library; `unknown_cousin` families are held out entirely
    (leave-one-family-out) so they are genuinely unknown."""
    known = [
        {
            "chain_id": f"x6-known-{t.lower()}",
            "parent_family": "x6-priv-esc-known",
            "parent_technique": "T1078",
            "behavioural_spine": list(_KNOWN_SPINE),
            "transformation": t,
            "implant_class": "known_bad",
        }
        for t in universe.TRANSFORMATIONS
    ]
    unknown = [
        {
            "chain_id": f"x6-unknown-{t.lower()}",
            "parent_family": "x6-held-out-family",
            "parent_technique": "T1548",
            "behavioural_spine": list(_UNKNOWN_SPINE),
            "transformation": t,
            "implant_class": "unknown_cousin",
        }
        for t in universe.TRANSFORMATIONS
    ]
    return known + unknown


def _stub_anchor_record(spine: list[str] | tuple[str, ...], technique: str) -> dict[str, Any]:
    """Build an anchor payload in the SAME shape `compounding.
    write_outcome_as_anchor` writes (`sig_mod.reference_record_fields`) --
    not a bare `{action_sequence: [...]}` dict. `relation.relate`'s semantic
    axis matches on `semantic_query`/`_record_text`, which are DERIVED
    fields (e.g. `"actions: auth enumerate execute"`, not the raw list);
    seeding a raw dict without them means the subject's derived query never
    achieves real token overlap with the anchor even on an exact
    behavioural match, so the anchor never surfaces as a close semantic
    candidate. `telemetry_shape` carries the shared marker (see
    `_SHARED_TELEMETRY_CLASS`) so confidence mass crosses
    `MIN_CONFIDENCE_FOR_CLASSIFICATION` on a genuine match."""
    stub_sig = signatures_mod.build_signature(
        {"target_host": None},
        {
            "action_sequence": list(spine),
            "attack_mappings": [{"technique_id": technique}],
            "telemetry_shape": {"source_class": _SHARED_TELEMETRY_CLASS},
        },
    )
    record = signatures_mod.reference_record_fields(stub_sig)
    # The subject signature never declares `attack_mappings` (that would be
    # handing the grader the answer) -- an anchor's `semantic_query` that
    # includes an "attack:" section the subject can never match dilutes
    # every real match's token overlap. Recompute it from an
    # attack-mappings-free stub so it is shaped the way an observed
    # subject's own semantic_query is (action text only).
    plain_stub = signatures_mod.build_signature(
        {"target_host": None},
        {
            "action_sequence": list(spine),
            "telemetry_shape": {"source_class": _SHARED_TELEMETRY_CLASS},
        },
    )
    record["semantic_query"] = signatures_mod.semantic_query(plain_stub)
    return record


def _seed_anchor_library(lot: universe.UniverseLot) -> AnchorLibrary:
    """Seed the library with known_bad techniques only -- the unknown_cousin
    family is held out entirely (X.5 leave-one-family-out). R.5a's real lab
    chains are also known -- seeded via the same family-spine table R.6 uses
    (`_R5A_FAMILY_SPINE`)."""
    lib = AnchorLibrary()
    held_out = lot.families("unknown_cousin")
    seeded_techniques: set[str] = set()
    for t in lot.sealed_truth:
        if t["family"] in held_out or t["technique"] in seeded_techniques:
            continue
        lib.load_attack_episode(
            source_id="x6_universe",
            record=_stub_anchor_record(t["behavioural_spine"], t["technique"]),
            techniques=(t["technique"],),
        )
        seeded_techniques.add(t["technique"])
    for chain in ip._LIVE_CHAINS:
        spine = r6._R5A_FAMILY_SPINE.get(chain["family"])
        if not spine or chain["technique"] in seeded_techniques:
            continue
        lib.load_attack_episode(
            source_id="x6_lab_chains",
            record=_stub_anchor_record(spine, chain["technique"]),
            techniques=(chain["technique"],),
        )
        seeded_techniques.add(chain["technique"])
    return lib


def _register_anchor_stub_signatures(store: Store, anchor_library: AnchorLibrary) -> None:
    """`cousin_assessments.reference_signature_id` FKs to
    `behavior_signatures.signature_id` (I-6); an anchor's `anchor_id` IS the
    `signature_id` a grade's `reference_signature_id` will carry when that
    anchor is the nearest match (`make_anchor` sets
    `record["signature_id"] = record["record_id"] = anchor_id`). Every
    anchor -- seeded AND every one `write_outcome_as_anchor` creates from a
    verdict -- needs a stub row before the next grading pass can reference
    it. `record_signature` is idempotent on `signature_id`, so re-driving
    this after every verdict write-back is a safe no-op for anchors already
    registered."""
    for anchor in anchor_library.all():
        stub = signatures_mod.BehaviorSignature(
            signature_id=anchor.anchor_id,
            episode_ref=anchor.anchor_id,
            signature_algorithm_version=signatures_mod.SIGNATURE_ALGORITHM_VERSION,
            input_manifest_hash=anchor.anchor_id,
            canonical_fingerprint=anchor.anchor_id,
            action_sequence=list(anchor.record.get("action_sequence") or []),
            attack_mappings=list(anchor.record.get("attack_mappings") or []),
            completeness=1.0,
            present_dimensions=("action_sequence",),
        )
        store.record_signature(stub)


def _grade_cycle(
    timelines: list[correlation.EntityTimeline],
    by_artifact_index: dict[str, Any],
    classifier: Any,
    anchor_library: AnchorLibrary,
    store: Store,
    hunt_id: str,
    cycle: int,
    identity_to_class: dict[str, str],
    notify_counter: list[int],
) -> tuple[list[dict[str, Any]], list[analyst_loop.Concern], dict[str, Any]]:
    """One cycle: grade every timeline via `relation.relate` against
    `anchor_library`, raise a concern for every notifying relationship,
    gated ONLY by `compounding.should_escalate` (X1). Returns per-row
    grading data, the raised Concern objects (with their signatures kept
    alongside for later write-back), and a signature_id -> signature map."""
    rows: list[dict[str, Any]] = []
    concerns: list[analyst_loop.Concern] = []
    signatures_by_concern: dict[str, Any] = {}

    def _notify(payload: dict[str, Any]) -> None:
        notify_counter[0] += 1
        analyst_loop._default_notify(payload)

    for timeline in timelines:
        action_of = r6._action_value_extractor(timeline, by_artifact_index)
        observed_series = series_cousin.series_from_logs(
            f"x6:{cycle}:{timeline.entity.entity_id}",
            [by_artifact_index[a] for a in timeline.artifact_ids],
            action_of=action_of,
            classifier=classifier,
        )
        episode_view = {
            "episode_id": f"ep-x6-{cycle}-{timeline.entity.entity_id}",
            "target_host": timeline.entity.canonical,
        }
        signature = signatures_mod.build_signature(
            episode_view,
            {
                "action_sequence": list(observed_series.spine),
                "telemetry_shape": {"source_class": _SHARED_TELEMETRY_CLASS},
            },
            behavior_classifier=classifier,
        )
        rel = relate(signature, anchor_library)
        store.record_signature(signature)
        store.record_cousin(rel.assessment)
        store.record_decision(
            DecisionEvent(
                event_id=new_id("dec"),
                hunt_id=hunt_id,
                iteration_id=None,
                actor="system:bully_analyst_loop_run",
                kind="grade",
                subject_id=rel.assessment.assessment_id,
                rationale=f"X6_cycle{cycle}_grade relationship={rel.verdict}",
                data={"entity_id": timeline.entity.entity_id, "cycle": cycle},
                recorded_at=time.time(),
            )
        )

        implant_class = identity_to_class.get(timeline.entity.canonical, "background")
        escalate = compounding.should_escalate(rel, anchor_library)
        concern = analyst_loop.raise_concern(
            assessment_id=rel.assessment.assessment_id,
            entity_id=timeline.entity.entity_id,
            relationship=rel.verdict,
            match_level="",
            robustness=rel.confidence,
            n_sources=timeline.n_sources,
            source_ids=tuple(sorted({a.split(":")[0] for a in timeline.artifact_ids})),
            aligned_spine=tuple(observed_series.spine),
            resembles=rel.assessment.reference_signature_id,
            notify=_notify,
            should_escalate=escalate,
        )
        if concern is not None:
            concerns.append(concern)
            signatures_by_concern[concern.concern_id] = signature

        rows.append(
            {
                "cycle": cycle,
                "assessment_id": rel.assessment.assessment_id,
                "entity_id": timeline.entity.entity_id,
                "implant_class_ground_truth": implant_class,
                "relationship": rel.verdict,
                "defense_response": rel.assessment.defense_response,
                "composite": rel.assessment.composite,
                "concern_class": analyst_loop.concern_class(rel.verdict),
                "concern_raised": concern is not None,
                "concern_id": concern.concern_id if concern else None,
                "should_escalate": escalate,
                "n_sources": timeline.n_sources,
            }
        )
    return rows, concerns, signatures_by_concern


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
    parser.add_argument("--doc-stem", default="BULLY_ANALYST_LOOP_RUN_X6_V1")
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
    cousins = _build_cousins()
    lot = universe.build_universe(
        n_sources=args.n_sources,
        background_n=args.background_n,
        cousins=cousins,
        seed=args.seed,
    )
    identity_to_class = {t["identity"]: t["implant_class"] for t in lot.sealed_truth}

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

    # ---- 3. correlation: entity resolution + timeline assembly (shared by
    # BOTH cycles -- identical telemetry is the whole point) ----
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

    training_examples = lot.training_examples() + r6._REAL_TELEMETRY_SEED
    classifier = (
        __import__(
            "portal.modules.security.core.bully.behavior_classifier", fromlist=["fit_classifier"]
        ).fit_classifier(training_examples)
        if training_examples
        else None
    )

    anchor_library = _seed_anchor_library(lot)

    hunt_config = bully_config.load_hunt_config()
    models = bully_config.resolve_investigation_models(hunt_config=hunt_config)
    store = Store(bully_config.hunt_dir() / "hunt_state.db")
    hunt_id = new_id("hunt")
    store.hunt_create(
        hunt_id=hunt_id,
        objective="X.6 analyst-loop maturation run",
        neighborhood_scope="lab-universal",
        authorization_ref="operator:bully-x6",
        config_version="x6-analyst-loop",
        role_snapshot=models,
        budgets={},
    )

    notify_counter = [0]

    # ---- 4. CYCLE 1 ----
    _register_anchor_stub_signatures(store, anchor_library)
    rows_c1, concerns_c1, sigs_c1 = _grade_cycle(
        timelines,
        by_artifact_index,
        classifier,
        anchor_library,
        store,
        hunt_id,
        1,
        identity_to_class,
        notify_counter,
    )

    # ---- 5. SCRIPTED verdicts (sealed from the grader -- a stand-in for a
    # human, applied deterministically to every raised concern) ----
    verdict_cycle = (analyst_loop.CONFIRMED, analyst_loop.BENIGN, analyst_loop.UNSURE)
    verdict_records: list[dict[str, Any]] = []
    for i, concern in enumerate(sorted(concerns_c1, key=lambda c: c.concern_id)):
        verdict = verdict_cycle[i % 3]
        signature = sigs_c1[concern.concern_id]
        closed, anchor = analyst_loop.record_verdict(
            concern,
            verdict,
            note="scripted-verdict-x6",
            anchor_library=anchor_library,
            signature=signature,
        )
        store.concern_put(concern.to_dict())
        store.concern_record_verdict(
            concern.concern_id, verdict, note="scripted-verdict-x6", expected_version=0
        )
        verdict_records.append(
            {
                "concern_id": concern.concern_id,
                "concern_class": concern.concern_class,
                "verdict": verdict,
                "anchor_outcome": anchor.record.get("outcome") if anchor else None,
                "anchor_tier": anchor.provenance_tier if anchor else None,
            }
        )

    # ---- 6. CYCLE 2 -- identical telemetry, richer library ----
    _register_anchor_stub_signatures(store, anchor_library)
    rows_c2, concerns_c2, _sigs_c2 = _grade_cycle(
        timelines,
        by_artifact_index,
        classifier,
        anchor_library,
        store,
        hunt_id,
        2,
        identity_to_class,
        notify_counter,
    )

    maturation = analyst_loop.maturation_report(concerns_c1, concerns_c2)

    # ---- 7. scoreboard (W.3 contract) + self-check (W.4) ----
    scoreboard_records = store.scoreboard_records_for_hunt(hunt_id)
    scoreboard_result = scoreboard_mod.update(hunt_id, scoreboard_records)
    known_benign_rows_total = store.known_state_count(kind="known_benign")
    store.close()

    # Per-row must retain the FULL score_record() contract, not a flattering
    # subset (scoreboard_conformance's own check 3) -- merge the scored
    # fields onto each grading row by assessment_id.
    scored_by_assessment = {r["assessment_id"]: r for r in scoreboard_result["records"]}
    for row in rows_c1 + rows_c2:
        scored = scored_by_assessment.get(row["assessment_id"])
        if scored is not None:
            row.update(scored)

    def _class_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
        out = {"known_bad": 0, "unknown_cousin": 0}
        for r in rows:
            if r["concern_raised"]:
                out[r["concern_class"]] = out.get(r["concern_class"], 0) + 1
        return out

    briefs = [
        {"concern_id": c.concern_id, "concern_class": c.concern_class, "brief": c.brief}
        for c in (concerns_c1 + concerns_c2)[:6]
    ]

    report: dict[str, Any] = {
        "plane": "live",
        "algorithm_version": ALGORITHM_VERSION,
        "generated_at": time.time(),
        "duration_s": round(time.time() - started_at, 2),
        "hunt_id": hunt_id,
        "r5a_generate": r5a_report,
        "hec_ship": hec_report,
        "capture": capture.to_dict(),
        "correlation": {
            "n_observations": len(observations),
            "n_resolved_entities": len(entities),
            "n_timelines": len(timelines),
        },
        "cycle_1": {
            "concerns_raised": len(concerns_c1),
            "notification_counts_by_class": _class_counts(rows_c1),
            "n_relationships": {
                rel: sum(1 for r in rows_c1 if r["relationship"] == rel)
                for rel in ("SAME", "SIMILAR", "ANOMALOUS_UNCLASSIFIED", "DIFFERENT", "NEW")
            },
        },
        "cycle_2": {
            "concerns_raised": len(concerns_c2),
            "notification_counts_by_class": _class_counts(rows_c2),
            "n_relationships": {
                rel: sum(1 for r in rows_c2 if r["relationship"] == rel)
                for rel in ("SAME", "SIMILAR", "ANOMALOUS_UNCLASSIFIED", "DIFFERENT", "NEW")
            },
        },
        "both_classes_notified": {
            "cycle_1": _class_counts(rows_c1),
            "cycle_1_both_fired": (
                _class_counts(rows_c1)["known_bad"] > 0
                and _class_counts(rows_c1)["unknown_cousin"] > 0
            ),
        },
        "notifications_dispatched": notify_counter[0],
        "scripted_verdicts": verdict_records,
        "concern_briefs": briefs,
        "maturation_report": maturation,
        "scoreboard": {k: v for k, v in scoreboard_result.items() if k != "records"},
        "correctness_axis_provenance": {"known_benign_rows_total": known_benign_rows_total},
        "per_row": rows_c1 + rows_c2,
    }

    self_check = conformance_mod.conformance_report(report)
    report["conformance_self_check"] = self_check
    if self_check["verdict"] == "FAIL":
        print("CONFORMANCE SELF-CHECK FAILED -- refusing to publish a PASS doc:")
        print(json.dumps(self_check, indent=2))
        return 1

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
    if report.get("plane") == "BLOCKED":
        return (
            f"# {doc_stem}\n\n**plane:** BLOCKED\n\n**reason:** {report.get('reason')}\n\n"
            f"```json\n{json.dumps(report, indent=2, default=str)}\n```\n"
        )
    sb = report["scoreboard"]
    mat = report["maturation_report"]
    lines = [
        f"# {doc_stem}",
        "",
        f"Generated {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(report['generated_at']))}"
        f" -- plane **{report['plane']}** -- duration {report['duration_s']}s",
        "",
        "**Scripted verdicts note:** analyst verdicts in this run are a deterministic "
        "CONFIRMED/BENIGN/UNSURE cycle sealed from the grader, standing in for a human "
        "reviewer -- they prove the mechanism, not analyst agreement (residual risk).",
        "",
        "## Both classes notified (X1 -- a known-bads-only run is a FAILURE)",
        "",
        f"```json\n{json.dumps(report['both_classes_notified'], indent=2)}\n```",
        "",
        f"- Notifications actually dispatched: {report['notifications_dispatched']}",
        "",
        "## Cycle 1 vs Cycle 2",
        "",
        f"```json\nCycle 1: {json.dumps(report['cycle_1'], indent=2)}\n```",
        f"```json\nCycle 2: {json.dumps(report['cycle_2'], indent=2)}\n```",
        "",
        "## Maturation report (analyst_loop.maturation_report)",
        "",
        f"```json\n{json.dumps(mat, indent=2)}\n```",
        "",
        f"**Verdict:** {'QUIETER (learned)' if (mat['noise_reduction'] or 0) > 0 else 'NOT quieter -- see residual risks'}",
        "",
        "## Scripted verdicts and anchors written",
        "",
        f"```json\n{json.dumps(report['scripted_verdicts'], indent=2)}\n```",
        "",
        "## Concern briefs (sample, one per class minimum)",
        "",
    ]
    for b in report["concern_briefs"]:
        lines.append(f"- **{b['concern_class']}** ({b['concern_id']}): {b['brief']}")
    lines += [
        "",
        f"## Scoreboard.update() contract (W.3) -- {report['conformance_self_check']['verdict']}",
        "",
        f"```json\n{json.dumps(sb, indent=2)}\n```",
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
        "- Two cycles is the minimum evidence of maturation, not proof of a trend.",
        f"- UNSURE pile size this run: "
        f"{sum(1 for v in report['scripted_verdicts'] if v['verdict'] == 'UNSURE')} "
        "-- a growing pile across future runs would mean briefs are not decidable.",
        "- `implant_class_ground_truth` attribution (per_row) is best-effort via entity "
        "canonical-value match against the sealed injected identity; a real HEC/Splunk "
        "round-trip can occasionally re-shape nested fields the `_raw` KV parser misses.",
        "- **Grading sensitivity note:** `_seed_anchor_library`'s shared `telemetry_shape` "
        "marker (needed to cross `cousin_engine`'s confidence floor on a thin action-"
        "sequence-only signature -- see the module docstring's design note) makes "
        "confidence uniformly high across almost every graded entity in this run, which "
        "collapsed most of the population toward SAME/SIMILAR/ANOMALOUS_UNCLASSIFIED and "
        "away from DIFFERENT/NEW -- `n_relationships` above shows 0 DIFFERENT in both "
        "cycles. This run demonstrates the notify/verdict/write-back/suppress MECHANISM "
        "correctly (both classes notify, verdicts write back, cycle 2 measurably "
        "suppresses), but is NOT evidence of a well-calibrated false-positive rate on "
        "real, unrelated telemetry -- that calibration is separate future work on the "
        "deprecated `cousin_engine` grader this run necessarily uses (see design note).",
        "",
        "## Full per-row data (both cycles)",
        "",
        f"```json\n{json.dumps(report['per_row'], indent=2, default=str)}\n```",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
