#!/usr/bin/env python3
"""Out-of-band scorer keys for next-wave hunt corpora — scorer plane only.

Reads raw UWF-ZeekData24, LMD-2023, or ICS-pcap JSONL/CSV/TSV (and Zeek TSV or
mission_logs sidecars) and writes attack windows, tactics/techniques, and affected
hosts to ``/Volumes/data01/hunt_keys/<dataset>_key.json``. The schema matches
keys_ait.py. Never imported by portal/.

    python3 scripts/hunt_bed/keys_nextwave.py --root <dir|.zip|.tar> --dataset UWF-ZeekData24 \
        --out /Volumes/data01/hunt_keys/UWF-ZeekData24_key.json --summary
"""

from __future__ import annotations

import argparse
import csv
import datetime
import gzip
import io
import json
import re
import sys
import tarfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_native import parse_time  # noqa: E402

DATASETS = ("UWF-ZeekData24", "LMD-2023", "ICS-pcap")
DATASET_INDEXES = {
    "UWF-ZeekData24": "hb_uwf_zeek24",
    "LMD-2023": "hb_lmd_2023",
    "ICS-pcap": "hb_ics_pcap",
}
_BENIGN = frozenset(
    {
        "",
        "-",
        "0",
        "false",
        "no",
        "benign",
        "normal",
        "clean",
        "none",
        "legitimate",
        "good",
        "no_conn",
        "nan",
        "null",
    }
)
_GENERIC_STEP = frozenset({"true", "yes", "attack", "malicious", "malware", "bad", "evil"})
_TACTIC_KEYS = ("label_tactic", "attack_cat", "tactic", "tactics")
_TECH_KEYS = ("label_technique", "mitre_attack", "technique", "attack", "mitre_technique")
_TIME_KEYS = (
    "ts",
    "timestamp",
    "utctime",
    "timecreated",
    "systemtime",
    "@timestamp",
    "event_time",
    "_time",
    "start",
    "start_time",
    "ts_start",
    "timestamp_start",
    "end",
    "end_time",
    "ts_end",
    "timestamp_end",
)
_HOST_KEYS = (
    "computer",
    "computername",
    "hostname",
    "host",
    "id.orig_h",
    "id.resp_h",
    "src_ip",
    "dst_ip",
    "source_ip",
    "dest_ip",
    "sourceip",
    "destinationip",
    "src",
    "dst",
)
_PRIMARY_KEYS = (
    "computer",
    "computername",
    "hostname",
    "host",
    "id.orig_h",
    "src_ip",
    "source_ip",
    "sourceip",
    "src",
)
_DATA_SUFFIX = (".json", ".jsonl", ".csv", ".tsv", ".log", ".gz")
_SKIP_SUFFIX = (".pcap", ".pcapng", ".parquet", ".zip", ".png", ".jpg", ".jpeg", ".xml", ".evtx")


def _minmax(current: float | None, value: float | None, *, pick_max: bool) -> float | None:
    if value is None:
        return current
    if current is None:
        return value
    return max(current, value) if pick_max else min(current, value)


@dataclass
class _Src:
    count: int = 0
    lines: list[int] = field(default_factory=list)
    min_ts: float | None = None
    max_ts: float | None = None

    def add(self, line_no: int, times: list[float]) -> None:
        self.count += 1
        self.lines.append(line_no)
        for ts in times:
            self.min_ts = _minmax(self.min_ts, ts, pick_max=False)
            self.max_ts = _minmax(self.max_ts, ts, pick_max=True)


@dataclass
class _Step:
    count: int = 0
    rules: set[str] = field(default_factory=set)
    hosts: set[str] = field(default_factory=set)
    paths: set[str] = field(default_factory=set)
    min_ts: float | None = None
    max_ts: float | None = None
    by_source: dict[tuple[str, str], _Src] = field(default_factory=dict)

    def add(self, host: str, path: str, line_no: int, times: list[float], rules: list[str]) -> None:
        self.count += 1
        self.rules.update(rules)
        self.hosts.add(host)
        self.paths.add(path)
        for ts in times:
            self.min_ts = _minmax(self.min_ts, ts, pick_max=False)
            self.max_ts = _minmax(self.max_ts, ts, pick_max=True)
        self.by_source.setdefault((host, path), _Src()).add(line_no, times)


