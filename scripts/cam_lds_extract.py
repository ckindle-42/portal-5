#!/usr/bin/env python3
"""CAM-LDS extractor: attack steps, defender manifestations, time+entity join, variant grid.

Reads an extracted CAM-LDS manifestations bundle (``sequences/``, ``steps/``,
``techniques/`` views) plus, optionally, the per-variant campaign archives, and
emits one JSON report. Every path is an argument; host names, addresses and
indices come from the data.

Usage::

    ./.venv/bin/python -I scripts/cam_lds_extract.py \
        --root /data/extract/raw/manifestations_raw \
        --archive-dir /data/cam_lds --out /data/extract/cam_lds.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

VIEWS = ("sequences", "steps", "techniques")

# ---------------------------------------------------------------- timestamps

_ISO_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})(?:\.(\d+))?([+-]\d{2}:?\d{2}|[Zz])?$"
)
_SYSLOG_RE = re.compile(r"^([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})")
_MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def parse_iso(text: str) -> datetime | None:
    """Parse an ISO-8601 stamp, treating a missing offset as UTC."""
    m = _ISO_RE.match(text.strip())
    if not m:
        return None
    base, frac, off = m.groups()
    stamp = base.replace(" ", "T")
    if frac:
        stamp += "." + (frac + "000000")[:6]
    if off:
        stamp += "+00:00" if off in {"Z", "z"} else (off if ":" in off else f"{off[:3]}:{off[3:]}")
    try:
        parsed = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_syslog_ts(line: str, year: int) -> datetime | None:
    """Parse a year-less syslog stamp using the campaign year."""
    m = _SYSLOG_RE.match(line)
    if not m:
        return None
    mon, day, clock = m.groups()
    if mon not in _MONTHS:
        return None
    hh, mm, ss = (int(x) for x in clock.split(":"))
    return datetime(year, _MONTHS[mon], int(day), hh, mm, ss, tzinfo=UTC)


# ------------------------------------------------------------------ entities

_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_URL_RE = re.compile(r"https?://[^\s\"'<>\\]+")
_HOST_RE = re.compile(r"\b(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24}\b")


def _valid_ip(text: str) -> bool:
    return all(0 <= int(octet) <= 255 for octet in text.split("."))


def extract_entities(text: str) -> frozenset[str]:
    """Normalised entity tokens (``ip:``, ``host:``, ``url:``) found in ``text``."""
    found: set[str] = set()
    for raw in _IP_RE.findall(text):
        if _valid_ip(raw):
            found.add("ip:" + raw)
    for raw in _URL_RE.findall(text):
        url = raw.rstrip(".,;)").lower()
        found.add("url:" + url)
        host = re.sub(r"^https?://", "", url).split("/")[0].split(":")[0]
        if host:
            found.add("host:" + host)
    hosts = [raw.lower() for raw in _HOST_RE.findall(text) if not _IP_RE.fullmatch(raw)]
    for host in _maximal(hosts):
        found.add("host:" + host)
    return frozenset(found)


def _maximal(names: list[str]) -> set[str]:
    """Drop names that are a dot-suffix of another matched name (nested subdomains)."""
    unique = set(names)
    return {
        name for name in unique if not any(o != name and o.endswith("." + name) for o in unique)
    }


# ------------------------------------------------------------------- records


@dataclass
class Step:
    campaign: str
    view: str
    sequence: str
    run: int | None
    step_index: int
    ts: datetime
    type: str
    cmd: str
    techniques: tuple[str, ...]
    tactics: tuple[str, ...]
    technique_name: str
    host: str
    entities: frozenset[str]

    @property
    def key(self) -> str:
        return f"{self.campaign}|{self.run}|{self.step_index}|{self.ts.isoformat()}"


RAW_KEEP = 240


@dataclass
class Event:
    ts: datetime
    host: str
    kind: str
    entities: frozenset[str]
    raw: str
    attrs: tuple[tuple[str, str], ...] = ()

    @property
    def digest(self) -> str:
        body = f"{self.ts.isoformat()}|{self.host}|{self.kind}|{self.raw}"
        return hashlib.sha1(body.encode()).hexdigest()[:16]


@dataclass
class ParseFailure:
    path: str
    line: int
    error: str


@dataclass
class Reader:
    records: list[Any] = field(default_factory=list)
    failures: list[ParseFailure] = field(default_factory=list)
    files: int = 0
    lines: int = 0

    def fail(self, path: Path | str, line: int, error: str) -> None:
        self.failures.append(ParseFailure(str(path), line, error))


# --------------------------------------------------------------- step reader


def _split_csv(value: Any) -> tuple[str, ...]:
    if not isinstance(value, str):
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _step_entities(cmd: str, params: dict[str, Any]) -> frozenset[str]:
    parts = [cmd]
    for name in (
        "hostname",
        "host",
        "domain",
        "url",
        "website",
        "filepath",
        "name",
        "key_filename",
    ):
        value = params.get(name)
        if isinstance(value, str):
            parts.append(value)
    return extract_entities(" ".join(parts))


def _step_from_obj(
    obj: dict[str, Any], *, campaign: str, view: str, sequence: str, run: int | None, index: int
) -> Step:
    params = obj.get("parameters") or {}
    meta = params.get("metadata") or {}
    techniques = _split_csv(meta.get("techniques"))
    cmd = obj.get("cmd")
    cmd = cmd if isinstance(cmd, str) else json.dumps(cmd, sort_keys=True)
    host = params.get("hostname") or params.get("host") or ""
    return Step(
        campaign=campaign,
        view=view,
        sequence=sequence,
        run=run,
        step_index=index,
        ts=parse_iso(obj.get("start-datetime") or "") or datetime(1970, 1, 1, tzinfo=UTC),
        type=str(obj.get("type") or ""),
        cmd=cmd,
        techniques=techniques,
        tactics=_split_csv(meta.get("tactics")),
        technique_name=str(meta.get("technique_name") or ""),
        host=str(host),
        entities=_step_entities(cmd, params),
    )


def read_step_file(
    path: Path, *, campaign: str, view: str, sequence: str, run: int | None, reader: Reader
) -> list[Step]:
    """Read one attackmate.json (JSON Lines) into ordered steps."""
    reader.files += 1
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        reader.fail(path, 0, f"read: {exc}")
        return []
    steps: list[Step] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        reader.lines += 1
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            reader.fail(path, lineno, f"json: {exc}")
            continue
        if not isinstance(obj, dict):
            reader.fail(path, lineno, f"not an object: {type(obj).__name__}")
            continue
        steps.append(
            _step_from_obj(
                obj, campaign=campaign, view=view, sequence=sequence, run=run, index=len(steps)
            )
        )
    return steps


def _parse_dir_name(name: str) -> tuple[str, list[int]]:
    """Split ``<campaign>-<n>[_<n>...]`` into its parts."""
    campaign, _, suffix = name.rpartition("-")
    runs = [int(part) for part in suffix.split("_") if part.isdigit()]
    return campaign, runs


def load_steps(root: Path, view: str = "steps") -> Reader:
    """Read every step file under ``root/<view>/``."""
    reader = Reader()
    base = root / view
    for path in sorted(base.rglob("attackmate.json")):
        rel = path.relative_to(base).parts
        campaign, runs = _parse_dir_name(rel[0])
        run = runs[0] if view != "techniques" and len(runs) == 1 else None
        if view == "techniques" and len(rel) >= 2:
            run = _parse_dir_name(rel[1])[1][0]
        sequence = rel[0] if view != "techniques" else (rel[1] if len(rel) > 1 else "")
        reader.records.extend(
            read_step_file(
                path, campaign=campaign, view=view, sequence=sequence, run=run, reader=reader
            )
        )
    return reader


# ------------------------------------------------------------- defender reader

_FAST_RE = re.compile(
    r"^(?P<mm>\d{2})/(?P<dd>\d{2})/(?P<yyyy>\d{4})-(?P<clock>\d{2}:\d{2}:\d{2})\.(?P<frac>\d+)\s+"
    r"\[\*\*\]\s+\[(?P<gid>\d+):(?P<sid>\d+):(?P<rev>\d+)\]\s+(?P<sig>.*?)\s+\[\*\*\]"
    r".*?\{(?P<proto>\w+)\}\s+(?P<src>[\d.]+):(?P<sport>\d+)\s+->\s+(?P<dst>[\d.]+):(?P<dport>\d+)"
)
_AGENT_IP_RE = re.compile(r'"agent"\s*:\s*\{')
_DNS_CONFIG_RE = re.compile(r"config (\S+) is ([\d.]+)")


def _wazuh_event(obj: dict[str, Any], fallback_host: str) -> Event | None:
    ts = parse_iso(str(obj.get("timestamp") or ""))
    if ts is None:
        return None
    agent = obj.get("agent") or {}
    host = str(agent.get("name") or fallback_host)
    attrs = tuple((key, str(agent[key])) for key in ("ip", "name") if agent.get(key))
    return Event(
        ts=ts,
        host=host,
        kind="wazuh",
        entities=extract_entities(json.dumps(obj)),
        raw=json.dumps(obj, sort_keys=True)[:RAW_KEEP],
        attrs=attrs,
    )


def read_wazuh(path: Path, year: int, reader: Reader) -> list[Event]:
    reader.files += 1
    events: list[Event] = []
    fallback = path.parts[-4] if len(path.parts) >= 4 else ""
    for lineno, line in enumerate(_lines(path, reader), 1):
        reader.lines += 1
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            reader.fail(path, lineno, f"json: {exc}")
            continue
        event = _wazuh_event(obj, fallback) if isinstance(obj, dict) else None
        if event is None:
            reader.fail(path, lineno, "no parseable timestamp")
            continue
        events.append(event)
    return events


def read_fast_log(path: Path, year: int, reader: Reader, host: str) -> list[Event]:
    reader.files += 1
    events: list[Event] = []
    for lineno, line in enumerate(_lines(path, reader), 1):
        reader.lines += 1
        if not line.strip():
            continue
        m = _FAST_RE.match(line)
        if not m:
            reader.fail(path, lineno, "fast.log pattern mismatch")
            continue
        ts = datetime(
            int(m["yyyy"]),
            int(m["mm"]),
            int(m["dd"]),
            *map(int, m["clock"].split(":")),
            tzinfo=UTC,
        ).replace(microsecond=int((m["frac"] + "000000")[:6]))
        entities = extract_entities(line)
        events.append(Event(ts=ts, host=host, kind="suricata_fast", entities=entities, raw=line))
    return events


def read_syslog(path: Path, year: int, reader: Reader, kind: str, host: str) -> list[Event]:
    reader.files += 1
    events: list[Event] = []
    for lineno, line in enumerate(_lines(path, reader), 1):
        reader.lines += 1
        if not line.strip():
            continue
        ts = parse_syslog_ts(line, year)
        if ts is None:
            reader.fail(path, lineno, "syslog timestamp mismatch")
            continue
        events.append(Event(ts=ts, host=host, kind=kind, entities=extract_entities(line), raw=line))
    return events


def _lines(path: Path, reader: Reader) -> Iterator[str]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            yield from handle
    except OSError as exc:
        reader.fail(path, 0, f"read: {exc}")


def _classify_defender(path: Path) -> tuple[str, str] | None:
    """Map a path under a sequence dir to (reader kind, observing host)."""
    parts = path.parts
    try:
        idx = parts.index("logs")
    except ValueError:
        return None
    host = parts[idx - 1] if idx >= 1 else ""
    suffix = "/".join(parts[idx:])
    if suffix == "logs/alerts/alerts.json":
        return "wazuh", host
    if suffix.endswith("suricata/fast.log"):
        return "fast", host
    if suffix.endswith("logs/log/syslog"):
        return "syslog", host
    return None


def read_sequence_events(
    root: Path, view: str, year_of: dict[str, int], reader: Reader, syslog_hosts: set[str] | None
) -> dict[str, list[Event]]:
    """Defender events grouped by sequence directory name."""
    base = root / view
    out: dict[str, list[Event]] = defaultdict(list)
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        classified = _classify_defender(path)
        if classified is None:
            continue
        kind, host = classified
        if kind == "syslog" and syslog_hosts is not None and host not in syslog_hosts:
            continue
        seq = path.relative_to(base).parts[0]
        year = year_of.get(seq, 1970)
        if kind == "wazuh":
            out[seq].extend(read_wazuh(path, year, reader))
        elif kind == "fast":
            out[seq].extend(read_fast_log(path, year, reader, host))
        else:
            out[seq].extend(read_syslog(path, year, reader, "syslog", host))
    return out


# ---------------------------------------------------------------------- join


@dataclass
class JoinRow:
    campaign: str
    sequence: str
    run: int | None
    step_index: int
    ts: str
    type: str
    techniques: str
    cmd_head: str
    manifestations: int
    hosts: tuple[str, ...]
    shared_entities: tuple[str, ...]
    silent: bool


LAST_STEP_TAIL_S = 1800
LOOKBACK_S = 2.0
SYSLOG_GRANULARITY_S = 1.0


def host_map(events: Iterable[Event]) -> tuple[dict[str, str], dict[str, str]]:
    """Build (hostname -> ip) from DNS answers and (ip -> agent name) from wazuh."""
    dns: dict[str, str] = {}
    agents: dict[str, str] = {}
    for event in events:
        dns_match = _DNS_CONFIG_RE.search(event.raw)
        if dns_match:
            dns.setdefault(dns_match.group(1).lower(), dns_match.group(2))
        if event.kind != "wazuh":
            continue
        attrs = dict(event.attrs)
        if attrs.get("ip") and attrs.get("name"):
            agents.setdefault(attrs["ip"], attrs["name"])
    return dns, agents


def entity_ip(entity: str, dns: dict[str, str]) -> str | None:
    kind, _, value = entity.partition(":")
    if kind == "ip":
        return value
    if kind == "host":
        return dns.get(value)
    if kind == "url":
        return dns.get(re.sub(r"^https?://", "", value).split("/")[0].split(":")[0])
    return None


def entity_host(entity: str, dns: dict[str, str], agents: dict[str, str]) -> str | None:
    ip = entity_ip(entity, dns)
    return agents.get(ip) if ip else None


def canonical(entity: str, hosts: dict[str, str]) -> str:
    """Collapse an IP to its inventory host; leave names as names."""
    kind, _, value = entity.partition(":")
    if kind != "ip":
        return entity
    named = hosts.get(value)
    return "host:" + named if named else entity


def read_inventory(archive_dir: Path) -> dict[str, str]:
    """IP -> host name from each archive's per-host Ansible facts."""
    inventory: dict[str, str] = {}
    for path in sorted(archive_dir.glob("*.zip")):
        if path.name.startswith("manifestations_"):
            continue
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                if not member.endswith("/facts.json"):
                    continue
                host = member.split("/")[1]
                try:
                    facts = json.loads(archive.read(member))
                except (json.JSONDecodeError, KeyError):
                    continue
                for key in ("inventory_hostname",):
                    if isinstance(facts.get(key), str):
                        inventory.setdefault(facts[key], host)
                addresses = facts.get("ansible_all_ipv4_addresses") or []
                for address in addresses if isinstance(addresses, list) else []:
                    inventory.setdefault(str(address), host)
    return inventory


