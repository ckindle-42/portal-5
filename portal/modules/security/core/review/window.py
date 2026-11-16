"""review.window -- uncapped, receipted windows over real or in-memory sources.

The product sees only extracted event fields. Search and count use separate Splunk exports;
the bounded raw-search count is the denominator for every fetched partition.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from ..siem.spl_backend import SplunkBackend
from .wall import assert_label_free

DEFAULT_PARTITION_SECONDS = 600
DEFAULT_TIMEOUT_SECONDS = 90
CANCEL_GRACE_SECONDS = 5.0


class WindowFetchError(RuntimeError):
    """A source query could not be completed or parsed as a complete window."""

    def __init__(
        self,
        message: str,
        *,
        sid: str | None = None,
        censored: bool = False,
        coverage: Mapping[str, Any] | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.sid = sid
        self.censored = censored
        self.coverage = dict(coverage or {})
        self.reason = reason


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


class JobCancel:
    """Cancel handle for one bounded read; the transport binds its own job cancellation.

    Binding happens once the job has a sid; a cancel requested before the bind fires as
    soon as it is bound, and a cancel requested after the read finished does nothing.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancel: Callable[[], None] | None = None
        self._closed = False

    def bind(self, cancel: Callable[[], None]) -> None:
        with self._lock:
            late = self._closed
            if not late:
                self._cancel = cancel
        if late:
            cancel()

    def release(self) -> None:
        with self._lock:
            self._closed = True
            self._cancel = None

    def cancel(self) -> None:
        with self._lock:
            self._closed = True
            cancel, self._cancel = self._cancel, None
        if cancel is not None:
            cancel()


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


_RESULT_PAGE = 5000  # transport page size; not a completeness cap
_STOPPED_STATES = frozenset(
    {
        "FAILED",
        "CANCELED",
        "USER_CANCEL",
        "INTERNAL_CANCEL",
        "BAD_INPUT_CANCEL",
        "QUIT",
        "FINALIZING",
    }
)


def _splunk_flag(value: Any) -> bool:
    """Splunk JSON booleans arrive as bools or as 0/1 strings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return False


def _done_progress(content: Mapping[str, Any]) -> float | None:
    value = content.get("doneProgress")
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _message_text(content: Mapping[str, Any]) -> str:
    messages = content.get("messages")
    if not isinstance(messages, list):
        return ""
    parts = [str(message.get("text", "")) for message in messages if isinstance(message, Mapping)]
    return " ".join(parts).lower()


_COMPLETENESS_MARKERS = (
    "subsearch",
    "truncat",
    "maxout",
    "maxtime",
    "partial result",
    "finaliz",
    "auto-canceled",
)


def _incomplete_message(content: Mapping[str, Any]) -> str | None:
    """The first WARN/ERROR message claiming incomplete subsearch/truncation work, if any.
    Benign metadata messages (info level, other topics) are not completeness failures."""
    messages = content.get("messages")
    if not isinstance(messages, list):
        return None
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        level = str(message.get("type", "")).upper()
        text = str(message.get("text", ""))
        if level in {"WARN", "ERROR"} and any(
            marker in text.lower() for marker in _COMPLETENESS_MARKERS
        ):
            return text
    return None


def _splunk_epoch(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _normalized_result(sid: str, result: Mapping[str, Any]) -> dict[str, Any]:
    """Decode one results-API row: /jobs/{sid}/results emits ISO8601 `_time` (the old export
    emits numeric epoch), so event time is normalized to epoch seconds here for every bounded
    read. Multivalue fields flatten to their first value, matching the consumers' scalar use."""
    row = {
        key: (value[0] if isinstance(value, list) and value else value)
        for key, value in result.items()
    }
    if "_time" in row:
        epoch = _splunk_epoch(row["_time"])
        if epoch is None:
            raise WindowFetchError(
                f"Splunk search job {sid} returned an unparseable _time {row['_time']!r}",
                sid=sid,
            )
        row["_time"] = epoch
    return row


def _cursor_behind(content: Mapping[str, Any]) -> bool:
    """doneProgress is (latest-cursor)/(latest-earliest); a lagging cursor is unfinished."""
    if _done_progress(content) is not None:
        return False
    cursor = _splunk_epoch(content.get("cursorTime"))
    latest = _splunk_epoch(content.get("latestTime"))
    if cursor is None or latest is None:
        return False
    return latest - cursor > 1


