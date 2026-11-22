#!/usr/bin/env python3
"""Out-of-band scorer key builder for AIT-LDS2 corpora — scorer plane only.

Reads AIT-LDS2 ground-truth `labels/` JSONL files from a raw `.zip` archive or extracted
directory (stripped out before Splunk ingest by ingest_canonical.py) and writes a clean,
deduplicated scorer key JSON (attack steps, affected hosts, time windows, step counts, zero
raw log duplication) for out-of-band scoring under `/Volumes/data01/hunt_keys/`. Never
imported by `portal/`.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_native import parse_time  # noqa: E402

DATASETS = ("fox", "harrison", "shaw", "wardbeck", "wilson")
PROOF_DATASETS = frozenset({"wardbeck", "wilson"})
TRAINING_DATASETS = frozenset({"fox", "harrison", "shaw"})
DATASET_INDEXES = {name: f"hb_ait_{name}" for name in DATASETS}
_DEFAULT_YEAR_FALLBACK = 2022
_YAML_YEAR = re.compile(r"^\s*start:\s*['\"]?(\d{4})-", re.MULTILINE)

SourceEntry = tuple[str, str, str, Callable[[], IO[bytes]], Callable[[], IO[bytes]] | None]


def _minmax(current: float | None, value: float | None, *, pick_max: bool) -> float | None:
    if value is None:
        return current
    if current is None:
        return value
    return max(current, value) if pick_max else min(current, value)


@dataclass
class _SourceAcc:
    count: int = 0
    lines: list[int] = field(default_factory=list)
    min_ts: float | None = None
    max_ts: float | None = None

    def add(self, line_no: int, ts: float | None) -> None:
        self.count += 1
        self.lines.append(line_no)
        self.min_ts = _minmax(self.min_ts, ts, pick_max=False)
        self.max_ts = _minmax(self.max_ts, ts, pick_max=True)


@dataclass
class _StepAcc:
    count: int = 0
    rules: set[str] = field(default_factory=set)
    hosts: set[str] = field(default_factory=set)
    log_paths: set[str] = field(default_factory=set)
    min_ts: float | None = None
    max_ts: float | None = None
    by_source: dict[tuple[str, str], _SourceAcc] = field(default_factory=dict)

    def add(
        self, host: str, log_path: str, line_no: int, ts: float | None, rules: tuple[str, ...]
    ) -> None:
        self.count += 1
        self.rules.update(rules)
        self.hosts.add(host)
        self.log_paths.add(log_path)
        self.min_ts = _minmax(self.min_ts, ts, pick_max=False)
        self.max_ts = _minmax(self.max_ts, ts, pick_max=True)
        self.by_source.setdefault((host, log_path), _SourceAcc()).add(line_no, ts)


@dataclass
class _HostAcc:
    count: int = 0
    steps: set[str] = field(default_factory=set)
    log_paths: set[str] = field(default_factory=set)
    min_ts: float | None = None
    max_ts: float | None = None

    def add(self, step: str, log_path: str, ts: float | None) -> None:
        self.count += 1
        self.steps.add(step)
        self.log_paths.add(log_path)
        self.min_ts = _minmax(self.min_ts, ts, pick_max=False)
        self.max_ts = _minmax(self.max_ts, ts, pick_max=True)


def _iso_utc(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    dt = datetime.datetime.fromtimestamp(epoch, tz=datetime.UTC)
    return dt.isoformat().replace("+00:00", "Z")


def _window_dict(min_ts: float | None, max_ts: float | None) -> dict[str, Any]:
    return {
        "start": _iso_utc(min_ts),
        "end": _iso_utc(max_ts),
        "start_epoch": min_ts,
        "end_epoch": max_ts,
    }


def _merge_lines(lines: list[int]) -> list[list[int]]:
    """Collapse line numbers into sorted inclusive [start, end] ranges."""
    unique = sorted(set(lines))
    if not unique:
        return []
    ranges: list[list[int]] = [[unique[0], unique[0]]]
    for n in unique[1:]:
        if n == ranges[-1][1] + 1:
            ranges[-1][1] = n
        else:
            ranges.append([n, n])
    return ranges


def _parse_ts_value(value: Any, default_year: int) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return parse_time(text, default_year)


def _strip_labels_prefix(rel_posix: str) -> str | None:
    rel = rel_posix.lstrip("/")
    if rel.startswith("labels/"):
        return rel[len("labels/") :]
    if "/labels/" in rel:
        return rel.split("/labels/", 1)[1]
    return None


def _parse_label_rel(rel_under_labels: str) -> tuple[str, str] | None:
    """Extract (host, /log_path) from a path relative to labels/."""
    clean = rel_under_labels.strip("/")
    host, _, rest = clean.partition("/")
    if not host or not rest:
        return None
    if rest.startswith("logs/"):
        log_path = "/" + rest[len("logs/") :]
    elif "/logs/" in rest:
        log_path = "/" + rest.split("/logs/", 1)[1]
    else:
        log_path = "/" + rest
    return host, log_path


def _year_from_yaml(text: str) -> int | None:
    match = _YAML_YEAR.search(text)
    return int(match.group(1)) if match else None


def _extract_rules(raw_rules: Any, labels: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    if isinstance(raw_rules, dict):
        return tuple(
            tuple(sorted({str(r) for r in (raw_rules.get(lbl) or ()) if str(r)})) for lbl in labels
        )
    if isinstance(raw_rules, list):
        shared = tuple(sorted({str(r) for r in raw_rules if str(r)}))
        return tuple(shared for _ in labels)
    return tuple(() for _ in labels)


def _read_label_entries(
    stream: IO[bytes], default_year: int
) -> tuple[
    dict[int, tuple[int, float | None]],
    list[tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]],
]:
    """Parse and deduplicate one labels JSONL file by line number, interning label combos."""
    by_line: dict[int, tuple[set[str], dict[str, set[str]], float | None]] = {}
    for raw in stream:
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        row = json.loads(text)
        line_no = int(row["line"])
        labels = tuple(
            sorted({str(lbl).strip() for lbl in (row.get("labels") or ()) if str(lbl).strip()})
        )
        if not labels:
            continue
        rules_per_lbl = _extract_rules(row.get("rules"), labels)
        ts_val = row.get("timestamp") if "timestamp" in row else row.get("time")
        explicit_ts = _parse_ts_value(ts_val, default_year)
        entry = by_line.get(line_no)
        if entry is None:
            rule_map = {lbl: set(rset) for lbl, rset in zip(labels, rules_per_lbl, strict=True)}
            by_line[line_no] = (set(labels), rule_map, explicit_ts)
            continue
        lbl_set, rule_map, prev_ts = entry
        lbl_set.update(labels)
        for lbl, rset in zip(labels, rules_per_lbl, strict=True):
            rule_map.setdefault(lbl, set()).update(rset)
        if prev_ts is None and explicit_ts is not None:
            by_line[line_no] = (lbl_set, rule_map, explicit_ts)

    combo_ids: dict[tuple[tuple[str, ...], tuple[tuple[str, ...], ...]], int] = {}
    combos: list[tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]] = []
    compact: dict[int, tuple[int, float | None]] = {}
    for line_no, (lbl_set, rule_map, ts) in by_line.items():
        labels = tuple(sorted(lbl_set))
        rules = tuple(tuple(sorted(rule_map.get(lbl, ()))) for lbl in labels)
        combo = (labels, rules)
        cid = combo_ids.get(combo)
        if cid is None:
            cid = len(combos)
            combo_ids[combo] = cid
            combos.append(combo)
        compact[line_no] = (cid, ts)
    return compact, combos


def _resolve_gather_times(
    gather_opener: Callable[[], IO[bytes]] | None,
    wanted_lines: set[int],
    default_year: int,
) -> dict[int, float]:
    """Stream the paired gather/ log file once to resolve timestamps for needed line numbers."""
    if gather_opener is None or not wanted_lines:
        return {}
    max_line = max(wanted_lines)
    resolved: dict[int, float] = {}
    last_t: float | None = None
    with gather_opener() as gf:
        for lineno, raw in enumerate(gf, 1):
            text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            parsed = parse_time(text, default_year)
            eff_t = parsed if parsed is not None else last_t
            last_t = eff_t
            if lineno in wanted_lines and eff_t is not None:
                resolved[lineno] = eff_t
            if lineno >= max_line:
                break
    return resolved


def _zip_opener(zf: zipfile.ZipFile, name: str) -> Callable[[], IO[bytes]]:
    def _open() -> IO[bytes]:
        return zf.open(name)

    return _open


def _path_opener(path: Path) -> Callable[[], IO[bytes]]:
    def _open() -> IO[bytes]:
        return path.open("rb")

    return _open


@contextmanager
def _open_zip_sources(
    archive_path: Path, default_year: int | None
) -> Iterator[tuple[int, list[SourceEntry]]]:
    with zipfile.ZipFile(archive_path) as zf:
        year = default_year
        if year is None:
            for candidate in sorted(n for n in zf.namelist() if n.endswith("dataset.yaml")):
                year = _year_from_yaml(zf.read(candidate).decode("utf-8", errors="replace"))
                if year is not None:
                    break
        resolved_year = year if year is not None else _DEFAULT_YEAR_FALLBACK
        names = {info.filename for info in zf.infolist() if not info.is_dir()}
        items: list[SourceEntry] = []
        for info in sorted(zf.infolist(), key=lambda i: i.filename):
            if info.is_dir() or info.file_size == 0:
                continue
            rel_under = _strip_labels_prefix(info.filename)
            if rel_under is None:
                continue
            parsed = _parse_label_rel(rel_under)
            if parsed is None:
                continue
            host, log_path = parsed
            prefix = info.filename[: len(info.filename) - len("labels/" + rel_under)]
            gather_name = f"{prefix}gather/{rel_under}"
            gather_opener = _zip_opener(zf, gather_name) if gather_name in names else None
            items.append((rel_under, host, log_path, _zip_opener(zf, info.filename), gather_opener))
        yield resolved_year, items


@contextmanager
def _open_dir_sources(
    labels_dir: Path, default_year: int | None
) -> Iterator[tuple[int, list[SourceEntry]]]:
    root_labels = labels_dir / "labels" if (labels_dir / "labels").is_dir() else labels_dir
    base_parent = root_labels.parent
    year = default_year
    if year is None and (base_parent / "dataset.yaml").is_file():
        year = _year_from_yaml(
            (base_parent / "dataset.yaml").read_text(encoding="utf-8", errors="replace")
        )
    resolved_year = year if year is not None else _DEFAULT_YEAR_FALLBACK
    gather_root = base_parent / "gather"
    items: list[SourceEntry] = []
    for path in sorted(root_labels.rglob("*")):
        if not path.is_file() or path.stat().st_size == 0:
            continue
        rel_under = path.relative_to(root_labels).as_posix()
        parsed = _parse_label_rel(rel_under)
        if parsed is None:
            continue
        host, log_path = parsed
        gather_path = gather_root / rel_under
        gather_opener = _path_opener(gather_path) if gather_path.is_file() else None
        items.append((rel_under, host, log_path, _path_opener(path), gather_opener))
    yield resolved_year, items


def _aggregate_sources(
    year: int, sources: list[SourceEntry]
) -> tuple[dict[str, _StepAcc], dict[str, _HostAcc], list[str], int, float | None, float | None]:
    step_accs: dict[str, _StepAcc] = {}
    host_accs: dict[str, _HostAcc] = {}
    label_files: list[str] = []
    total_labelled_lines = 0
    overall_min_ts: float | None = None
    overall_max_ts: float | None = None
    for rel_under, host, log_path, label_opener, gather_opener in sources:
        with label_opener() as lf:
            line_entries, combos = _read_label_entries(lf, year)
        if not line_entries:
            continue
        label_files.append(rel_under)
        total_labelled_lines += len(line_entries)
        need_gather = {ln for ln, (_cid, ts) in line_entries.items() if ts is None}
        gather_times = _resolve_gather_times(gather_opener, need_gather, year)
        host_acc = host_accs.setdefault(host, _HostAcc())
        for line_no, (cid, explicit_ts) in sorted(line_entries.items()):
            ts = explicit_ts if explicit_ts is not None else gather_times.get(line_no)
            overall_min_ts = _minmax(overall_min_ts, ts, pick_max=False)
            overall_max_ts = _minmax(overall_max_ts, ts, pick_max=True)
            labels, rules_tuple = combos[cid]
            for step, rules in zip(labels, rules_tuple, strict=True):
                step_accs.setdefault(step, _StepAcc()).add(host, log_path, line_no, ts, rules)
                host_acc.add(step, log_path, ts)
    return step_accs, host_accs, label_files, total_labelled_lines, overall_min_ts, overall_max_ts


def _serialize_key(
    dataset: str,
    source_ref: str,
    step_accs: dict[str, _StepAcc],
    host_accs: dict[str, _HostAcc],
    label_files: list[str],
    total_labelled_lines: int,
    overall_min_ts: float | None,
    overall_max_ts: float | None,
) -> dict[str, Any]:
    ordered_steps = sorted(
        step_accs.items(),
        key=lambda item: (
            item[1].min_ts if item[1].min_ts is not None else float("inf"),
            item[0],
        ),
    )
    attack_steps = [
        {
            "step": step,
            "rules": sorted(acc.rules),
            "count": acc.count,
            "affected_hosts": sorted(acc.hosts),
            "log_paths": sorted(acc.log_paths),
            "time_window": _window_dict(acc.min_ts, acc.max_ts),
            "sources": [
                {
                    "host": h,
                    "log_path": lp,
                    "count": src.count,
                    "line_ranges": _merge_lines(src.lines),
                    "time_window": _window_dict(src.min_ts, src.max_ts),
                }
                for (h, lp), src in sorted(acc.by_source.items())
            ],
        }
        for step, acc in ordered_steps
    ]
    hosts = {
        host: {
            "count": acc.count,
            "steps": sorted(acc.steps),
            "log_paths": sorted(acc.log_paths),
            "time_window": _window_dict(acc.min_ts, acc.max_ts),
        }
        for host, acc in sorted(host_accs.items())
    }
    return {
        "dataset": dataset,
        "index": DATASET_INDEXES[dataset],
        "split": "proof" if dataset in PROOF_DATASETS else "build",
        "source": source_ref,
        "label_files": sorted(label_files),
        "total_labelled_lines": total_labelled_lines,
        "affected_hosts": sorted(host_accs),
        "step_counts": {step: acc.count for step, acc in sorted(step_accs.items())},
        "time_window": _window_dict(overall_min_ts, overall_max_ts),
        "attack_steps": attack_steps,
        "hosts": hosts,
    }


def build_key(
    *,
    dataset: str,
    archive: Path | None = None,
    labels_dir: Path | None = None,
    default_year: int | None = None,
) -> dict[str, Any]:
    """Build a deduplicated out-of-band AIT-LDS2 scorer key from a zip or extracted labels dir."""
    if dataset not in DATASET_INDEXES:
        raise ValueError(f"unsupported AIT-LDS2 dataset {dataset!r}; expected one of {DATASETS}")
    if (archive is None) == (labels_dir is None):
        raise ValueError("provide exactly one of archive or labels_dir")

    if archive is not None:
        ctx = _open_zip_sources(archive, default_year)
        source_ref = str(archive)
    else:
        assert labels_dir is not None
        ctx = _open_dir_sources(labels_dir, default_year)
        source_ref = str(labels_dir)

    with ctx as (year, sources):
        step_accs, host_accs, label_files, total_lines, min_ts, max_ts = _aggregate_sources(
            year, sources
        )
    return _serialize_key(
        dataset, source_ref, step_accs, host_accs, label_files, total_lines, min_ts, max_ts
    )


def format_summary(key: dict[str, Any]) -> str:
    """Render a compact step/host/window summary without raw log content."""
    tw = key["time_window"]
    lines = [
        f"dataset={key['dataset']} index={key['index']} split={key['split']} "
        f"label_files={len(key['label_files'])} labelled_lines={key['total_labelled_lines']}",
        f"window: {tw['start'] or 'unknown'} .. {tw['end'] or 'unknown'}",
        f"affected_hosts ({len(key['affected_hosts'])}): {', '.join(key['affected_hosts'])}",
        "attack_steps:",
    ]
    for step in key["attack_steps"]:
        stw = step["time_window"]
        lines.append(
            f"  - {step['step']}: count={step['count']} "
            f"hosts={','.join(step['affected_hosts'])} "
            f"window={stw['start'] or 'unknown'}..{stw['end'] or 'unknown'}"
        )
    return "\n".join(lines)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--archive", type=Path, help="path to AIT-LDS2 .zip archive")
    src.add_argument("--labels-dir", type=Path, help="path to extracted AIT-LDS2 labels directory")
    ap.add_argument("--dataset", required=True, choices=DATASETS, help="AIT-LDS2 scenario name")
    ap.add_argument("--out", type=Path, help="output scorer key JSON path")
    ap.add_argument("--default-year", type=int, help="year for yearless syslog timestamps")
    ap.add_argument("--summary", action="store_true", help="print step/host/window summary")
    args = ap.parse_args(argv)
    if args.archive is not None and not args.archive.is_file():
        ap.error(f"--archive not found: {args.archive}")
    if args.labels_dir is not None and not args.labels_dir.is_dir():
        ap.error(f"--labels-dir not found: {args.labels_dir}")
    if args.out is None and not args.summary:
        ap.error("at least one of --out or --summary is required")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    key = build_key(
        dataset=args.dataset,
        archive=args.archive,
        labels_dir=args.labels_dir,
        default_year=args.default_year,
    )
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(key, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.summary:
        print(format_summary(key))
    elif args.out is not None:
        print(
            f"wrote {args.out}: dataset={key['dataset']} steps={len(key['attack_steps'])} "
            f"hosts={len(key['affected_hosts'])} labelled_lines={key['total_labelled_lines']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