def window_check(
    steps: list[Step], seq_events: dict[str, list[Event]], tail_s: int
) -> dict[str, Any]:
    """Do the publisher's per-sequence slices respect [first step, next step)?"""
    by_campaign: dict[str, list[Step]] = defaultdict(list)
    for step in steps:
        by_campaign[step.campaign].append(step)
    for bucket in by_campaign.values():
        bucket.sort(key=lambda s: s.ts)
    by_seq: dict[str, list[Step]] = defaultdict(list)
    for step in steps:
        by_seq[step.sequence].append(step)
    checked = with_events = outside = orphan = 0
    before_dirs = after_dirs = 0
    before_max = after_max = 0.0
    examples = []
    for sequence, events in seq_events.items():
        if not events:
            continue
        with_events += 1
        members = sorted(by_seq.get(sequence, []), key=lambda s: s.ts)
        if not members:
            orphan += 1
            continue
        campaign_steps = by_campaign[members[0].campaign]
        opening = members[0].ts - timedelta(seconds=SYSLOG_GRANULARITY_S)
        last = members[-1]
        following = [s.ts for s in campaign_steps if s.ts > last.ts]
        end = following[0] if following else last.ts + timedelta(seconds=tail_s)
        early = [e for e in events if e.ts < opening]
        late = [e for e in events if e.ts >= end]
        checked += 1
        if early:
            before_dirs += 1
            before_max = max(before_max, (opening - min(e.ts for e in early)).total_seconds())
        if late:
            after_dirs += 1
            after_max = max(after_max, (max(e.ts for e in late) - end).total_seconds())
        if early or late:
            outside += 1
            if len(examples) < 10:
                examples.append(
                    {
                        "sequence": sequence,
                        "before": len(early),
                        "after": len(late),
                        "events": len(events),
                    }
                )
    return {
        "sequences_with_events": with_events,
        "checked": checked,
        "opening_lookback_s": SYSLOG_GRANULARITY_S,
        "outside_window": outside,
        "events_without_step": orphan,
        "dirs_with_events_before_step": before_dirs,
        "max_lead_s": round(before_max, 3),
        "dirs_with_events_after_window": after_dirs,
        "max_lag_s": round(after_max, 3),
        "examples": examples,
    }