def _job_coverage(sid: str, content: Mapping[str, Any], *, censored: bool) -> dict[str, Any]:
    return {
        "sid": sid,
        "isDone": _splunk_flag(content.get("isDone")),
        "isFinalized": _splunk_flag(content.get("isFinalized")),
        "dispatchState": str(content.get("dispatchState", "")).upper(),
        "doneProgress": _done_progress(content),
        "censored": censored,
    }


def _coverage_problem(sid: str, content: Mapping[str, Any]) -> tuple[str, bool] | None:
    """None means the job finished the requested window. Otherwise (message, censored)."""
    state = str(content.get("dispatchState", "")).upper()
    progress = _done_progress(content)
    finalized = _splunk_flag(content.get("isFinalized")) or "finaliz" in _message_text(content)
    incomplete = (progress is not None and progress < 0.999) or _cursor_behind(content)
    if _splunk_flag(content.get("isFailed")) or state == "FAILED":
        detail = _message_text(content)
        suffix = f": {detail}" if detail else ""
        return (f"Splunk search job {sid} failed{suffix}", False)
    if finalized or incomplete or state == "FINALIZING":
        why = "finalized early" if finalized or state == "FINALIZING" else "incomplete coverage"
        return (f"Splunk search job {sid} {why}", True)
    if state in _STOPPED_STATES or state not in {"", "DONE"}:
        return (f"Splunk search job {sid} ended in {state or 'unknown'} before completion", True)
    warning = _incomplete_message(content)
    if warning:
        # a DONE job whose subsearches timed out or truncated is censored, never exact
        return (f"Splunk search job {sid} reported incomplete work: {warning}", True)
    if state == "DONE" or _splunk_flag(content.get("isDone")):
        return None
    return (f"Splunk search job {sid} failed or was finalized early", True)


def _ensure_job_succeeded(sid: str, content: Mapping[str, Any]) -> None:
    problem = _coverage_problem(sid, content)
    if problem is None:
        return
    message, censored = problem
    raise WindowFetchError(
        message,
        sid=sid,
        censored=censored,
        coverage=_job_coverage(sid, content, censored=censored),
        reason="censored" if censored else None,
    )


