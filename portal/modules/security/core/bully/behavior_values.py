"""bully.behavior_values -- the behavior a telemetry record carries, as normalized terms.

Signatures used to keep only a record's event code and field *names*
(``event-3:4688 field:CommandLine``). Two records of the same behavior and two of unrelated
behavior then look alike, and an embedder has nothing to compare but schema. This module keeps
the *values* that describe behavior -- which process ran, with what command line, what it
opened, which service or registry key it touched, which syscall, URI or identity event -- and
masks what is environment identity rather than behavior: users, hosts, domains, SIDs, GUIDs,
hashes, process ids, IPs, timestamps.

Pure and deterministic: the same records always give the same terms, in the same order.
"""

from __future__ import annotations

import html
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

MAX_TERMS = 48
#: No one label may take more than this many of the MAX_TERMS slots, so a burst of one
#: background activity (inventory registry writes, a heartbeat's command line) cannot crowd out
#: the rest of the window.
MAX_PER_LABEL = 6

# field -> term label. Only behavior-bearing fields; identity fields are never listed.
_FIELDS: dict[str, str] = {
    # process lineage
    "Image": "image",
    "NewProcessName": "image",
    "ProcessName": "image",
    "exe": "image",
    "comm": "image",
    "SourceImage": "source image",
    "TargetImage": "target image",
    "ParentImage": "parent image",
    "ParentProcessName": "parent image",
    "ImageLoaded": "loaded",
    "OriginalFileName": "original name",
    "CommandLine": "command",
    "ParentCommandLine": "parent command",
    "proctitle": "command",
    "ScriptBlockText": "script",
    "GrantedAccess": "access",
    "AccessMask": "access",
    "IntegrityLevel": "integrity",
    "TokenElevationType": "elevation",
    # files, registry, pipes, network
    "TargetFilename": "file",
    "TargetObject": "registry",
    "PipeName": "pipe",
    "QueryName": "dns",
    "DestinationPort": "dest port",
    "dest_port": "dest port",
    "Protocol": "protocol",
    # services, tasks
    "ServiceName": "service",
    "ImagePath": "service image",
    "StartType": "start type",
    "ServiceType": "service type",
    "TaskName": "task",
    # authentication and directory
    "LogonType": "logon type",
    "TicketEncryptionType": "ticket encryption",
    "TicketOptions": "ticket options",
    "PrivilegeList": "privileges",
    "ObjectType": "object type",
    "OperationType": "operation",
    "AttributeLDAPDisplayName": "ldap attribute",
    "ShareName": "share",
    "RelativeTargetName": "share file",
    "FailureReason": "failure",
    "Status": "status",
    "SubcategoryId": "audit subcategory",
    "AuditPolicyChanges": "audit policy change",
    "param1": "detail",
    "param2": "detail",
    "param3": "detail",
    "Message": "message",
    # linux audit
    "type": "record type",
    "syscall": "syscall",
    "SYSCALL": "syscall",
    "key": "audit key",
    "cwd": "cwd",
    "name": "path",
    "a0": "argument",
    "a1": "argument",
    "a2": "argument",
    # web
    "http_method": "method",
    "uri_path": "uri",
    "status": "http status",
    "http_user_agent": "agent",
    # identity providers
    "eventType": "event type",
    "displayMessage": "event",
    "outcome.result": "outcome",
}
_PATH_LABELS = frozenset(
    {
        "image",
        "source image",
        "target image",
        "parent image",
        "loaded",
        "original name",
        "file",
        "service image",
        "cwd",
        "path",
    }
)
# Coded values (access masks, ticket flags, logon types): the code IS the behavior, so the
# random-name masking that collapses temp files must not touch them.
_CODE_LABELS = frozenset(
    {
        "access",
        "ticket encryption",
        "ticket options",
        "logon type",
        "audit subcategory",
        "audit policy change",
        "status",
        "failure",
        "syscall",
        "dest port",
        "http status",
    }
)
_TEXT_LABELS = {
    "command": 160,
    "parent command": 160,
    "script": 300,
    "event": 120,
    "message": 120,
    "agent": 80,
}

_KEY = re.compile(r"(?:^|(?<=[\s\x1d]))([A-Za-z_][\w.]*)=")
_GUID = re.compile(r"\{?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}?")
_SID = re.compile(r"s-1-[0-9-]{5,}")
_IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_B64 = re.compile(r"[a-z0-9+/=]{40,}")
_HEXRUN = re.compile(r"\b(?:0x)?[0-9a-f]{12,}\b")
_LONGNUM = re.compile(r"\b\d{4,}\b")
# A Windows path that ends in a file with an extension, spaces allowed inside directory names
# ("c:\program files\splunk\bin\x.exe"): keep the file name.
_WINFILE = re.compile(
    r"(?:[a-z]:|%\w+%|\\systemroot|\\\\[\w.$-]+)?(?:\\[^\\\"'|<>]+)*\\([^\\\s\"'|<>]+\.[a-z0-9]{1,4})\b"
)
# any remaining backslash path, or a unix path with two or more separators (so "/c" and
# "/create" switches survive)
_PATHTOKEN = re.compile(r"\S*\\\S*|\S*/\S*/\S*")
_SPACE = re.compile(r"\s+")
_HEXINNER = re.compile(r"[0-9a-f]{16,}")
_ALNUM = re.compile(r"[a-z0-9]{6,}")