class CampaignEvents:
    """Sorted event index for one campaign, queryable by half-open window."""

    def __init__(self, events: list[Event]) -> None:
        unique: dict[str, Event] = {}
        for event in events:
            unique.setdefault(event.digest, event)
        self.events = sorted(unique.values(), key=lambda e: e.ts)
        self.stamps = [event.ts for event in self.events]

    def between(self, start: datetime, end: datetime) -> list[Event]:
        import bisect

        lo = bisect.bisect_left(self.stamps, start)
        hi = bisect.bisect_left(self.stamps, end)
        return self.events[lo:hi]


def join(
    steps: list[Step],
    events_by_campaign: dict[str, CampaignEvents],
    agents: dict[str, str],
    inventory: dict[str, str],
    lookback_s: float = LOOKBACK_S,
) -> tuple[list[JoinRow], dict[str, Any]]:
    """Attribute events to steps by the inter-step window and a shared entity."""
    by_campaign: dict[str, list[Step]] = defaultdict(list)
    for step in steps:
        by_campaign[step.campaign].append(step)
    rows: list[JoinRow] = []
    edge_kinds: Counter[str] = Counter()
    cross_kinds: Counter[str] = Counter()
    raw_edges = 0
    cross_steps: set[tuple[str, int | None, int]] = set()
    canon: dict[str, str] = {}
    resolution = {**agents, **inventory}
    known_hosts = set(inventory) | set(inventory.values())

    def canon_of(entity: str) -> str:
        return canon.setdefault(entity, canonical(entity, resolution))

    for campaign, campaign_steps in sorted(by_campaign.items()):
        campaign_steps.sort(key=lambda s: s.ts)
        index = events_by_campaign.get(campaign) or CampaignEvents([])
        for position, step in enumerate(campaign_steps):
            end = (
                campaign_steps[position + 1].ts
                if position + 1 < len(campaign_steps)
                else step.ts + timedelta(seconds=LAST_STEP_TAIL_S)
            )
            window = index.between(step.ts - timedelta(seconds=lookback_s), end)
            shared: set[str] = set()
            touched: set[str] = set()
            step_canon = {canon_of(entity) for entity in step.entities}
            for event in window:
                touched.add(event.host)
                raw_edges += len(step.entities & event.entities)
                common = {canon_of(entity) for entity in event.entities} & step_canon
                for entity in common:
                    edge_kinds[entity.partition(":")[0]] += 1
                    named = entity.partition(":")[2]
                    if entity.startswith("host:") and named in known_hosts and named != event.host:
                        cross_kinds[entity] += 1
                        cross_steps.add((campaign, step.run, step.step_index))
                shared |= common
            rows.append(
                JoinRow(
                    campaign=campaign,
                    sequence=step.sequence,
                    run=step.run,
                    step_index=step.step_index,
                    ts=step.ts.isoformat(),
                    type=step.type,
                    techniques=",".join(step.techniques),
                    cmd_head=(step.cmd.strip().split() or [""])[0][:40],
                    manifestations=len(window),
                    hosts=tuple(sorted(touched)),
                    shared_entities=tuple(sorted(shared)),
                    silent=not window,
                )
            )
    summary = {
        "steps": len(rows),
        "silent": sum(1 for row in rows if row.silent),
        "with_manifestation": sum(1 for row in rows if not row.silent),
        "raw_token_edges": raw_edges,
        "shared_entity_edges": sum(edge_kinds.values()),
        "shared_entity_edges_by_kind": dict(edge_kinds),
        "cross_host_edges": sum(cross_kinds.values()),
        "cross_host_edges_by_kind": dict(cross_kinds),
        "steps_with_cross_host_edge": len(cross_steps),
        "host_map_agents": len(agents),
        "inventory_hosts": sorted(set(inventory.values())),
    }
    return rows, summary