class SplunkWindowSource:
    """Read-only Splunk REST export source with an independent raw-search count per partition."""

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

    def _cancel_job(self, client: httpx.Client, sid: str) -> None:
        try:
            response = client.post(
                f"{self.url}/services/search/jobs/{sid}/control",
                auth=(self.user, self.password),
                data={"action": "cancel"},
            )
            response.raise_for_status()
            deadline = time.monotonic() + CANCEL_GRACE_SECONDS
            while time.monotonic() < deadline:
                try:
                    state_response = client.get(
                        f"{self.url}/services/search/jobs/{sid}",
                        params={"output_mode": "json"},
                        auth=(self.user, self.password),
                        timeout=1.0,
                    )
                    if state_response.status_code == 404:
                        return
                    state_response.raise_for_status()
                    entry = state_response.json().get("entry", [])
                    content = entry[0].get("content", {}) if entry else {}
                    if content.get("isDone") or str(content.get("dispatchState", "")).upper() in {
                        "FAILED",
                        "CANCELED",
                        "USER_CANCEL",
                        "INTERNAL_CANCEL",
                        "BAD_INPUT_CANCEL",
                        "QUIT",
                    }:
                        return
                except ValueError:
                    pass
                time.sleep(0.2)
            raise WindowFetchError(f"Splunk search job {sid} did not stop after cancel", sid=sid)
        except httpx.HTTPError as exc:
            raise WindowFetchError(
                f"Splunk search cancellation failed for {sid}: {exc}", sid=sid
            ) from exc

    def _cancel_preserving(self, sid: str, timeout_seconds: float) -> None:
        """Cancel a job that did not finish exactly, without hiding the original error."""
        pending = sys.exc_info()[1]
        if pending is not None and not isinstance(pending, Exception):
            pending = None  # generator close/timeouts of the interpreter are not hunt errors
        try:
            with httpx.Client(
                verify=False,
                timeout=min(5.0, max(0.1, timeout_seconds)),
                transport=self.transport,
            ) as cancel_client:
                self._cancel_job(cancel_client, sid)
        except Exception as cancel_exc:
            coverage = dict(getattr(pending, "coverage", {}) or {})
            coverage["sid"] = sid
            coverage["cancellation_error"] = f"{type(cancel_exc).__name__}: {cancel_exc}"
            message = (
                f"{pending}; cancellation of {sid} failed: {cancel_exc}"
                if pending is not None
                else f"Splunk search cancellation failed for {sid}: {cancel_exc}"
            )
            cause = pending if isinstance(pending, BaseException) else cancel_exc
            raise WindowFetchError(
                message,
                sid=sid,
                censored=bool(getattr(pending, "censored", False)),
                coverage=coverage,
                reason=getattr(pending, "reason", None),
            ) from cause

    def iter_post_bounded(
        self,
        search: str,
        start: float,
        end: float,
        *,
        timeout_seconds: float,
        max_results: int | None,
        cancel: JobCancel | None = None,
    ) -> Iterator[Mapping[str, Any]]:
        """Run a hunt search as a cancellable job with a server and client deadline.

        ``max_results`` caps an evidence read. ``None`` pages until the job's own
        result set ends; a finalized job is still censored, not an exact count.
        ``cancel`` is bound to the run's own job so a caller's hard stop can stop it.
        """
        if timeout_seconds <= 0 or (max_results is not None and max_results <= 0):
            raise ValueError("bounded search limits must be positive")
        deadline = time.monotonic() + timeout_seconds
        sid: str | None = None
        terminal = False
        try:
            with httpx.Client(
                verify=False,
                timeout=httpx.Timeout(timeout_seconds, connect=min(5.0, timeout_seconds)),
                transport=self.transport,
            ) as client:
                try:
                    sid = self._submit_bounded(client, search, start, end, deadline)
                    if cancel is not None:
                        job_sid = sid
                        cancel.bind(lambda: self._cancel_job(client, job_sid))
                    self._wait_bounded(client, sid, deadline, timeout_seconds)
                    terminal = True
                    yield from self._bounded_results(client, sid, deadline, max_results)
                except httpx.HTTPError as exc:
                    raise WindowFetchError(f"Splunk bounded search failed: {exc}", sid=sid) from exc
        finally:
            if cancel is not None:
                cancel.release()
            if sid and not terminal:
                self._cancel_preserving(sid, timeout_seconds)

    def _submit_bounded(
        self, client: httpx.Client, search: str, start: float, end: float, deadline: float
    ) -> str:
        response = client.post(
            f"{self.url}/services/search/jobs",
            auth=(self.user, self.password),
            data={
                "search": search,
                "earliest_time": _epoch(start),
                "latest_time": _epoch(end),
                "output_mode": "json",
                "max_time": max(1, int(deadline - time.monotonic())),
            },
            timeout=max(0.1, deadline - time.monotonic()),
        )
        response.raise_for_status()
        sid = str(response.json().get("sid") or "")
        if not sid:
            raise WindowFetchError("Splunk search job response omitted sid")
        return sid

    def _wait_bounded(
        self, client: httpx.Client, sid: str, deadline: float, timeout_seconds: float
    ) -> None:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WindowFetchError(
                    f"Splunk search job {sid} exceeded {timeout_seconds}s",
                    sid=sid,
                    censored=True,
                    coverage={"sid": sid, "censored": True, "doneProgress": None},
                    reason="query_bound",
                )
            response = client.get(
                f"{self.url}/services/search/jobs/{sid}",
                params={"output_mode": "json"},
                auth=(self.user, self.password),
                timeout=max(0.1, min(5.0, remaining)),
            )
            response.raise_for_status()
            entry = response.json().get("entry", [])
            content = entry[0].get("content", {}) if entry else {}
            dispatch_state = str(content.get("dispatchState", "")).upper()
            if (
                _splunk_flag(content.get("isDone"))
                or _splunk_flag(content.get("isFailed"))
                or dispatch_state in _STOPPED_STATES
            ):
                _ensure_job_succeeded(sid, content)
                return
            time.sleep(min(0.2, max(0.0, remaining)))

    def _bounded_results(
        self, client: httpx.Client, sid: str, deadline: float, max_results: int | None
    ) -> Iterator[Mapping[str, Any]]:
        if max_results is None:
            yield from self._paged_results(client, sid, deadline)
            return
        rows, cut = self._one_result_page(client, sid, deadline, max_results + 1, 0, max_results)
        yield from rows
        if cut:
            # The rows read before the cap are still usable evidence; the query is censored.
            raise WindowFetchError(
                f"Splunk search job {sid} result budget exceeded ({max_results + 1} > {max_results})",
                sid=sid,
                censored=True,
                coverage={
                    "sid": sid,
                    "censored": True,
                    "returned": max_results + 1,
                    "cap": max_results,
                },
                reason="row_cap",
            )

    def _one_result_page(
        self,
        client: httpx.Client,
        sid: str,
        deadline: float,
        count: int,
        offset: int,
        cap: int | None,
    ) -> tuple[list[Mapping[str, Any]], bool]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise WindowFetchError(
                f"Splunk search job {sid} exceeded its deadline while reading results",
                sid=sid,
                censored=True,
                coverage={"sid": sid, "censored": True},
                reason="query_bound",
            )
        response = client.get(
            f"{self.url}/services/search/jobs/{sid}/results",
            params={"output_mode": "json", "count": count, "offset": offset},
            auth=(self.user, self.password),
            timeout=max(0.1, remaining),
        )
        response.raise_for_status()
        payload = response.json()
        warning = _incomplete_message(payload)
        if warning:
            raise WindowFetchError(
                f"Splunk search job {sid} results reported incomplete work: {warning}",
                sid=sid,
                censored=True,
                coverage={"sid": sid, "censored": True, "message": warning},
                reason="censored",
            )
        results = payload.get("results")
        if not isinstance(results, list):
            raise WindowFetchError(f"Splunk search job {sid} returned no results list", sid=sid)
        cut = cap is not None and len(results) > cap
        if cut and cap is not None:
            results = results[:cap]
        rows: list[Mapping[str, Any]] = []
        for result in results:
            if not isinstance(result, Mapping):
                raise WindowFetchError(f"Splunk search job {sid} returned an invalid row", sid=sid)
            rows.append(_normalized_result(sid, result))
        return rows, cut

    def _paged_results(
        self, client: httpx.Client, sid: str, deadline: float
    ) -> Iterator[Mapping[str, Any]]:
        offset = 0
        while True:
            page, _cut = self._one_result_page(client, sid, deadline, _RESULT_PAGE, offset, None)
            yield from page
            if len(page) < _RESULT_PAGE:
                return
            offset += len(page)

    def _post(self, search: str, start: float, end: float) -> list[Mapping[str, Any]]:
        return list(self.iter_post(search, start, end))

    def _base_search(self, source: SourceSpec) -> str:
        return f"search index={_quote(source.index)} sourcetype={_quote(source.sourcetype)}"

    def _count(self, base_search: str, source: SourceSpec, start: float, end: float) -> int:
        search = f"{base_search} | stats count"
        rows = self._post(search, start, end)
        if len(rows) != 1 or "count" not in rows[0]:
            raise WindowFetchError(
                f"raw-search count returned {len(rows)} rows for {source.source_id}"
            )
        try:
            count = int(str(rows[0]["count"]))
        except (TypeError, ValueError) as exc:
            raise WindowFetchError(f"invalid raw-search count for {source.source_id}") from exc
        if count < 0:
            raise WindowFetchError(f"negative raw-search count for {source.source_id}")
        return count

    def _events(
        self, base_search: str, source: SourceSpec, start: float, end: float
    ) -> list[dict[str, Any]]:
        rows = self._post(base_search, start, end)
        records: list[dict[str, Any]] = []
        for row in rows:
            record = normalize_splunk_record(source, row)
            assert_label_free(record, where=f"splunk:{source.source_id}")
            records.append(record)
        return records

    def health(self) -> dict[str, Any]:
        """Probe Splunk's read-only index catalog and return aggregate index counts."""
        try:
            with httpx.Client(
                verify=False,
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = client.get(
                    f"{self.url}/services/data/indexes",
                    auth=(self.user, self.password),
                    params={"output_mode": "json", "count": 0},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise WindowFetchError(f"Splunk index health probe failed: {exc}") from exc
        if not isinstance(payload, Mapping) or not isinstance(payload.get("entry"), list):
            raise WindowFetchError("Splunk index catalog response has no entry list")
        counts: dict[str, int | None] = {}
        for entry in payload["entry"]:
            if not isinstance(entry, Mapping):
                continue
            name = str(entry.get("name") or "")
            content = entry.get("content")
            if not name or not isinstance(content, Mapping):
                continue
            raw_count = content.get("totalEventCount")
            try:
                count = int(raw_count) if raw_count is not None else None
            except (TypeError, ValueError):
                count = None
            counts[name] = count
        return {"reachable": True, "index_count": len(counts), "indexes": counts}

    def _fetch_source(
        self, base_search: str, source: SourceSpec, start: float, end: float
    ) -> tuple[list[dict[str, Any]], list[PartitionReceipt], list[str]]:
        records: list[dict[str, Any]] = []
        receipts: list[PartitionReceipt] = []
        degraded: list[str] = []
        cursor = start
        while cursor < end:
            boundary = min(cursor + self.partition_seconds, end)
            expected = self._count(base_search, source, cursor, boundary)
            partition_rows = self._events(base_search, source, cursor, boundary)
            records.extend(partition_rows)
            mismatch = expected != len(partition_rows)
            receipts.append(
                PartitionReceipt(
                    source.source_id,
                    cursor,
                    boundary,
                    expected,
                    len(partition_rows),
                    mismatch,
                )
            )
            if mismatch:
                degraded.append(
                    f"{source.source_id} [{_epoch(cursor)}, {_epoch(boundary)}): "
                    f"expected {expected}, fetched {len(partition_rows)}"
                )
            cursor = boundary
        return records, receipts, degraded

    def fetch(self, sources: Sequence[SourceSpec], start: float, end: float) -> WindowBatch:
        if end <= start:
            raise ValueError("end must be greater than start")
        batch = WindowBatch()
        for source in sources:
            records, receipts, degraded = self._fetch_source(
                self._base_search(source), source, start, end
            )
            batch.records_by_source.setdefault(source.source_id, []).extend(records)
            batch.receipts.extend(receipts)
            batch.degraded.extend(degraded)
        return batch

    def indexed_source_values(self, source: SourceSpec) -> tuple[str, ...]:
        """Source values carrying this declared sourcetype, from tsidx metadata (aggregates only).

        BOTS corpora rename ``wineventlog:*`` at search time (the Windows TA collapses it to
        ``WinEventLog``), so a raw ``sourcetype=`` filter can match the indexed events never;
        tstats resolves the declared name either way and ``source`` is not renamed.
        """
        rows = self._post(
            f"| tstats count where index={_quote(source.index)}"
            f" sourcetype={_quote(source.sourcetype)} by source",
            0.0,
            time.time() + 1.0,
        )
        return tuple(str(row["source"]) for row in rows if row.get("source") is not None)

    def fetch_by_indexed_source(self, source: SourceSpec, start: float, end: float) -> WindowBatch:
        """Read one declared sourcetype's window scoped by its indexed source values.

        Where a corpus's search-time sourcetype rename makes the ``sourcetype=`` read of
        :meth:`fetch` match nothing (measured live on botsv1/2/3 Windows sourcetypes), the
        declared sourcetype is resolved to its indexed sources via tsidx metadata and those
        scope the same partitioned count+read, so expected-vs-fetched still compares like
        with like. Raises when the metadata holds no source, so a declared-but-absent
        sourcetype fails loudly instead of silently fetching an empty window.
        """
        if end <= start:
            raise ValueError("end must be greater than start")
        resolved = self.indexed_source_values(source)
        if not resolved:
            raise WindowFetchError(f"index metadata holds no source for {source.source_id}")
        scoped = (
            f"search index={_quote(source.index)} ("
            + " OR ".join(f"source={_quote(value)}" for value in resolved)
            + ")"
        )
        batch = WindowBatch()
        records, receipts, degraded = self._fetch_source(scoped, source, start, end)
        batch.records_by_source.setdefault(source.source_id, []).extend(records)
        batch.receipts.extend(receipts)
        batch.degraded.extend(degraded)
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
