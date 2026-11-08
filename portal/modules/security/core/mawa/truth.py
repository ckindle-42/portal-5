"""Scorer-side bridge between raw parsed events and published MAWA ground truth.

Only this module reads ground-truth files, and only after the join has
produced its candidate groups. The join never sees anything from here.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from portal.modules.security.core.mawa.events import ParsedEvent
from portal.modules.security.core.mawa.join import CandidateGroup

RECOVERY_IOU_THRESHOLD = 0.5


@dataclass(frozen=True)
class LowRow:
    """One published low-level truth event."""

    event_id: int
    ts: float
    display_name: str
    parser: str
    message: str
    label: str


@dataclass(frozen=True)
class StageTruth:
    """One published high-level stage and its low-level event ids."""

    label: str
    datetime: str
    low_level_ids: frozenset[int]
    published_actor: str


def read_low_level(path: str) -> list[LowRow]:
    rows: list[LowRow] = []
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.append(
                LowRow(
                    event_id=int(row["event_id"]),
                    ts=datetime.fromisoformat(row["datetime"]).timestamp(),
                    display_name=row["display_name"],
                    parser=row["parser"],
                    message=row["message"],
                    label=row["ground_truth_label"],
                )
            )
    return rows


def read_high_level(path: str) -> list[StageTruth]:
    stages: list[StageTruth] = []
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ids = frozenset(int(x) for x in row["low_level_ids"].split("|") if x)
            stages.append(
                StageTruth(
                    label=row["ground_truth_label"],
                    datetime=row["datetime"],
                    low_level_ids=ids,
                    published_actor=row["actor"],
                )
            )
    return stages


def plaso_apache_message(fields: Mapping[str, str]) -> str:
    """Reconstruct the plaso apache_access message from raw parsed fields."""
    parts = [
        f"http_request: {fields['method']} {fields['url']} {fields['proto']}",
        f"from: {fields['client']}",
        f"code: {fields['code']}",
    ]
    if fields["referer"] != "-":
        parts.append(f"referer: {fields['referer']}")
    parts.append(f"user_agent: {fields['user_agent']}")
    return " ".join(parts)


def plaso_syslog_message(tag: str, pid: str, message: str) -> str:
    """Reconstruct the plaso syslog message: strip, comma->space, escape quotes."""
    body = message.replace(",", " ").replace("'", "\\'")
    if pid:
        return f"[{tag}  pid: {pid}] {body}"
    return f"[{tag}] {body}"


def _bridge_key(file_base: str, ts: float, message: str) -> tuple[str, int, str]:
    return (file_base, int(ts), message)


def _file_base(name: str) -> str:
    """Basename across POSIX and windows-style path separators."""
    return name.replace("\\", "/").split("/")[-1]


def _event_truth_key(event: ParsedEvent) -> tuple[str, int, str] | None:
    base = _file_base(event.source_file)
    if event.kind == "apache_access":
        message = plaso_apache_message(event.fields)
    elif event.kind == "syslog":
        message = plaso_syslog_message(event.tag, event.pid, event.message)
    else:
        return None
    return _bridge_key(base, event.ts, message)


@dataclass(frozen=True)
class BridgeResult:
    """One-to-one mapping between raw event ids and published truth ids."""

    raw_to_gt: dict[int, int]
    gt_to_raw: dict[int, int]
    unmatched_gt: list[LowRow]
    unmatched_raw: list[ParsedEvent]


def match_events_to_truth(
    events: Sequence[ParsedEvent], low_rows: Sequence[LowRow]
) -> BridgeResult:
    """Greedy one-to-one match on (file basename, second, reconstructed message)."""
    gt_buckets: dict[tuple[str, int, str], list[LowRow]] = {}
    for row in low_rows:
        base = _file_base(row.display_name)
        gt_buckets.setdefault(_bridge_key(base, row.ts, row.message), []).append(row)
    raw_to_gt: dict[int, int] = {}
    gt_to_raw: dict[int, int] = {}
    unmatched_raw: list[ParsedEvent] = []
    for event in events:
        key = _event_truth_key(event)
        bucket = gt_buckets.get(key) if key is not None else None
        if bucket:
            row = bucket.pop(0)
            raw_to_gt[event.event_id] = row.event_id
            gt_to_raw[row.event_id] = event.event_id
        else:
            unmatched_raw.append(event)
    used_gt = set(gt_to_raw)
    unmatched_gt = [row for row in low_rows if row.event_id not in used_gt]
    return BridgeResult(
        raw_to_gt=raw_to_gt,
        gt_to_raw=gt_to_raw,
        unmatched_gt=unmatched_gt,
        unmatched_raw=unmatched_raw,
    )


@dataclass(frozen=True)
class EventMetrics:
    """Per-event precision/recall against published attack labels."""

    attack_total: int
    tp: int
    fp_strict: int
    fp_matched_only: int
    fn: int
    flagged: int
    unmatched_flagged: int

    @property
    def precision_strict(self) -> float:
        denom = self.tp + self.fp_strict
        return self.tp / denom if denom else 0.0

    @property
    def precision_matched_only(self) -> float:
        denom = self.tp + self.fp_matched_only
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        return self.tp / self.attack_total if self.attack_total else 0.0

    @property
    def f1_strict(self) -> float:
        p, r = self.precision_strict, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    @property
    def f1_matched_only(self) -> float:
        p, r = self.precision_matched_only, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


def per_event_metrics(
    groups: Sequence[CandidateGroup],
    bridge: BridgeResult,
    low_rows: Sequence[LowRow],
) -> EventMetrics:
    """Events in any multi-member group are the join's flagged manifestations."""
    attack_ids = {row.event_id for row in low_rows if row.label != "benign"}
    flagged: set[int] = set()
    for group in groups:
        if group.size >= 2:
            flagged.update(group.member_ids)
    flagged_gt = {bridge.raw_to_gt[eid] for eid in flagged if eid in bridge.raw_to_gt}
    unmatched_flagged = sum(1 for eid in flagged if eid not in bridge.raw_to_gt)
    tp = len(flagged_gt & attack_ids)
    fp_matched = len(flagged_gt - attack_ids)
    return EventMetrics(
        attack_total=len(attack_ids),
        tp=tp,
        fp_strict=fp_matched + unmatched_flagged,
        fp_matched_only=fp_matched,
        fn=len(attack_ids - flagged_gt),
        flagged=len(flagged),
        unmatched_flagged=unmatched_flagged,
    )


