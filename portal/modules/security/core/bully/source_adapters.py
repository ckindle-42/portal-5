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


class SourceAdapter(Protocol):
    """Stable source plugin interface from the source-agnostic design."""

    def adapt(
        self, raw_events: Iterable[dict[str, Any] | str], source_meta: Mapping[str, Any]
    ) -> dict[str, Any]: ...


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

    def adapt(
        self, raw_events: Iterable[dict[str, Any] | str], source_meta: Mapping[str, Any]
    ) -> dict[str, Any]:
        return _base_view(list(raw_events), source_meta)


def _nested(event: Mapping[str, Any], *path: str) -> Any:
    value: Any = event
    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


@dataclass(frozen=True)
class IdentitySourceAdapter:
    """Translate auth/session/audit events into identity-shaped dimensions."""

    def adapt(
        self, raw_events: Iterable[dict[str, Any] | str], source_meta: Mapping[str, Any]
    ) -> dict[str, Any]:
        events = list(raw_events)
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
class FallbackSourceAdapter:
    """Recognize an unmapped source without inventing semantic dimensions."""

    def adapt(
        self, raw_events: Iterable[dict[str, Any] | str], source_meta: Mapping[str, Any]
    ) -> dict[str, Any]:
        events = list(raw_events)
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


def adapter_for(sourcetype: str) -> SourceAdapter:
    normalized = str(sourcetype or "")
    if normalized in _ENDPOINT_SOURCES:
        return EndpointSourceAdapter()
    if normalized.lower().startswith(_IDENTITY_SOURCE_PREFIXES):
        return IdentitySourceAdapter()
    return FallbackSourceAdapter()


def adapt(
    raw_events: Iterable[dict[str, Any] | str], source_meta: Mapping[str, Any]
) -> dict[str, Any]:
    """Dispatch one source class through its registered adapter."""
    return adapter_for(str(source_meta.get("sourcetype") or "")).adapt(raw_events, source_meta)
