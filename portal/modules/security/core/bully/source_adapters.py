"""Source-class adapters for the stable eight-dimension telemetry contract.

Adapters translate at the edge.  Signatures and grading remain unaware of raw
event formats.  Missing dimensions are omitted or empty and therefore lower
signature completeness; no adapter pads unavailable evidence.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

Record = dict[str, Any] | str

_EVENT_CODE = re.compile(r"(?:EventCode|EventID)\s*[=:]\s*([A-Za-z0-9_.-]+)")
_OBSERVED_FIELD = re.compile(r"(?:Name=['\"]|\b)([A-Za-z][A-Za-z0-9_.-]+)(?:['\"]|)\s*[=>]")
_ENDPOINT_SOURCES = frozenset(
    {
        "windows:security",
        "windows:sysmon",
        "windows:powershell",
        "windows:system",
        "linux:auditd",
        "web:access",
        "docker:daemon",
    }
)
_IDENTITY_SOURCE_PREFIXES = ("okta", "azure:monitor:aad", "o365:", "gws:reports:login")
_CLOUD_SOURCE_PREFIXES = ("aws:", "azure:", "gcp:", "cloudtrail")


class SourceAdapter(Protocol):
    """Stable record-shaped source plugin interface.

    ``raw_events`` remains accepted by the dispatcher for compatibility with
    the pre-SA7 event lane, but adapters consume records: events, documents,
    inventory rows, and tickets are all valid inputs.
    """

    def adapt(
        self, records: Iterable[Record], source_meta: Mapping[str, Any]
    ) -> dict[str, Any]: ...


def _records(records: Iterable[Record] | None, raw_events: Iterable[Record] | None) -> list[Record]:
    return list(records if records is not None else (raw_events or ()))


def _event_actions(event: dict[str, Any] | str, index: int) -> list[str]:
    if isinstance(event, dict):
        value = event.get("EventCode") or event.get("EventID") or event.get("type")
        fields = [str(key) for key in event if not str(key).startswith("@")]
        return [
            f"event-{index}:{value or 'record'}",
            *(f"field:{key}" for key in fields[:4]),
        ]
    match = _EVENT_CODE.search(str(event))
    fields = list(dict.fromkeys(_OBSERVED_FIELD.findall(str(event))))
    return [
        f"event-{index}:{match.group(1) if match else 'record'}",
        *(f"field:{key}" for key in fields[:4]),
    ]


def _base_view(
    events: list[dict[str, Any] | str], source_meta: Mapping[str, Any]
) -> dict[str, Any]:
    source = str(source_meta.get("sourcetype") or "unmapped")
    actions = [
        action for index, event in enumerate(events) for action in _event_actions(event, index)
    ]
    field_names = sorted(
        {
            str(key)
            for event in events
            if isinstance(event, dict)
            for key in event
            if not str(key).lower().startswith(("technique", "mitre", "parent"))
        }
    )
    techniques = sorted({str(value) for value in source_meta.get("techniques") or () if value})
    topology: dict[str, Any] = {"source_classes": [source]}
    # New classes share behavior families by ATT&CK truth so cross-class
    # retrieval can be measured.  The frozen four-class representation remains
    # unchanged and is still available for the V3 regression cohort.
    source_classes = source_meta.get("source_classes") or (source,)
    if (
        len(source_classes) == 1
        and source not in {"windows:security", "linux:auditd", "web:access", "docker:daemon"}
        and techniques
    ):
        topology["family"] = f"attack:{techniques[0]}"
    return {
        "action_sequence": actions,
        "event_graph": {"ordered": actions},
        "parameter_families": {"event_volume_band": min(len(events), 10)},
        "context_topology": topology,
        "artifacts": {"observed_fields": field_names[:24]},
        "attack_mappings": [{"technique_id": value} for value in techniques],
        "telemetry_shape": {
            "sourcetypes": [source],
            "event_count": len(events),
        },
        "detector_outcomes": {},
        "origin": str(source_meta.get("origin") or ""),
        "trust_tier": str(source_meta.get("trust_tier") or ""),
    }


@dataclass(frozen=True)
class EndpointSourceAdapter:
    """Behavior-preserving adapter for host, web, audit, and container logs."""

    def adapt(self, records: Iterable[Record], source_meta: Mapping[str, Any]) -> dict[str, Any]:
        return _base_view(list(records), source_meta)


def _nested(event: Mapping[str, Any], *path: str) -> Any:
    value: Any = event
    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _account_from_arn(arn: str) -> str | None:
    """Extract the AWS account id from an ARN (``arn:aws:iam::123:user/x``)."""
    parts = str(arn or "").split(":")
    return parts[4] if len(parts) > 4 and parts[4].isdigit() else None


@dataclass(frozen=True)
class IdentitySourceAdapter:
    """Translate auth/session/audit events into identity-shaped dimensions."""

    def adapt(self, records: Iterable[Record], source_meta: Mapping[str, Any]) -> dict[str, Any]:
        events = list(records)
        view = _base_view(events, source_meta)
        mappings = [event for event in events if isinstance(event, Mapping)]
        actions = [
            action
            for index, event in enumerate(mappings)
            if (
                operation := event.get("eventType")
                or event.get("Operation")
                or event.get("activityDisplayName")
                or event.get("action")
            )
            for action in (
                f"identity-{index}:{operation}",
                *(f"field:{key}" for key in list(event)[:4]),
            )
        ]
        if actions:
            view["action_sequence"] = actions
            view["event_graph"] = {"ordered": actions}
        users = sorted(
            {
                str(value)
                for event in mappings
                for value in (
                    _nested(event, "actor", "alternateId"),
                    _nested(event, "target", "alternateId"),
                    event.get("userPrincipalName"),
                    event.get("UserId"),
                )
                if value
            }
        )
        source_ips = sorted(
            {
                str(value)
                for event in mappings
                for value in (
                    _nested(event, "client", "ipAddress"),
                    event.get("clientIpAddress"),
                    event.get("ClientIP"),
                    event.get("ipAddress"),
                )
                if value
            }
        )
        topology = dict(view["context_topology"])
        if users:
            topology["users"] = users[:24]
        if source_ips:
            topology["source_ips"] = source_ips[:24]
        view["context_topology"] = topology
        results = sorted(
            {
                str(value)
                for event in mappings
                for value in (
                    _nested(event, "outcome", "result"),
                    event.get("ResultStatus"),
                    event.get("result"),
                )
                if value
            }
        )
        view["parameter_families"] = {
            "event_volume_band": min(len(events), 10),
            **({"outcomes": results} if results else {}),
        }
        view["artifacts"] = {
            **view["artifacts"],
            **({"sessions_or_users": users[:24]} if users else {}),
        }
        return view


@dataclass(frozen=True)
class CloudSourceAdapter:
    """Translate AWS CloudTrail records into cloud-shaped dimensions (A3).

    Cloud-trail semantics map into the stable eight-dimension contract without
    padding: ``action_sequence`` from eventName/eventSource (the API action
    the record observed), ``context_topology`` from account/region/principal
    (who did what where), and ``artifacts`` from resource ARNs. A dimension
    with no evidence stays absent (honest completeness), never invented.
    """

    def adapt(self, records: Iterable[Record], source_meta: Mapping[str, Any]) -> dict[str, Any]:
        events = list(records)
        view = _base_view(events, source_meta)
        mappings = [event for event in events if isinstance(event, Mapping)]
        actions = [
            action
            for index, event in enumerate(mappings)
            if (
                operation := event.get("eventName")
                or event.get("eventSource")
                or event.get("eventType")
            )
            for action in (
                f"cloud-{index}:{operation}",
                *(
                    [f"cloud-{index}:{event.get('eventSource')}"]
                    if event.get("eventSource") and event.get("eventName")
                    else []
                ),
                *(f"field:{key}" for key in list(event)[:4]),
            )
        ]
        if actions:
            view["action_sequence"] = actions
            view["event_graph"] = {"ordered": actions}
        topology = dict(view["context_topology"])
        accounts = sorted(
            {
                str(value)
                for event in mappings
                for value in (
                    event.get("recipientAccountId"),
                    _nested(event, "userIdentity", "accountId"),
                    _account_from_arn(str(_nested(event, "userIdentity", "arn") or "")),
                )
                if value
            }
        )
        regions = sorted({str(value) for event in mappings if (value := event.get("awsRegion"))})
        principals = sorted(
            {
                str(value)
                for event in mappings
                for value in (
                    _nested(event, "userIdentity", "arn"),
                    _nested(event, "userIdentity", "userName"),
                    _nested(event, "userIdentity", "principalId"),
                )
                if value
            }
        )
        if accounts:
            topology["accounts"] = accounts[:24]
        if regions:
            topology["regions"] = regions[:24]
        if principals:
            topology["principals"] = principals[:24]
        view["context_topology"] = topology
        arns = sorted(
            {
                str(item.get("ARN") or item.get("arn"))
                for event in mappings
                for item in (event.get("resources") or ())
                if isinstance(item, Mapping) and (item.get("ARN") or item.get("arn"))
            }
        )
        events_seen = {str(event.get("eventName")) for event in mappings if event.get("eventName")}
        view["artifacts"] = {
            **view["artifacts"],
            **({"resource_arns": arns[:24]} if arns else {}),
            **({"observed_actions": sorted(events_seen)[:24]} if events_seen else {}),
        }
        view["parameter_families"] = {
            "event_volume_band": min(len(events), 10),
            **({"regions": regions[:24]} if regions else {}),
        }
        return view


@dataclass(frozen=True)
class FallbackSourceAdapter:
    """Recognize an unmapped source without inventing semantic dimensions."""

    def adapt(self, records: Iterable[Record], source_meta: Mapping[str, Any]) -> dict[str, Any]:
        events = list(records)
        source = str(source_meta.get("sourcetype") or "unmapped")
        return {
            "artifacts": {"raw_event_count": len(events)},
            "attack_mappings": [
                {"technique_id": str(value)}
                for value in sorted(source_meta.get("techniques") or ())
            ],
            "telemetry_shape": {
                "sourcetypes": [source],
                "source_class": source,
                "event_count": len(events),
                "adapter_status": "unmapped",
            },
            "origin": str(source_meta.get("origin") or ""),
            "trust_tier": str(source_meta.get("trust_tier") or ""),
        }


@dataclass(frozen=True)
class DocumentSourceAdapter:
    """Adapt advisory/document records without manufacturing event dimensions."""

    def adapt(self, records: Iterable[Record], source_meta: Mapping[str, Any]) -> dict[str, Any]:
        documents = [record for record in records if isinstance(record, (str, Mapping))]
        artifacts = []
        mappings = []
        for record in documents:
            if isinstance(record, Mapping):
                mappings.append(record)
                artifacts.extend(
                    str(record[key])
                    for key in ("ioc", "artifact", "url", "title")
                    if record.get(key)
                )
            else:
                artifacts.append(str(record))
        result: dict[str, Any] = {
            "artifacts": {"document_count": len(documents), "values": artifacts[:24]},
            "context_topology": {
                "source_classes": [str(source_meta.get("source_id") or "document")]
            },
            "telemetry_shape": {"source_class": "document", "record_count": len(documents)},
        }
        if mappings:
            result["semantic_text"] = [
                str(item.get("text") or item.get("content") or item.get("body"))
                for item in mappings
                if item.get("text") or item.get("content") or item.get("body")
            ]
        return result


@dataclass(frozen=True)
class InventorySourceAdapter:
    """Adapt asset/identity inventory rows; absent activity stays absent."""

    def adapt(self, records: Iterable[Record], source_meta: Mapping[str, Any]) -> dict[str, Any]:
        rows = [record for record in records if isinstance(record, Mapping)]
        identities = sorted(
            {
                str(record[key])
                for record in rows
                for key in ("id", "asset_id", "account", "user", "owner")
                if record.get(key)
            }
        )
        result: dict[str, Any] = {
            "context_topology": {
                "source_classes": [str(source_meta.get("source_id") or "inventory")]
            },
            "artifacts": {"inventory_ids": identities[:24]},
            "telemetry_shape": {"source_class": "inventory", "record_count": len(rows)},
        }
        if rows:
            result["parameter_families"] = {
                "inventory_fields": sorted({str(key) for row in rows for key in row})[:24]
            }
        return result


@dataclass(frozen=True)
class CaseHistorySourceAdapter:
    """Adapt tickets and analyst decisions as first-class context."""

    def adapt(self, records: Iterable[Record], source_meta: Mapping[str, Any]) -> dict[str, Any]:
        rows = [record for record in records if isinstance(record, Mapping)]
        decisions = sorted(
            {
                str(record[key])
                for record in rows
                for key in ("decision", "outcome", "status")
                if record.get(key)
            }
        )
        return {
            "context_topology": {"source_classes": ["case_history"]},
            "artifacts": {
                "ticket_ids": [
                    str(row[key])
                    for row in rows
                    for key in ("ticket_id", "case_id")
                    if row.get(key)
                ][:24]
            },
            "parameter_families": {"analyst_decisions": decisions},
            "telemetry_shape": {"source_class": "case_history", "record_count": len(rows)},
        }


@dataclass(frozen=True)
class CoverageSourceAdapter:
    """Adapt detections/rules as queryable response-axis content."""

    def adapt(self, records: Iterable[Record], source_meta: Mapping[str, Any]) -> dict[str, Any]:
        rows = [record for record in records if isinstance(record, Mapping)]
        techniques = sorted(
            {
                str(record[key])
                for record in rows
                for key in ("technique", "technique_id", "rule_id")
                if record.get(key)
            }
        )
        return {
            "attack_mappings": [{"technique_id": value} for value in techniques],
            "context_topology": {"source_classes": ["coverage"]},
            "artifacts": {
                "rule_ids": [
                    str(row[key])
                    for row in rows
                    for key in ("rule_id", "detection_id")
                    if row.get(key)
                ][:24]
            },
            "telemetry_shape": {"source_class": "coverage", "record_count": len(rows)},
        }


def adapter_for(sourcetype: str, *, record_class: str | None = None) -> SourceAdapter:
    normalized = str(sourcetype or "").lower()
    explicit_class = str(record_class or "").lower()
    if explicit_class in {"advisory", "document"}:
        return DocumentSourceAdapter()
    if explicit_class in {"inventory", "asset", "identity_inventory"}:
        return InventorySourceAdapter()
    if explicit_class in {"case", "ticket", "case_history"}:
        return CaseHistorySourceAdapter()
    if explicit_class in {"coverage", "detection"}:
        return CoverageSourceAdapter()
    if normalized in _ENDPOINT_SOURCES:
        return EndpointSourceAdapter()
    if normalized.startswith(_IDENTITY_SOURCE_PREFIXES):
        return IdentitySourceAdapter()
    if normalized.startswith(_CLOUD_SOURCE_PREFIXES):
        return CloudSourceAdapter()
    return FallbackSourceAdapter()


def adapt(
    records: Iterable[Record] | None = None,
    source_meta: Mapping[str, Any] | None = None,
    *,
    raw_events: Iterable[Record] | None = None,
) -> dict[str, Any]:
    """Dispatch one record source through its registered adapter.

    The keyword-only ``raw_events`` alias lets existing event callers migrate
    without a flag day while the canonical contract is now ``records``.
    """
    meta = source_meta or {}
    return adapter_for(
        str(meta.get("sourcetype") or meta.get("source_id") or ""),
        record_class=meta.get("record_class") or meta.get("source_class"),
    ).adapt(_records(records, raw_events), meta)
