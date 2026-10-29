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
from scripts import acquire_corpus_sources as acquisition  # noqa: E402
from scripts import corpus_ingest as legacy  # noqa: E402
from scripts import lab_delete_cousins  # noqa: E402

INDEX = "labelled_corpus"
DATA_SUFFIXES = (*legacy.DATA_SUFFIXES, ".csv", ".xml")
BATCH = 500
EXPECTED_COMMITS = {
    "attack_data": "4145e8b60fd8a3d44bc2170d1eb343fe7247387b",
    "mordor": "d9d40ef123d2c87d5d3df28c96bcab4f0faccc87",
    "evtx_samples": "4ceed2f4706daf601c212a8f91c113dd85349a2c",
    "evtx_mitre": "474856008f037ccd42753f02a631b42690195829",
    "invictus_ir": "4667aa9c26330bc3317ed8bd526f4b83cff13602",
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
    event_format: str
    date_fallback: bool
    unknown_sourcetype: bool
    unknown_host: bool
    sourcetype_replaced: bool
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


_SYSLOG_RFC5424_HOST = re.compile(r"^(?:<\d{1,3}>)?\d+\s+\S+\s+(\S+)(?:\s|$)")
_SYSLOG_RFC3164_HOST = re.compile(
    r"^(?:<\d{1,3}>)?[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+(\S+)"
)
_SYSLOG_ISO_HOST = re.compile(r"^\S+T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})\s+(\S+)")
_SYSLOG_RFC3164_TIME = re.compile(
    r"^(?:<\d{1,3}>)?([A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
)
_EVENT_TIMESTAMP_KEYS = {
    "@timestamp",
    "timestamp",
    "timecreated",
    "systemtime",
    "utctime",
    "eventtime",
    "event_time",
    "timegenerated",
    "time_generated",
    "eventcreated",
    "creationtime",
    "created_at",
    "datetime",
    "date",
    "time",
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


def event_format(event: dict[str, Any] | str) -> str:
    if isinstance(event, str):
        if event.lstrip().startswith("<"):
            return "windows_xml"
        if _syslog_host(event) is not None:
            return "syslog"
        return "line"
    return "cloudtrail_json" if _is_cloudtrail(event) else "json"


def _syslog_host(line: str) -> str | None:
    for pattern in (_SYSLOG_RFC5424_HOST, _SYSLOG_RFC3164_HOST, _SYSLOG_ISO_HOST):
        match = pattern.match(line)
        if match and match.group(1) != "-":
            return match.group(1)
    return None


def _cloud_source_identity(event: Mapping[str, Any]) -> str | None:
    for key in (
        "recipientAccountId",
        "accountId",
        "account_id",
        "awsAccountId",
        "subscriptionId",
        "tenantId",
        "ResourceId",
        "resourceId",
    ):
        value = event.get(key)
        if value not in (None, "") and not isinstance(value, Mapping):
            return str(value).strip()
    for key in ("userIdentity", "identity", "cloud"):
        value = event.get(key)
        if not isinstance(value, Mapping):
            continue
        for identity_key in ("accountId", "account_id", "subscriptionId", "tenantId", "id"):
            identity = value.get(identity_key)
            if identity not in (None, "") and not isinstance(identity, Mapping):
                return str(identity).strip()
    return None


def _host_value(event: dict[str, Any] | str, xml_fields: Mapping[str, str] | None = None) -> str:
    if isinstance(event, str):
        value = (xml_fields or _xml_fields(event)).get("Computer")
        return value or _syslog_host(event) or "unknown"
    nested_host = event.get("host")
    nested_hostname = (
        nested_host.get("name") or nested_host.get("hostname")
        if isinstance(nested_host, Mapping)
        else None
    )
    values: list[Any] = [
        event.get("Computer"),
        event.get("hostname"),
        event.get("host") if not isinstance(nested_host, Mapping) else nested_hostname,
        event.get("Hostname"),
        event.get("host_name"),
        event.get("_HOSTNAME"),
    ]
    event_root = event.get("Event")
    if isinstance(event_root, Mapping):
        system = event_root.get("System")
        if isinstance(system, Mapping):
            values.append(system.get("Computer"))
    for value in values:
        if value not in (None, "") and not isinstance(value, Mapping):
            normalized = str(value).strip()
            if normalized:
                return normalized
    return _cloud_source_identity(event) or "unknown"


def _path_tokens(item: CorpusFile) -> set[str]:
    test_parts = list(Path(item.test_id).parts)
    file_parts = list(item.path.relative_to(item.root).parts)
    parts = test_parts + file_parts
    tokens = {part for part in parts if len(part) >= 4}
    tokens.update(Path(part).stem for part in file_parts if len(Path(part).stem) >= 4)
    lower = [part.casefold() for part in test_parts]
    for index, part in enumerate(lower[:-1]):
        if part in {"malware", "campaign", "campaigns", "apt_simulations"}:
            tokens.add(parts[index + 1])
    tokens.update(PUBLISHER_NAMES.get(item.publisher, ()))
    tokens.add(item.publisher)
    return {token.casefold() for token in tokens if len(token) >= 4}


def value_has_leak(value: str, item: CorpusFile) -> bool:
    if TECHNIQUE_RE.search(value):
        return True
    return any(
        re.search(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])", value, re.IGNORECASE)
        for token in _path_tokens(item)
    )


def _tool_tells(item: CorpusFile, event: dict[str, Any] | str) -> tuple[str, ...]:
    body = (
        event if isinstance(event, str) else json.dumps(event, ensure_ascii=False, sort_keys=True)
    )
    haystack = f"{item.test_id}\n{body}"
    return tuple(name for name, pattern in TOOL_TELLS.items() if pattern.search(haystack))


def _timestamp_epoch(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if math.isfinite(number) and number >= 100_000_000:
            return number / 1000 if number >= 100_000_000_000 else number
    elif value not in (None, ""):
        epoch = legacy.event_epoch({"timestamp": str(value)}, math.nan)
        if math.isfinite(epoch):
            return epoch
    return None


def _nested_timestamps(value: Any) -> Iterator[Any]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).casefold() in _EVENT_TIMESTAMP_KEYS:
                yield item
            if isinstance(item, (Mapping, list)):
                yield from _nested_timestamps(item)
    elif isinstance(value, list):
        for item in value:
            yield from _nested_timestamps(item)


def _event_epoch(event: dict[str, Any] | str, fallback: float | None) -> tuple[float | None, bool]:
    own_epoch = legacy.event_epoch(event, math.nan)
    if math.isfinite(own_epoch):
        return own_epoch, False
    if isinstance(event, Mapping):
        for value in _nested_timestamps(event):
            if (epoch := _timestamp_epoch(value)) is not None:
                return epoch, False
    if isinstance(event, str) and fallback is not None:
        match = _SYSLOG_RFC3164_TIME.match(event)
        if match:
            year = dt.datetime.fromtimestamp(fallback, dt.UTC).year
            parsed = dt.datetime.strptime(f"{year} {match.group(1)}", "%Y %b %d %H:%M:%S")
            return parsed.replace(tzinfo=dt.UTC).timestamp(), True
    return fallback, fallback is not None


def _safe_sourcetype(sourcetype: str, item: CorpusFile, event: dict[str, Any] | str) -> str:
    if not value_has_leak(sourcetype, item):
        return sourcetype
    format_fallback = {
        "windows_xml": "XmlWinEventLog",
        "cloudtrail_json": "aws:cloudtrail",
        "json": "_json",
        "syslog": "syslog",
        "line": "raw",
    }[event_format(event)]
    for candidate in (format_fallback, "unknown", "raw", "x"):
        if not value_has_leak(candidate, item):
            return candidate
    return "x"


def resolve_event(item: CorpusFile, event: dict[str, Any] | str) -> ResolvedEvent:
    original_sourcetype, source = _source_fields(
        item.publisher, event, item.declared_sourcetype, item.declared_source
    )
    xml_fields = (
        _xml_fields(event) if isinstance(event, str) and event.lstrip().startswith("<") else {}
    )
    host = _host_value(event, xml_fields)
    epoch, date_fallback = _event_epoch(event, item.fallback_epoch)
    sourcetype_replaced = value_has_leak(original_sourcetype, item)
    sourcetype = _safe_sourcetype(original_sourcetype, item, event)
    source_replaced = value_has_leak(source, item)
    host_replaced = value_has_leak(host, item)
    safe_source = sourcetype if source_replaced else source
    safe_host = sourcetype if host_replaced else host
    residual = any(value_has_leak(value, item) for value in (sourcetype, safe_source, safe_host))
    return ResolvedEvent(
        event,
        sourcetype,
        safe_source,
        safe_host,
        epoch,
        event_format(event),
        date_fallback,
        original_sourcetype.endswith(":unknown") or sourcetype_replaced,
        host == "unknown",
        sourcetype_replaced,
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
    top = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if top.returncode != 0:
        return {
            "status": "not_git",
            "path": str(root),
            "commit": None,
            "dirty_paths": None,
            "expected_commit": EXPECTED_COMMITS.get(name),
        }
    repo_root = Path(top.stdout.strip())
    repo = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    status = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    commit = repo.stdout.strip() if repo.returncode == 0 else None
    dirty_paths = (
        sum(bool(line) for line in status.stdout.splitlines()) if status.returncode == 0 else None
    )
    return {
        "status": "available_local"
        if repo.returncode == 0 and status.returncode == 0
        else "invalid_git",
        "path": str(root),
        "commit": commit,
        "dirty_paths": dirty_paths,
        "expected_commit": EXPECTED_COMMITS.get(name),
        "commit_matches_expected": commit == EXPECTED_COMMITS[name]
        if name in EXPECTED_COMMITS
        else None,
    }


def source_plan_blockers(facts: Mapping[str, Mapping[str, Any]]) -> list[str]:
    return sorted(
        name
        for name, record in facts.items()
        if record.get("status") not in {"missing", "available_local"}
        or record.get("dirty_paths") not in (0, None)
        or record.get("commit_matches_expected") is False
    )


def _roots_from_args(args: argparse.Namespace) -> tuple[dict[str, Path], set[str]]:
    roots = default_roots(args.sources_root, args.corpora_root)
    overrides = {
        "attack_data": args.attack_data_root,
        "mordor": args.mordor_root,
        "evtx_samples": args.evtx_samples_root,
        "evtx_mitre": args.evtx_mitre_root,
        "invictus_ir": args.invictus_root,
    }
    chosen = {name: path for name, path in overrides.items() if path is not None}
    roots.update(chosen)
    return roots, set(chosen)


def prefer_pinned_siblings(
    roots: Mapping[str, Path],
    sources_root: Path,
    corpora_root: Path,
    overridden: set[str],
) -> tuple[dict[str, Path], dict[str, dict[str, str]]]:
    """Prefer a verified <name>.pinned-<sha12> sibling over an unverifiable default checkout."""
    specs = {spec.name: spec for spec in acquisition.source_specs(sources_root, corpora_root)}
    resolved = dict(roots)
    selections: dict[str, dict[str, str]] = {}
    for name, root in roots.items():
        selection = {"root": str(root), "source": "default"}
        spec = specs.get(name)
        if spec is not None and name not in overridden and root.is_relative_to(spec.target):
            sibling = acquisition.sibling_checkout(spec.target, spec.commit)
            if acquisition.inspect_checkout(spec.target, spec.commit)["status"] != "verified":
                if acquisition.inspect_checkout(sibling, spec.commit)["status"] == "verified":
                    resolved[name] = sibling / root.relative_to(spec.target)
                    selection = {
                        "root": str(resolved[name]),
                        "source": "pinned_sibling",
                        "pinned_commit": spec.commit[:12],
                    }
        selections[name] = selection
    return resolved, selections


def _report_blocked_sources(facts: Mapping[str, Mapping[str, Any]]) -> bool:
    blockers = source_plan_blockers(facts)
    if not blockers:
        return False
    print(
        json.dumps(
            {
                "mode": "BLOCKED",
                "reason": "source provenance",
                "sources": {
                    name: {
                        "status": facts[name].get("status"),
                        "commit": facts[name].get("commit"),
                        "dirty_paths": facts[name].get("dirty_paths"),
                        "commit_matches_expected": facts[name].get("commit_matches_expected"),
                    }
                    for name in blockers
                },
            },
            sort_keys=True,
        )
    )
    return True


def _item_bucket(
    items: dict[str, dict[str, Any]],
    item: CorpusFile,
    item_id: str,
    *,
    include_data_file: bool = True,
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
            "sourcetype_replacements": 0,
            "residual_leaks": 0,
            "unknown_hosts_by_sourcetype": Counter(),
            "date_fallback_by_format": Counter(),
            "formats": Counter(),
            "tool_tells": set(),
            "excluded_files": [],
        },
    )
    if include_data_file and item.path.is_file():
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
    unknown_hosts_by_sourcetype: Counter[str] = field(default_factory=Counter)
    date_fallback_by_format: Counter[str] = field(default_factory=Counter)
    by_format: Counter[str] = field(default_factory=Counter)
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
        bucket["sourcetype_replacements"] += int(resolved.sourcetype_replaced)
        bucket["residual_leaks"] += int(resolved.residual_leak)
        bucket.setdefault("unknown_hosts_by_sourcetype", Counter())
        bucket["unknown_hosts_by_sourcetype"][resolved.sourcetype] += int(resolved.unknown_host)
        bucket.setdefault("date_fallback_by_format", Counter())
        bucket["date_fallback_by_format"][resolved.event_format] += int(resolved.date_fallback)
        bucket.setdefault("formats", Counter())
        bucket["formats"][resolved.event_format] += 1
        bucket["tool_tells"].update(resolved.tool_tells)
        self.totals["events"] += 1
        self.totals["unknown_sourcetype"] += int(resolved.unknown_sourcetype)
        self.totals["unknown_host"] += int(resolved.unknown_host)
        self.totals["date_fallback"] += int(resolved.date_fallback)
        self.totals["missing_time"] += int(resolved.epoch is None)
        self.totals["source_replacements"] += int(resolved.source_replaced)
        self.totals["host_replacements"] += int(resolved.host_replaced)
        self.totals["sourcetype_replacements"] += int(resolved.sourcetype_replaced)
        self.totals["residual_leaks"] += int(resolved.residual_leak)
        self.by_publisher[item.publisher] += 1
        self.by_sourcetype[resolved.sourcetype] += 1
        self.by_source[resolved.source] += 1
        self.by_host[resolved.host] += 1
        self.unknown_hosts_by_sourcetype[resolved.sourcetype] += int(resolved.unknown_host)
        self.date_fallback_by_format[resolved.event_format] += int(resolved.date_fallback)
        self.by_format[resolved.event_format] += 1
        self.distinct_sources.add(resolved.source_checked_value)
        self.distinct_hosts.add(resolved.host_checked_value)

    def merge(self, other: ScanAccumulator) -> None:
        for name in (
            "totals",
            "by_publisher",
            "by_sourcetype",
            "by_source",
            "by_host",
            "unknown_hosts_by_sourcetype",
            "date_fallback_by_format",
            "by_format",
            "pointer_skips",
            "file_counts",
        ):
            getattr(self, name).update(getattr(other, name))
        self.distinct_sources.update(other.distinct_sources)
        self.distinct_hosts.update(other.distinct_hosts)
        for item_id, incoming in other.items.items():
            current = self.items.get(item_id)
            if current is None:
                self.items[item_id] = incoming
                continue
            current["data_files"].update(incoming["data_files"])
            current["excluded_files"].extend(incoming["excluded_files"])
            current["tool_tells"].update(incoming["tool_tells"])
            for key, value in incoming.items():
                if isinstance(value, Counter):
                    current[key].update(value)
                elif key in {
                    "events",
                    "unknown_sourcetype",
                    "unknown_host",
                    "date_fallback",
                    "missing_time",
                    "source_replacements",
                    "host_replacements",
                    "sourcetype_replacements",
                    "residual_leaks",
                }:
                    current[key] += value

    def output(self, read_errors: list[dict[str, str]]) -> dict[str, Any]:
        for bucket in self.items.values():
            for key in (
                "declared_sourcetypes",
                "indexed_sourcetypes",
                "hosts",
                "unknown_hosts_by_sourcetype",
                "date_fallback_by_format",
                "formats",
            ):
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
            "by_format": dict(sorted(self.by_format.items())),
            "unknown_hosts_by_sourcetype": dict(sorted(self.unknown_hosts_by_sourcetype.items())),
            "date_fallback_by_format": dict(sorted(self.date_fallback_by_format.items())),
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


def _tracked_files(root: Path) -> set[str] | None:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        return None
    return {os.fsdecode(name) for name in result.stdout.split(b"\0") if name}


def _file_key(item: CorpusFile) -> tuple[str, str]:
    return item.publisher, item.path.relative_to(item.root).as_posix()


def _exclude_file(
    accumulator: ScanAccumulator,
    item: CorpusFile,
    item_id: str,
    reason: str,
    error: str,
    data_files: Mapping[str, str] | None = None,
) -> dict[str, str]:
    publisher, path = _file_key(item)
    excluded = {"path": path, "reason": reason, "error": error}
    bucket = _item_bucket(accumulator.items, item, item_id, include_data_file=data_files is None)
    if data_files is not None:
        bucket["data_files"].update(data_files)
    bucket["excluded_files"].append(excluded)
    return {"publisher": publisher, "test_id": item.test_id, **excluded}


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
    roots = {item.root.resolve() for files in files_by_publisher.values() for item in files}
    tracked_by_root = {root: _tracked_files(root) for root in roots}
    for publisher, files in files_by_publisher.items():
        for item in files:
            if not item.path.is_file():
                _, path = _file_key(item)
                tracked = tracked_by_root[item.root.resolve()]
                reason = (
                    "upstream_missing"
                    if tracked is not None and path not in tracked
                    else "acquisition_gap"
                )
                read_errors.append(
                    _exclude_file(
                        accumulator,
                        item,
                        p5_item_id(publisher, item.test_id),
                        reason,
                        "missing_file",
                    )
                )
                continue
            if legacy.is_lfs_pointer(item.path):
                accumulator.pointer_skips[publisher] += 1
                continue
            item_id = p5_item_id(publisher, item.test_id)
            file_accumulator = ScanAccumulator()
            bucket = _item_bucket(file_accumulator.items, item, item_id)
            try:
                for event in _iter_file_events(item):
                    file_accumulator.record(item, bucket, event)
            except Exception as exc:
                read_errors.append(
                    _exclude_file(
                        accumulator,
                        item,
                        item_id,
                        "unparseable",
                        type(exc).__name__,
                        bucket["data_files"],
                    )
                )
                continue
            file_accumulator.file_counts[publisher] += 1
            accumulator.merge(file_accumulator)
    return accumulator.output(read_errors)


def _blocking_read_errors(scan: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [row for row in scan["read_errors"] if row.get("reason") == "acquisition_gap"]


def _ship_gate_blocked(
    scan: Mapping[str, Any],
    missing_roots: Mapping[str, Path],
    lab_census: bool,
    cousin_inventory: Mapping[str, Any] | None,
    cousin_census_error: str | None,
) -> bool:
    census_failed = lab_census and (
        cousin_census_error is not None
        or cousin_inventory is None
        or not cousin_inventory.get("reconciled", False)
    )
    return bool(
        missing_roots
        or _blocking_read_errors(scan)
        or scan["totals"].get("residual_leaks", 0)
        or scan["totals"].get("missing_time", 0)
        or census_failed
    )


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
        parts.append(f"{name}-{commit[:12] if commit else 'missing'}")
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
                "root_selection": facts.get("root_selection"),
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


def _fidelity_counter_tables(scan: Mapping[str, Any]) -> list[str]:
    lines = [
        "",
        "## Unknown hosts by sourcetype",
        "",
        "| Sourcetype | Unknown-host events | Total events |",
        "|---|---:|---:|",
    ]
    lines.extend(
        f"| `{name}` | {count} | {scan['by_sourcetype'].get(name, 0)} |"
        for name, count in scan["unknown_hosts_by_sourcetype"].items()
    )
    lines.extend(
        [
            "",
            "## Timestamp fallbacks by format",
            "",
            "| Format | Date-fallback events | Total events |",
            "|---|---:|---:|",
        ]
    )
    lines.extend(
        f"| `{name}` | {count} | {scan['by_format'].get(name, 0)} |"
        for name, count in scan["date_fallback_by_format"].items()
    )
    return lines


def _write_fidelity(path: Path, report: Mapping[str, Any]) -> None:
    scan = report["scan"]
    lines = [
        "# R0c corpus fidelity dry run",
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
        "| Publisher | Commit | Dirty source paths | Scanned root |",
        "|---|---|---:|---|",
        *[
            f"| {name} | `{facts.get('commit') or 'not acquired'}` | {facts.get('dirty_paths', 'n/a')} | `{facts.get('path', 'n/a')}` |"
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
    lines.extend(_fidelity_counter_tables(scan))
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
            f"- Sourcetype replacements: {totals.get('sourcetype_replacements', 0)}.",
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
    lines.extend(["", "### Source files excluded from this run", ""])
    if scan["read_errors"]:
        lines.extend(
            f"- **{row['publisher']}/{row['test_id']}** `{row['path']}`: "
            f"`{row['reason']}` ({row['error']})."
            for row in scan["read_errors"]
        )
    else:
        lines.append("None.")
    lines.extend(["", "## Missing or failed inputs", ""])
    lines.extend(
        f"- Missing source tree: `{name}` ({root})."
        for name, root in report["missing_roots"].items()
    )
    lines.extend(
        f"- Read failure: `{row['publisher']}/{row['path']}` ({row['reason']}: {row['error']})."
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


def _iter_resolved(
    files: Iterator[CorpusFile], excluded_files: set[tuple[str, str]] | None = None
) -> Iterator[tuple[str, ResolvedEvent]]:
    for item in files:
        if excluded_files is not None and _file_key(item) in excluded_files:
            continue
        if not item.path.is_file() or legacy.is_lfs_pointer(item.path):
            continue
        item_id = p5_item_id(item.publisher, item.test_id)
        for event in _iter_file_events(item):
            yield item_id, resolve_event(item, event)


def ship_inputs(
    files_by_publisher: Mapping[str, list[CorpusFile]],
    excluded_files: set[tuple[str, str]] | None = None,
) -> dict[str, int]:
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
        for item_id, resolved in _iter_resolved(iter(files), excluded_files):
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


def _manifest_records(corpora_root: Path) -> dict[str, dict[str, Any]]:
    """The acquisition manifest's records keyed by source_id ({} when there is none)."""
    manifest_path = corpora_root / "manifest.json"
    manifest_doc = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    )
    return {
        str(record.get("source_id")): record
        for record in manifest_doc.get("sources", [])
        if isinstance(record, dict) and record.get("source_id")
    }


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
    parser.add_argument("--attack-data-root", type=Path)
    parser.add_argument("--mordor-root", type=Path)
    parser.add_argument("--evtx-samples-root", type=Path)
    parser.add_argument("--evtx-mitre-root", type=Path)
    parser.add_argument("--invictus-root", type=Path)
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

    roots, overridden = _roots_from_args(args)
    roots, root_selections = prefer_pinned_siblings(
        roots, args.sources_root, args.corpora_root, overridden
    )
    for name, selection in sorted(root_selections.items()):
        print(f"[source-root] {name}: {selection['root']} ({selection['source']})")
    facts = {name: source_facts(name, root) for name, root in roots.items()}
    for name, selection in root_selections.items():
        facts[name]["root_selection"] = selection
    if _report_blocked_sources(facts):
        return 2
    missing_roots = {name: root for name, root in roots.items() if not root.is_dir()}
    files_by_publisher = {
        name: publisher_files(name, root) for name, root in roots.items() if root.is_dir()
    }
    scan = scan_inputs(files_by_publisher)
    manifest_records = _manifest_records(args.corpora_root)
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
            {
                "events": scan["totals"].get("events", 0),
                "missing_roots": list(missing_roots),
                "unknown_hosts_by_sourcetype": scan["unknown_hosts_by_sourcetype"],
                "date_fallback_by_format": scan["date_fallback_by_format"],
                "residual_leaks": scan["totals"].get("residual_leaks", 0),
            },
            sort_keys=True,
        )
    )
    ship_blocked = _ship_gate_blocked(
        scan, missing_roots, args.lab_census, cousin_inventory, cousin_census_error
    )
    if args.ship:
        if ship_blocked:
            print(
                "[BLOCKED] source completeness, provenance, timestamps, or leak checks prevent shipping",
                file=sys.stderr,
            )
            return 2
        if scan["totals"].get("events", 0) != sum(scan["by_publisher"].values()):
            print("[BLOCKED] event census did not reconcile", file=sys.stderr)
            return 2
        excluded_files = {(str(row["publisher"]), str(row["path"])) for row in scan["read_errors"]}
        shipped = ship_inputs(files_by_publisher, excluded_files)
        print(json.dumps({"mode": "SHIPPED", "counts_by_p5_item": shipped}, sort_keys=True))
        return 0
    return 2 if ship_blocked else 0


if __name__ == "__main__":
    sys.exit(main())