@dataclass(frozen=True)
class StageResult:
    """Recovery of one published stage by the best-overlapping candidate group."""

    label: str
    n_ids: int
    published_actor: str
    best_group_id: int | None
    best_iou: float
    overlap: int
    best_group_size: int
    best_group_files: frozenset[str]

    @property
    def recovered(self) -> bool:
        return self.best_iou >= RECOVERY_IOU_THRESHOLD

    @property
    def any_overlap(self) -> bool:
        return self.overlap > 0


def per_stage_recovery(
    groups: Sequence[CandidateGroup],
    bridge: BridgeResult,
    stages: Sequence[StageTruth],
) -> list[StageResult]:
    """Best candidate group per published stage by IoU over matched truth ids."""
    results: list[StageResult] = []
    for stage in stages:
        best: tuple[float, int, int, int, frozenset[str] | None] = (0.0, -1, 0, 0, None)
        for group in groups:
            matched = {bridge.raw_to_gt[m] for m in group.member_ids if m in bridge.raw_to_gt}
            inter = len(matched & stage.low_level_ids)
            if inter == 0:
                continue
            union = len(matched | stage.low_level_ids)
            iou = inter / union
            if iou > best[0]:
                best = (iou, group.group_id, inter, group.size, group.files)
        iou, gid, inter, gsize, gfiles = best
        results.append(
            StageResult(
                label=stage.label,
                n_ids=len(stage.low_level_ids),
                published_actor=stage.published_actor,
                best_group_id=gid if gid >= 0 else None,
                best_iou=iou,
                overlap=inter,
                best_group_size=gsize,
                best_group_files=gfiles or frozenset(),
            )
        )
    return results
