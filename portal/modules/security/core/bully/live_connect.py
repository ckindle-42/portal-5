"""Live SA7 data-plane source registrations.

The registrations in this module bind existing Portal sources to the universal
connector contract.  They do not copy live query results into a second index;
the data plane only retains the bounded profile sample and the query audit.
"""

from __future__ import annotations

import gzip
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .connectors import (
    ConnectorCredentials,
    CredentialedConnector,
    IterableIngestConnector,
    NativeQuery,
    QueryInPlaceConnector,
    QueryIntent,
    SourceConnector,
)
from .data_plane import DataPlane, SourceProfile


def _search_from_intent(intent: QueryIntent, *, index: str) -> dict[str, Any]:
    """Translate a `QueryIntent` to native SPL.

    `intent.entities` is the signal that this is an anchor-pivot investigation
    query (`investigation_pivot.PivotQuery.to_intent()` always sets it): those
    queries are held to the I1/I2/I6 discipline below -- bounded, entity-
    scoped, never `sourcetype=`-filtered, and `earliest=0` is refused outright
    rather than defaulted. Non-entity intents (census/profile probes that
    predate the investigation engine) keep the prior "0"/"now" default so
    this change does not silently re-scope unrelated call sites; the point of
    this task is the discovery/capture path, not every live-plane probe.
    """
    requested = str(intent.seed.get("spl") or "").strip()
    # A leading-pipe SPL string (`| eventcount ...`, `| tstats ...`) is
    # already a complete generating/report command -- prepending "search "
    # turns it into an empty search piped into that command, which Splunk
    # silently answers with zero rows rather than an error (verified live).
    # `spl_backend.py`'s own dispatch already treats a leading "|" as
    # complete for the same reason; this mirrors that check. It is also the
    # one legitimate unbounded use (index sizing via `eventcount`/`tstats`):
    # a generating/report command reads Splunk's bucket metadata, not events,
    # so time bounds do not apply to it and it is exempt from the raise below.
    is_pipe_command = requested.startswith("|")

    if intent.entities and not is_pipe_command:
        if intent.start is None or intent.end is None:
            raise ValueError(
                "corpus query has no explicit earliest/latest window -- "
                f"earliest=0 is forbidden on a corpus index: {intent!r}"
            )
        if not requested:
            requested = f"search index={index}"
        elif not requested.lower().startswith("search "):
            requested = f"search {requested}"
        if "index=" not in requested.lower():
            requested = requested.replace("search ", f"search index={index} ", 1)
        # Entity-scoped: the whole point of a pivot query. No `sourcetype=`
        # filter is ever added here (I6) -- a capture that filters cannot
        # discover a source it was not told to look at. No `| head` either
        # (I1): the time/entity window bounds the result, not truncation.
        terms = " OR ".join(f'"{e}"' for e in intent.entities)
        return {
            "search": f"{requested} ({terms})",
            "earliest": intent.start,
            "latest": intent.end,
        }

    if not requested:
        requested = f"search index={index}"
    elif not requested.lower().startswith("search ") and not is_pipe_command:
        requested = f"search {requested}"
    if not is_pipe_command and "index=" not in requested.lower():
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


def _records_from_path(path: Path) -> Iterator[Any]:
    suffixes = path.suffixes
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.strip():
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        yield line.rstrip("\n")
        return
    if path.suffix == ".gz" or ".json.gz" in "".join(suffixes):
        opener = gzip.open
    elif path.suffix == ".json":
        opener = Path.open
    else:
        return
    with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
        try:
            payload = json.load(handle)
        except json.JSONDecodeError:
            return
    if isinstance(payload, dict):
        payload = payload.get("Records", [payload])
    if isinstance(payload, list):
        yield from (record for record in payload if isinstance(record, (dict, str)))


def iter_staged_records(root: Path) -> Iterator[Any]:
    """Read standard JSON/JSONL staged records without retaining the corpus."""
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        yield from _records_from_path(path)


def count_staged_records(root: Path) -> int:
    """Count records from a staged root without retaining them."""
    return sum(1 for _ in iter_staged_records(root))


def register_staged_source(
    plane: DataPlane,
    *,
    source_id: str,
    root: Path,
    sample_limit: int = 128,
    record_count: int | None = None,
    source_meta: dict[str, Any] | None = None,
) -> SourceProfile:
    """Register a staged root through the ingest fulfilment."""

    def factory() -> Iterator[Any]:
        return iter_staged_records(root)

    connector = IterableIngestConnector(
        source_id,
        factory,
        language="JSON-records",
        record_count=record_count,
    )
    sample = connector.read(QueryIntent("profile staged records", limit=sample_limit))
    meta = {
        "record_class": "telemetry",
        "freshness_at": sample.finished_at,
        "record_count_override": record_count,
        **(source_meta or {}),
    }
    return plane.connect(source_id, connector, sample.records, source_meta=meta)


def register_staged_corpora(
    plane: DataPlane,
    *,
    corpora_root: Path,
    attack_data_root: Path,
    sample_limit: int = 128,
    counts: dict[str, int] | None = None,
) -> tuple[SourceProfile, ...]:
    """Register the staged attack-data and acquired cloud corpus roots."""
    specs = (
        ("attack_data", attack_data_root, {"label_basis": True}),
        (
            "flaws_cloud_cloudtrail",
            corpora_root / "flaws_cloud_cloudtrail" / "records" / "flaws_cloudtrail_logs",
            {"label_basis": True},
        ),
        (
            "invictus_ir_aws_dataset",
            corpora_root / "invictus_ir_aws_dataset" / "repo" / "CloudTrail",
            {"label_basis": True},
        ),
    )
    profiles = []
    resolved_counts = dict(counts or {})
    for source_id, root, meta in specs:
        if not root.is_dir():
            continue
        if source_id not in resolved_counts:
            resolved_counts[source_id] = count_staged_records(root)
        profiles.append(
            register_staged_source(
                plane,
                source_id=source_id,
                root=root,
                sample_limit=sample_limit,
                record_count=resolved_counts[source_id],
                source_meta=meta,
            )
        )
    return tuple(profiles)
