#!/usr/bin/env python3
"""Plan and ship publisher-faithful telemetry into the isolated labelled_corpus index."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portal.modules.security.core.siem.hec_ship import ship_batch  # noqa: E402
from scripts import corpus_ingest as legacy  # noqa: E402
from scripts import lab_delete_cousins  # noqa: E402

INDEX = "labelled_corpus"
DATA_SUFFIXES = (*legacy.DATA_SUFFIXES, ".csv", ".xml")
BATCH = 500
EXPECTED_COMMITS = {
    "attack_data": "4145e8b60fd8a3d44bc2170d1eb343fe7247387b",
    "mordor": "d9d40ef123d2c87d5d3df28c96bcab4f0faccc87",
}
EXPECTED_INPUTS = {
    "attack_data": "1352 manifest tests (task baseline)",
    "mordor": "111 metadata datasets plus APT29 and APT3 (task baseline)",
    "invictus_ir": "2900 CloudTrail records (task baseline)",
}
MANIFEST_SOURCE_IDS = {"invictus_ir": "invictus_ir_aws_dataset"}
SOURCE_URLS = {
    "attack_data": "https://github.com/splunk/attack_data",
    "mordor": "https://github.com/OTRF/Security-Datasets",
    "evtx_samples": "https://github.com/sbousseaden/EVTX-ATTACK-SAMPLES",
    "evtx_mitre": "https://github.com/mdecrevoisier/EVTX-to-MITRE-Attack",
    "invictus_ir": "https://github.com/invictus-ir/aws_dataset",
}
PUBLISHER_NAMES = {
    "attack_data": ("attack_data", "splunk attack data"),
    "mordor": ("mordor", "otrf", "security datasets"),
    "evtx_samples": ("evtx attack samples", "sbousseaden"),
    "evtx_mitre": ("evtx to mitre attack", "mdecrevoisier"),
    "invictus_ir": ("invictus ir", "invictus-ir", "aws dataset"),
}
NOT_INGESTED = {
    "flaws.cloud": "public CTF CloudTrail has no labels and is not benign background",
    "CloudTrail ATT&CK research": "an API-to-tactic table, not telemetry",
    "DARPA OpTC": "only the ground-truth PDF is present; the approximately 1 TB captures were not fetched",
}
TECHNIQUE_RE = re.compile(r"\bT\d{4}(?:\.\d{3})?\b", re.IGNORECASE)
TOOL_TELLS = {
    "Atomic Red Team": re.compile(r"atomic[\s_-]*red[\s_-]*team", re.IGNORECASE),
    "Stratus Red Team": re.compile(r"stratus[\s_-]*red[\s_-]*team", re.IGNORECASE),
}


@dataclass(frozen=True)
class CorpusFile:
    publisher: str
    test_id: str
    path: Path
    root: Path
    declared_sourcetype: str | None = None
    declared_source: str | None = None
    fallback_epoch: float | None = None
    scenario: str | None = None


@dataclass(frozen=True)
class ResolvedEvent:
    body: dict[str, Any] | str
    sourcetype: str
    source: str
    host: str
    epoch: float | None
    date_fallback: bool
    unknown_sourcetype: bool
    unknown_host: bool
    source_replaced: bool
    host_replaced: bool
    residual_leak: bool
    source_checked_value: str
    host_checked_value: str
    tool_tells: tuple[str, ...]


def default_roots(sources_root: Path, corpora_root: Path) -> dict[str, Path]:
    return {
        "attack_data": sources_root / "attack_data",
        "mordor": sources_root / "mordor",
        "evtx_samples": sources_root / "evtx_samples",
        "evtx_mitre": sources_root / "evtx_mitre",
        "invictus_ir": corpora_root / "invictus_ir_aws_dataset" / "repo" / "CloudTrail",
    }


def _date_epoch(value: Any) -> float | None:
    if value is None:
        return None
    epoch = legacy.event_epoch({"timestamp": str(value)}, math.nan)
    return epoch if math.isfinite(epoch) else None


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _mordor_dates(root: Path) -> dict[str, float]:
    dates: dict[str, float] = {}
    for meta in sorted(root.rglob("*.y*ml")):
        if "_metadata" not in meta.parts:
            continue
        try:
            doc = yaml.safe_load(meta.read_text(encoding="utf-8", errors="replace"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(doc, dict) or (epoch := _date_epoch(doc.get("creation_date"))) is None:
            continue
        dates[meta.stem.casefold()] = epoch
        for link in _strings(doc):
            name = Path(urlparse(link).path).name.casefold()
            if name.endswith(DATA_SUFFIXES):
                dates[name] = epoch
    return dates


def _mordor_date(path: Path, root: Path, dates: Mapping[str, float]) -> float | None:
    candidates = [path.name.casefold(), path.stem.casefold()]
    candidates.extend(part.casefold() for part in reversed(path.relative_to(root).parts))
    return next((dates[name] for name in candidates if name in dates), None)


def _tree_files(publisher: str, root: Path) -> Iterator[CorpusFile]:
    mordor_dates = _mordor_dates(root) if publisher == "mordor" else {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in DATA_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if any(part.startswith(".") or part == "_metadata" for part in relative.parts):
            continue
        if publisher == "invictus_ir":
            test_id = "aws_dataset/stratus_red_team_scenario"
            scenario = "named_cloud_scenario"
            fallback = None
        elif publisher == "mordor":
            test_id = relative.parent.as_posix()
            scenario = None
            fallback = _mordor_date(path, root, mordor_dates)
        else:
            test_id = relative.with_suffix("").as_posix()
            scenario = None
            fallback = None
        yield CorpusFile(publisher, test_id, path, root, fallback_epoch=fallback, scenario=scenario)


def p5_item_id(publisher: str, test_id: str) -> str:
    return hashlib.sha256(f"{publisher}|{test_id}".encode()).hexdigest()[:16]


def read_attack_data(root: Path) -> list[CorpusFile]:
    return [
        CorpusFile(
            "attack_data",
            item.path.parent.relative_to(root).as_posix(),
            item.path,
            root,
            item.sourcetype,
            item.source,
            item.dataset_epoch,
        )
        for item in legacy.load_manifest_catalog(root)
    ]


def read_mordor(root: Path) -> list[CorpusFile]:
    return list(_tree_files("mordor", root))


def read_evtx_samples(root: Path) -> list[CorpusFile]:
    return list(_tree_files("evtx_samples", root))


def read_evtx_mitre(root: Path) -> list[CorpusFile]:
    return list(_tree_files("evtx_mitre", root))


def read_invictus_ir(root: Path) -> list[CorpusFile]:
    return list(_tree_files("invictus_ir", root))


def publisher_files(publisher: str, root: Path) -> list[CorpusFile]:
    readers = {
        "attack_data": read_attack_data,
        "mordor": read_mordor,
        "evtx_samples": read_evtx_samples,
        "evtx_mitre": read_evtx_mitre,
        "invictus_ir": read_invictus_ir,
    }
    return readers[publisher](root) if root.is_dir() else []


def _xml_fields(body: str) -> dict[str, str]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return {}
    return {
        element.tag.rsplit("}", 1)[-1]: (element.text or "").strip()
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] in {"Channel", "Computer"} and element.text
    }


def _json_channel(event: Mapping[str, Any]) -> str | None:
    values: list[Any] = [event.get("Channel"), event.get("channel")]
    winlog = event.get("winlog")
    if isinstance(winlog, Mapping):
        values.append(winlog.get("channel"))
    event_root = event.get("Event")
    if isinstance(event_root, Mapping):
        system = event_root.get("System")
        if isinstance(system, Mapping):
            values.append(system.get("Channel"))
    return next((str(value).strip() for value in values if value), None)


def _is_cloudtrail(event: Any) -> bool:
    return isinstance(event, Mapping) and bool(event.get("eventSource") and event.get("eventName"))


def _source_fields(
    publisher: str,
    event: dict[str, Any] | str,
    declared_sourcetype: str | None,
    declared_source: str | None,
) -> tuple[str, str]:
    xml = _xml_fields(event) if isinstance(event, str) and event.lstrip().startswith("<") else {}
    channel = xml.get("Channel") if xml else None
    is_xml = bool(channel)
    if isinstance(event, Mapping) and not channel:
        channel = _json_channel(event)
    if declared_sourcetype:
        sourcetype = declared_sourcetype
    elif channel:
        sourcetype = "XmlWinEventLog" if is_xml else "_json"
    elif _is_cloudtrail(event):
        sourcetype = "aws:cloudtrail"
    else:
        sourcetype = f"{publisher}:unknown"
    if declared_source:
        source = declared_source
    elif channel:
        source = f"XmlWinEventLog:{channel}" if is_xml else channel
    elif _is_cloudtrail(event):
        source = "aws_cloudtrail"
    else:
        source = f"{publisher}:unknown"
    return sourcetype, source


def _host_value(event: dict[str, Any] | str, xml_fields: Mapping[str, str] | None = None) -> str:
    if isinstance(event, str):
        value = (xml_fields or _xml_fields(event)).get("Computer")
        return value or "unknown"
    values: list[Any] = [
        event.get("Computer"),
        event.get("hostname"),
        event.get("host"),
        event.get("Hostname"),
    ]
    event_root = event.get("Event")
    if isinstance(event_root, Mapping):
        system = event_root.get("System")
        if isinstance(system, Mapping):
            values.append(system.get("Computer"))
    if not any(values):
        values.append(event.get("recipientAccountId"))
    return next((str(value).strip() for value in values if value not in (None, "")), "unknown")


def _path_tokens(item: CorpusFile) -> set[str]:
    parts = list(Path(item.test_id).parts)
    tokens = {part for part in parts if len(part) >= 4}
    lower = [part.casefold() for part in parts]
    for index, part in enumerate(lower[:-1]):
        if part in {"malware", "campaign", "campaigns", "apt_simulations"}:
            tokens.add(parts[index + 1])
    tokens.update(PUBLISHER_NAMES.get(item.publisher, ()))
    tokens.add(item.publisher)
    return {token.casefold() for token in tokens if len(token) >= 4}


def value_has_leak(value: str, item: CorpusFile) -> bool:
    if TECHNIQUE_RE.search(value):
        return True
    normalized = re.sub(r"[^a-z0-9]", "", value.casefold())
    return any(re.sub(r"[^a-z0-9]", "", token) in normalized for token in _path_tokens(item))


def _tool_tells(item: CorpusFile, event: dict[str, Any] | str) -> tuple[str, ...]:
    body = (
        event if isinstance(event, str) else json.dumps(event, ensure_ascii=False, sort_keys=True)
    )
    haystack = f"{item.test_id}\n{body}"
    return tuple(name for name, pattern in TOOL_TELLS.items() if pattern.search(haystack))


def resolve_event(item: CorpusFile, event: dict[str, Any] | str) -> ResolvedEvent:
    sourcetype, source = _source_fields(
        item.publisher, event, item.declared_sourcetype, item.declared_source
    )
    xml_fields = (
        _xml_fields(event) if isinstance(event, str) and event.lstrip().startswith("<") else {}
    )
    host = _host_value(event, xml_fields)
    own_epoch = legacy.event_epoch(event, math.nan)
    date_fallback = not math.isfinite(own_epoch) and item.fallback_epoch is not None
    epoch = own_epoch if math.isfinite(own_epoch) else item.fallback_epoch
    source_replaced = value_has_leak(source, item)
    host_replaced = value_has_leak(host, item)
    safe_source = sourcetype if source_replaced else source
    safe_host = sourcetype if host_replaced else host
    residual = (source_replaced and value_has_leak(safe_source, item)) or (
        host_replaced and value_has_leak(safe_host, item)
    )
    return ResolvedEvent(
        event,
        sourcetype,
        safe_source,
        safe_host,
        epoch,
        date_fallback,
        sourcetype.endswith(":unknown"),
        host == "unknown",
        source_replaced,
        host_replaced,
        residual,
        source,
        host,
        _tool_tells(item, event),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_facts(name: str, root: Path) -> dict[str, Any]:
    if not root.exists():
        return {
            "status": "missing",
            "path": str(root),
            "commit": None,
            "dirty_paths": None,
            "expected_commit": EXPECTED_COMMITS.get(name),
        }
    repo = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    commit = repo.stdout.strip() if repo.returncode == 0 else None
    dirty_paths = (
        sum(bool(line) for line in status.stdout.splitlines()) if status.returncode == 0 else None
    )
    return {
        "status": "available_local",
        "path": str(root),
        "commit": commit,
        "dirty_paths": dirty_paths,
        "expected_commit": EXPECTED_COMMITS.get(name),
        "commit_matches_expected": commit == EXPECTED_COMMITS[name]
        if name in EXPECTED_COMMITS
        else None,
    }


def _item_bucket(
    items: dict[str, dict[str, Any]], item: CorpusFile, item_id: str
) -> dict[str, Any]:
    record = items.setdefault(
        item_id,
        {
            "publisher": item.publisher,
            "test_id": item.test_id,
            "scenario": item.scenario,
            "data_files": {},
            "declared_sourcetypes": Counter(),
            "indexed_sourcetypes": Counter(),
            "hosts": Counter(),
            "events": 0,
            "unknown_sourcetype": 0,
            "unknown_host": 0,
            "date_fallback": 0,
            "missing_time": 0,
            "source_replacements": 0,
            "host_replacements": 0,
            "residual_leaks": 0,
            "tool_tells": set(),
        },
    )
    record["data_files"][item.path.relative_to(item.root).as_posix()] = _sha256(item.path)
    return record


@dataclass
class ScanAccumulator:
    items: dict[str, dict[str, Any]] = field(default_factory=dict)
    totals: Counter[str] = field(default_factory=Counter)
    by_publisher: Counter[str] = field(default_factory=Counter)
    by_sourcetype: Counter[str] = field(default_factory=Counter)
    by_source: Counter[str] = field(default_factory=Counter)
    by_host: Counter[str] = field(default_factory=Counter)
    distinct_sources: set[str] = field(default_factory=set)
    distinct_hosts: set[str] = field(default_factory=set)
    pointer_skips: Counter[str] = field(default_factory=Counter)
    file_counts: Counter[str] = field(default_factory=Counter)

    def record(self, item: CorpusFile, bucket: dict[str, Any], event: dict[str, Any] | str) -> None:
        resolved = resolve_event(item, event)
        bucket["events"] += 1
        bucket["indexed_sourcetypes"][resolved.sourcetype] += 1
        bucket["declared_sourcetypes"][item.declared_sourcetype or "unspecified"] += 1
        bucket["hosts"][resolved.host] += 1
        bucket["unknown_sourcetype"] += int(resolved.unknown_sourcetype)
        bucket["unknown_host"] += int(resolved.unknown_host)
        bucket["date_fallback"] += int(resolved.date_fallback)
        bucket["missing_time"] += int(resolved.epoch is None)
        bucket["source_replacements"] += int(resolved.source_replaced)
        bucket["host_replacements"] += int(resolved.host_replaced)
        bucket["residual_leaks"] += int(resolved.residual_leak)
        bucket["tool_tells"].update(resolved.tool_tells)
        self.totals["events"] += 1
        self.totals["unknown_sourcetype"] += int(resolved.unknown_sourcetype)
        self.totals["unknown_host"] += int(resolved.unknown_host)
        self.totals["date_fallback"] += int(resolved.date_fallback)
        self.totals["missing_time"] += int(resolved.epoch is None)
        self.totals["source_replacements"] += int(resolved.source_replaced)
        self.totals["host_replacements"] += int(resolved.host_replaced)
        self.totals["residual_leaks"] += int(resolved.residual_leak)
        self.by_publisher[item.publisher] += 1
        self.by_sourcetype[resolved.sourcetype] += 1
        self.by_source[resolved.source] += 1
        self.by_host[resolved.host] += 1
        self.distinct_sources.add(resolved.source_checked_value)
        self.distinct_hosts.add(resolved.host_checked_value)

    def output(self, read_errors: list[dict[str, str]]) -> dict[str, Any]:
        for bucket in self.items.values():
            for key in ("declared_sourcetypes", "indexed_sourcetypes", "hosts"):
                bucket[key] = dict(sorted(bucket[key].items()))
            bucket["data_files"] = [
                {"path": name, "sha256": digest}
                for name, digest in sorted(bucket["data_files"].items())
            ]
            bucket["tool_tells"] = sorted(bucket["tool_tells"])
        tests_by_publisher = Counter(item["publisher"] for item in self.items.values())
        return {
            "items": dict(sorted(self.items.items())),
            "totals": dict(self.totals),
            "tests_by_publisher": dict(sorted(tests_by_publisher.items())),
            "by_publisher": dict(sorted(self.by_publisher.items())),
            "by_sourcetype": dict(sorted(self.by_sourcetype.items())),
            "by_source": dict(sorted(self.by_source.items())),
            "by_host": dict(sorted(self.by_host.items())),
            "distinct_source_values_checked": len(self.distinct_sources),
            "distinct_host_values_checked": len(self.distinct_hosts),
            "read_errors": read_errors,
            "lfs_pointer_skips": dict(self.pointer_skips),
            "files_read": dict(self.file_counts),
        }


def iter_evtx_text(path: Path) -> Iterator[str]:
    from Evtx.Evtx import Evtx  # type: ignore[import-untyped]

    with Evtx(str(path)) as source:
        for record in source.records():
            yield record.xml()


def _iter_file_events(item: CorpusFile) -> Iterator[dict[str, Any] | str]:
    if item.path.suffix.lower() == ".evtx":
        for event in iter_evtx_text(item.path):
            yield from legacy.iter_cloudtrail_records(event)
        return
    for line in legacy.iter_events_text(item.path):
        yield from legacy.iter_cloudtrail_records(line)


def scan_inputs(files_by_publisher: Mapping[str, list[CorpusFile]]) -> dict[str, Any]:
    accumulator = ScanAccumulator()
    read_errors: list[dict[str, str]] = []
    for publisher, files in files_by_publisher.items():
        for item in files:
            if not item.path.is_file():
                read_errors.append(
                    {"publisher": publisher, "path": item.path.name, "error": "missing_file"}
                )
                continue
            if legacy.is_lfs_pointer(item.path):
                accumulator.pointer_skips[publisher] += 1
                continue
            accumulator.file_counts[publisher] += 1
            item_id = p5_item_id(publisher, item.test_id)
            try:
                bucket = _item_bucket(accumulator.items, item, item_id)
                for event in _iter_file_events(item):
                    accumulator.record(item, bucket, event)
            except Exception as exc:
                read_errors.append(
                    {
                        "publisher": publisher,
                        "path": item.path.relative_to(item.root).as_posix(),
                        "error": type(exc).__name__,
                    }
                )
    return accumulator.output(read_errors)


def _tree_checksum(items: Mapping[str, Mapping[str, Any]], publisher: str) -> str | None:
    values: list[str] = []
    for entry in items.values():
        if entry["publisher"] != publisher:
            continue
        values.extend(
            f"{entry['test_id']}|{file['path']}|{file['sha256']}" for file in entry["data_files"]
        )
    if not values:
        return None
    return hashlib.sha256("\n".join(sorted(values)).encode()).hexdigest()


def _stamp(source_facts_by_name: Mapping[str, Mapping[str, Any]]) -> str:
    parts = []
    for name, facts in source_facts_by_name.items():
        commit = facts.get("commit") or facts.get("expected_commit")
        parts.append(f"{name}-{commit if commit else 'missing'}")
    now = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{now}__{'__'.join(parts)}"


def _source_summary(
    roots: Mapping[str, Path],
    source_facts_by_name: dict[str, dict[str, Any]],
    scan: dict[str, Any],
    manifest_records: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    records = []
    for name, root in roots.items():
        facts = source_facts_by_name[name]
        acquisition = manifest_records.get(MANIFEST_SOURCE_IDS.get(name, ""), {})
        observed_checksum = _tree_checksum(scan["items"], name)
        records.append(
            {
                "publisher": name,
                "url": SOURCE_URLS[name],
                "path": str(root),
                "status": facts["status"],
                "commit": facts.get("commit"),
                "expected_commit": facts.get("expected_commit"),
                "dirty_paths": facts.get("dirty_paths"),
                "commit_matches_expected": facts.get("commit_matches_expected"),
                "checksum_algorithm": "acquisition manifest and sha256 over event-file path/hash tuples",
                "checksum": acquisition.get("checksum") or observed_checksum,
                "observed_event_file_checksum": observed_checksum,
                "existing_manifest_checksum": acquisition.get("checksum"),
                "bytes": acquisition.get("bytes")
                or sum(
                    item.path.stat().st_size
                    for item in publisher_files(name, root)
                    if item.path.is_file()
                ),
                "license": acquisition.get("license")
                or (
                    "LICENSE file present; not independently reviewed"
                    if (root / "LICENSE").is_file()
                    else None
                ),
                "fetched_at": acquisition.get("fetched_at"),
            }
        )
    return records


def _write_fidelity(path: Path, report: Mapping[str, Any]) -> None:
    scan = report["scan"]
    lines = [
        "# R0b corpus fidelity dry run",
        "",
        f"Stamp: `{report['stamp']}`",
        "",
        "Mode: DRY-RUN. No index was created and no HEC events were sent.",
        f"Status: {report['status']}.",
        "",
        "## Expected input counts",
        "",
        *[f"- **{name}:** {expectation}." for name, expectation in EXPECTED_INPUTS.items()],
        "",
        "## Current source status",
        "",
        "| Publisher | Commit | Dirty source paths |",
        "|---|---|---:|",
        *[
            f"| {name} | `{facts.get('commit') or 'not acquired'}` | {facts.get('dirty_paths', 'n/a')} |"
            for name, facts in report["source_facts"].items()
        ],
        "",
        "## Publisher counts",
        "",
        "| Publisher | Tests | Files | Events parsed / would ship |",
        "|---|---:|---:|---:|",
    ]
    for publisher in report["roots"]:
        lines.append(
            f"| {publisher} | {scan['tests_by_publisher'].get(publisher, 0)} | "
            f"{scan['files_read'].get(publisher, 0)} | {scan['by_publisher'].get(publisher, 0)} |"
        )
    lines.extend(["", "## Sourcetype counts", "", "| Sourcetype | Events |", "|---|---:|"])
    lines.extend(f"| {name} | {count} |" for name, count in scan["by_sourcetype"].items())
    lines.extend(["", "## Source counts", "", "| Sanitized source | Events |", "|---|---:|"])
    lines.extend(f"| `{name}` | {count} |" for name, count in scan["by_source"].items())
    lines.extend(["", "## Host counts", "", "| Sanitized host | Events |", "|---|---:|"])
    lines.extend(f"| `{name}` | {count} |" for name, count in scan["by_host"].items())
    totals = scan["totals"]
    total_events = totals.get("events", 0)

    def share(name: str) -> str:
        count = totals.get(name, 0)
        percent = 100 * count / total_events if total_events else 0.0
        return f"{count} / {total_events} ({percent:.2f}%)"

    lines.extend(
        [
            "",
            "## Fidelity counters",
            "",
            f"- Unknown sourcetype: {share('unknown_sourcetype')}.",
            f"- Unknown host: {share('unknown_host')}.",
            f"- Date-fallback timestamps: {share('date_fallback')}.",
            f"- Missing event and manifest dates: {share('missing_time')}.",
            f"- Leak replacements: source {totals.get('source_replacements', 0)}, host {totals.get('host_replacements', 0)}.",
            f"- Residual leak values after sourcetype replacement: {totals.get('residual_leaks', 0)}.",
            f"- Distinct source values checked: {scan['distinct_source_values_checked']}.",
            f"- Distinct host values checked: {scan['distinct_host_values_checked']}.",
            "",
            "## Cousins selected for deletion",
            "",
        ]
    )
    if report.get("cousin_inventory"):
        inv = report["cousin_inventory"]
        lines.append(
            f"Read-only Splunk census: raw {inv['raw_count']}, tstats {inv['tstats_count']}, reconciled `{inv['reconciled']}`."
        )
        lines.extend(["", "| Source | Sourcetype | Host | Events |", "|---|---|---|---:|"])
        lines.extend(
            f"| `{row['source']}` | `{row['sourcetype']}` | `{row['host']}` | {row['count']} |"
            for row in inv["by_source_sourcetype_host"]
        )
    else:
        reason = report.get("cousin_census_error") or "not requested"
        lines.append(
            f"Not collected ({reason}); rerun with `--lab-census` to request read-only counts."
        )
    lines.extend(
        [
            "",
            "## Before/after shape",
            "",
            "| Property | Publisher record | Current lab copy (task baseline 2026-10-10) | This run after |",
            "|---|---|---|---|",
            "| Sourcetype | Declared or event channel | About 10 Portal types plus `corpus:raw` | Not indexed in dry run |",
            "| Source | Declared source or channel | `portal5:corpus:<src>:<test path>` | Not indexed in dry run |",
            "| Host | Event host or account id | `corpus-<src>` | Not indexed in dry run |",
            "| Body | XML, JSON, or line as published | Some Windows bodies flattened | Preserved by plan |",
            "",
            "## Extraction checks",
            "",
            "Not run: this lane does not create the index or ship events.",
            "",
            "## Not ingested",
            "",
        ]
    )
    lines.extend(f"- **{name}:** {reason}." for name, reason in NOT_INGESTED.items())
    lines.extend(["", "## Missing or failed inputs", ""])
    lines.extend(
        f"- Missing source tree: `{name}` ({root})."
        for name, root in report["missing_roots"].items()
    )
    lines.extend(
        f"- Read failure: `{row['publisher']}/{row['path']}` ({row['error']})."
        for row in scan["read_errors"]
    )
    if not report["missing_roots"] and not scan["read_errors"]:
        lines.append("None.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_report(
    output_root: Path,
    roots: Mapping[str, Path],
    scan: dict[str, Any],
    source_facts_by_name: dict[str, dict[str, Any]],
    cousin_inventory: dict[str, Any] | None,
    missing_roots: Mapping[str, Path],
    manifest_records: Mapping[str, Mapping[str, Any]],
    cousin_census_error: str | None,
) -> Path:
    stamp = _stamp(source_facts_by_name)
    output = output_root / stamp
    output.mkdir(parents=True, exist_ok=False)
    partial = bool(
        missing_roots
        or scan["read_errors"]
        or cousin_census_error
        or scan["totals"].get("residual_leaks", 0)
        or any(fact.get("dirty_paths", 0) for fact in source_facts_by_name.values())
    )
    report = {
        "schema": "CORPUS_FIDELITY_DRY_RUN_V1",
        "stamp": stamp,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "mode": "DRY-RUN",
        "status": "PARTIAL" if partial else "COMPLETE",
        "index": INDEX,
        "roots": list(roots),
        "scan": scan,
        "cousin_inventory": cousin_inventory,
        "cousin_census_error": cousin_census_error,
        "source_facts": source_facts_by_name,
        "manifest_records": manifest_records,
        "missing_roots": {name: str(root) for name, root in missing_roots.items()},
    }
    items_doc = {
        "schema": "CORPUS_FIDELITY_ITEMS_V1",
        "stamp": stamp,
        "totals": scan["totals"],
        "items": scan["items"],
    }
    (output / "items.json").write_text(json.dumps(items_doc, indent=2, sort_keys=True) + "\n")
    acquisition = {
        "schema": "CORPUS_FIDELITY_ACQUISITION_V1",
        "stamp": stamp,
        "sources": _source_summary(roots, source_facts_by_name, scan, manifest_records),
    }
    (output / "acquisition.json").write_text(
        json.dumps(acquisition, indent=2, sort_keys=True) + "\n"
    )
    _write_fidelity(output / "fidelity.md", report)
    return output


def _iter_resolved(files: Iterator[CorpusFile]) -> Iterator[tuple[str, ResolvedEvent]]:
    for item in files:
        if not item.path.is_file() or legacy.is_lfs_pointer(item.path):
            continue
        item_id = p5_item_id(item.publisher, item.test_id)
        for event in _iter_file_events(item):
            yield item_id, resolve_event(item, event)


def ship_inputs(files_by_publisher: Mapping[str, list[CorpusFile]]) -> dict[str, int]:
    buffers: dict[tuple[str, str, str, str], list[tuple[dict[str, Any] | str, float]]] = (
        defaultdict(list)
    )
    counts: Counter[str] = Counter()

    def flush(key: tuple[str, str, str, str]) -> None:
        entries = buffers.pop(key)
        item_id, sourcetype, source, host = key
        result = ship_batch(
            [event for event, _ in entries],
            sourcetype=sourcetype,
            source=source,
            host=host,
            index=INDEX,
            event_times=[epoch for _, epoch in entries],
            fields={"p5_item": item_id},
        )
        if not result.get("ok"):
            raise RuntimeError(f"HEC batch failed for p5_item={item_id}")
        counts[item_id] += len(entries)

    for files in files_by_publisher.values():
        for item_id, resolved in _iter_resolved(iter(files)):
            if resolved.epoch is None:
                raise RuntimeError(
                    f"event has neither its own timestamp nor a manifest date: {item_id}"
                )
            key = (item_id, resolved.sourcetype, resolved.source, resolved.host)
            buffers[key].append((resolved.body, resolved.epoch))
            if len(buffers[key]) >= BATCH:
                flush(key)
    for key in list(buffers):
        flush(key)
    return dict(counts)


def verify_plan(items_path: Path) -> dict[str, Any]:
    doc = json.loads(items_path.read_text(encoding="utf-8"))
    expected = {item_id: int(item["events"]) for item_id, item in doc["items"].items()}
    rows = lab_delete_cousins.export_rows(f"| tstats count where index={INDEX} by p5_item")
    actual = {str(row.get("p5_item", "")): int(row.get("count", 0)) for row in rows}
    mismatches = {
        item_id: {"expected": count, "actual": actual.get(item_id, 0)}
        for item_id, count in expected.items()
        if actual.get(item_id, 0) != count
    }
    extras = sorted(set(actual) - set(expected))
    return {"ok": not mismatches and not extras, "mismatches": mismatches, "extra_p5_items": extras}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--ship", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument(
        "--sources-root", type=Path, default=Path("/Volumes/data01/portal5_hunt/sources")
    )
    parser.add_argument(
        "--corpora-root", type=Path, default=Path("/Volumes/data01/portal5_hunt/corpora")
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(
            os.environ.get("PORTAL_DATA_ROOT", str(Path.home() / "AI_Output" / "portal-data"))
        )
        / "reports/review_eval/corpus_fidelity",
    )
    parser.add_argument(
        "--items", type=Path, help="items.json written by --dry-run, required for --verify"
    )
    parser.add_argument(
        "--lab-census", action="store_true", help="include read-only portal5_lab cousin counts"
    )
    args = parser.parse_args()
    if args.verify:
        if args.items is None:
            parser.error("--verify requires --items")
        result = verify_plan(args.items)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1

    roots = default_roots(args.sources_root, args.corpora_root)
    facts = {name: source_facts(name, root) for name, root in roots.items()}
    missing_roots = {name: root for name, root in roots.items() if not root.is_dir()}
    files_by_publisher = {
        name: publisher_files(name, root) for name, root in roots.items() if root.is_dir()
    }
    scan = scan_inputs(files_by_publisher)
    manifest_path = args.corpora_root / "manifest.json"
    manifest_doc = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    )
    manifest_records = {
        str(record.get("source_id")): record
        for record in manifest_doc.get("sources", [])
        if isinstance(record, dict) and record.get("source_id")
    }
    cousin_inventory = None
    cousin_census_error = None
    if args.lab_census:
        try:
            cousin_inventory = lab_delete_cousins.cousin_inventory()
        except Exception as exc:
            cousin_census_error = type(exc).__name__
    output = write_report(
        args.output_root,
        roots,
        scan,
        facts,
        cousin_inventory,
        missing_roots,
        manifest_records,
        cousin_census_error,
    )
    print(f"DRY-RUN report: {output}")
    print(
        json.dumps(
            {"events": scan["totals"].get("events", 0), "missing_roots": list(missing_roots)},
            sort_keys=True,
        )
    )
    if args.ship:
        stale_source = any(
            facts[name].get("commit_matches_expected") is False
            or facts[name].get("dirty_paths", 0) > 0
            for name in ("attack_data", "mordor")
            if facts[name].get("status") == "available_local"
        )
        if (
            missing_roots
            or scan["read_errors"]
            or scan["totals"].get("residual_leaks", 0)
            or scan["totals"].get("missing_time", 0)
            or stale_source
        ):
            print(
                "[BLOCKED] source completeness, provenance, timestamps, or leak checks prevent shipping",
                file=sys.stderr,
            )
            return 2
        if scan["totals"].get("events", 0) != sum(scan["by_publisher"].values()):
            print("[BLOCKED] event census did not reconcile", file=sys.stderr)
            return 2
        shipped = ship_inputs(files_by_publisher)
        print(json.dumps({"mode": "SHIPPED", "counts_by_p5_item": shipped}, sort_keys=True))
        return 0
    return 2 if missing_roots or scan["read_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