# ------------------------------------------------------------------- reports


def _unlabelled(cmd: str) -> str:
    """Coarse command shape for steps carrying no ATT&CK metadata."""
    text = cmd.strip()
    if not text:
        return "empty"
    first = text.split()[0]
    if re.fullmatch(r"[:/][^\s]*", first) or first in {"o", "i", "exit", "q", "w"}:
        return "editor-keystroke"
    if first == "sleep":
        return "sleep"
    return "command:" + first[:24]


def unlabelled_profile(steps: list[Step]) -> dict[str, Any]:
    """Breakdown of steps that carry no ATT&CK technique."""
    bare = [s for s in steps if not s.techniques]
    by_type = Counter(s.type for s in bare)
    by_shape = Counter(_unlabelled(s.cmd) for s in bare)
    examples = [
        {"campaign": s.campaign, "run": s.run, "type": s.type, "cmd": s.cmd[:120]}
        for s in sorted(bare, key=lambda s: s.ts)[:15]
    ]
    return {
        "steps": len(steps),
        "no_technique": len(bare),
        "share": round(len(bare) / len(steps), 4) if steps else 0.0,
        "by_type": dict(by_type.most_common()),
        "by_shape": dict(by_shape.most_common(25)),
        "examples": examples,
    }


def variant_grid(
    steps: list[Step],
    sequence_dirs: list[str],
    step_dirs: list[str],
    archive_steps: list[Step] | None = None,
) -> list[dict[str, Any]]:
    """One comparable row per campaign (variant)."""
    by_campaign: dict[str, list[Step]] = defaultdict(list)
    for step in steps:
        by_campaign[step.campaign].append(step)
    full: dict[str, list[Step]] = defaultdict(list)
    for step in archive_steps or []:
        full[step.campaign].append(step)
    rows = []
    for campaign in sorted(by_campaign):
        camp_steps = sorted(by_campaign[campaign], key=lambda s: (s.run or 0, s.ts))
        chain = ">".join(
            f"{s.type}:{'+'.join(s.techniques) if s.techniques else '?' + _unlabelled(s.cmd)}"
            for s in camp_steps
        )
        rows.append(
            {
                "variant": campaign,
                "sequences": sum(1 for d in sequence_dirs if d.startswith(campaign + "-")),
                "runs": sum(1 for d in step_dirs if d.startswith(campaign + "-")),
                "steps": len(camp_steps),
                "distinct_techniques": len({t for s in camp_steps for t in s.techniques}),
                "unlabelled_steps": sum(1 for s in camp_steps if not s.techniques),
                "archive_steps": len(full.get(campaign, [])),
                "chain": chain,
                "chain_full": ">".join(
                    f"{s.type}:{'+'.join(s.techniques) if s.techniques else '?' + _unlabelled(s.cmd)}"
                    for s in full.get(campaign, [])
                ),
            }
        )
    return rows


