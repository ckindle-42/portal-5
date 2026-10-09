"""review.window -- uncapped, receipted windows over real or in-memory sources.

The product sees only extracted event fields. Search and count use separate Splunk exports;
the indexed-field count is the denominator for every fetched partition.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from ..siem.spl_backend import SplunkBackend
from .wall import assert_label_free

DEFAULT_PARTITION_SECONDS = 600
DEFAULT_TIMEOUT_SECONDS = 90


class WindowFetchError(RuntimeError):
    """A source query could not be completed or parsed as a complete window."""


@dataclass(frozen=True)
class SourceSpec:
    index: str
    sourcetype: str

    @property
    def source_id(self) -> str:
        return f"{self.index}:{self.sourcetype}"


@dataclass(frozen=True)
class PartitionReceipt:
    source_id: str
    start: float
    end: float
    expected: int
    fetched: int
    degraded: bool = False


@dataclass
class WindowBatch:
    records_by_source: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    receipts: list[PartitionReceipt] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)

    @property
    def expected(self) -> int:
        return sum(receipt.expected for receipt in self.receipts)

    @property
    def fetched(self) -> int:
        return sum(receipt.fetched for receipt in self.receipts)


class WindowSource(Protocol):
    """Read every event in a set of source/time partitions."""

    def fetch(self, sources: Sequence[SourceSpec], start: float, end: float) -> WindowBatch: ...


def normalize_splunk_record(source: SourceSpec, row: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one Splunk result exactly as the product window reader does."""
    raw_time = row.get("_time")
    raw_event = row.get("_raw")
    if raw_time is None or raw_event is None:
        raise WindowFetchError(f"Splunk event omitted _time or _raw for {source.source_id}")
    try:
        event_time = float(raw_time)
    except (TypeError, ValueError) as exc:
        raise WindowFetchError(f"invalid _time for {source.source_id}") from exc
    record = dict(row)
    record["_time"] = event_time
    record["_raw"] = str(raw_event)
    record["index"] = source.index
    record["sourcetype"] = source.sourcetype
    record["host"] = str(row.get("host") or "")
    record["source"] = str(row.get("source") or "")
    return record


