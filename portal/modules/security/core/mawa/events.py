"""Raw-log event reader for the MAWA join: apache combined access + syslog lines.

Reads untrusted third-party log files from disk only. Entities are extracted
from line content; client identity fields (client address, user-agent, referer)
are deliberately NOT extracted and never become join features.
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

MONTHS = {
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

APACHE_RE = re.compile(
    r"^(\S+) (\S+) (\S+) \[([^\]]+)\] \"([^\"]*)\" (\d{3}|-) (\d+|-) \"([^\"]*)\" \"([^\"]*)\"\s*$"
)
APACHE_TS_RE = re.compile(
    r"^(\d{1,2})/([A-Z][a-z]{2})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) ([+-])(\d{2})(\d{2})$"
)
SYSLOG_RE = re.compile(
    r"^([A-Z][a-z]{2}) +(\d{1,2}) (\d{2}):(\d{2}):(\d{2}) (\S+) ([\w.-]+)(?:\[(\d+)\])?: (.*)$"
)
PATH_RE = re.compile(r"/[A-Za-z0-9._/@%-]+")
B64_RE = re.compile(r"^[A-Za-z0-9+/%]+={0,2}$")
MAX_TOKEN_LEN = 64


@dataclass(frozen=True)
class ParsedEvent:
    """One raw log line with content-derived entities (no identity features)."""

    event_id: int
    ts: float
    source_file: str
    kind: str
    tag: str
    pid: str
    message: str
    fields: Mapping[str, str]
    entities: frozenset[str]
    raw: str


@dataclass(frozen=True)
class ParseFailure:
    """A line that did not parse; never dropped silently."""

    file: str
    line_no: int
    reason: str
    excerpt: str


@dataclass
class ParseReport:
    """Per-file parse accounting."""

    file: str
    lines_read: int = 0
    empty_lines: int = 0
    events: int = 0
    failures: list[ParseFailure] = field(default_factory=list)


def _parse_apache_ts(raw_ts: str) -> float | None:
    m = APACHE_TS_RE.match(raw_ts)
    if m is None:
        return None
    day, mon, year, hh, mm, ss, sign, oh, om = m.groups()
    month = MONTHS.get(mon)
    if month is None:
        return None
    offset = timedelta(hours=int(oh), minutes=int(om))
    if sign == "-":
        offset = -offset
    dt = datetime(
        int(year),
        month,
        int(day),
        int(hh),
        int(mm),
        int(ss),
        tzinfo=timezone(offset),
    )
    return dt.timestamp()


def _cmd_entities(url: str) -> set[str]:
    """Percent-decode query values and decode base64-JSON arrays into tokens."""
    out: set[str] = set()
    if "?" not in url:
        return out
    for part in url.split("?", 1)[1].split("&"):
        _, _, value = part.partition("=")
        out.add(f"qval:{value}")
        decoded = unquote(value)
        if B64_RE.match(decoded) and len(decoded) % 4 == 0:
            try:
                payload = base64.b64decode(decoded).decode("utf-8")
                arr = json.loads(payload)
                if isinstance(arr, list):
                    out.update(
                        f"cmd:{tok}"
                        for tok in arr
                        if isinstance(tok, str) and len(tok) <= MAX_TOKEN_LEN
                    )
            except (ValueError, UnicodeDecodeError):
                pass
    return out


def _apache_entities(url: str, code: str) -> frozenset[str]:
    path = url.split("?", 1)[0]
    out = {f"path:{path}", f"url:{url}", f"code:{code}"}
    out |= _cmd_entities(url)
    return frozenset(out)


def _parse_apache_line(
    line: str, event_id: int, source_file: str
) -> tuple[float, ParsedEvent] | None:
    m = APACHE_RE.match(line)
    if m is None:
        return None
    ts = _parse_apache_ts(m.group(4))
    if ts is None:
        return None
    request = m.group(5)
    req_parts = request.split(" ")
    method = req_parts[0] if req_parts else ""
    url = req_parts[1] if len(req_parts) > 1 else ""
    proto = req_parts[2] if len(req_parts) > 2 else ""
    fields = {
        "method": method,
        "url": url,
        "proto": proto,
        "client": m.group(1),
        "code": m.group(6),
        "bytes": m.group(7),
        "referer": m.group(8),
        "user_agent": m.group(9),
    }
    entities = _apache_entities(url, m.group(6))
    event = ParsedEvent(
        event_id=event_id,
        ts=ts,
        source_file=source_file,
        kind="apache_access",
        tag="",
        pid="",
        message=request,
        fields=fields,
        entities=entities,
        raw=line.rstrip("\n"),
    )
    return ts, event


def _sudo_entities(msg: str, out: set[str]) -> None:
    m = re.match(r"^(\S+) : TTY=(\S+) ; PWD=(\S+) ; USER=(\S+) ; COMMAND=(.*)$", msg)
    if m is None:
        return
    user, _tty, pwd, runas, command = m.groups()
    out.add(f"user:{user}")
    out.add(f"user:{runas}")
    out.add(f"path:{pwd}")
    for tok in command.split():
        out.add(f"cmd:{tok}")


def _syslog_entities(tag: str, msg: str) -> frozenset[str]:
    out: set[str] = {f"tag:{tag}"}
    _sudo_entities(msg, out)
    for m in re.finditer(r"\(to (\S+)\)", msg):
        out.add(f"user:{m.group(1)}")
    for m in re.finditer(r"(?:for|of) user (\S+?)(?:\(|\.|$| )", msg):
        out.add(f"user:{m.group(1)}")
    for m in re.finditer(r"\b(?:session|Session) (c?\d+)", msg):
        out.add(f"sess:{m.group(1)}")
    for m in re.finditer(r"\b(pts/\d+|tty\d+)\b", msg):
        out.add(f"tty:{m.group(1)}")
    for m in PATH_RE.finditer(msg):
        out.add(f"path:{m.group(0)}")
    return frozenset(out)


def _parse_syslog_line(
    line: str, event_id: int, source_file: str, year: int, tz_hours: float
) -> tuple[float, ParsedEvent] | None:
    m = SYSLOG_RE.match(line)
    if m is None:
        return None
    mon, day, hh, mm, ss, _host, tag, pid, msg = m.groups()
    month = MONTHS.get(mon)
    if month is None:
        return None
    tz = timezone(timedelta(hours=tz_hours))
    dt = datetime(year, month, int(day), int(hh), int(mm), int(ss), tzinfo=tz)
    event = ParsedEvent(
        event_id=event_id,
        ts=dt.timestamp(),
        source_file=source_file,
        kind="syslog",
        tag=tag,
        pid=pid or "",
        message=msg.strip(),
        fields={},
        entities=_syslog_entities(tag, msg.strip()),
        raw=line.rstrip("\n"),
    )
    return dt.timestamp(), event


def read_events(
    paths: list[str], syslog_year: int, syslog_tz_hours: float
) -> tuple[list[ParsedEvent], list[ParseReport]]:
    """Read log files, content-sniffing apache vs syslog per line."""
    events: list[ParsedEvent] = []
    reports: list[ParseReport] = []
    next_id = 1
    for path in paths:
        report = ParseReport(file=path)
        for line_no, line in enumerate(
            Path(path).read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            report.lines_read += 1
            if not line.strip():
                report.empty_lines += 1
                continue
            parsed = _parse_apache_line(line, next_id, path)
            kind = "apache_access"
            if parsed is None:
                parsed = _parse_syslog_line(line, next_id, path, syslog_year, syslog_tz_hours)
                kind = "syslog"
            if parsed is None:
                report.failures.append(
                    ParseFailure(
                        file=path,
                        line_no=line_no,
                        reason=f"no parser matched ({kind} tried)",
                        excerpt=line[:120],
                    )
                )
                continue
            events.append(parsed[1])
            next_id += 1
            report.events += 1
        reports.append(report)
    return events, reports