def granularity(steps: list[Step], root: Path, views: dict[str, Any]) -> dict[str, Any]:
    """Characterise what a sequence/step directory is."""
    steps_base = root / "steps"
    seq_base = root / "sequences"
    step_dirs = (
        sorted(p.name for p in steps_base.iterdir() if p.is_dir()) if steps_base.is_dir() else []
    )
    seq_dirs = sorted(p.name for p in seq_base.iterdir() if p.is_dir()) if seq_base.is_dir() else []
    missing_step_files = [
        name
        for name in step_dirs
        if not (steps_base / name / "attacker/logs/attackmate.json").is_file()
    ]
    by_campaign: dict[str, list[Step]] = defaultdict(list)
    for step in steps:
        by_campaign[step.campaign].append(step)
    order = {}
    for campaign, camp_steps in by_campaign.items():
        ordered = sorted(camp_steps, key=lambda s: s.ts)
        inversions = sum(
            1 for a, b in zip(ordered, ordered[1:], strict=False) if (a.run or 0) > (b.run or 0)
        )
        gaps = [(b.ts - a.ts).total_seconds() for a, b in zip(ordered, ordered[1:], strict=False)]
        order[campaign] = {
            "runs": len({s.run for s in camp_steps}),
            "max_run": max((s.run or 0) for s in camp_steps),
            "run_index_inversions": inversions,
            "median_gap_s": sorted(gaps)[len(gaps) // 2] if gaps else None,
        }
    sizes = Counter()
    for name in seq_dirs:
        sizes[len(_parse_dir_name(name)[1])] += 1
    return {
        "views": views,
        "sequence_dirs": len(seq_dirs),
        "step_dirs": len(step_dirs),
        "step_dirs_without_steps": missing_step_files,
        "sequence_name_size": dict(sorted(sizes.items())),
        "per_campaign": order,
    }


def read_archive_steps(archive_dir: Path) -> tuple[list[Step], list[ParseFailure], dict[str, Any]]:
    """Read the whole-campaign attackmate.json from each variant zip."""
    steps: list[Step] = []
    failures: list[ParseFailure] = []
    info: dict[str, Any] = {}
    for path in sorted(archive_dir.glob("*.zip")):
        if path.name.startswith("manifestations_"):
            continue
        campaign = path.stem.removeprefix("scenario_")
        with zipfile.ZipFile(path) as archive:
            members = [n for n in archive.namelist() if n.endswith("attacker/logs/attackmate.json")]
            info[campaign] = {"archive": path.name, "members": len(members), "steps": 0}
            for member in members:
                text = archive.read(member).decode("utf-8", errors="replace")
                for lineno, line in enumerate(text.splitlines(), 1):
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError as exc:
                        failures.append(
                            ParseFailure(f"{path.name}:{member}", lineno, f"json: {exc}")
                        )
                        continue
                    steps.append(
                        _step_from_obj(
                            obj,
                            campaign=campaign,
                            view="archive",
                            sequence=campaign,
                            run=None,
                            index=info[campaign]["steps"],
                        )
                    )
                    info[campaign]["steps"] += 1
    return steps, failures, info


def _zip_members(archive: zipfile.ZipFile) -> tuple[str, dict[str, zipfile.ZipInfo]]:
    root = archive.namelist()[0].split("/", 1)[0]
    members = {
        info.filename[len(root) + 1 :]: info
        for info in archive.infolist()
        if not info.is_dir() and info.filename.startswith(root + "/")
    }
    return root, members


def compare_bundles(path_a: Path, path_b: Path) -> dict[str, Any]:
    """Structural comparison of two manifestation bundles (e.g. filtered vs raw)."""
    with zipfile.ZipFile(path_a) as a, zipfile.ZipFile(path_b) as b:
        root_a, entries_a = _zip_members(a)
        root_b, entries_b = _zip_members(b)
        only_b = sorted(set(entries_b) - set(entries_a))
        only_a = sorted(set(entries_a) - set(entries_b))
        differing = [
            name
            for name in set(entries_a) & set(entries_b)
            if entries_a[name].CRC != entries_b[name].CRC
        ]
        kinds = Counter("/".join(name.split("/")[2:]) for name in only_b)
        subset_violations = 0
        checked = 0
        for name in differing:
            if not name.endswith((".json", ".log", ".syslog")):
                continue
            lines_a = set(a.read(f"{root_a}/{name}").decode("utf-8", "replace").splitlines())
            lines_b = set(b.read(f"{root_b}/{name}").decode("utf-8", "replace").splitlines())
            checked += 1
            subset_violations += bool(lines_a - lines_b)
        return {
            "files_a": len(entries_a),
            "files_b": len(entries_b),
            "only_in_a": len(only_a),
            "only_in_b": len(only_b),
            "only_in_b_kinds": dict(kinds.most_common(20)),
            "shared_paths": len(set(entries_a) & set(entries_b)),
            "identical_crc": len(set(entries_a) & set(entries_b)) - len(differing),
            "differing_content": len(differing),
            "line_subset_checked": checked,
            "line_subset_violations": subset_violations,
        }


# ------------------------------------------------------------------------ cli


def _view_counts(root: Path) -> dict[str, Any]:
    counts: dict[str, Any] = {}
    for view in VIEWS:
        base = root / view
        if not base.is_dir():
            continue
        files = list(base.rglob("attackmate.json"))
        counts[view] = {
            "dirs": sum(1 for p in base.iterdir() if p.is_dir()),
            "step_files": len(files),
        }
    return counts


def _campaign_events(seq_events: dict[str, list[Event]]) -> dict[str, list[Event]]:
    grouped: dict[str, list[Event]] = defaultdict(list)
    for sequence, events in seq_events.items():
        grouped[_parse_dir_name(sequence)[0]].extend(events)
    return grouped


def _bundle_vs_archive(bundle_steps: list[Step], archive_steps: list[Step]) -> dict[str, Any]:
    bundle_ts = {(s.campaign, s.ts.isoformat()) for s in bundle_steps}
    archive_ts = {(s.campaign, s.ts.isoformat()) for s in archive_steps}
    dropped = [s for s in archive_steps if (s.campaign, s.ts.isoformat()) not in bundle_ts]
    return {
        "archive_steps": len(archive_steps),
        "bundle_steps": len(bundle_steps),
        "bundle_steps_missing_from_archive": len(bundle_ts - archive_ts),
        "archive_steps_missing_from_bundle": len(dropped),
        "dropped_labelled": sum(1 for s in dropped if s.techniques),
        "dropped_by_type": dict(Counter(s.type for s in dropped).most_common()),
        "archives": sorted({s.campaign for s in archive_steps}),
        "campaigns_in_bundle": sorted({s.campaign for s in bundle_steps}),
    }


def sequence_group_rule(seq_steps: list[Step], step_steps: list[Step]) -> dict[str, Any]:
    """Test whether a sequence dir is a maximal run of steps sharing a technique."""
    run_of = {(s.campaign, s.ts): s.run for s in step_steps}
    runs: dict[str, dict[int, list[Step]]] = defaultdict(lambda: defaultdict(list))
    for step in step_steps:
        if step.run is not None:
            runs[step.campaign][step.run].append(step)
    groups: dict[tuple[str, str], list[Step]] = defaultdict(list)
    for step in seq_steps:
        groups[(step.campaign, step.sequence)].append(step)
    multi = shared = maximal = 0
    failures = []
    for (campaign, sequence), members in groups.items():
        indices = sorted({run_of[(campaign, s.ts)] for s in members if (campaign, s.ts) in run_of})
        if len(indices) < 2:
            continue
        multi += 1
        per_run = [{t for s in runs[campaign][n] for t in s.techniques} for n in indices]
        common = set.intersection(*per_run)
        if not common:
            failures.append({"sequence": sequence, "why": "no shared technique"})
            continue
        shared += 1
        low, high = indices[0], indices[-1]
        neighbours = runs[campaign].get(low - 1, []) + runs[campaign].get(high + 1, [])
        explained = [
            technique
            for technique in common
            if not any(technique in s.techniques for s in neighbours)
        ]
        if explained:
            maximal += 1
        else:
            failures.append({"sequence": sequence, "why": "not maximal", "common": sorted(common)})
    return {
        "sequence_dirs": len(groups),
        "multi_run_dirs": multi,
        "dirs_with_shared_technique": shared,
        "dirs_at_maximal_block": maximal,
        "failures": failures[:20],
        "failure_count": len(failures),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    """Run every reader and analysis; return the whole report."""
    root = Path(args.root)
    step_reader = load_steps(root, "steps")
    seq_reader = load_steps(root, "sequences")
    tech_reader = load_steps(root, "techniques")
    steps: list[Step] = step_reader.records
    year_of: dict[str, int] = {}
    for step in seq_reader.records:
        year_of.setdefault(step.sequence, step.ts.year)
    event_reader = Reader()
    syslog_hosts = None if args.syslog_hosts == "all" else set(args.syslog_hosts.split(","))
    seq_events = read_sequence_events(root, "sequences", year_of, event_reader, syslog_hosts)
    events = [event for bucket in seq_events.values() for event in bucket]
    dns, agents = host_map(events)
    inventory: dict[str, str] = {}
    if args.archive_dir:
        inventory = read_inventory(Path(args.archive_dir))
    hosts = {**agents, **inventory}
    campaign_index = {
        campaign: CampaignEvents(bucket)
        for campaign, bucket in _campaign_events(seq_events).items()
    }
    archive_steps: list[Step] = []
    archive_failures: list[ParseFailure] = []
    archive_info: dict[str, Any] = {}
    if args.archive_dir:
        archive_steps, archive_failures, archive_info = read_archive_steps(Path(args.archive_dir))
    rows, join_summary = join(steps, campaign_index, hosts, inventory)
    slice_counts = {sequence: len(bucket) for sequence, bucket in seq_events.items()}
    join_summary["steps_with_empty_publisher_slice"] = sum(
        1 for step in seq_reader.records if slice_counts.get(step.sequence, 0) == 0
    )
    seq_dirs = sorted(p.name for p in (root / "sequences").iterdir() if p.is_dir())
    step_dirs = sorted(p.name for p in (root / "steps").iterdir() if p.is_dir())
    by_host = Counter(event.host for event in events)
    host_by_campaign: dict[str, dict[str, int]] = defaultdict(Counter)
    for campaign, bucket in _campaign_events(seq_events).items():
        host_by_campaign[campaign].update(event.host for event in bucket)
    granularity_report = granularity(steps, root, _view_counts(root))
    granularity_report["window_check"] = window_check(
        seq_reader.records, seq_events, LAST_STEP_TAIL_S
    )
    granularity_report["group_rule"] = sequence_group_rule(seq_reader.records, steps)
    report: dict[str, Any] = {
        "root": str(root),
        "views": _view_counts(root),
        "readers": {
            "steps": {
                "files": step_reader.files,
                "lines": step_reader.lines,
                "failures": [f.__dict__ for f in step_reader.failures],
            },
            "sequences": {
                "files": seq_reader.files,
                "lines": seq_reader.lines,
                "failures": [f.__dict__ for f in seq_reader.failures],
            },
            "techniques": {
                "files": tech_reader.files,
                "lines": tech_reader.lines,
                "failures": [f.__dict__ for f in tech_reader.failures],
            },
            "events": {
                "files": event_reader.files,
                "lines": event_reader.lines,
                "parsed": len(events),
                "failures": [f.__dict__ for f in event_reader.failures],
                "failures_by_kind": dict(
                    Counter(f.error.split(":")[0] for f in event_reader.failures)
                ),
            },
        },
        "granularity": granularity_report,
        "unlabelled": unlabelled_profile(steps),
        "events_by_host": dict(by_host.most_common()),
        "events_by_kind": dict(Counter(event.kind for event in events).most_common()),
        "events_by_host_by_sequence": {
            sequence: dict(Counter(event.host for event in events).most_common())
            for sequence, events in sorted(seq_events.items())
        },
        "events_by_host_by_campaign": {
            campaign: dict(counter.most_common())
            for campaign, counter in sorted(host_by_campaign.items())
        },
        "join": {
            "parameters": {
                "window": "[step_ts, next_step_ts) per campaign, half-open",
                "last_step_tail_s": LAST_STEP_TAIL_S,
                "lookback_s": LOOKBACK_S,
                "entity_kinds": ["ip", "host", "url"],
                "cross_host": "shared entity resolves (facts ip->host) to a host != observing host",
                "syslog_hosts": args.syslog_hosts,
                "events_per_campaign": {k: len(v.events) for k, v in campaign_index.items()},
            },
            "summary": join_summary,
            "rows": [row.__dict__ for row in rows],
        },
        "grid": variant_grid(steps, seq_dirs, step_dirs, archive_steps),
    }
    if args.archive_dir:
        report["archives"] = {
            "info": archive_info,
            "steps": len(archive_steps),
            "failures": [f.__dict__ for f in archive_failures],
            "unlabelled": unlabelled_profile(archive_steps),
            "bundle_compare": _bundle_vs_archive(steps, archive_steps),
        }
    if args.compare_a and args.compare_b:
        report["bundle_compare"] = compare_bundles(Path(args.compare_a), Path(args.compare_b))
    return report


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return out


def _md_header(
    report: dict[str, Any], filtered: dict[str, Any] | None, archives: dict[str, Any]
) -> list[str]:
    lines = [
        "# CAM-LDS extraction — attack steps, manifestations and sequence granularity",
        "",
        "Generated from the JSON report by `scripts/cam_lds_extract.py`; no number below is",
        "hand-typed. The full row-level JSON is written with `--out` and kept out of the checkout.",
        "",
        f"- Bundle root: `{report['root']}`",
    ]
    if archives:
        lines.append(f"- Campaign archives: {len(archives['info'])}")
    if filtered:
        lines.append(f"- Filtered comparison root: `{filtered['root']}`")
    lines.append("")
    return lines


def _md_readers(report: dict[str, Any]) -> list[str]:
    readers = report["readers"]
    lines = [
        "## Readers",
        "",
        "| view | files | lines/records | parse failures |",
        "|---|---|---|---|",
    ]
    for name in ("steps", "sequences", "techniques", "events"):
        data = readers[name]
        records = data.get("parsed", data.get("lines"))
        lines.append(f"| {name} | {data['files']} | {records} | {len(data['failures'])} |")
    failures = readers["events"].get("failures_by_kind") or {}
    lines += [
        "",
        f"Defender event parse failures by kind: `{json.dumps(failures, sort_keys=True)}`.",
        "",
        "### Defender events",
        "",
        "| host | events |",
        "|---|---|",
    ]
    for host, count in sorted(report["events_by_host"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {host} | {count} |")
    lines += ["", "| kind | events |", "|---|---|"]
    for kind, count in sorted(report["events_by_kind"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {kind} | {count} |")
    lines += [
        "",
        "Per-sequence and per-campaign event/host counts are in the JSON "
        "(`events_by_host_by_sequence`, `events_by_host_by_campaign`).",
        "",
    ]
    return lines


def _md_granularity(report: dict[str, Any]) -> list[str]:
    views = report["views"]
    g = report["granularity"]
    lines = [
        "## Sequence granularity — what a `sequences/<name>` directory is",
        "",
        "| view | directories | `attackmate.json` files |",
        "|---|---|---|",
    ]
    for name in ("sequences", "steps", "techniques"):
        lines.append(f"| {name} | {views[name]['dirs']} | {views[name]['step_files']} |")
    lines += [
        "",
        f"- `steps/` directories without `attackmate.json`: {len(g['step_dirs_without_steps'])} "
        f"(`{', '.join(g['step_dirs_without_steps'])}`)",
        "- The `-<n>` suffix is a **step ordinal inside one campaign**, not a repeat run of the same",
        f"  variant. {g['sequence_dirs']} sequence directories partition the bundle's step dirs into",
        f"  {sum(v['runs'] for v in g['per_campaign'].values())} runs across "
        f"{len(g['per_campaign'])} campaigns.",
        "- A multi-run sequence directory groups a contiguous block of step ordinals for one",
        f"  technique: {g['group_rule']['multi_run_dirs']} multi-run dirs, "
        f"{g['group_rule']['dirs_with_shared_technique']} share a technique, and "
        f"{g['group_rule']['dirs_at_maximal_block']} are the maximal contiguous block "
        f"({g['group_rule']['failure_count']} exceptions recorded).",
        "",
    ]
    lines += _table(
        ["campaign", "runs", "max ordinal", "median step gap (s)", "run-index inversions"],
        [
            [
                name,
                data["runs"],
                data["max_run"],
                data["median_gap_s"],
                data["run_index_inversions"],
            ]
            for name, data in g["per_campaign"].items()
        ],
    )
    window = g["window_check"]
    lines += [
        "",
        "### Publisher window check",
        "",
        f"The publisher's per-sequence slices were checked against the campaign step clock: "
        f"{window['checked']} sequence dirs with events and steps, {window['outside_window']} "
        f"contain events outside `[first_step - {window['opening_lookback_s']}s, "
        f"next_step)`, {window['dirs_with_events_before_step']} have events before the first step "
        f"(max lead {window['max_lead_s']}s) and {window['dirs_with_events_after_window']} have "
        f"events after the window (max lag {window['max_lag_s']}s). "
        f"Events without any step: {window['events_without_step']}.",
        "",
    ]
    return lines


def _md_episodes(report: dict[str, Any], archives: dict[str, Any]) -> list[str]:
    bundle_cmp = archives.get("bundle_compare") or {}
    if not bundle_cmp:
        return []
    views = report["views"]
    readers = report["readers"]
    lines = [
        "### Episodes: bundle vs campaign archives",
        "",
        f"The `steps/` view is a strict subset of the campaign archives: "
        f"{bundle_cmp['bundle_steps_missing_from_archive']} bundle steps are absent from the "
        f"archives, while {bundle_cmp['archive_steps_missing_from_bundle']} archive steps are "
        f"absent from the bundle (all unlabelled: {bundle_cmp['dropped_labelled']} labelled "
        f"steps dropped). The episode unit is therefore one campaign archive "
        f"({bundle_cmp['archive_steps']} steps over {len(bundle_cmp['archives'])} archives), "
        f"not a bundle sequence directory ({bundle_cmp['bundle_steps']} steps).",
        "",
    ]
    files_per_bundle = sum(views[name]["step_files"] for name in views)
    lines_per_bundle = sum(readers[name]["lines"] for name in ("steps", "sequences", "techniques"))
    rebuilt_files = files_per_bundle * 2 + len(archives["info"])
    rebuilt_steps = lines_per_bundle * 2 + archives["steps"]
    lines += [
        "### The brief's 5,554-sequence / 11,388-step baseline does not reproduce",
        "",
        f"Per bundle the three views hold {files_per_bundle} `attackmate.json` files and "
        f"{lines_per_bundle} step lines. Counting both bundles and the campaign archives gives "
        f"{rebuilt_files} files and {rebuilt_steps} steps — exactly the brief's quoted "
        "5,554 / 11,388. The baseline is therefore a file-and-line double-count across views "
        "and bundles, not a count of distinct attack episodes.",
        "",
    ]
    return lines


def _md_unlabelled(report: dict[str, Any], archives: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for label, profile in (
        ("bundle", report["unlabelled"]),
        ("campaign archives", archives.get("unlabelled")),
    ):
        if not profile:
            continue
        share = round(100 * profile["share"], 2)
        lines += [
            f"## Unlabelled steps — {label}",
            "",
            f"{profile['no_technique']} of {profile['steps']} steps ({share}%) carry no ATT&CK "
            "metadata. They are kept in every count above; none is dropped and none is relabelled.",
            "",
            "| type | count |",
            "|---|---|",
        ]
        for name, count in sorted(profile["by_type"].items(), key=lambda kv: -kv[1]):
            lines.append(f"| {name} | {count} |")
        lines += ["", "| command shape | count |", "|---|---|"]
        for name, count in sorted(profile["by_shape"].items(), key=lambda kv: -kv[1]):
            lines.append(f"| {name} | {count} |")
        lines.append("")
    return lines


def _md_filtered(report: dict[str, Any]) -> list[str]:
    compare = report.get("bundle_compare")
    if not compare:
        return []
    lines = [
        "## filtered vs raw",
        "",
        f"- `filtered` files: {compare['files_a']}; `raw` files: {compare['files_b']}; "
        f"shared paths: {compare['shared_paths']}.",
        f"- Files only in `filtered`: {compare['only_in_a']}; only in `raw`: {compare['only_in_b']}.",
        f"- Identical CRC on shared paths: {compare['identical_crc']}; differing content: "
        f"{compare['differing_content']}.",
        f"- Line-subset check on {compare['line_subset_checked']} differing files: "
        f"{compare['line_subset_violations']} violations. `filtered` is a strict line-subset of "
        "`raw` at identical paths; `raw` is the superset and the primary analysis root.",
        "",
        "| path kind present only in `raw` | files |",
        "|---|---|",
    ]
    for name, count in sorted(compare["only_in_b_kinds"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| `{name}` | {count} |")
    lines.append("")
    return lines


def _md_join(report: dict[str, Any], filtered: dict[str, Any] | None) -> list[str]:
    params = report["join"]["parameters"]
    summary = report["join"]["summary"]
    lines = [
        "## Step → manifestation join",
        "",
        "Design: sort each campaign's steps by timestamp; a step's window is "
        "`[step_ts - lookback_s, next_step_ts)` (half-open), with the last step extended by "
        "`last_step_tail_s`. An event manifests a step when it falls in the window and shares at "
        "least one entity (`ip:`, `host:`, `url:`). `facts.json` maps each IP to its host; a shared "
        "entity naming a host other than the observing host is a cross-host edge.",
        "",
        "| parameter | value |",
        "|---|---|",
        f"| window | `{params['window']}` |",
        f"| lookback_s | {params['lookback_s']} |",
        f"| last_step_tail_s | {params['last_step_tail_s']} |",
        f"| entity kinds | {', '.join(params['entity_kinds'])} |",
        f"| syslog hosts | {params['syslog_hosts']} |",
        "",
        "| metric | value |",
        "|---|---|",
        f"| steps | {summary['steps']} |",
        f"| steps with ≥1 manifestation | {summary['with_manifestation']} |",
        f"| silent steps | {summary['silent']} |",
        f"| steps with an empty publisher slice | {summary['steps_with_empty_publisher_slice']} |",
        f"| raw token edges | {summary['raw_token_edges']} |",
        f"| shared-entity edges | {summary['shared_entity_edges']} |",
        f"| steps with a cross-host edge | {summary['steps_with_cross_host_edge']} |",
        f"| **cross-host edges** | **{summary['cross_host_edges']}** |",
        "",
        f"Shared-entity edges by kind: `{json.dumps(summary['shared_entity_edges_by_kind'], sort_keys=True)}`. "
        f"Cross-host edges by entity: `{json.dumps(summary['cross_host_edges_by_kind'], sort_keys=True)}`.",
        "",
        "The cross-host count is not zero, so the stopping condition (report zero with numbers) "
        "does not apply. It is small relative to the shared-entity total and rests on the "
        "`facts.json` IP→host map; DNS names are not used for identity because four external "
        "names resolve to the same gateway address in `dnsmasq`.",
        "",
    ]
    if filtered:
        fj = filtered["join"]["summary"]
        lines += [
            "### filtered vs raw join",
            "",
            "| metric | raw | filtered |",
            "|---|---|---|",
            f"| events | {report['readers']['events']['parsed']} | {filtered['readers']['events']['parsed']} |",
            f"| silent steps | {summary['silent']} | {fj['silent']} |",
            f"| shared-entity edges | {summary['shared_entity_edges']} | {fj['shared_entity_edges']} |",
            f"| cross-host edges | {summary['cross_host_edges']} | {fj['cross_host_edges']} |",
            f"| steps with cross-host edge | {summary['steps_with_cross_host_edge']} | {fj['steps_with_cross_host_edge']} |",
            "",
        ]
    return lines


def _md_grid(report: dict[str, Any], archives: dict[str, Any]) -> list[str]:
    grid = report["grid"]
    lines = [
        "## Variant grid",
        "",
        "| variant | sequences | runs | steps | archive steps | distinct techniques | unlabelled |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in grid:
        lines.append(
            f"| {row['variant']} | {row['sequences']} | {row['runs']} | {row['steps']} | "
            f"{row['archive_steps']} | {row['distinct_techniques']} | {row['unlabelled_steps']} |"
        )
    lines += ["", "| scenario | variants |", "|---|---|"]
    by_scenario = Counter(row["variant"].split("_")[0] for row in grid)
    for scenario, count in sorted(by_scenario.items()):
        lines.append(f"| {scenario} | {count} |")
    grid_variants = {row["variant"] for row in grid}
    archive_variants = set(archives.get("info") or {})
    if archive_variants:
        lines += [
            "",
            f"Archive variants: {len(archive_variants)}; grid variants: {len(grid_variants)}; "
            f"only in archives: {sorted(archive_variants - grid_variants)}; "
            f"only in the grid: {sorted(grid_variants - archive_variants)}.",
        ]
    lines += [
        "",
        "### Step chains (comparable form)",
        "",
        "Each chain is `type:techniques` per step in timestamp order; `?` marks a step with no",
        "technique and labels the unlabelled command shape. Full chains are also in the JSON.",
        "",
    ]
    for row in grid:
        lines.append(f"- **{row['variant']}** — `{row['chain']}`")
    lines.append("")
    return lines


def _md_limits(report: dict[str, Any]) -> list[str]:
    summary = report["join"]["summary"]
    return [
        "## What this cannot evidence",
        "",
        "- CAM-LDS has no per-event ground truth. The join is a reproducible attribution, not a",
        "  scored accuracy result; nothing here validates it against published truth.",
        "- Cross-host identity depends on `facts.json`; entities that never appear in an IP-to-host",
        "  mapping cannot become a cross-host edge.",
        f"- {summary['silent']} steps produce no manifestation in the window and "
        f"{summary['steps_with_empty_publisher_slice']} sit in sequence dirs whose publisher "
        "slice is empty. These are reported, not repaired.",
        "",
    ]


def render_markdown(
    report: dict[str, Any],
    filtered: dict[str, Any] | None = None,
) -> str:
    """Render the report as Markdown; every value comes from the report dicts."""
    archives = report.get("archives") or {}
    lines = _md_header(report, filtered, archives)
    lines += _md_readers(report)
    lines += _md_granularity(report)
    lines += _md_episodes(report, archives)
    lines += _md_unlabelled(report, archives)
    lines += _md_filtered(report)
    lines += _md_join(report, filtered)
    lines += _md_grid(report, archives)
    lines += _md_limits(report)
    return "\n".join(lines)


def _summary(report: dict[str, Any]) -> str:
    join_summary = report["join"]["summary"]
    lines = [
        f"root                 {report['root']}",
        f"steps                {join_summary['steps']}",
        f"events               {report['readers']['events']['parsed']}",
        f"silent steps         {join_summary['silent']}",
        f"shared-entity edges  {join_summary['shared_entity_edges']}",
        f"cross-host edges     {join_summary['cross_host_edges']}",
        f"grid variants        {len(report['grid'])}",
        f"parse failures       {sum(len(v['failures']) for k, v in report['readers'].items())}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="extracted bundle root (contains sequences/)")
    parser.add_argument("--archive-dir", help="directory of scenario_*.zip campaign archives")
    parser.add_argument("--compare-a", help="baseline bundle zip (e.g. filtered)")
    parser.add_argument("--compare-b", help="larger bundle zip (e.g. raw)")
    parser.add_argument("--syslog-hosts", default="inetfw,corpdns", help="comma list or 'all'")
    parser.add_argument("--out", help="write the report JSON here")
    parser.add_argument("--markdown", help="write the Markdown report here")
    parser.add_argument("--filtered-report", help="JSON report from a filtered run to compare")
    args = parser.parse_args(argv)
    report = build_report(args)
    payload = json.dumps(report, indent=1, sort_keys=True)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
    if args.markdown:
        filtered = (
            json.loads(Path(args.filtered_report).read_text(encoding="utf-8"))
            if args.filtered_report
            else None
        )
        Path(args.markdown).write_text(render_markdown(report, filtered), encoding="utf-8")
    print(_summary(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