def _epoch(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _iter_result_objects(chunks: Iterable[str]) -> Iterator[Mapping[str, Any]]:
    decoder = json.JSONDecoder()
    remainder = ""
    for chunk in chunks:
        remainder += chunk
        while remainder:
            offset = len(remainder) - len(remainder.lstrip())
            if offset == len(remainder):
                remainder = ""
                break
            try:
                obj, end = decoder.raw_decode(remainder, offset)
            except json.JSONDecodeError:
                break
            remainder = remainder[end:]
            if not isinstance(obj, Mapping):
                raise WindowFetchError("Splunk export returned a non-object JSON item")
            # The export endpoint can emit an interim aggregate result followed by the final
            # result. Counting both inflates entity-event scans and can trigger false degraded
            # receipts, so only final rows enter the product window.
            if obj.get("preview") is True:
                continue
            messages = obj.get("messages")
            if isinstance(messages, list):
                errors = [
                    message
                    for message in messages
                    if isinstance(message, Mapping)
                    and str(message.get("type", "")).upper() == "ERROR"
                ]
                if errors:
                    raise WindowFetchError(f"Splunk export returned errors: {errors[:3]}")
            result = obj.get("result")
            if result is None:
                continue
            if not isinstance(result, Mapping):
                raise WindowFetchError("Splunk export result is not a JSON object")
            yield result
    if remainder.strip():
        raise WindowFetchError("Splunk export ended with incomplete or invalid JSON")


def _result_objects(chunks: Iterable[str]) -> list[Mapping[str, Any]]:
    return list(_iter_result_objects(chunks))


class SplunkWindowSource:
    """Read-only Splunk REST export source with an indexed-field count per partition."""

    def __init__(
        self,
        *,
        url: str | None = None,
        user: str | None = None,
        password: str | None = None,
        partition_seconds: int = DEFAULT_PARTITION_SECONDS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        backend = SplunkBackend()
        self.url = (url or backend.url).rstrip("/")
        self.user = user if user is not None else backend.user
        self.password = (
            password if password is not None else os.environ.get("LAB_SPLUNK_PASSWORD", backend.pw)
        )
        self.partition_seconds = partition_seconds
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        if partition_seconds <= 0:
            raise ValueError("partition_seconds must be positive")

    def iter_post(self, search: str, start: float, end: float) -> Iterator[Mapping[str, Any]]:
        """Stream final rows from a read-only export without materializing a full corpus slice."""
        try:
            with (
                httpx.Client(
                    verify=False,
                    timeout=self.timeout_seconds,
                    transport=self.transport,
                ) as client,
                client.stream(
                    "POST",
                    f"{self.url}/services/search/jobs/export",
                    auth=(self.user, self.password),
                    data={
                        "search": search,
                        "exec_mode": "oneshot",
                        "earliest_time": _epoch(start),
                        "latest_time": _epoch(end),
                        "output_mode": "json",
                        "time_format": "%s",
                    },
                ) as response,
            ):
                response.raise_for_status()
                yield from _iter_result_objects(response.iter_text())
        except httpx.HTTPError as exc:
            raise WindowFetchError(f"Splunk export failed: {exc}") from exc

    def _post(self, search: str, start: float, end: float) -> list[Mapping[str, Any]]:
        return list(self.iter_post(search, start, end))

    def _count(self, source: SourceSpec, start: float, end: float) -> int:
        search = (
            "| tstats count where "
            f"index={_quote(source.index)} sourcetype={_quote(source.sourcetype)} "
            f"earliest={_epoch(start)} latest={_epoch(end)}"
        )
        rows = self._post(search, start, end)
        if len(rows) != 1 or "count" not in rows[0]:
            raise WindowFetchError(f"tstats count returned {len(rows)} rows for {source.source_id}")
        try:
            count = int(str(rows[0]["count"]))
        except (TypeError, ValueError) as exc:
            raise WindowFetchError(f"invalid tstats count for {source.source_id}") from exc
        if count < 0:
            raise WindowFetchError(f"negative tstats count for {source.source_id}")
        return count

    def _events(self, source: SourceSpec, start: float, end: float) -> list[dict[str, Any]]:
        search = f"search index={_quote(source.index)} sourcetype={_quote(source.sourcetype)}"
        rows = self._post(search, start, end)
        records: list[dict[str, Any]] = []
        for row in rows:
            record = normalize_splunk_record(source, row)
            assert_label_free(record, where=f"splunk:{source.source_id}")
            records.append(record)
        return records

    def fetch(self, sources: Sequence[SourceSpec], start: float, end: float) -> WindowBatch:
        if end <= start:
            raise ValueError("end must be greater than start")
        batch = WindowBatch()
        for source in sources:
            cursor = start
            records = batch.records_by_source.setdefault(source.source_id, [])
            while cursor < end:
                boundary = min(cursor + self.partition_seconds, end)
                expected = self._count(source, cursor, boundary)
                partition_rows = self._events(source, cursor, boundary)
                records.extend(partition_rows)
                mismatch = expected != len(partition_rows)
                receipt = PartitionReceipt(
                    source.source_id,
                    cursor,
                    boundary,
                    expected,
                    len(partition_rows),
                    mismatch,
                )
                batch.receipts.append(receipt)
                if mismatch:
                    batch.degraded.append(
                        f"{source.source_id} [{_epoch(cursor)}, {_epoch(boundary)}): "
                        f"expected {expected}, fetched {len(partition_rows)}"
                    )
                cursor = boundary
        return batch


class InMemoryWindowSource:
    """Deterministic source used by adapter and service tests."""

    def __init__(
        self,
        records_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
        *,
        expected_overrides: Mapping[tuple[str, float, float], int] | None = None,
        partition_seconds: int = DEFAULT_PARTITION_SECONDS,
    ) -> None:
        if partition_seconds <= 0:
            raise ValueError("partition_seconds must be positive")
        self.records_by_source = records_by_source
        self.expected_overrides = expected_overrides or {}
        self.partition_seconds = partition_seconds

    def fetch(self, sources: Sequence[SourceSpec], start: float, end: float) -> WindowBatch:
        if end <= start:
            raise ValueError("end must be greater than start")
        batch = WindowBatch()
        for source in sources:
            source_records = self.records_by_source.get(source.source_id, ())
            selected = batch.records_by_source.setdefault(source.source_id, [])
            cursor = start
            while cursor < end:
                boundary = min(cursor + self.partition_seconds, end)
                partition = []
                for item in source_records:
                    record = dict(item)
                    try:
                        event_time = float(record["_time"])
                    except (KeyError, TypeError, ValueError) as exc:
                        raise WindowFetchError(
                            f"in-memory event lacks numeric _time for {source.source_id}"
                        ) from exc
                    if cursor <= event_time < boundary:
                        assert_label_free(record, where=f"memory:{source.source_id}")
                        partition.append(record)
                expected = self.expected_overrides.get(
                    (source.source_id, cursor, boundary), len(partition)
                )
                selected.extend(partition)
                mismatch = expected != len(partition)
                batch.receipts.append(
                    PartitionReceipt(
                        source.source_id,
                        cursor,
                        boundary,
                        expected,
                        len(partition),
                        mismatch,
                    )
                )
                if mismatch:
                    batch.degraded.append(
                        f"{source.source_id} [{_epoch(cursor)}, {_epoch(boundary)}): "
                        f"expected {expected}, fetched {len(partition)}"
                    )
                cursor = boundary
        return batch