@dataclass
class _Host:
    count: int = 0
    steps: set[str] = field(default_factory=set)
    paths: set[str] = field(default_factory=set)
    min_ts: float | None = None
    max_ts: float | None = None

    def add(self, step: str, path: str, times: list[float]) -> None:
        self.count += 1
        self.steps.add(step)
        self.paths.add(path)
        for ts in times:
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


def _field(row: dict[str, Any], key: str) -> Any:
    want = key.casefold()
    for name, value in row.items():
        if str(name).casefold() == want:
            return value
    return None


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    return text.casefold() if text else ""


def _raw_text(value: Any) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value).strip()


def _useful(value: Any) -> bool:
    text = _text(value)
    return text not in (None, "", "-", "(empty)")


def _parse_ts(value: Any, default_year: int) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, dict):
        for key in ("systemtime", "timestamp", "#text"):
            for name, inner in value.items():
                if str(name).casefold() == key:
                    return _parse_ts(inner, default_year)
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text in {"-", "(empty)"}:
        return None
    try:
        return float(text)
    except ValueError:
        return parse_time(text, default_year)


def _row_times(row: dict[str, Any], default_year: int) -> list[float]:
    found: list[float] = []
    seen: set[str] = set()
    for key in _TIME_KEYS:
        if key in seen:
            continue
        seen.add(key)
        ts = _parse_ts(_field(row, key), default_year)
        if ts is not None:
            found.append(ts)
    return found


