"""Universal source connector contracts for the Bully data plane.

Connectors deliberately expose a small, source-agnostic read surface.  An
implementation may read from a staged ingest lane or query a system in place;
the investigation planner receives the same ``QueryResult`` either way.  The
native query is retained in the result so that a run can be replayed and
audited without pretending that the source had a common schema.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

ConnectorMode = str
INGEST_MODE = "ingest"
QUERY_IN_PLACE_MODE = "query_in_place"


@dataclass(frozen=True)
class ConnectorCredentials:
    credential_ref: str
    scopes: tuple[str, ...] = ()


class MissingCredentialsError(RuntimeError):
    """A connector cannot issue a query without its declared credential."""


def require_credentials(credentials: ConnectorCredentials | None) -> ConnectorCredentials:
    if credentials is None or not credentials.credential_ref.strip():
        raise MissingCredentialsError("source connector credentials are missing")
    return credentials


@dataclass(frozen=True)
class QueryIntent:
    """A source-independent request that a connector translates natively."""

    purpose: str
    seed: dict[str, Any] = field(default_factory=dict)
    start: float | None = None
    end: float | None = None
    entities: tuple[str, ...] = ()
    limit: int | None = None

    def __post_init__(self) -> None:
        if not self.purpose.strip():
            raise ValueError("QueryIntent.purpose is required")
        if self.limit is not None and self.limit <= 0:
            raise ValueError("QueryIntent.limit must be positive")


@dataclass(frozen=True)
class NativeQuery:
    source_id: str
    language: str
    expression: Any
    intent: QueryIntent


@dataclass(frozen=True)
class QueryResult:
    source_id: str
    mode: ConnectorMode
    native_query: NativeQuery
    records: tuple[Any, ...]
    started_at: float
    finished_at: float
    truncated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def elapsed_ms(self) -> float:
        return max(0.0, (self.finished_at - self.started_at) * 1000.0)


class SourceConnector(Protocol):
    """Contract shared by ingest and query-in-place sources.

    ``read`` is the only operation the investigation plane needs.  ``translate``
    is intentionally separate so native query construction remains owned by the
    connector, not by a dataset-specific planner branch.
    """

    source_id: str
    mode: ConnectorMode

    def translate(self, intent: QueryIntent) -> NativeQuery: ...

    def read(self, intent: QueryIntent) -> QueryResult: ...


@dataclass
class IterableIngestConnector:
    """Connector for staged records; it still satisfies the common read API."""

    source_id: str
    records: tuple[Any, ...]
    language: str = "records"
    mode: ConnectorMode = INGEST_MODE

    def __init__(self, source_id: str, records: Iterable[Any], *, language: str = "records"):
        self.source_id = source_id
        self.records = tuple(records)
        self.language = language
        self.mode = INGEST_MODE

    def translate(self, intent: QueryIntent) -> NativeQuery:
        return NativeQuery(self.source_id, self.language, {"intent": intent.purpose}, intent)

    def read(self, intent: QueryIntent) -> QueryResult:
        started = time.time()
        selected = list(self.records)
        if intent.limit is not None:
            selected = selected[: intent.limit]
        return QueryResult(
            self.source_id,
            self.mode,
            self.translate(intent),
            tuple(selected),
            started,
            time.time(),
            truncated=intent.limit is not None and len(self.records) > intent.limit,
        )


@dataclass
class QueryInPlaceConnector:
    """Small adapter for a live native query function.

    The callback receives the connector-owned native expression and returns
    records.  No records are copied into the Bully store by this class.
    """

    source_id: str
    query_fn: Any
    language: str = "native"
    mode: ConnectorMode = QUERY_IN_PLACE_MODE

    def translate(self, intent: QueryIntent) -> NativeQuery:
        language = self.language.lower()
        if language == "spl":
            expression = f'search purpose="{intent.purpose}"' + (
                f" earliest={intent.start} latest={intent.end}"
                if intent.start is not None and intent.end is not None
                else ""
            )
        elif language == "sql":
            expression = "SELECT * FROM source WHERE purpose = :purpose" + (
                " LIMIT :limit" if intent.limit else ""
            )
        elif language in {"kql", "api"}:
            expression = {
                "query": intent.purpose,
                "entities": list(intent.entities),
                "limit": intent.limit,
            }
        else:
            expression = {
                "purpose": intent.purpose,
                "seed": dict(intent.seed),
                "start": intent.start,
                "end": intent.end,
                "entities": list(intent.entities),
                "limit": intent.limit,
            }
        return NativeQuery(self.source_id, self.language, expression, intent)

    def read(self, intent: QueryIntent) -> QueryResult:
        started = time.time()
        native = self.translate(intent)
        result = self.query_fn(native.expression)
        if isinstance(result, Mapping) and "records" in result:
            records = tuple(result["records"])
            metadata = dict(result.get("metadata") or {})
        else:
            records = tuple(result)
            metadata = {}
        truncated = intent.limit is not None and len(records) >= intent.limit
        if intent.limit is not None:
            records = records[: intent.limit]
        return QueryResult(
            self.source_id,
            self.mode,
            native,
            records,
            started,
            time.time(),
            truncated=truncated,
            metadata=metadata,
        )


@dataclass
class CredentialedConnector:
    """Wrap a connector and fail closed when a credential is unavailable."""

    connector: SourceConnector
    credentials: ConnectorCredentials | None

    @property
    def source_id(self) -> str:
        return self.connector.source_id

    @property
    def mode(self) -> ConnectorMode:
        return self.connector.mode

    def translate(self, intent: QueryIntent) -> NativeQuery:
        require_credentials(self.credentials)
        return self.connector.translate(intent)

    def read(self, intent: QueryIntent) -> QueryResult:
        require_credentials(self.credentials)
        return self.connector.read(intent)


@dataclass(frozen=True)
class QueryAuditEntry:
    audit_id: str
    source_id: str
    mode: ConnectorMode
    native_query: NativeQuery
    result_count: int
    started_at: float
    finished_at: float
    sensitivity: str = "internal"

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "source_id": self.source_id,
            "mode": self.mode,
            "language": self.native_query.language,
            "expression": self.native_query.expression,
            "purpose": self.native_query.intent.purpose,
            "result_count": self.result_count,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "sensitivity": self.sensitivity,
        }


class QueryAuditLog:
    """Append-only in-process audit log used by records and replay."""

    def __init__(self) -> None:
        self._entries: list[QueryAuditEntry] = []

    def record(self, result: QueryResult, *, sensitivity: str = "internal") -> QueryAuditEntry:
        entry = QueryAuditEntry(
            audit_id=f"qa-{len(self._entries) + 1:06d}",
            source_id=result.source_id,
            mode=result.mode,
            native_query=result.native_query,
            result_count=len(result.records),
            started_at=result.started_at,
            finished_at=result.finished_at,
            sensitivity=sensitivity,
        )
        self._entries.append(entry)
        return entry

    def entries(self) -> tuple[QueryAuditEntry, ...]:
        return tuple(self._entries)

    def replay_plan(self) -> tuple[dict[str, Any], ...]:
        return tuple(entry.to_dict() for entry in self._entries)

    def export(self) -> list[dict[str, Any]]:
        restricted = [entry for entry in self._entries if entry.sensitivity == "restricted"]
        if restricted:
            raise PermissionError("restricted query audit entries cannot be exported")
        return [entry.to_dict() for entry in self._entries]
