#!/usr/bin/env python3
"""TASK_BULLY_INVESTIGATION_V1 (I.6) -- THE LIVE INVESTIGATION RUN.

Live, over BOTS. Discovers each queried index's real time range, runs
anchor-pivot investigations from real symptom anchors (one data-intrinsic,
one truth-targeted per answer-key technique), plans and ships cousins
inside each technique's real corpus range under their own real
`anchor_entity` (I4/I5), tests per-cousin recovery by pivoting from that
same real entity, and publishes classifier coverage/inference reports
alongside throughput -- so the comparison against T.3's 53 rec/sec
unbounded-scan figure is explicit.

Cousins are shipped live by default (`--dry-run-cousins` to plan without
shipping): they are tagged (`evidence_origin=corpus:cousin:<id>`) and
reversible via the documented rollback
(`index=<index> evidence_origin=corpus:cousin:<id> | delete`).
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

ALGORITHM_VERSION = "investigation-run-i6-v1"

# T.3's own measured figure, for the explicit comparison this task requires.
T3_UNBOUNDED_SCAN_REC_PER_SEC = 53.0

# Real hosts, live-discovered from each technique's own sourcetype in its
# own dataset -- never fabricated. The answer-key naming (`wineventlog:
# security`, `xmlwineventlog:sysmon`) does not always match this lab's real
# capture naming (bare `WinEventLog`/`xmlwineventlog`), a live naming-
# variant gap this run surfaces rather than papers over.
_DISCOVERED_ANCHORS: dict[str, tuple[str, str]] = {
    # technique -> (real sourcetype used to discover it, real host found)
    "T1558.004": ("WinEventLog", "BGIST-L"),
    "T1071.001": ("stream:http", "gacrux.i-0920036c8ca91e501"),
    "T1496": ("xmlwineventlog", "venus"),
    "T1190": ("stream:http", "splunk-02"),
}


def _discover_ranges(indexes: tuple[str, ...]) -> dict[str, ip.IndexRange]:
    from portal.modules.security.core.bully.live_connect import lab_splunk_connector

    out = {}
    for index in indexes:
        connector = lab_splunk_connector(index=index)
        out[index] = ip.discover_index_range(connector, index)
    return out


def _find_real_anchor_entity(
    index: str, sourcetype: str, extra_filter: str = ""
) -> tuple[str, float] | None:
    """Discover a genuinely real (entity, time) pair from the live corpus --
    never fabricated. Returns the first matching row's host and real event
    time, or None if nothing matched."""
    from portal.modules.security.core.siem.spl_backend import SplunkBackend

    backend = SplunkBackend()
    spl = f"search index={index} sourcetype={sourcetype} {extra_filter}".strip()
    rows = backend._run_search(spl, "0", "now")
    for row in rows:
        if row.get("host"):
            return str(row["host"]), float(row["_time"])
    return None


def _action_of(r: dict[str, Any]) -> str | None:
    # `_dig` (I.6 fix) falls back to parsing `_raw`'s key=value text --
    # required here because this lab only surfaces a field in export JSON
    # when the search itself referenced it, so an entity-substring pivot
    # query (no `EventCode=` term) never gets it as a flat field.
    return tb._dig(r, *tb._FIELD_EVENTCODE) or tb._dig(r, "event_type")


def main() -> int:  # noqa: PLR0915, C901, PLR0912
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="docs")
    parser.add_argument("--doc-stem", default="BULLY_INVESTIGATION_RUN_I6_V1")
    parser.add_argument("--dry-run-cousins", action="store_true")
    args = parser.parse_args()

    available, reason = ip.lab_available()
    if not available:
        print(json.dumps({"plane": "unavailable", "reason": reason}, indent=2))
        return 1

    datasets = ("botsv1", "botsv2", "botsv3")
    index_ranges = _discover_ranges(datasets)

    # ---- one data-intrinsic anchor (a real symptom, discovered directly) --
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

    # ---- one truth-targeted anchor per answer-key technique, built on a
    # REAL entity discovered from that technique's own real sourcetype ----
    local_answer_key = []
    for entry in BOTS_ANSWER_KEY:
        st, host = _DISCOVERED_ANCHORS.get(entry.technique, (None, None))
        if not host:
            local_answer_key.append(entry)
            continue
        anchor_id = f"a-truth-{entry.technique}"
        found = _find_real_anchor_entity(entry.dataset, st, f'host="{host}"')
        at = found[1] if found else index_ranges[entry.dataset].earliest
        # `confirmed_at` places every transformation-cousin of this entry
        # ADJACENT to this same real activity (I5) -- without it, plan_cousins
        # spreads cousins across the corpus's ENTIRE span (its no-confirmed-
        # time fallback), which is the right behaviour when no confirmation
        # time is known but scatters this run's cousins so far apart that a
        # single recovery-test anchor could only ever reach one of them.
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

    # ---- run investigations, grouped by index (capture_investigation
    # scopes ALL its anchors' queries to the SAME index tuple) ----
    per_investigation = []
    total_events = 0
    all_records: list[dict[str, Any]] = []
    truth_targeted_reach: dict[str, tuple[str, ...]] = {
        f"a-truth-{e.technique}": (host,)
        for e in BOTS_ANSWER_KEY
        if (host := _DISCOVERED_ANCHORS.get(e.technique, (None, None))[1])
    }

    last_bed_report = None
    t0 = time.time()
    for dataset in datasets:
        dataset_anchors = [a for a in anchors if anchor_index.get(a.anchor_id) == dataset]
        if not dataset_anchors:
            continue
        capture = ip.capture_investigation(dataset_anchors, indexes=(dataset,))
        last_bed_report = capture.bed_report
        for inv in capture.investigations:
            total_events += len(inv.events)
            all_records.extend(inv.events)
            entry_report = {
                "anchor_id": inv.anchor.anchor_id,
                "anchor_provenance": anchor_provenance.get(inv.anchor.anchor_id, "unknown"),
                "dataset": dataset,
                "n_queries": len(inv.queries),
                "n_events": len(inv.events),
                "n_entities": len(inv.entities_seen),
                "sourcetypes": list(inv.sourcetypes),
                "span_seconds": inv.span_seconds,
                "truncated_reasons": list(inv.truncated_reasons),
            }
            if inv.anchor.anchor_id in truth_targeted_reach:
                r = pivot.reach_report(inv, truth_targeted_reach[inv.anchor.anchor_id])
                entry_report["reach_report"] = r.to_dict()
            per_investigation.append(entry_report)
    elapsed = time.time() - t0
    throughput_rec_per_sec = (total_events / elapsed) if elapsed else None

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

    # ---- plan + ship cousins inside each technique's REAL corpus range,
    # under their real anchor_entity (I4/I5) ----
    all_cousins = []
    inject_reports = []
    for entry in local_answer_key:
        rng = index_ranges[entry.dataset]
        if rng.earliest is None or rng.latest is None:
            continue
        cousins = corpus_bed.plan_cousins(
            [entry],
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
    scoreboard_records: list[dict[str, Any]] = []
    if not args.dry_run_cousins:
        time.sleep(5.0)  # let HEC-shipped cousin events land before capture
        for entry in local_answer_key:
            host = entry.entities[0] if entry.entities else None
            if not host:
                continue
            rng = index_ranges[entry.dataset]
            entry_cousins = [c for c in all_cousins if c.parent_technique == entry.technique]
            recovery_anchor = pivot.Anchor(
                anchor_id=f"a-cousin-recovery-{entry.technique}",
                at=(entry_cousins[0].injected_at if entry_cousins else rng.earliest),
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
                bucket = per_transformation_recovery.setdefault(
                    cousin.transformation, {"reached": 0, "total": 0}
                )
                bucket["total"] += 1
                bucket["reached"] += int(reached)
                scoreboard_records.append(
                    {
                        "assessment_id": cousin.cousin_id,
                        "relationship": "SAME" if reached else "DIFFERENT",
                        "defense_response": "OBSERVED" if reached else "NOT_OBSERVED",
                        "composite": 1.0 if reached else 0.0,
                        # Ground truth is known here (this run planted the
                        # cousin itself): a real investigation reaching it
                        # is a genuinely confirmed-correct verdict, and one
                        # a real investigation missed is genuinely
                        # confirmed-wrong -- PROMOTED/KILLED are the
                        # existing trust-axis vocabulary for exactly that.
                        "candidate_state": "PROMOTED" if reached else "KILLED",
                        "known_benign": False,
                    }
                )

    scoreboard_row = (
        scoreboard.update("i6-live-investigation-run", scoreboard_records)
        if scoreboard_records
        else scoreboard.update("i6-live-investigation-run", [])
    )

    report = {
        "algorithm_version": ALGORITHM_VERSION,
        "plane": "live",
        "generated_at": time.time(),
        "hunt_id": "i6-live-investigation-run",
        "index_ranges": {k: v.to_dict() for k, v in index_ranges.items()},
        "investigations": per_investigation,
        "throughput": {
            "total_events": total_events,
            "elapsed_seconds": elapsed,
            "records_per_second": throughput_rec_per_sec,
            "t3_unbounded_scan_records_per_second": T3_UNBOUNDED_SCAN_REC_PER_SEC,
        },
        "classifier_coverage_report": coverage.to_dict(),
        "inference_report": inference,
        "cousins_planned": len(all_cousins),
        "cousins_shipped": not args.dry_run_cousins,
        "inject_reports": [r.to_dict() for r in inject_reports],
        "per_transformation_cousin_recovery": per_transformation_recovery,
        "scoreboard": scoreboard_row,
        "correctness_axis_provenance": (
            "trust_mean_rank/false_flag_count are computed by scoreboard.update() over "
            "real per-cousin reachability: relationship=SAME when a live investigation "
            "pivoting from the cousin's own real anchor_entity found that cousin's "
            "cousin_id, DIFFERENT otherwise. candidate_state is PROMOTED/KILLED on the "
            "same reachability signal -- ground truth is known here (this run planted "
            "every scored cousin itself), so a real investigation reaching it is a "
            "genuinely confirmed-correct verdict and a miss is genuinely confirmed-wrong. "
            "known_benign=False throughout (every scored record is a planted cousin, "
            "never a real-corpus record graded as benign), so false_flag_count is "
            "structurally 0 for this run -- it measures cousin recovery, not background "
            "false-positive rate."
        ),
        "per_row": scoreboard_row.get("records", []),
        "bed_report": last_bed_report.to_dict() if last_bed_report else None,
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.doc_stem}.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