def _tokens(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        parts = [str(item) for item in value]
    else:
        parts = re.split(r"[|,;/]+", str(value))
    out: list[str] = []
    for part in parts:
        piece = part.strip()
        if piece and _text(piece) not in _BENIGN and _text(piece) not in _GENERIC_STEP:
            out.append(piece)
    return out


def _tactic(row: dict[str, Any]) -> str:
    for key in _TACTIC_KEYS:
        for token in _tokens(_field(row, key)):
            return token
    return ""


def _techniques(row: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for key in _TECH_KEYS:
        found.extend(_tokens(_field(row, key)))
    ordered: list[str] = []
    seen: set[str] = set()
    for token in found:
        mark = token.casefold()
        if mark not in seen:
            seen.add(mark)
            ordered.append(token)
    return ordered


def _step_name(row: dict[str, Any], techniques: list[str]) -> str:
    tactic = _tactic(row)
    if tactic:
        return tactic
    raw = _raw_text(_field(row, "label"))
    if raw and _text(raw) not in _BENIGN and _text(raw) not in _GENERIC_STEP:
        return raw
    if techniques:
        return techniques[0]
    return "attack"


def row_is_attack(row: dict[str, Any]) -> bool:
    """True when the row is an attack label, not a benign/normal telemetry row."""
    benign = _text(_field(row, "benign"))
    if benign in {"true", "1", "yes"}:
        return False
    flag = _text(_field(row, "is_attack"))
    if flag not in (None, ""):
        return flag not in _BENIGN
    for key in ("label", "ground_truth", "attack_cat", "label_tactic"):
        token = _text(_field(row, key))
        if token in (None, ""):
            continue
        return token not in _BENIGN
    return bool(_tactic(row) or _techniques(row))


def _hosts(row: dict[str, Any]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for key in _HOST_KEYS:
        value = _field(row, key)
        if not _useful(value):
            continue
        text = str(value).strip()
        if text not in seen:
            seen.add(text)
            found.append(text)
    return found


def _primary(row: dict[str, Any], hosts: list[str]) -> str:
    for key in _PRIMARY_KEYS:
        value = _field(row, key)
        if _useful(value):
            return str(value).strip()
    return hosts[0] if hosts else "unknown"


def _rules_for(step: str, techniques: list[str]) -> list[str]:
    if techniques:
        return techniques
    if step and step != "attack":
        return [step]
    return []


def _keep_name(name: str) -> bool:
    low = name.lower()
    if low.endswith(_SKIP_SUFFIX):
        return False
    return low.endswith(_DATA_SUFFIX)


def _decode(name: str, blob: bytes) -> str:
    if name.lower().endswith(".gz"):
        blob = gzip.decompress(blob)
    return blob.decode("utf-8", errors="replace")


def _iter_sources(root: Path) -> Iterator[tuple[str, bytes]]:
    if root.is_file() and (
        root.name.endswith(".zip") or root.name.endswith((".tar", ".tar.gz", ".tgz"))
    ):
        yield from _iter_archive(root)
        return
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.stat().st_size and _keep_name(path.name):
            yield path.relative_to(root).as_posix(), path.read_bytes()


def _iter_archive(root: Path) -> Iterator[tuple[str, bytes]]:
    if root.name.endswith(".zip"):
        with zipfile.ZipFile(root) as zf:
            for info in zf.infolist():
                if info.is_dir() or not info.file_size or not _keep_name(info.filename):
                    continue
                yield info.filename, zf.read(info)
        return
    with tarfile.open(root, "r:*") as tf:
        for member in tf:
            if not member.isfile() or not member.size or not _keep_name(member.name):
                continue
            extracted = tf.extractfile(member)
            if extracted is not None:
                yield member.name, extracted.read()


def _json_rows(text: str) -> list[tuple[int, dict[str, Any]]] | None:
    stripped = text.lstrip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        doc = None
    if isinstance(doc, dict):
        return [(1, doc)]
    if isinstance(doc, list):
        return [(i, item) for i, item in enumerate(doc, 1) if isinstance(item, dict)]
    rows: list[tuple[int, dict[str, Any]]] = []
    for i, line in enumerate(text.splitlines(), 1):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append((i, obj))
    return rows


def _table_delim(text: str) -> str:
    head = text.lstrip().splitlines()[:12]
    if any(line.startswith("#separator") or line.startswith("#fields") for line in head):
        return "\t"
    first = next((line for line in text.splitlines() if line.strip()), "")
    return "\t" if "\t" in first else ","


def _table_rows(text: str) -> list[tuple[int, dict[str, Any]]]:
    lines = text.splitlines()
    delim = _table_delim(text)
    header: list[str] | None = None
    header_at = 0
    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue
        if line.startswith("#") and not line.startswith("#fields"):
            continue
        body = line.split("\t", 1)[1] if line.startswith("#fields") and "\t" in line else line
        header = next(csv.reader(io.StringIO(body), delimiter=delim))
        header_at = i
        break
    if not header:
        return []
    rows: list[tuple[int, dict[str, Any]]] = []
    for i, line in enumerate(lines[header_at:], header_at + 1):
        if not line.strip() or line.startswith("#"):
            continue
        cols = next(csv.reader(io.StringIO(line), delimiter=delim))
        row = {header[j]: cols[j] for j in range(min(len(header), len(cols))) if header[j]}
        rows.append((i, row))
    return rows


def iter_rows(name: str, blob: bytes) -> list[tuple[int, dict[str, Any]]]:
    text = _decode(name, blob)
    parsed = _json_rows(text)
    if parsed is not None:
        return parsed
    return _table_rows(text)


def _touch(
    steps: dict[str, _Step], hosts: dict[str, _Host], rel: str, line_no: int, row: dict, year: int
) -> bool:
    if not row_is_attack(row):
        return False
    techniques = _techniques(row)
    step = _step_name(row, techniques)
    times = _row_times(row, year)
    affected = _hosts(row) or ["unknown"]
    primary = _primary(row, affected)
    rules = _rules_for(step, techniques)
    acc = steps.setdefault(step, _Step())
    acc.add(primary, "/" + rel.lstrip("/"), line_no, times, rules)
    for host in affected:
        acc.hosts.add(host)
        hosts.setdefault(host, _Host()).add(step, "/" + rel.lstrip("/"), times)
    return True


def _aggregate(root: Path, default_year: int):
    steps: dict[str, _Step] = {}
    hosts: dict[str, _Host] = {}
    files: list[str] = []
    total = 0
    min_ts: float | None = None
    max_ts: float | None = None
    for rel, blob in _iter_sources(root):
        hits = 0
        file_min: float | None = None
        file_max: float | None = None
        for line_no, row in iter_rows(rel, blob):
            if not _touch(steps, hosts, rel, line_no, row, default_year):
                continue
            hits += 1
            for ts in _row_times(row, default_year):
                file_min = _minmax(file_min, ts, pick_max=False)
                file_max = _minmax(file_max, ts, pick_max=True)
        if hits:
            files.append(rel)
            total += hits
            min_ts = _minmax(min_ts, file_min, pick_max=False)
            max_ts = _minmax(max_ts, file_max, pick_max=True)
    return steps, hosts, files, total, min_ts, max_ts


def _serialize(
    dataset: str,
    source: str,
    steps: dict[str, _Step],
    hosts: dict[str, _Host],
    files: list[str],
    total: int,
    min_ts: float | None,
    max_ts: float | None,
) -> dict[str, Any]:
    ordered = sorted(
        steps.items(),
        key=lambda item: (item[1].min_ts if item[1].min_ts is not None else float("inf"), item[0]),
    )
    attack_steps = [_step_dict(step, acc) for step, acc in ordered]
    host_dict = {
        host: {
            "count": acc.count,
            "steps": sorted(acc.steps),
            "log_paths": sorted(acc.paths),
            "time_window": _window_dict(acc.min_ts, acc.max_ts),
        }
        for host, acc in sorted(hosts.items())
    }
    return {
        "dataset": dataset,
        "index": DATASET_INDEXES[dataset],
        "split": "proof",
        "source": source,
        "label_files": sorted(files),
        "total_labelled_lines": total,
        "affected_hosts": sorted(hosts),
        "step_counts": {step: acc.count for step, acc in sorted(steps.items())},
        "time_window": _window_dict(min_ts, max_ts),
        "attack_steps": attack_steps,
        "hosts": host_dict,
    }


def _step_dict(step: str, acc: _Step) -> dict[str, Any]:
    return {
        "step": step,
        "rules": sorted(acc.rules),
        "count": acc.count,
        "affected_hosts": sorted(acc.hosts),
        "log_paths": sorted(acc.paths),
        "time_window": _window_dict(acc.min_ts, acc.max_ts),
        "sources": [
            {
                "host": host,
                "log_path": path,
                "count": src.count,
                "line_ranges": _merge_lines(src.lines),
                "time_window": _window_dict(src.min_ts, src.max_ts),
            }
            for (host, path), src in sorted(acc.by_source.items())
        ],
    }


def build_key(*, dataset: str, root: Path, default_year: int = 2024) -> dict[str, Any]:
    """Build one out-of-band scorer key. Attack rows only; raw log lines are not copied."""
    if dataset not in DATASET_INDEXES:
        raise ValueError(f"unsupported dataset {dataset!r}; expected one of {DATASETS}")
    if not root.exists():
        raise ValueError(f"root does not exist: {root}")
    steps, hosts, files, total, min_ts, max_ts = _aggregate(root, default_year)
    return _serialize(dataset, str(root), steps, hosts, files, total, min_ts, max_ts)


def format_summary(key: dict[str, Any]) -> str:
    """Compact step/host/window summary. Raw telemetry is not included."""
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


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--root", required=True, type=Path, help="dataset directory or .zip/.tar archive"
    )
    ap.add_argument("--dataset", required=True, choices=DATASETS)
    ap.add_argument(
        "--out",
        type=Path,
        help="scorer key JSON path (operator default: /Volumes/data01/hunt_keys/<dataset>_key.json)",
    )
    ap.add_argument("--default-year", type=int, default=2024)
    ap.add_argument("--summary", action="store_true", help="print step/host/window summary")
    args = ap.parse_args(argv)
    if not args.root.exists():
        ap.error(f"--root does not exist: {args.root}")
    if args.out is None and not args.summary:
        ap.error("at least one of --out or --summary is required")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    key = build_key(dataset=args.dataset, root=args.root, default_year=args.default_year)
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
