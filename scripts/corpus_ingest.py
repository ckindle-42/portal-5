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
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portal.modules.security.core.siem.hec_ship import ship_batch  # noqa: E402

INDEX = os.environ.get("LAB_SPLUNK_INDEX", "portal5_lab")
BATCH = int(os.environ.get("CORPUS_BATCH", "500"))

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
# fallbacks. Only the four detection sourcetypes drive the canned SPL; the rest
# are descriptive and ship huntable-but-unmatched by design.
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


def load_manifests(root: Path) -> dict[str, tuple[str | None, str | None, float | None]]:
    """Map absolute data-file path -> (sourcetype, source, dataset epoch).

    splunk/attack_data ships a ``data.yml`` beside each dataset declaring the
    authoritative sourcetype/source. Corpora without manifests yield {} and fall
    back to body inspection.
    """
    manifests: dict[str, tuple[str | None, str | None, float | None]] = {}
    for yml in list(root.rglob("*.yml")) + list(root.rglob("*.yaml")):
        try:
            doc = yaml.safe_load(yml.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("datasets"), list):
            continue
        date_epoch = _parse_ts(f"{doc['date']} 00:00:00") if doc.get("date") else None
        for entry in doc["datasets"]:
            if not isinstance(entry, dict) or not entry.get("path"):
                continue
            # manifest paths are repo-absolute ("/datasets/..."); the file sits
            # beside the yml, so resolve by basename within the dataset dir.
            data_file = yml.parent / os.path.basename(str(entry["path"]))
            manifests[str(data_file)] = (
                entry.get("sourcetype"),
                entry.get("source"),
                date_epoch,
            )
    return manifests


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
    """Buffers events by (sourcetype, whole second) so a batch keeps one true
    timestamp — ``ship_batch`` stamps every event in a call with a single time,
    so batching across seconds would flatten the timeline."""

    def __init__(self, src: str, index: str, ship: bool) -> None:
        self.src = src
        self.index = index
        self.ship = ship
        self.buckets: dict[tuple[str, int], list[dict | str]] = defaultdict(list)
        self.manifest: Counter[tuple[str, str]] = Counter()
        self.total = 0
        self.failures = 0
        self.label = ""

    def add(self, sourcetype: str, ev: dict | str, epoch: float) -> None:
        self.manifest[(self.label, sourcetype)] += 1
        self.total += 1
        key = (sourcetype, int(epoch))
        self.buckets[key].append(ev)
        if len(self.buckets[key]) >= BATCH:
            self._flush(key)

    def _flush(self, key: tuple[str, int]) -> None:
        events = self.buckets.pop(key, [])
        if not events or not self.ship:
            return
        sourcetype, epoch = key
        result = ship_batch(
            events,
            sourcetype=sourcetype,
            host=f"corpus-{self.src}",
            index=self.index,
            event_time=float(epoch),
            evidence_origin=f"corpus:{self.src}:{self.label}",
        )
        if not result.get("ok"):
            self.failures += 1
            if self.failures <= 5:
                print(f"  [ship-fail] {sourcetype} @{epoch}: {result}", file=sys.stderr)

    def flush(self) -> None:
        for key in list(self.buckets):
            self._flush(key)


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
                ev = coerce(line)
                sourcetype = resolve_sourcetype(declared_st, declared_src, ev, path.name)
                epoch = event_epoch(ev, fallback)
                # Windows channels ship as key=value so the SPL library matches
                # them; non-Windows JSON keeps its structure, which Splunk's own
                # JSON extraction already handles well.
                if sourcetype.startswith("windows:") and isinstance(ev, dict):
                    ev = windows_kv(ev) or ev
                shipper.add(sourcetype, ev, epoch)
                count += 1
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
    print("\n  events by sourcetype:")
    for sourcetype, n in by_sourcetype.most_common():
        flag = (
            "  <- fires canned detections"
            if sourcetype
            in {
                "windows:security",
                "linux:auditd",
                "web:access",
                "docker:daemon",
            }
            else ""
        )
        print(f"    {n:>10}  {sourcetype}{flag}")
    print("\n  top datasets:")
    for (label, sourcetype), n in shipper.manifest.most_common(20):
        print(f"    {n:>10}  {sourcetype:<20} {label}")
    return shipper.total


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
    args = ap.parse_args()

    if not args.root.is_dir():
        print(f"[FAIL] --root {args.root} is not a directory")
        return 2
    run(args.src, args.root, args.ship, args.backdate_days, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
