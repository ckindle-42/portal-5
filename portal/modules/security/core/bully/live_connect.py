"""Live SA7 data-plane source registrations.

The registrations in this module bind existing Portal sources to the universal
connector contract.  They do not copy live query results into a second index;
the data plane only retains the bounded profile sample and the query audit.
"""

from __future__ import annotations

import os
from typing import Any

from .connectors import (
    ConnectorCredentials,
    CredentialedConnector,
    NativeQuery,
    QueryInPlaceConnector,
    QueryIntent,
    SourceConnector,
)
from .data_plane import DataPlane, SourceProfile


def _search_from_intent(intent: QueryIntent, *, index: str) -> dict[str, Any]:
    requested = str(intent.seed.get("spl") or "").strip()
    if not requested:
        requested = f"search index={index}"
    elif not requested.lower().startswith("search "):
        requested = f"search {requested}"
    if "index=" not in requested.lower():
        requested = f"search index={index} | {requested[7:].strip()}"
    limit = intent.limit or 100
    if "| head " not in requested.lower():
        requested = f"{requested} | head {limit}"
    return {
        "search": requested,
        "earliest": intent.start if intent.start is not None else "0",
        "latest": intent.end if intent.end is not None else "now",
    }


class SplunkQueryInPlaceConnector(QueryInPlaceConnector):
    """Native SPL connector backed by the existing :class:`SplunkBackend`."""

    def __init__(self, backend: Any, *, source_id: str, index: str) -> None:
        self.backend = backend
        self.index = index
        super().__init__(source_id, self._run_native, language="SPL")

    def translate(self, intent: QueryIntent) -> NativeQuery:
        return NativeQuery(
            self.source_id,
            "SPL",
            _search_from_intent(intent, index=self.index),
            intent,
        )

    def _run_native(self, expression: dict[str, Any]) -> dict[str, Any]:
        rows = self.backend._run_search(
            expression["search"],
            str(expression["earliest"]),
            str(expression["latest"]),
        )
        return {
            "records": rows,
            "metadata": {
                "native_language": "SPL",
                "index": self.index,
                "query_in_place": True,
            },
        }


def lab_splunk_connector(
    *,
    backend: Any | None = None,
    source_id: str = "lab-splunk",
    index: str | None = None,
) -> SourceConnector:
    """Build the credential-guarded connector for the lab Splunk index.

    The secret itself is never placed in a profile or audit entry.  A missing
    environment secret leaves the connector fail-closed through
    ``CredentialedConnector``.
    """
    if backend is None:
        from ..siem.spl_backend import SplunkBackend

        backend = SplunkBackend()
    resolved_index = index or getattr(
        backend, "index", os.environ.get("LAB_SPLUNK_INDEX", "portal5_lab")
    )
    connector = SplunkQueryInPlaceConnector(backend, source_id=source_id, index=resolved_index)
    secret = os.environ.get("LAB_SPLUNK_PASSWORD")
    credentials = ConnectorCredentials("env:LAB_SPLUNK_PASSWORD") if secret else None
    return CredentialedConnector(connector, credentials)


def connect_lab_splunk(
    plane: DataPlane,
    *,
    sample_limit: int = 100,
    backend: Any | None = None,
    source_id: str = "lab-splunk",
    index: str | None = None,
    count_records: bool = True,
) -> tuple[SourceProfile, dict[str, Any]]:
    """Probe and register lab Splunk as a real query-in-place source."""
    connector = lab_splunk_connector(
        backend=backend,
        source_id=source_id,
        index=index,
    )
    resolved_index = index or "portal5_lab"
    probe = connector.read(
        QueryIntent(
            "profile live indexed telemetry",
            seed={"spl": f"search index={resolved_index} sourcetype=aws:cloudtrail"},
            limit=sample_limit,
        )
    )
    count_result = None
    record_count = None
    if count_records:
        count_result = connector.read(
            QueryIntent(
                "count live indexed telemetry",
                seed={
                    "spl": f"search index={resolved_index} sourcetype=aws:cloudtrail | stats count"
                },
                limit=1,
            )
        )
        if count_result.records:
            first = count_result.records[0]
            fields = first.get("fields", {}) if isinstance(first, dict) else {}
            raw_count = (
                fields.get("count") or first.get("count") if isinstance(first, dict) else None
            )
            try:
                record_count = int(raw_count) if raw_count is not None else None
            except (TypeError, ValueError):
                record_count = None
    profile = plane.connect(
        source_id,
        connector,
        probe.records,
        source_meta={
            "record_class": "telemetry",
            "credential_ref": "env:LAB_SPLUNK_PASSWORD",
            "freshness_at": probe.finished_at,
            "record_count_override": record_count,
            "capabilities": {
                "queryable_in_place": True,
                "benign_present": True,
            },
        },
    )
    plane.audit.record(probe, sensitivity=profile.access.sensitivity)
    if count_result is not None:
        plane.audit.record(count_result, sensitivity=profile.access.sensitivity)
    return profile, {
        "source_id": source_id,
        "mode": connector.mode,
        "records": len(probe.records),
        "record_count": profile.record_count,
        "native_query": probe.native_query.expression,
        "metadata": probe.metadata,
    }
