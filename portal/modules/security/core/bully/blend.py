"""bully.blend -- the deterministic, offline multi-schema blend fixture
(E.3, TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1).

Q2 -- universality is proven on plural data or it is not proven. Every
dataset in the M.3 eval was attack_data; the system silently reduced to a
single schema and nothing ever caught RC1's hardcoded field-name lists
because no second schema was ever present to disagree with them. A
universality claim requires a plural corpus *by construction*.

This module composes records from four genuinely different schemas --
CloudTrail, Sysmon, osquery, and a firewall/syslog line -- sharing zero
field names, into one time-ordered stream. It has no live dependency, so
E.1/E.2 and every grader test can exercise true plurality in CI, always,
regardless of lab availability. It is the deterministic sibling of the live
plane (`inject_plane.py`, E.5): both emit the same record shape (each
record carries `__source_id`), so downstream code -- field-role inference,
the artifact graph, grading -- is identical regardless of which one fed it.

Ground truth (family/technique/chain/step, injected-vs-benign) never rides
inside the graded record content -- it is returned as a separate provenance
mapping, keyed by a stable per-record fingerprint, mirroring the sealed
scorer-side wall `specimen_ledger.py` already provides for the live plane
(Q3). This module does not seal anything itself (it is deterministic and
reproducible by construction, unlike a live capture); callers that want a
sealed record for the fixture pass its provenance dicts to
`specimen_ledger.SpecimenRecord(..., source_lane="replay_mutation")`
directly -- no second sealing mechanism is built here.

Pure compute, no I/O, no model calls (COLD).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

ALGORITHM_VERSION = "blend-v1"

SCHEMAS: tuple[str, ...] = ("cloudtrail", "sysmon", "osquery", "firewall_syslog")

_EPOCH_BASE = 1_700_000_000.0


def _fingerprint(record: dict[str, Any]) -> str:
    """Stable content fingerprint, independent of stream position -- the
    join key between a captured (blind) record and its provenance entry."""
    digest = hashlib.sha256(json.dumps(record, sort_keys=True, default=str).encode()).hexdigest()
    return f"art-{digest[:16]}"


@dataclass(frozen=True)
class Provenance:
    """Ground truth for one injected or benign artifact. Never present on
    the blind record itself -- joined only after grading (Q3/Q4)."""

    fingerprint: str
    source_id: str
    schema: str
    injected: bool
    family: str | None = None
    technique: str | None = None
    chain_id: str | None = None
    step_idx: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "source_id": self.source_id,
            "schema": self.schema,
            "injected": self.injected,
            "family": self.family,
            "technique": self.technique,
            "chain_id": self.chain_id,
            "step_idx": self.step_idx,
        }


def _benign_cloudtrail(n: int, *, start: float) -> list[dict[str, Any]]:
    users = [f"alice{i}" for i in range(12)]
    verbs = ["ListBuckets", "GetObject", "DescribeInstances", "AssumeRole"]
    return [
        {
            "eventTime": f"{_iso(start + i * 5.0)}",
            "eventName": verbs[i % len(verbs)],
            "userIdentity": {"arn": f"arn:aws:iam::111122223333:user/{users[i % len(users)]}"},
            "sourceIPAddress": f"10.0.{i % 4}.{i % 250}",
            "awsRegion": "us-east-1",
            "__source_id": "blend-cloudtrail",
        }
        for i in range(n)
    ]


def _benign_sysmon(n: int, *, start: float) -> list[dict[str, Any]]:
    hosts = [f"WS0{i}.corp.local" for i in range(8)]
    event_ids = [1, 3, 5, 11]
    return [
        {
            "UtcTime": f"{_iso(start + i * 7.0)}",
            "Computer": hosts[i % len(hosts)],
            "EventID": event_ids[i % len(event_ids)],
            "Image": f"C:\\Windows\\System32\\svc{i % 5}.exe",
            "ParentImage": "C:\\Windows\\explorer.exe",
            "__source_id": "blend-sysmon",
        }
        for i in range(n)
    ]


def _benign_osquery(n: int, *, start: float) -> list[dict[str, Any]]:
    hosts = [f"host-{i}" for i in range(8)]
    actions = ["added", "removed"]
    return [
        {
            "calendarTime": f"{_ctime(start + i * 9.0)}",
            "hostIdentifier": hosts[i % len(hosts)],
            "columns": {"action": actions[i % len(actions)], "path": f"/var/log/app{i}.log"},
            "name": "file_events",
            "__source_id": "blend-osquery",
        }
        for i in range(n)
    ]


def _benign_firewall(n: int, *, start: float) -> list[dict[str, Any]]:
    src = [f"192.168.1.{i}" for i in range(20)]
    dst_ports = [443, 80, 53, 22]
    return [
        {
            "_time": f"{_iso(start + i * 3.0)}",
            "src_ip": src[i % len(src)],
            "dst_ip": "10.10.10.10",
            "dst_port": dst_ports[i % len(dst_ports)],
            "disposition": "allowed" if i % 11 else "denied",
            "__source_id": "blend-firewall",
        }
        for i in range(n)
    ]


def _iso(epoch: float) -> str:
    import datetime as _dt

    return _dt.datetime.fromtimestamp(epoch, tz=_dt.timezone.utc).strftime(  # noqa: UP017
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _ctime(epoch: float) -> str:
    import datetime as _dt

    return _dt.datetime.fromtimestamp(epoch, tz=_dt.timezone.utc).strftime(  # noqa: UP017
        "%a %b %d %H:%M:%S %Y UTC"
    )


# One small labelled chain per schema -- the injected side. Sparse relative
# to the benign backdrop, matching the analyst's real ratio (Q4: family,
# technique, chain_id and step_idx are known for every one of these).
_CHAINS: tuple[dict[str, Any], ...] = (
    {
        "schema": "cloudtrail",
        "family": "credential_access",
        "technique": "T1078",
        "steps": ["AssumeRole", "GetSessionToken", "AttachUserPolicy", "PutBucketPolicy"],
        "entity_field": "userIdentity",
        "entity_value": {"arn": "arn:aws:iam::111122223333:user/attacker"},
        "verb_field": "eventName",
        "time_field": "eventTime",
        "time_fmt": _iso,
        "source_id": "blend-cloudtrail",
    },
    {
        "schema": "sysmon",
        "family": "persistence",
        "technique": "T1547",
        "steps": [1, 1, 13, 1],
        "entity_field": "Computer",
        "entity_value": "WS-ATTACKER.corp.local",
        "verb_field": "EventID",
        "time_field": "UtcTime",
        "time_fmt": _iso,
        "source_id": "blend-sysmon",
    },
    {
        "schema": "osquery",
        "family": "discovery",
        "technique": "T1082",
        "steps": ["added", "added", "removed"],
        "entity_field": "hostIdentifier",
        "entity_value": "host-attacker",
        "verb_field": None,  # lives in columns.action
        "time_field": "calendarTime",
        "time_fmt": _ctime,
        "source_id": "blend-osquery",
    },
)


def _chain_records(chain: dict[str, Any], *, start: float, chain_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for step_idx, step in enumerate(chain["steps"]):
        record: dict[str, Any] = {
            chain["time_field"]: chain["time_fmt"](start + step_idx * 20.0),
            chain["entity_field"]: chain["entity_value"],
            "__source_id": chain["source_id"],
        }
        if chain["schema"] == "osquery":
            record["columns"] = {"action": step, "path": f"/etc/shadow{step_idx}"}
            record["name"] = "file_events"
        else:
            record[chain["verb_field"]] = step
        records.append(record)
    return records


def compose_blend(
    *,
    benign_per_schema: int = 60,
    seed_start: float = _EPOCH_BASE,
) -> tuple[list[dict[str, Any]], dict[str, Provenance]]:
    """Compose one time-ordered, multi-schema, mostly-benign stream with a
    sparse labelled attack chain threaded through each schema. Returns the
    blind record list (what a grader sees) and a provenance map keyed by
    fingerprint (what only the scorer, joining after grading, ever sees) --
    Q3/Q4.
    """
    all_records: list[dict[str, Any]] = []
    provenance: dict[str, Provenance] = {}

    generators = (
        ("blend-cloudtrail", "cloudtrail", _benign_cloudtrail),
        ("blend-sysmon", "sysmon", _benign_sysmon),
        ("blend-osquery", "osquery", _benign_osquery),
        ("blend-firewall", "firewall_syslog", _benign_firewall),
    )
    for source_id, schema, generator in generators:
        records = generator(benign_per_schema, start=seed_start)
        for record in records:
            fp = _fingerprint(record)
            provenance[fp] = Provenance(
                fingerprint=fp, source_id=source_id, schema=schema, injected=False
            )
        all_records.extend(records)

    for chain in _CHAINS:
        chain_id = f"chain-{chain['family']}-{chain['technique']}"
        records = _chain_records(chain, start=seed_start + 5_000.0, chain_id=chain_id)
        for step_idx, record in enumerate(records):
            fp = _fingerprint(record)
            provenance[fp] = Provenance(
                fingerprint=fp,
                source_id=chain["source_id"],
                schema=chain["schema"],
                injected=True,
                family=chain["family"],
                technique=chain["technique"],
                chain_id=chain_id,
                step_idx=step_idx,
            )
        all_records.extend(records)

    return all_records, provenance


def schemas_present(records: list[dict[str, Any]], provenance: dict[str, Provenance]) -> set[str]:
    """The Q2 check surface: how many genuinely distinct schemas are
    present in a captured stream, derived from provenance, never guessed
    from the blind records."""
    fps = {_fingerprint(r) for r in records}
    return {p.schema for fp, p in provenance.items() if fp in fps}
