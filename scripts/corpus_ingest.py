#!/usr/bin/env python3
"""Bulk-inject public ATT&CK-labeled corpora into lab Splunk via the existing HEC
``ship_batch`` primitive — no new HEC code, no new transport.

Three properties make corpus data coexist cleanly with live bench traffic in the
same ``portal5_lab`` index:

* **Detection sourcetypes.** Events are mapped onto the four sourcetypes
  ``spl_detections.yaml`` actually fires on (``windows:security``,
  ``linux:auditd``, ``web:access``, ``docker:daemon``) whenever the source data
  supports it, so the existing SPL library lights up with zero rule changes.
  Everything else keeps a descriptive sourcetype and stays huntable free-form.
* **Backdating.** Every event ships with its original timestamp, so it lands on
  the real SIEM timeline and stays out of ``blue_triage.poll_alerts``' recent
  ``earliest=-Nm`` window. Events with no recoverable timestamp are backdated by
  ``--backdate-days`` rather than defaulting to ship time.
* **Provenance.** ``evidence_origin='corpus:<src>:<label>'`` and no ``episode_id``,
  so corpus events never enter episode-scoped bench scoring and the whole
  injection is reversible with a single tagged search.

Usage::

    python3 scripts/corpus_ingest.py --src mordor --root /tmp/Security-Datasets --dry-run
    python3 scripts/corpus_ingest.py --src mordor --root /tmp/Security-Datasets --ship

Always dry-run first — it prints the exact per-sourcetype volume that a --ship
pass would inject.

Rollback (requires the ``can_delete`` role)::

    index=portal5_lab evidence_origin=corpus:* | delete
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import io
import json
import os
import re
import sys
import tarfile
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portal.modules.security.core.siem.hec_ship import ship_batch  # noqa: E402
from portal.modules.security.core.siem.spl_detections import (  # noqa: E402
    validated_detection_sourcetypes,
)
from portal.modules.security.core.telemetry import IMPORTED_OBSERVED  # noqa: E402

INDEX = os.environ.get("LAB_SPLUNK_INDEX", "portal5_lab")
BATCH = int(os.environ.get("CORPUS_BATCH", "500"))
# Compatibility name retained for callers, but capability is derived from the
# validated production detection library rather than a parallel allowlist.
INGESTED_SOURCETYPES = validated_detection_sourcetypes()

# Label tiers (TASK_BULLY_SA4 A1): ingestion is not gated on label quality;
# the tier governs what may serve as ground truth. T0/T1 are scoreable;
# T2/T3 participate in retrieval but a graded pair involving them resolves
# INDETERMINATE, never a hit or a miss.
LABEL_TIER_AUTHORITATIVE = "T0"
LABEL_TIER_CONFIRMED = "T1"
LABEL_TIER_PROPOSED = "T2"
LABEL_TIER_UNKNOWN = "T3"
LABEL_TIERS = (
    LABEL_TIER_AUTHORITATIVE,
    LABEL_TIER_CONFIRMED,
    LABEL_TIER_PROPOSED,
    LABEL_TIER_UNKNOWN,
)
SCOREABLE_LABEL_TIERS = frozenset({LABEL_TIER_AUTHORITATIVE, LABEL_TIER_CONFIRMED})


def label_tier_for(labeling: str | None) -> str:
    """Map a declared labeling quality to a T0-T3 tier (A1).

    ``authoritative`` (external per-entry/per-dataset labels, e.g. attack_data
    ``data.yml``, per-entry ATT&CK sets) -> ``T0``;
    ``confirmed``/``reviewed``/``corroborated`` -> ``T1``;
    ``proposed``/``machine``/``clustered``/``unconfirmed`` -> ``T2``; anything
    else (unlabeled, benign/background, unknown) -> ``T3``.
    """
    normalized = str(labeling or "").strip().lower().replace("-", "_").replace("&", "_")
    if any(
        marker in normalized
        for marker in ("unconfirmed", "proposed", "machine", "clustered", "hypothesis")
    ):
        return LABEL_TIER_PROPOSED
    if any(
        marker in normalized for marker in ("authoritative", "per_entry", "per_dataset", "data_yml")
    ):
        return LABEL_TIER_AUTHORITATIVE
    if any(
        marker in normalized for marker in ("confirmed", "reviewed", "corroborated", "validated")
    ):
        return LABEL_TIER_CONFIRMED
    return LABEL_TIER_UNKNOWN


def tier_is_scoreable(tier: str) -> bool:
    """Only T0/T1 may serve as ground truth (A1)."""
    return tier in SCOREABLE_LABEL_TIERS


# Broad-class resolution for sourcetypes we do not yet model well. Evaluation
# decides tier and priority, not admission: an unmapped class is routed through
# the fallback adapter and censused, never dropped (SA4.2 A7).
_CLASS_PREFIX_RULES: tuple[tuple[str, str], ...] = (
    ("aws:", "cloud"),
    ("cloudtrail", "cloud"),
    ("azure:", "cloud"),
    ("gcp:", "cloud"),
    ("okta", "identity"),
    ("identity:", "identity"),
    ("azure:monitor:aad", "identity"),
    ("o365:", "identity"),
    ("gws:reports:login", "identity"),
    ("threat-intel", "threat_intel"),
    ("threatintel", "threat_intel"),
    ("netflow", "network"),
    ("syslog", "network"),
    ("windows:", "endpoint"),
    ("linux:", "endpoint"),
    ("web:", "endpoint"),
    ("docker:", "endpoint"),
)


def resolve_source_class(sourcetype: str | None) -> str | None:
    """Resolve a sourcetype to a broad source class (cloud/identity/endpoint/
    network/threat_intel), or None when unmapped (A7)."""
    normalized = str(sourcetype or "").strip().lower()
    for prefix, source_class in _CLASS_PREFIX_RULES:
        if normalized.startswith(prefix):
            return source_class
    return None


def dataset_census(root: Path, *, manifest_labeling: str = "authoritative") -> dict:
    """Census every input dataset under ``root`` (SA4.2 A7).

    Each dataset is either admitted (source class resolved, label tier
    stamped) or counted as unmapped / no-events / error -- never silently
    dropped. Datasets with a manifest (e.g. attack_data ``data.yml``) carry
    authoritative labels (T0); everything else is unlabeled (T3).
    """
    manifests = load_manifests(root)
    files = sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and p.name.lower().endswith(DATA_SUFFIXES) and str(p) not in manifests
    )
    files = sorted(set(files) | {Path(p) for p in manifests if os.path.exists(p)})
    admitted: list[dict] = []
    unmapped: list[dict] = []
    no_events: list[str] = []
    read_errors: list[dict] = []
    for path in files:
        relative = str(path.relative_to(root))
        if is_lfs_pointer(path):
            continue
        declared_st, declared_src, _ = manifests.get(str(path), (None, None, None))
        try:
            first = next(iter_events_text(path), None)
        except Exception as exc:  # a malformed archive must not kill the census
            read_errors.append({"dataset": relative, "error": str(exc)})
            continue
        if first is None:
            no_events.append(relative)
            continue
        first_record = iter_cloudtrail_records(first)[0]
        first_coerced = first_record if isinstance(first_record, dict) else coerce(first_record)
        sourcetype = resolve_sourcetype(declared_st, declared_src, first_coerced, path.name)
        source_class = resolve_source_class(sourcetype)
        tier = label_tier_for(manifest_labeling if str(path) in manifests else None)
        entry = {
            "dataset": relative,
            "sourcetype": sourcetype,
            "source_class": source_class or "unmapped",
            "label_tier": tier,
            "scoreable": tier_is_scoreable(tier),
        }
        if source_class is None:
            unmapped.append(entry)
        else:
            admitted.append(entry)
    skipped_pointers = sum(1 for p in files if is_lfs_pointer(p))
    census = {
        "schema": "CORPUS_INPUT_CENSUS_V1",
        "datasets_observed": len(files),
        "admitted": admitted,
        "unmapped": unmapped,
        "no_events": no_events,
        "read_errors": read_errors,
        "lfs_pointers_skipped": skipped_pointers,
    }
    census["reconciled"] = len(admitted) + len(unmapped) + len(no_events) + len(
        read_errors
    ) + skipped_pointers == len(files)
    return census


# Containers we can read events out of. .log/.txt are raw-line formats
# (XmlWinEventLog, auditd, nginx); the rest are JSON-ish or archives.
DATA_SUFFIXES = (
    ".json",
    ".jsonl",
    ".ndjson",
    ".log",
    ".txt",
    ".gz",
    ".tgz",
    ".zip",
    ".tar",
    ".evtx",
)

# ---------------------------------------------------------------------------
# sourcetype resolution
# ---------------------------------------------------------------------------

# Matched in order against "<declared sourcetype> <declared source> <channel>".
# Sysmon is tested before Security so a Sysmon channel never grabs the Windows
# Security detections, and web/docker are tested before the generic Windows
# fallbacks. Detection-capable sourcetypes are derived from the SPL library;
# recognized classes without one remain descriptive and are censused honestly.
_SOURCETYPE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("windows:sysmon", ("sysmon",)),
    ("linux:auditd", ("auditd", "linux:audit", "linux_audit")),
    ("docker:daemon", ("docker",)),
    (
        "web:access",
        ("nginx", "apache", "httpd", "iis", "web:access", "cs-uri", "access.log", "access_log"),
    ),
    ("windows:security", ("security", "wineventlog:security")),
    ("windows:powershell", ("powershell",)),
    ("windows:system", ("xmlwineventlog:system", "wineventlog:system")),
    # Non-endpoint classes: recognized broadly, censused honestly, admitted
    # through the fallback adapter when no class adapter exists yet (SA4.2 A7).
    ("aws:cloudtrail", ("cloudtrail", "aws_cloudtrail")),
    ("okta:log", ("okta",)),
    ("netflow", ("netflow",)),
)

_WEB_KEYS = ("http_method", "cs_method", "cs_uri_stem", "uri", "request_uri", "http_user_agent")


def _system(ev: Any) -> dict:
    """The ``Event.System`` block of a decoded EVTX record, else {}."""
    if isinstance(ev, dict) and isinstance(ev.get("Event"), dict):
        system = ev["Event"].get("System")
        if isinstance(system, dict):
            return system
    return {}


def _channel(ev: Any) -> str:
    """Windows channel / source name off a parsed event, if it carries one."""
    if not isinstance(ev, dict):
        return ""
    winlog = ev.get("winlog")
    channel = ev.get("Channel") or ev.get("channel") or _system(ev).get("Channel")
    if not channel and isinstance(winlog, dict):
        channel = winlog.get("channel")
    return str(channel or ev.get("SourceName") or ev.get("source_name") or "")


def _match_rules(haystack: str) -> str | None:
    for sourcetype, needles in _SOURCETYPE_RULES:
        if any(n in haystack for n in needles):
            return sourcetype
    return None


def resolve_sourcetype(
    declared_st: str | None, declared_src: str | None, ev: Any, path_hint: str = ""
) -> str:
    """Map an event onto a detection sourcetype, else a descriptive fallback.

    Evidence is consulted strongest-first, because a weaker signal must never
    override a stronger one: a corpus manifest's declared sourcetype/source
    (splunk/attack_data ships one per dataset), then the event's own Windows
    channel, then the event's field shape, and only last the file name — plenty
    of corpora encode the log type there (``windows-sysmon.log``,
    ``..._access_log.txt``) but a name is a hint, not a declaration.
    """
    declared = f"{declared_st or ''} {declared_src or ''} {_channel(ev)}".lower()
    if sourcetype := _match_rules(declared):
        return sourcetype
    if isinstance(ev, dict):
        if ev.get("type") in ("EXECVE", "SYSCALL", "PATH", "CWD"):
            return "linux:auditd"
        if any(k in ev for k in _WEB_KEYS):
            return "web:access"
        if ev.get("eventSource") or ev.get("eventName"):
            return "aws:cloudtrail"
        if ev.get("eventType") or ev.get("userPrincipalName"):
            return "identity:event"
    if sourcetype := _match_rules(path_hint.lower()):
        return sourcetype
    if declared_st:
        return declared_st
    # A record decoded out of an .evtx *is* a Windows event log even when the
    # ETW provider omits System/Channel, so it stays Windows rather than raw.
    if "windows" in declared or path_hint.lower().endswith(".evtx"):
        return "windows:event"
    return "corpus:raw"


# ---------------------------------------------------------------------------
# timestamps
# ---------------------------------------------------------------------------

_TS_KEYS = ("@timestamp", "TimeCreated", "UtcTime", "timestamp", "_time", "EventTime", "eventTime")
_SYSTEMTIME_RE = re.compile(r'SystemTime=["\']([^"\']+)["\']')
_ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")


def _parse_ts(value: str) -> float | None:
    """Parse an ISO-ish timestamp to epoch seconds. Windows emits 7-digit
    fractional seconds, which datetime rejects, so fractions are truncated to 6."""
    text = str(value).strip().replace("Z", "+00:00")
    text = re.sub(r"(\.\d{6})\d+", r"\1", text)
    for parse in (
        dt.datetime.fromisoformat,
        lambda x: dt.datetime.strptime(x, "%Y-%m-%d %H:%M:%S.%f"),
        lambda x: dt.datetime.strptime(x, "%Y-%m-%d %H:%M:%S"),
        lambda x: dt.datetime.strptime(x, "%m/%d/%Y %I:%M:%S %p"),  # Splunk export header
    ):
        try:
            parsed = parse(text)
        except (ValueError, TypeError):
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.UTC)
        return parsed.timestamp()
    return None


def event_epoch(ev: Any, fallback: float) -> float:
    """Original event time in epoch seconds, else ``fallback``.

    The fallback is a backdated stamp, never ship time — an event landing at
    ship time would appear in blue's live triage window and pollute bench runs.
    """
    if isinstance(ev, dict):
        for key in _TS_KEYS:
            if ev.get(key) and (epoch := _parse_ts(ev[key])) is not None:
                return epoch
        created = _system(ev).get("TimeCreated")
        if isinstance(created, dict):
            attrs = created.get("#attributes") or {}
            if attrs.get("SystemTime") and (epoch := _parse_ts(attrs["SystemTime"])) is not None:
                return epoch
    else:
        text = str(ev)
        # A reassembled export record carries its time on the header line.
        header = text.split("\n", 1)[0]
        if _EXPORT_HEADER_RE.match(header) and (epoch := _parse_ts(header)) is not None:
            return epoch
        match = _SYSTEMTIME_RE.search(text) or _ISO_RE.search(text)
        if match:
            captured = match.group(1) if match.re is _SYSTEMTIME_RE else match.group(0)
            if (epoch := _parse_ts(captured)) is not None:
                return epoch
    return fallback


# ---------------------------------------------------------------------------
# corpus manifests (splunk/attack_data data.yml)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ManifestDataset:
    path: Path
    sourcetype: str | None
    source: str | None
    dataset_epoch: float | None
    techniques: tuple[str, ...]
    mapped_sourcetype: str


def load_manifest_catalog(root: Path) -> tuple[ManifestDataset, ...]:
    """Read data.yml datasets with their sealed scorer-side ATT&CK truth."""
    records: list[ManifestDataset] = []
    for yml in sorted((*root.rglob("*.yml"), *root.rglob("*.yaml"))):
        try:
            doc = yaml.safe_load(yml.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("datasets"), list):
            continue
        date_epoch = _parse_ts(f"{doc['date']} 00:00:00") if doc.get("date") else None
        techniques = tuple(sorted({str(item) for item in doc.get("mitre_technique") or []}))
        for entry in doc["datasets"]:
            if not isinstance(entry, dict) or not entry.get("path"):
                continue
            data_file = yml.parent / os.path.basename(str(entry["path"]))
            declared_st = entry.get("sourcetype")
            declared_src = entry.get("source")
            records.append(
                ManifestDataset(
                    path=data_file,
                    sourcetype=declared_st,
                    source=declared_src,
                    dataset_epoch=date_epoch,
                    techniques=techniques,
                    mapped_sourcetype=resolve_sourcetype(
                        declared_st, declared_src, {}, data_file.name
                    ),
                )
            )
    return tuple(sorted(records, key=lambda item: str(item.path)))


def load_manifests(root: Path) -> dict[str, tuple[str | None, str | None, float | None]]:
    """Map absolute data-file path -> (sourcetype, source, dataset epoch).

    splunk/attack_data ships a ``data.yml`` beside each dataset declaring the
    authoritative sourcetype/source. Corpora without manifests yield {} and fall
    back to body inspection.
    """
    return {
        str(item.path): (item.sourcetype, item.source, item.dataset_epoch)
        for item in load_manifest_catalog(root)
    }


# ---------------------------------------------------------------------------
# event iteration
# ---------------------------------------------------------------------------


def _lines(stream: io.TextIOBase | Iterator[str]) -> Iterator[str]:
    for line in stream:
        text = line.strip()
        if text:
            yield text


# Archive members we can read as text. Everything else — chiefly the .pcap/.pcapng
# captures bundled alongside Mordor's host telemetry — is binary: decoding it as
# text yields millions of junk "events". Packet data needs a Zeek/Suricata lane,
# which is deliberately out of scope here.
_TEXT_MEMBER_SUFFIXES = (".json", ".jsonl", ".ndjson", ".log", ".txt", ".csv", ".xml", ".evtx.json")


def _is_text_member(name: str) -> bool:
    lowered = name.lower()
    return lowered.endswith(_TEXT_MEMBER_SUFFIXES) or "." not in os.path.basename(lowered)


def iter_evtx_records(path: Path) -> Iterator[str]:
    """Decode a Windows .evtx binary log to one JSON record per line.

    The EVTX corpora (sbousseaden, mdecrevoisier) ship raw .evtx, so conversion
    happens inline rather than as a manual pre-step. Requires ``pip install evtx``.
    """
    try:
        from evtx import PyEvtxParser
    except ImportError:
        print(f"  [skip-evtx] {path.name}: `pip install evtx` to ingest .evtx", file=sys.stderr)
        return
    for record in PyEvtxParser(str(path)).records_json():
        data = record.get("data")
        if data:
            yield data.strip()


def iter_raw_lines(path: Path) -> Iterator[str]:
    """Yield non-empty text lines out of a plain, gzipped, tar, zip or evtx file."""
    name = path.name.lower()
    if name.endswith(".evtx"):
        yield from iter_evtx_records(path)
    elif name.endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            for member in zf.namelist():
                if member.endswith("/") or not _is_text_member(member):
                    continue
                with zf.open(member) as fh:
                    yield from _lines(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"))
    elif name.endswith((".tar.gz", ".tgz", ".tar")):
        with tarfile.open(path) as tf:
            for member in tf.getmembers():
                if not member.isfile() or not _is_text_member(member.name):
                    continue
                fh = tf.extractfile(member)
                if fh is not None:
                    yield from _lines(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"))
    elif name.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
            yield from _lines(fh)
    else:
        with open(path, encoding="utf-8", errors="replace") as fh:
            yield from _lines(fh)


# A Splunk-exported Windows event log opens each record with its local-time
# header ("11/23/2020 09:47:20 AM") and then runs many key=value lines. Treating
# those lines as separate events is not just a miscount — it splits EventCode=
# away from the fields the SPL library correlates it with, so the canned
# detections silently match nothing. Records are reassembled on this header.
_EXPORT_HEADER_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}:\d{2} [AP]M\s*$")


def iter_events_text(path: Path) -> Iterator[str]:
    """Yield whole events: one per line for line-oriented logs, or multi-line
    Splunk-export records reassembled into a single event each.

    The format is decided once per file from its first line rather than per
    line, so a key=value line inside a record can never be mistaken for the
    start of a new one.
    """
    lines = iter_raw_lines(path)
    first = next(lines, None)
    if first is None:
        return
    if not _EXPORT_HEADER_RE.match(first):
        yield first
        yield from lines
        return
    record = [first]
    for line in lines:
        if _EXPORT_HEADER_RE.match(line):
            yield "\n".join(record)
            record = [line]
        else:
            record.append(line)
    if record:
        yield "\n".join(record)


# EVTX/Mordor name their principal differently than the SPL library does.
_ACCOUNT_ALIASES = ("TargetUserName", "SubjectUserName", "AccountName", "User")
# Envelope keys that describe the record rather than the event.
_KV_SKIP = {"Message", "Keywords", "Correlation", "Execution", "Provider", "#attributes"}


def windows_kv(ev: dict) -> str | None:
    """Render a Windows event as flat ``EventCode=... Field=value`` text.

    Shipping the JSON as-is is what breaks this lane: Splunk indexes it happily,
    but ``spl_detections.yaml`` filters on ``EventCode=4769 TicketEncryptionType=0x17``
    and an event whose ID lives at ``Event.System.EventID`` matches none of it —
    the same JSON-envelope trap ``siem/capture_store.py`` documents. This mirrors
    ``siem/collect.py::_normalize_windows_security_events`` so corpus events and
    live bench telemetry present identically to the detections.

    Returns None when the event carries no recognizable event ID.
    """
    system = _system(ev)
    if system:
        code = system.get("EventID")
        data = ev["Event"].get("EventData")
        fields = dict(data) if isinstance(data, dict) else {}
    else:
        code = ev.get("EventCode") or ev.get("EventID")
        fields = {k: v for k, v in ev.items() if not k.startswith("@")}
    if isinstance(code, dict):  # <EventID Qualifiers=..>4769</EventID>
        code = code.get("#text")
    if code in (None, ""):
        return None

    parts = [f"EventCode={code}"]
    for alias in _ACCOUNT_ALIASES:
        if fields.get(alias):
            parts.append(f"Account={fields[alias]}")
            break
    for key, value in fields.items():
        if key in _KV_SKIP or value is None or isinstance(value, dict | list):
            continue
        text = str(value).replace("\n", " ").replace("\r", " ").strip()
        if text:
            parts.append(f"{key}={text}")
    return " ".join(parts)


_XML_EVENT_ID = re.compile(r"<EventID(?:\s[^>]*)?>([^<]+)</EventID>", re.IGNORECASE)
_XML_DATA = re.compile(r"<Data\s+Name=['\"]([^'\"]+)['\"]>(.*?)</Data>", re.IGNORECASE | re.DOTALL)


def windows_xml_kv(event: str) -> str | None:
    """Flatten a one-line Windows Event XML record for field-based SPL."""
    event_id = _XML_EVENT_ID.search(event)
    if event_id is None:
        return None
    parts = [f"EventCode={event_id.group(1).strip()}"]
    fields = [
        (name, re.sub(r"\s+", " ", value).strip()) for name, value in _XML_DATA.findall(event)
    ]
    for alias in _ACCOUNT_ALIASES:
        value = next((value for name, value in fields if name == alias and value), "")
        if value:
            parts.append(f"Account={value}")
            break
    parts.extend(f"{name}={value}" for name, value in fields if value)
    return " ".join(parts)


def coerce(line: str) -> dict | str:
    """A JSON object becomes a dict (so fields index); anything else stays raw."""
    if line[:1] in "{[":
        try:
            parsed = json.loads(line)
        except ValueError:
            return line
        if isinstance(parsed, dict):
            return parsed
    return line


def iter_cloudtrail_records(line: str) -> list[dict | str]:
    """Expand a CloudTrail ``{"Records": [...]}`` envelope into its records.

    CloudTrail exports bundle many records under one ``Records`` key; without
    expansion a single line would ingest as one giant event and every
    detection-shaped search would miss the individual API calls. Non-envelope
    input returns the coerced line unchanged, so plain JSONL still works.
    """
    if line[:1] != "{":
        return [coerce(line)]
    try:
        parsed = json.loads(line)
    except ValueError:
        return [coerce(line)]
    if isinstance(parsed, dict) and isinstance(parsed.get("Records"), list):
        records = parsed["Records"]
        return [record for record in records if isinstance(record, dict)]
    return [parsed]
    return line


def is_lfs_pointer(path: Path) -> bool:
    """git-lfs pointer files are ~130 bytes of text, not data. Shipping them
    would inject garbage, so they are skipped and counted separately."""
    if path.stat().st_size > 1024:
        return False
    try:
        with open(path, "rb") as fh:
            return fh.read(64).startswith(b"version https://git-lfs")
    except OSError:
        return False


# ---------------------------------------------------------------------------
# shipping
# ---------------------------------------------------------------------------


class Shipper:
    """Buffers events by sourcetype and ships BATCH-sized POSTs, each carrying
    every event's original timestamp (SA5.4): ``ship_batch`` now accepts a
    parallel ``event_times`` list, so events spanning years batch by count
    instead of one HTTP call per second."""

    def __init__(self, src: str, index: str, ship: bool) -> None:
        self.src = src
        self.index = index
        self.ship = ship
        self.buckets: dict[str, list[tuple[dict | str, float]]] = defaultdict(list)
        self.manifest: Counter[tuple[str, str]] = Counter()
        self.classes: Counter[str] = Counter()
        self.tiers: Counter[str] = Counter()
        self.unmapped_sourcetypes: Counter[str] = Counter()
        self.total = 0
        self.failures = 0
        self.label = ""

    def add(self, sourcetype: str, ev: dict | str, epoch: float) -> None:
        self.manifest[(self.label, sourcetype)] += 1
        self.total += 1
        self.classes[resolve_source_class(sourcetype) or "unmapped"] += 1
        if resolve_source_class(sourcetype) is None:
            self.unmapped_sourcetypes[sourcetype] += 1
        self.buckets[sourcetype].append((ev, float(epoch)))
        if len(self.buckets[sourcetype]) >= BATCH:
            self._flush(sourcetype)

    def _flush(self, sourcetype: str) -> None:
        entries = self.buckets.pop(sourcetype, [])
        if not entries or not self.ship:
            return
        events, epochs = zip(*entries, strict=True)
        result = ship_batch(
            list(events),
            sourcetype=sourcetype,
            host=f"corpus-{self.src}",
            index=self.index,
            event_times=list(epochs),
            evidence_origin=IMPORTED_OBSERVED,
            evidence_provenance="external_corpus",
        )
        if not result.get("ok"):
            self.failures += 1
            if self.failures <= 5:
                print(f"  [ship-fail] {sourcetype}: {result}", file=sys.stderr)

    def flush(self) -> None:
        for sourcetype in list(self.buckets):
            self._flush(sourcetype)


def run(src: str, root: Path, ship: bool, backdate_days: int, limit: int) -> int:
    manifests = load_manifests(root)
    default_epoch = (dt.datetime.now(dt.UTC) - dt.timedelta(days=backdate_days)).timestamp()

    files = sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and p.name.lower().endswith(DATA_SUFFIXES) and str(p) not in manifests
    )
    files = sorted(set(files) | {Path(p) for p in manifests if os.path.exists(p)})

    shipper = Shipper(src, INDEX, ship)
    skipped_pointers = 0
    for path in files:
        if is_lfs_pointer(path):
            skipped_pointers += 1
            continue
        declared_st, declared_src, dataset_epoch = manifests.get(str(path), (None, None, None))
        shipper.label = str(path.relative_to(root).with_suffix(""))
        fallback = dataset_epoch if dataset_epoch is not None else default_epoch
        count = 0
        try:
            for line in iter_events_text(path):
                for ev in iter_cloudtrail_records(line):
                    sourcetype = resolve_sourcetype(declared_st, declared_src, ev, path.name)
                    epoch = event_epoch(ev, fallback)
                    # Windows channels ship as key=value so the SPL library matches
                    # them; non-Windows JSON keeps its structure, which Splunk's own
                    # JSON extraction already handles well.
                    if sourcetype.startswith("windows:"):
                        flattened = (
                            windows_kv(ev) if isinstance(ev, dict) else windows_xml_kv(str(ev))
                        )
                        ev = flattened if flattened is not None else ev
                    shipper.add(sourcetype, ev, epoch)
                    count += 1
                    if limit and count >= limit:
                        break
                if limit and count >= limit:
                    break
        except Exception as exc:  # a malformed archive must not kill the whole run
            print(f"  [read-fail] {path}: {exc}", file=sys.stderr)
        shipper.flush()

    mode = "SHIPPED" if ship else "DRY-RUN"
    print(f"\n{mode}: {shipper.total} events from {len(files)} files under {root}")
    if skipped_pointers:
        print(f"  ({skipped_pointers} git-lfs pointer files skipped — run `git lfs pull`)")
    if shipper.failures:
        print(f"  WARNING: {shipper.failures} batches failed to ship")
    by_sourcetype = Counter()
    for (_, sourcetype), n in shipper.manifest.items():
        by_sourcetype[sourcetype] += n
    _report_census(shipper, by_sourcetype)
    return shipper.total


def verify_index_confirmed(src: str, *, expect_min: int = 1, index: str = INDEX) -> dict:
    """Confirm a shipped source is searchable in lab Splunk (P7.2 standard).

    Polls a per-source count search (``host=corpus-<src>`` -- the exact host
    every event for this source shipped under) until the index confirms the
    events are searchable. Returns ``{ok, count, source, index}``. This is
    the A5 ``live_indexed`` receipt, not an offline artifact count.
    """
    from portal.modules.security.core.siem.index_wait import wait_indexed

    # Corpus events are backdated to their ORIGINAL timestamps (2018-2023
    # for the acquired CloudTrail sets), so the confirmation poll must cover
    # the full timeline -- a recent-window earliest bound would find nothing.
    confirmed = wait_indexed(
        host=f"corpus-{src}",
        since_epoch=0,
        expect_min=expect_min,
        timeout_s=60,
        index=index,
    )
    count = _confirm_count_search(src, index=index) if confirmed else 0
    return {
        "schema": "CORPUS_SHIP_RECEIPT_V1",
        "source": src,
        "index": index,
        "indexed_confirmed": confirmed,
        "confirmed_count": count,
    }


def _confirm_count_search(src: str, *, index: str) -> int:
    """Count search for ``host=corpus-<src>`` in ``index``; 0 on failure."""
    url = os.environ.get("LAB_SPLUNK_URL", "https://10.0.1.30:8089")
    user = os.environ.get("LAB_SPLUNK_USER", "admin")
    pw = os.environ.get("LAB_SPLUNK_PASSWORD", "")
    try:
        import httpx

        r = httpx.post(
            f"{url.rstrip('/')}/services/search/jobs/export",
            auth=(user, pw),
            verify=False,
            timeout=90.0,
            data={
                "search": (f'search earliest=0 index={index} host="corpus-{src}" | stats count'),
                "exec_mode": "oneshot",
                "output_mode": "json",
            },
        )
        # oneshot export streams progressive preview rows; the last row is the
        # final count. Take the max observed so a stale preview never reads low.
        counts = [
            int(json.loads(ln).get("result", {}).get("count", "0"))
            for ln in r.text.splitlines()
            if '"count"' in ln
        ]
        if counts:
            return max(counts)
    except Exception:  # noqa: BLE001 -- count is supplementary to confirmation
        pass
    return 0


def _report_census(shipper: Shipper, by_sourcetype: Counter) -> None:
    """Per-sourcetype, per-source-class, and unmapped census output (SA4.2)."""
    print("\n  events by sourcetype:")
    for sourcetype, n in by_sourcetype.most_common():
        flag = "  <- fires canned detections" if sourcetype in INGESTED_SOURCETYPES else ""
        print(f"    {n:>10}  {sourcetype}{flag}")
    print("\n  events by source class (broad):")
    for source_class, n in shipper.classes.most_common():
        print(f"    {n:>10}  {source_class}")
    if shipper.unmapped_sourcetypes:
        print("\n  unmapped sourcetypes (fallback adapter, censused -- never dropped):")
        for sourcetype, n in shipper.unmapped_sourcetypes.most_common():
            print(f"    {n:>10}  {sourcetype}")
    print("\n  top datasets:")
    for (label, sourcetype), n in shipper.manifest.most_common(20):
        print(f"    {n:>10}  {sourcetype:<20} {label}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--src", required=True, help="provenance label, e.g. mordor / attack_data")
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--backdate-days", type=int, default=30, help="fallback age for undated events")
    ap.add_argument("--limit", type=int, default=0, help="max events per file (0 = all)")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--ship", action="store_true")
    group.add_argument("--verify-index", action="store_true")
    args = ap.parse_args()

    if not args.root.is_dir():
        print(f"[FAIL] --root {args.root} is not a directory")
        return 2
    if args.verify_index:
        receipt = verify_index_confirmed(args.src)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0 if receipt["indexed_confirmed"] else 1
    run(args.src, args.root, args.ship, args.backdate_days, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