def _random_token(tok: str) -> bool:
    """A generated name (temp file, compiler scratch, session id): letters and digits
    interleaved at least twice (``04hirqe5``, ``3apz1eaj``), not a name with a version
    suffix (``sysmon64``, ``sha256``)."""
    if not (any(c.isdigit() for c in tok) and any(c.isalpha() for c in tok)):
        return False
    flips = sum(a.isdigit() != b.isdigit() for a, b in zip(tok, tok[1:], strict=False))
    return flips >= 2


# Environment identity, not behavior: lab-internal host names and machine accounts. Public
# domains stay (a lookup of a paste site is behavior; the lab DC's name is not).
_INTERNAL_FQDN = re.compile(
    r"\b(?:[a-z0-9-]+\.)+(?:local|lan|internal|corp|localdomain|home|intranet)\b"
)
# ...but not the admin shares (ipc$, admin$, c$, print$), whose use IS the behavior.
_MACHINE_ACCOUNT = re.compile(r"\b(?!(?:ipc|admin|print|[a-z])\$)[\w-]+\$(?=$|[\s;,\\])")


def _derandom(v: str) -> str:
    v = _MACHINE_ACCOUNT.sub("<machine>", _INTERNAL_FQDN.sub("<host>", v))
    v = _HEXINNER.sub("<hex>", v)
    return _ALNUM.sub(lambda m: "<r>" if _random_token(m.group(0)) else m.group(0), v)


def _kv(text: str) -> dict[str, str]:
    """Split ``Key=value Key2=value two`` (values may contain spaces) into a dict."""
    text = text.replace("\x1d", " ")
    marks = list(_KEY.finditer(text))
    out: dict[str, str] = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.setdefault(m.group(1), text[m.end() : end].strip().strip('"'))
    return out


def _flatten(d: Mapping[str, Any], prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, Mapping):
            out.update(_flatten(v, f"{key}."))
        elif v is not None and not isinstance(v, (list, tuple)):
            out[key] = str(v)
    return out


def _fields(record: Any) -> dict[str, str]:
    if isinstance(record, Mapping):
        return _flatten(record)
    text = str(record)
    if text[:1] == "{":
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            return _flatten(parsed)
    return _kv(text)


def _decode_proctitle(value: str) -> str:
    if len(value) % 2 == 0 and re.fullmatch(r"[0-9A-Fa-f]{8,}", value):
        try:
            return bytes.fromhex(value).replace(b"\x00", b" ").decode("utf-8", "ignore")
        except ValueError:
            return value
    return value


def _basename(value: str) -> str:
    return re.split(r"[\\/]", value.rstrip("\\/"))[-1]


def _mask(value: str) -> str:
    v = _GUID.sub("<guid>", value.replace('"', " ").replace("'", " "))
    v = _SID.sub("<sid>", v)
    v = _IPV4.sub("<ip>", v)
    v = _B64.sub("<b64>", v)
    v = _HEXRUN.sub("<hex>", v)
    v = _WINFILE.sub(lambda m: m.group(1), v)
    v = _PATHTOKEN.sub(lambda m: _basename(m.group(0)) or m.group(0), v)
    v = _LONGNUM.sub("<n>", v)
    return _SPACE.sub(" ", v).strip()


def normalize(label: str, value: str) -> str:
    """One field value as a behavior term, or ``""`` when it carries no behavior."""
    raw = html.unescape(value).strip().strip('"')
    v = raw.lower()
    if label == "command":
        v = _decode_proctitle(raw).lower()
    if not v or v in {"-", "null", "none", "n/a", "%%1936", "%%1937", "%%1938"}:
        return ""
    if label in _PATH_LABELS:
        v = _LONGNUM.sub("<n>", _GUID.sub("<guid>", _basename(v)))
    elif label == "registry":
        masked = _HEXRUN.sub("<hex>", _SID.sub("<sid>", _GUID.sub("<guid>", v)))
        parts = [p for p in re.split(r"\\", re.sub(r"\|<hex>|\|[0-9a-f]{8,}", "", masked)) if p]
        v = "\\".join(parts[-3:])
    elif label in _CODE_LABELS:
        return _SPACE.sub(" ", v)[:64]
    else:
        v = _mask(v)[: _TEXT_LABELS.get(label, 64)]
    return _derandom(v)


def behavior_values(records: Iterable[Any], *, limit: int = MAX_TERMS) -> list[str]:
    """Distinct normalized ``label: value`` terms over ``records``, rarest first (ties keep first
    appearance), capped at ``limit``. Rarest first because a capture window is mostly recurring
    background (the same service touching the same process every few seconds); the actions that
    distinguish one behavior from another tend to occur once or twice."""
    counts: Counter[str] = Counter()
    first: dict[str, int] = {}
    for record in records:
        for key, value in _fields(record).items():
            label = _FIELDS.get(key)
            if label is None:
                continue
            term = normalize(label, value)
            if not term:
                continue
            t = f"{label}: {term}"
            counts[t] += 1
            first.setdefault(t, len(first))
    out: list[str] = []
    per_label: Counter[str] = Counter()
    for t in sorted(counts, key=lambda t: (counts[t], first[t])):
        label = t.split(": ", 1)[0]
        if per_label[label] >= MAX_PER_LABEL:
            continue
        per_label[label] += 1
        out.append(t)
        if len(out) >= limit:
            break
    return out
