#!/usr/bin/env python3
"""TASK_BULLY_ADAPTIVE_REACH_V1 (A.6) -- THE LIVE ADAPTIVE-REACH RUN.

Live, across all three BOTS indexes. Unlike I.6 (`bully_investigation_run_
i6.py`, whose flat `MAX_EVENTS` let query one consume the whole budget so
`pivots: 0` on all five investigations), this run uses the adaptive engine
(A1-A5): every query re-scopes against what it actually returns, budget is
reserved per depth, cousins are planted at a known pivot DISTANCE from their
parent's real entity, and recovery is measured by hop rather than by whether
the anchor found its own entity.

Flow, per truth-targeted answer-key technique:
  1. Discover a real anchor entity from the technique's own real sourcetype
     (unchanged from I.6 -- never fabricated).
  2. Run the PRIMARY investigation from that anchor. With adaptive scoping
     this investigation itself pivots, so its own `pivots` list carries
     REAL entities at real hop distances from the anchor -- no separate
     "scouting" pass is needed; the investigation model doing its job IS
     the distance discovery.
  3. Build `entities_by_distance` from those real pivots (first entity seen
     at each of hop 1/2/3) and plant one cousin per known distance (0 hop
     control included) via `corpus_bed.plan_cousins`.
  4. Ship cousins, let them land, then run a RECOVERY investigation from the
     SAME anchor (never from the cousin's own entity -- that would just
     re-measure 0-hop reach) and record which cousins were actually reached
     by the pivot chain.
  5. Publish `distance_recovery` (recall per hop, `max_reached_distance`,
     0-hop explicitly labelled a control) alongside `saturation_report`
     (`pivot_ran` per investigation, and the count where it ran -- the
     headline gating number this task exists to move off zero) and
     `reach_report` over the answer key's documented multi-entity chain
     (single-entity expectations refused, A3).

`bed_acceptance` is mandatory in the published output (A5):
`cost_background_fp_rate` is honestly published as unmeasured (`None`) --
this run has no concern-classifier in the investigation-pivot path, only
reachability, and a fabricated cost figure would be worse than an absent one.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from portal.modules.security.core.bully import adaptive_scope as ascope  # noqa: E402
from portal.modules.security.core.bully import behavior_inference as bi  # noqa: E402
from portal.modules.security.core.bully import (
    corpus_bed,  # noqa: E402
    cousin_inject,  # noqa: E402
    scoreboard,  # noqa: E402
)
from portal.modules.security.core.bully import inject_plane as ip  # noqa: E402
from portal.modules.security.core.bully import investigation_pivot as pivot  # noqa: E402
from portal.modules.security.core.bully import telemetry_behavior as tb  # noqa: E402
from portal.modules.security.core.bully.bots_answer_key import BOTS_ANSWER_KEY  # noqa: E402

ALGORITHM_VERSION = "investigation-run-a6-v1"

T3_UNBOUNDED_SCAN_REC_PER_SEC = 53.0
I6_BOUNDED_UNADAPTIVE_REC_PER_SEC = 950.0

# Real hosts, live-discovered from each technique's own sourcetype in its own
# dataset (unchanged from I.6 -- this lab's real capture naming does not
# always match the answer-key's documented naming).
_DISCOVERED_ANCHORS: dict[str, tuple[str, str]] = {
    "T1558.004": ("WinEventLog", "BGIST-L"),
    "T1071.001": ("stream:http", "gacrux.i-0920036c8ca91e501"),
    "T1496": ("xmlwineventlog", "venus"),
    "T1190": ("stream:http", "splunk-02"),
}

# I.6's own permanent regression case (A7 item 7): the density profile that
# produced pivots:0 there must now pivot here.
I6_DENSITY_ROWS_PER_HOUR = 900


def _discover_ranges(indexes: tuple[str, ...]) -> dict[str, ip.IndexRange]:
    from portal.modules.security.core.bully.live_connect import lab_splunk_connector

    return {
        index: ip.discover_index_range(lab_splunk_connector(index=index), index)
        for index in indexes
    }


def _find_real_anchor_entity(
    index: str, sourcetype: str, extra_filter: str = ""
) -> tuple[str, float] | None:
    from portal.modules.security.core.siem.spl_backend import SplunkBackend

    backend = SplunkBackend()
    spl = f"search index={index} sourcetype={sourcetype} {extra_filter}".strip()
    rows = backend._run_search(spl, "0", "now")
    for row in rows:
        if row.get("host"):
            return str(row["host"]), float(row["_time"])
    return None


def _action_of(r: dict[str, Any]) -> str | None:
    return tb._dig(r, *tb._FIELD_EVENTCODE) or tb._dig(r, "event_type")


def _entities_by_distance_from_pivots(
    pivots: list[dict[str, Any]], anchor_entity: str
) -> dict[int, str]:
    """The real entities a live investigation's OWN pivot chain reached, one
    per hop -- built from `Investigation.pivots` (`{to_entity, depth, ...}`),
    never fabricated. First entity seen at each depth wins."""
    by_depth: dict[int, str] = {0: anchor_entity}
    for p in pivots:
        depth = p.get("depth")
        entity = p.get("to_entity")
        if isinstance(depth, int) and entity and depth not in by_depth:
            by_depth[depth] = str(entity)
    return by_depth


def main() -> int:  # noqa: PLR0915, C901, PLR0912
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="docs")
    parser.add_argument("--doc-stem", default="BULLY_ADAPTIVE_REACH_RUN_A6_V1")
    parser.add_argument("--dry-run-cousins", action="store_true")
    args = parser.parse_args()

    available, reason = ip.lab_available()
    if not available:
        print(json.dumps({"plane": "unavailable", "reason": reason}, indent=2))
        return 1

    datasets = ("botsv1", "botsv2", "botsv3")
    index_ranges = _discover_ranges(datasets)

    anchors: list[pivot.Anchor] = []
    anchor_provenance: dict[str, str] = {}
    anchor_index: dict[str, str] = {}

    found = _find_real_anchor_entity("botsv3", "WinEventLog", "EventCode=4625")
    if found:
        entity, at = found
        anchors.append(
            pivot.Anchor(
                anchor_id="a-discovered-failed-logon",
                at=at,
                entity=entity,
                entity_kind="host",
                sourcetype="WinEventLog",
                why="repeated_failed_logon",
                index="botsv3",
            )
        )
        anchor_provenance["a-discovered-failed-logon"] = "discovered"
        anchor_index["a-discovered-failed-logon"] = "botsv3"

    # The answer key's own DOCUMENTED multi-entity chains (A3), kept
    # separate from the live-discovered single anchor host below: the two
    # are not required to be the same real host, and conflating them would
    # let a live discovery mismatch silently narrow the chain test back to
    # a single entity. `reach_report` is scored against this real,
    # documented chain regardless of which host the investigation's own
    # anchor query happened to start from.
    documented_chains: dict[str, tuple[str, ...]] = {
        e.technique: e.entities for e in BOTS_ANSWER_KEY if len(e.entities) >= 2
    }

    local_answer_key: list[Any] = []
    for entry in BOTS_ANSWER_KEY:
        st, host = _DISCOVERED_ANCHORS.get(entry.technique, (None, None))
        if not host:
            local_answer_key.append(entry)
            continue
        anchor_id = f"a-truth-{entry.technique}"
        found = _find_real_anchor_entity(entry.dataset, st, f'host="{host}"')
        at = found[1] if found else index_ranges[entry.dataset].earliest
        local_answer_key.append(dataclasses.replace(entry, entities=(host,), confirmed_at=at))
        anchors.append(
            pivot.Anchor(
                anchor_id=anchor_id,
                at=at,
                entity=host,
                entity_kind="host",
                sourcetype=st,
                why=f"answer_key:{entry.technique}",
                index=entry.dataset,
            )
        )
        anchor_provenance[anchor_id] = "truth_targeted"
        anchor_index[anchor_id] = entry.dataset

    # ---- PRIMARY investigations (adaptive: A1-A2), grouped by index ----
    per_investigation = []
    total_events = 0
    all_records: list[dict[str, Any]] = []
    investigations_by_anchor_id: dict[str, Any] = {}
    n_pivot_ran = 0
    last_bed_report = None

    t0 = time.time()
    for dataset in datasets:
        dataset_anchors = [a for a in anchors if anchor_index.get(a.anchor_id) == dataset]
        if not dataset_anchors:
            continue
        capture = ip.capture_investigation(dataset_anchors, indexes=(dataset,))
        last_bed_report = capture.bed_report
        for inv in capture.investigations:
            investigations_by_anchor_id[inv.anchor.anchor_id] = inv
            total_events += len(inv.events)
            all_records.extend(inv.events)
            sat = inv.saturation_report
            if sat and sat.pivot_ran:
                n_pivot_ran += 1
            per_investigation.append(
                {
                    "anchor_id": inv.anchor.anchor_id,
                    "anchor_provenance": anchor_provenance.get(inv.anchor.anchor_id, "unknown"),
                    "dataset": dataset,
                    "n_queries": len(inv.queries),
                    "n_events": len(inv.events),
                    "n_entities": len(inv.entities_seen),
                    "sourcetypes": list(inv.sourcetypes),
                    "span_seconds": inv.span_seconds,
                    "truncated_reasons": list(inv.truncated_reasons),
                    "saturation_report": sat.to_dict() if sat else None,
                    "pivots": inv.pivots,
                }
            )
    elapsed = time.time() - t0
    throughput_rec_per_sec = (total_events / elapsed) if elapsed else None

    # ---- reach_report over the answer key's own DOCUMENTED multi-entity
    # chain (A3) -- never the single live-discovered anchor host, which
    # would always be degenerate (one entity, and it IS the anchor) ----
    reach_reports = {}
    for entry in local_answer_key:
        anchor_id = f"a-truth-{entry.technique}"
        inv = investigations_by_anchor_id.get(anchor_id)
        if inv is None:
            continue
        # Techniques with no documented chain still get scored, against the
        # single live-discovered host -- on purpose, to publish the refusal
        # mechanism itself (`degenerate_expectation`) working, not just the
        # cases where a chain happens to be available.
        expected = documented_chains.get(entry.technique) or entry.entities
        r = pivot.reach_report(inv, expected)
        reach_reports[anchor_id] = r.to_dict()

    # ---- classifier coverage + inference report over what was captured ----
    coverage_input = [(r, str(r.get("sourcetype") or "")) for r in all_records]
    coverage = tb.coverage_report(coverage_input)
    profiles = bi.profile_actions(
        all_records,
        action_of=_action_of,
        entity_of=lambda r: [str(v) for _k, v in ip._extract_pivot_entities(r) if v],
        time_of=lambda r: r.get("_time") if isinstance(r.get("_time"), (int, float)) else None,
        sourcetype_of=lambda r: str(r.get("sourcetype") or ""),
    )
    behaviors = bi.infer_behaviors(profiles)
    inference = bi.inference_report(profiles, behaviors)

    # ---- plant cousins at KNOWN PIVOT DISTANCE (A4), using each primary
    # investigation's OWN real pivot chain as the distance source ----
    all_cousins = []
    inject_reports = []
    for entry in local_answer_key:
        rng = index_ranges[entry.dataset]
        if rng.earliest is None or rng.latest is None:
            continue
        anchor_id = f"a-truth-{entry.technique}"
        inv = investigations_by_anchor_id.get(anchor_id)
        anchor_entity = entry.entities[0] if entry.entities else ""
        distances = (
            _entities_by_distance_from_pivots(inv.pivots, anchor_entity)
            if inv is not None
            else {0: anchor_entity}
        )
        dated_entry = dataclasses.replace(entry, entities_by_distance=distances)
        cousins = corpus_bed.plan_cousins(
            [dated_entry],
            corpus_earliest=rng.earliest,
            corpus_latest=rng.latest,
            corpus_sourcetypes=tuple(sorted(coverage.by_sourcetype)),
        )
        all_cousins.extend(cousins)
        inject_reports.extend(
            cousin_inject.inject_cousins(
                cousins,
                index=entry.dataset,
                corpus_earliest=rng.earliest,
                corpus_latest=rng.latest,
                dry_run=args.dry_run_cousins,
            )
        )

    per_transformation_recovery: dict[str, dict[str, int]] = {}
    per_distance_recovery: dict[str, dict[str, dict[str, int]]] = {}
    scoreboard_records: list[dict[str, Any]] = []
    all_planted: list[tuple[str, int]] = []
    all_reached: set[str] = set()

    if not args.dry_run_cousins:
        time.sleep(5.0)  # let HEC-shipped cousin events land before capture
        for entry in local_answer_key:
            host = entry.entities[0] if entry.entities else None
            if not host:
                continue
            rng = index_ranges[entry.dataset]
            entry_cousins = [c for c in all_cousins if c.parent_technique == entry.technique]
            if not entry_cousins:
                continue
            # RECOVERY from the SAME anchor entity, not the cousin's own
            # entity (A4): re-measuring from the cousin's own entity would
            # just repeat I.6's 0-hop measurement.
            recovery_anchor = pivot.Anchor(
                anchor_id=f"a-cousin-recovery-{entry.technique}",
                at=min(c.injected_at for c in entry_cousins),
                entity=host,
                entity_kind="host",
                sourcetype=entry.sourcetypes[0] if entry.sourcetypes else "",
                why=f"cousin_recovery_test:{entry.technique}",
                index=entry.dataset,
            )
            capture = ip.capture_investigation([recovery_anchor], indexes=(entry.dataset,))
            inv = capture.investigations[0] if capture.investigations else None
            seen_cousin_ids = {str(tb._dig(e, "cousin_id")) for e in inv.events} if inv else set()
            for cousin in entry_cousins:
                reached = cousin.cousin_id in seen_cousin_ids
                all_planted.append((cousin.cousin_id, cousin.planted_distance))
                if reached:
                    all_reached.add(cousin.cousin_id)

                t_bucket = per_transformation_recovery.setdefault(
                    cousin.transformation, {"reached": 0, "total": 0}
                )
                t_bucket["total"] += 1
                t_bucket["reached"] += int(reached)

                d_key = str(cousin.planted_distance)
                d_by_t = per_distance_recovery.setdefault(d_key, {})
                dt_bucket = d_by_t.setdefault(cousin.transformation, {"reached": 0, "total": 0})
                dt_bucket["total"] += 1
                dt_bucket["reached"] += int(reached)

                scoreboard_records.append(
                    {
                        "assessment_id": cousin.cousin_id,
                        "relationship": "SAME" if reached else "DIFFERENT",
                        "defense_response": "OBSERVED" if reached else "NOT_OBSERVED",
                        "composite": 1.0 if reached else 0.0,
                        "candidate_state": "PROMOTED" if reached else "KILLED",
                        "known_benign": False,
                    }
                )

    distance_recovery = ascope.distance_recovery(all_planted, all_reached)

    scoreboard_row = scoreboard.update("a6-live-adaptive-reach-run", scoreboard_records)

    # ---- bed_acceptance (A5 -- mandatory) ----
    # floor: the one real multi-entity chain this run can score without
    # being degenerate (BOTSv3 T1558.004); cost is honestly None -- this
    # run measures reachability, not a concern classifier's false-positive
    # rate, and a fabricated number would be worse than an absent one.
    chain_reach = reach_reports.get("a-truth-T1558.004")
    floor_known_recall = chain_reach.get("reach_recall") if chain_reach else None
    acceptance = corpus_bed.bed_acceptance(
        answer_key_hit=1 if floor_known_recall == 1.0 else 0,
        answer_key_total=1 if chain_reach and not chain_reach.get("degenerate_expectation") else 0,
        cousin_hit=len(all_reached),
        cousin_total=len(all_planted),
        background_flagged=0,
        background_total=0,
        bed=last_bed_report,
    )

    report = {
        "algorithm_version": ALGORITHM_VERSION,
        "plane": "live",
        "generated_at": time.time(),
        "hunt_id": "a6-live-adaptive-reach-run",
        "index_ranges": {k: v.to_dict() for k, v in index_ranges.items()},
        "investigations": per_investigation,
        "pivot_ran_count": n_pivot_ran,
        "pivot_ran_total": len(per_investigation),
        "reach_report": reach_reports,
        "distance_recovery": distance_recovery.to_dict(),
        "throughput": {
            "total_events": total_events,
            "elapsed_seconds": elapsed,
            "records_per_second": throughput_rec_per_sec,
            "i6_bounded_unadaptive_records_per_second": I6_BOUNDED_UNADAPTIVE_REC_PER_SEC,
            "t3_unbounded_scan_records_per_second": T3_UNBOUNDED_SCAN_REC_PER_SEC,
        },
        "classifier_coverage_report": coverage.to_dict(),
        "inference_report": inference,
        "cousins_planned": len(all_cousins),
        "cousins_shipped": not args.dry_run_cousins,
        "inject_reports": [r.to_dict() for r in inject_reports],
        "per_transformation_cousin_recovery": per_transformation_recovery,
        "per_distance_cousin_recovery": per_distance_recovery,
        "scoreboard": scoreboard_row,
        "bed_acceptance": acceptance.to_dict(),
        "bed_report": last_bed_report.to_dict() if last_bed_report else None,
        "correctness_axis_provenance": (
            "relationship=SAME/candidate_state=PROMOTED when a live RECOVERY investigation, "
            "scoped to the same real anchor entity the cousin's parent technique was discovered "
            "under (never the cousin's own entity), reached that cousin's cousin_id via its "
            "pivot chain. cost_background_fp_rate is published as None: this run measures "
            "reachability by pivot distance, not a concern classifier's false-positive rate, "
            "and no such classifier runs on the investigation-pivot path -- a fabricated cost "
            "figure would be worse than an honestly absent one."
        ),
        "per_row": scoreboard_row.get("records", []),
    }
    corpus_bed.require_bed_acceptance(report)  # A5: refuse to publish without it

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.doc_stem}.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
