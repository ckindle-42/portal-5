"""Scored run CLI for the MAWA join: hashes in, frozen params, metrics and record out.

Run with: ./.venv/bin/python -I -m portal.modules.security.core.mawa.run --dataset-root <root>
Ground truth is read only here, after the join has produced its groups.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from portal.modules.security.core.mawa.events import ParsedEvent, ParseReport, read_events
from portal.modules.security.core.mawa.join import (
    DEFAULT_GRAPH_PARAMS,
    DEFAULT_JOIN_PARAMS,
    CandidateGroup,
    build_groups,
)
from portal.modules.security.core.mawa.truth import (
    BridgeResult,
    EventMetrics,
    StageResult,
    StageTruth,
    match_events_to_truth,
    per_event_metrics,
    per_stage_recovery,
    read_high_level,
    read_low_level,
)

DEFAULT_LOGS = ("log/apache2/access.log", "log/auth.log", "log/syslog")
DEFAULT_HIGH = "ground-truth/high-level-ground-truth.csv"
DEFAULT_LOW = "ground-truth/low-level-ground-truth.csv"
RECOVERY_IOU = 0.5


@dataclass(frozen=True)
class ChainLink:
    """One entity link between consecutive candidate groups."""

    entity: str
    group_a: int
    group_b: int
    delta_s: float
    files_a: list[str]
    files_b: list[str]
    cross_file: bool


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=10
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _stage_class(n_ids: int) -> str:
    if n_ids == 1:
        return "single"
    if n_ids == 2:
        return "pair"
    return "bulk"


def _chain_links(events: list[ParsedEvent], groups: list[CandidateGroup]) -> list[ChainLink]:
    """Consecutive-in-time links per shared entity between candidate groups."""
    df: dict[str, int] = {}
    for event in events:
        for entity in event.entities:
            df[entity] = df.get(entity, 0) + 1
    group_of: dict[int, CandidateGroup] = {}
    for group in groups:
        for member in group.member_ids:
            group_of[member] = group
    ent_groups: dict[str, dict[int, CandidateGroup]] = {}
    for event in events:
        member_group = group_of.get(event.event_id)
        if member_group is None:
            continue
        for entity in event.entities:
            if df[entity] <= DEFAULT_GRAPH_PARAMS.max_entity_df:
                ent_groups.setdefault(entity, {})[member_group.group_id] = member_group
    links: list[ChainLink] = []
    for entity, members in ent_groups.items():
        ordered = sorted(members.values(), key=lambda g: (g.ts_min, g.group_id))
        for prev, cur in zip(ordered, ordered[1:], strict=False):
            links.append(_link(entity, prev, cur))
    links.sort(key=lambda link: (not link.cross_file, link.entity, link.delta_s))
    return links


def _link(entity: str, prev: CandidateGroup, cur: CandidateGroup) -> ChainLink:
    files_a, files_b = sorted(prev.files), sorted(cur.files)
    return ChainLink(
        entity=entity,
        group_a=prev.group_id,
        group_b=cur.group_id,
        delta_s=round(max(0.0, cur.ts_min - prev.ts_max), 3),
        files_a=files_a,
        files_b=files_b,
        cross_file=files_a != files_b,
    )


def _reconciliation(
    reports: list[ParseReport], events: list[ParsedEvent], bridge: BridgeResult
) -> dict[str, Any]:
    per_file: dict[str, dict[str, int]] = {}
    for report in reports:
        per_file[Path(report.file).name] = {
            "lines_read": report.lines_read,
            "empty_lines": report.empty_lines,
            "parsed": report.events,
            "failures": len(report.failures),
        }
    event_by_id = {e.event_id: e for e in events}
    matched_by_base: dict[str, int] = {}
    for raw_id in bridge.raw_to_gt:
        base = Path(event_by_id[raw_id].source_file).name
        matched_by_base[base] = matched_by_base.get(base, 0) + 1
    for base, count in matched_by_base.items():
        per_file.setdefault(base, {})["matched_to_truth"] = count
    out_of_scope: dict[str, int] = {}
    for row in bridge.unmatched_gt:
        base = Path(row.display_name.replace("\\", "/")).name
        out_of_scope[base] = out_of_scope.get(base, 0) + 1
    return {
        "per_file": per_file,
        "matched_total": len(bridge.raw_to_gt),
        "unmatched_raw_total": len(bridge.unmatched_raw),
        "unmatched_raw_by_file": sorted({Path(e.source_file).name for e in bridge.unmatched_raw}),
        "unmatched_truth_rows_by_source": out_of_scope,
    }


def _per_event_row(metrics: EventMetrics) -> dict[str, Any]:
    return {
        "attack_total": metrics.attack_total,
        "tp": metrics.tp,
        "fp_strict": metrics.fp_strict,
        "fp_matched_only": metrics.fp_matched_only,
        "fn": metrics.fn,
        "flagged": metrics.flagged,
        "unmatched_flagged": metrics.unmatched_flagged,
        "precision_strict": round(metrics.precision_strict, 6),
        "precision_matched_only": round(metrics.precision_matched_only, 6),
        "recall": round(metrics.recall, 6),
        "f1_strict": round(metrics.f1_strict, 6),
        "f1_matched_only": round(metrics.f1_matched_only, 6),
    }


def _per_stage_rows(stages: list[StageTruth], results: list[StageResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for stage, result in zip(stages, results, strict=True):
        rows.append(
            {
                "stage": stage.label,
                "published_ts": stage.datetime,
                "published_actor": stage.published_actor,
                "truth_event_ids": len(stage.low_level_ids),
                "class": _stage_class(len(stage.low_level_ids)),
                "best_group_id": result.best_group_id,
                "best_iou": round(result.best_iou, 4),
                "overlap_events": result.overlap,
                "best_group_size": result.best_group_size,
                "best_group_files": sorted(result.best_group_files),
                "recovered_iou_ge_0_5": result.recovered,
                "any_overlap": result.any_overlap,
            }
        )
    return rows


def _stage_split(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    split: dict[str, dict[str, int]] = {}
    for row in rows:
        bucket = split.setdefault(
            str(row["class"]), {"stages": 0, "recovered": 0, "any_overlap": 0}
        )
        bucket["stages"] += 1
        bucket["recovered"] += int(bool(row["recovered_iou_ge_0_5"]))
        bucket["any_overlap"] += int(bool(row["any_overlap"]))
    return split


def _render_md(
    run_meta: dict[str, str],
    params_json: str,
    pe: dict[str, Any],
    stage_rows: list[dict[str, Any]],
    split: dict[str, dict[str, int]],
    links: list[ChainLink],
) -> str:
    lines = [
        "# MAWA join scored run",
        "",
        f"- commit: `{run_meta['git_head']}`",
        f"- params: `{params_json}`",
        f"- flagged (multi-event groups): {pe['flagged']} events; strict precision {pe['precision_strict']}, "
        f"matched-only precision {pe['precision_matched_only']}, recall {pe['recall']}, F1 strict {pe['f1_strict']}",
        "",
        "| stage | ids | class | best IoU | overlap | group size | recovered | any overlap |",
        "|---|---:|---|---:|---:|---:|---|---|",
    ]
    for row in stage_rows:
        lines.append(
            f"| {row['stage']} | {row['truth_event_ids']} | {row['class']} | {row['best_iou']} | "
            f"{row['overlap_events']} | {row['best_group_size']} | {row['recovered_iou_ge_0_5']} | "
            f"{row['any_overlap']} |"
        )
    lines += ["", f"stage split: `{json.dumps(split, sort_keys=True)}`", ""]
    lines += ["## Cross-file chain links (produced without actor)", ""]
    for link in links:
        if link.cross_file:
            lines.append(
                f"- `{link.entity}`: group {link.group_a} -> group {link.group_b} "
                f"(+{link.delta_s}s), {link.files_a} -> {link.files_b}"
            )
    return "\n".join(lines) + "\n"


def _write_record(out_dir: Path, record: dict[str, Any], md: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"mawa_join_run_{stamp}.json"
    json_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    md_path = out_dir / f"mawa_join_run_{stamp}.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"run record: {json_path}")
    print(f"run record: {md_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="MAWA step->manifestation join scored run")
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--logs", nargs="+", default=list(DEFAULT_LOGS))
    parser.add_argument("--high-level", default=DEFAULT_HIGH)
    parser.add_argument("--low-level", default=DEFAULT_LOW)
    parser.add_argument("--syslog-year", type=int, default=2026)
    parser.add_argument("--syslog-tz-hours", type=float, default=7.0)
    parser.add_argument("--out-dir", default="reports/mawa")
    args = parser.parse_args()
    root = Path(args.dataset_root)
    log_paths = [str(root / rel) for rel in args.logs]
    events, reports = read_events(log_paths, args.syslog_year, args.syslog_tz_hours)
    groups = build_groups(events, DEFAULT_JOIN_PARAMS)
    low_rows = read_low_level(str(root / args.low_level))
    stages = read_high_level(str(root / args.high_level))
    bridge = match_events_to_truth(events, low_rows)
    metrics = per_event_metrics(groups, bridge, low_rows)
    results = per_stage_recovery(groups, bridge, stages)
    stage_rows = _per_stage_rows(stages, results)
    pe = _per_event_row(metrics)
    links = _chain_links(events, groups)
    params: dict[str, object] = {
        "time_window_s": DEFAULT_JOIN_PARAMS.time_window_s,
        "entity_window_s": DEFAULT_JOIN_PARAMS.entity_window_s,
        "max_entity_df": DEFAULT_JOIN_PARAMS.max_entity_df,
        "graph_max_entity_df": DEFAULT_GRAPH_PARAMS.max_entity_df,
        "recovery_iou_threshold": RECOVERY_IOU,
        "syslog_year": args.syslog_year,
        "syslog_tz_hours": args.syslog_tz_hours,
    }
    run_meta = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "git_head": _git_head(),
        "dataset_root": str(root),
    }
    input_paths = [*log_paths, str(root / args.high_level), str(root / args.low_level)]
    biggest = max(groups, key=lambda g: g.size)
    record: dict[str, Any] = {
        "run": run_meta,
        "inputs": {
            p: {"sha256": _sha256(Path(p)), "bytes": Path(p).stat().st_size} for p in input_paths
        },
        "params": params,
        "parse": {
            Path(r.file).name: {
                "lines_read": r.lines_read,
                "empty_lines": r.empty_lines,
                "events": r.events,
                "failures": [asdict(f) for f in r.failures],
            }
            for r in reports
        },
        "reconciliation": _reconciliation(reports, events, bridge),
        "join": {
            "events": len(events),
            "groups": len(groups),
            "groups_size_ge2": sum(1 for g in groups if g.size >= 2),
            "singletons": sum(1 for g in groups if g.size == 1),
            "flagged_events": sum(g.size for g in groups if g.size >= 2),
            "largest_group": {
                "size": biggest.size,
                "span_s": round(biggest.span_s, 1),
                "files": sorted(biggest.files),
            },
        },
        "per_event": pe,
        "per_stage": stage_rows,
        "stage_split": _stage_split(stage_rows),
        "chain_links": [asdict(link) for link in links],
    }
    md = _render_md(
        run_meta,
        json.dumps(params, sort_keys=True),
        pe,
        stage_rows,
        _stage_split(stage_rows),
        links,
    )
    _write_record(Path(args.out_dir), record, md)


if __name__ == "__main__":
    main()
