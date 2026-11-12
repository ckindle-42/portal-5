"""The one object every hunt Splunk read goes through: one budget, one deadline, one
classification (a query cut by its own cap or time bound is censored coverage; a spent
shared budget or job deadline ends the work)."""

from __future__ import annotations

import inspect
import re
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from ..review.window import JobCancel
from .engine import (
    Search,
    SearchBudgetExceededError,
    SearchCoverageCensoredError,
    SearchQueryBoundError,
)
from .ranking import query_progress_kind, query_progress_shape

DEFAULT_BUDGETS: dict[str, float] = {
    "query_seconds": 30.0,  # effort budget: server-side duration for one query
    "job_seconds": 720.0,  # effort budget: shared hunt wall time across every worker
    "requests": 2000,  # effort budget: total Splunk requests, including parallel calls
    "cells": 10000,  # effort budget: evidence location cells, not discovery aggregates
    "events": 5000,  # effort budget: raw evidence rows, not ranking samples
}
QUERY_BOUND = "query_bound"  # cut by the query's own time bound
ROW_CAP = "row_cap"  # cut by the query's own row cap
CENSORED = "censored"  # the transport reported incomplete coverage
CANCEL_WAIT_SECONDS = 0.2  # how long a read gets to answer after its own time bound


class HuntBudgetExceededError(SearchBudgetExceededError):
    """A hunt ran out of its shared request, result, or wall-time effort."""


class HuntDeadlineExceededError(HuntBudgetExceededError):
    """The single job deadline expired; the read path stopped the job."""


class HuntSearchFailedError(RuntimeError):
    """A bounded search could not run or return trustworthy results."""


class HuntCoverageError(SearchCoverageCensoredError):
    """A search stopped early; returned rows are not an exact count."""

    def __init__(
        self,
        message: str,
        *,
        sid: str | None = None,
        coverage: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.sid = sid
        self.coverage = dict(coverage or {})


def query_budget_kind(query: str, phase: str = "investigating") -> str:
    """discovery | cells | events, by execution phase then query shape. Ranking reads
    (samples, peers, links, aggregates) are discovery effort; investigation raw reads are
    events and its location enumerations are cells. Ranking keeps per-sample caps."""
    if phase != "investigating":
        return "discovery"
    if not query.lstrip().startswith("| tstats"):
        return "events"
    if " by host source punct" in query:
        return "discovery"
    if " by host source" in query:
        return "cells"
    return "discovery"


def per_sample_cap(query: str) -> int | None:
    """A ranking read is bounded by the sample size its own query declares."""
    head = re.search(r"head (\d+)", query)
    return int(head.group(1)) if head else None


@dataclass(frozen=True)
class Read:
    """One query's outcome: what it returned, and whether that is all of it."""

    rows: list[dict[str, Any]]
    censored: bool = False
    reason: str | None = None


@dataclass
class HuntBudget:
    limits: dict[str, float]
    seed_budget: int = 0
    started: float = field(default_factory=time.monotonic)
    queries: int = 0
    cells: int = 0
    events: int = 0
    discovery_rows: int = 0
    phase: str = "ranking"
    seed_rank: int | None = None
    lead_count: int = 0
    pivot_count: int = 0
    exhausted: str | None = None
    last_write: float = 0.0
    last_write_query: int = -1
    kind_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    observation_request_kinds: dict[str, dict[str, Any]] = field(default_factory=dict)
    listed_observations: list[dict[str, Any]] = field(default_factory=list)
    ranking_notes: set[str] = field(default_factory=set)
    lock: threading.RLock = field(default_factory=threading.RLock)
    on_progress: Callable[[dict[str, Any]], None] | None = None
    judge_requests: int = 0
    judge_seconds: float = 0.0
    host_hours: list[dict[str, Any]] = field(default_factory=list)
    judge_block: dict[str, Any] = field(default_factory=dict)

    @property
    def deadline(self) -> float:
        return self.started + self.limits["job_seconds"]

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def record_rows(self, kind: str, count: int) -> None:
        with self.lock:
            if kind == "events":
                self.events += count
                if self.events > self.limits["events"]:
                    self.exhausted = "event_budget_exhausted"
                    raise HuntBudgetExceededError(self.exhausted)
            elif kind == "cells":
                self.cells += count
                if self.cells > self.limits["cells"]:
                    self.exhausted = "cell_budget_exhausted"
                    raise HuntBudgetExceededError(self.exhausted)
            else:
                self.discovery_rows += count
        self.publish()

    def add_kind(
        self,
        kind: str,
        seconds: float,
        *,
        query: str | None = None,
        query_start: float = 0.0,
        query_end: float = 0.0,
        censored: bool = False,
    ) -> None:
        with self.lock:
            slot = self.kind_stats.setdefault(kind, {"requests": 0, "seconds": 0.0, "censored": 0})
            slot["requests"] = int(slot["requests"]) + 1
            slot["seconds"] = round(float(slot["seconds"]) + seconds, 3)
            if censored:
                slot["censored"] = int(slot.get("censored", 0)) + 1
            if query is not None:
                slot["shape"] = query_progress_shape(query, query_start, query_end)

    def update(self, **values: Any) -> None:
        with self.lock:
            for key, value in values.items():
                setattr(self, key, value)
        self.publish(force=True)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            kinds = {
                kind: {
                    "requests": int(slot["requests"]),
                    "seconds": round(float(slot["seconds"]), 3),
                    "censored": int(slot.get("censored", 0)),
                    **({"shape": slot["shape"]} if "shape" in slot else {}),
                }
                for kind, slot in sorted(self.kind_stats.items())
            }
            reasons = sorted(self.ranking_notes)
        return {
            "phase": self.phase,
            "seed_rank": self.seed_rank,
            "lead_count": self.lead_count,
            "pivot_count": self.pivot_count,
            "query_count": self.queries,
            "cell_count": self.cells,
            "event_count": self.events,
            "discovery_row_count": self.discovery_rows,
            "remaining_requests": max(0, int(self.limits["requests"] - self.queries)),
            "remaining_cells": max(0, int(self.limits["cells"] - self.cells)),
            "remaining_events": max(0, int(self.limits["events"] - self.events)),
            "remaining_seed_budget": max(
                0,
                min(self.seed_budget, self.lead_count) - (self.seed_rank or 0),
            ),
            "elapsed_s": round(time.monotonic() - self.started, 1),
            "remaining_s": round(self.remaining(), 1),
            "exhausted_reason": self.exhausted,
            "limits": dict(self.limits),
            "last_progress_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "coverage_complete": False,
            "request_kinds": kinds,
            "observation_request_kinds": {
                kind: dict(slot) for kind, slot in sorted(self.observation_request_kinds.items())
            },
            "ranking_coverage_complete": not reasons,
            "ranking_coverage_reasons": reasons,
            "judge_requests": self.judge_requests,
            "judge_seconds": round(float(self.judge_seconds), 3),
        }

    def publish(self, *, force: bool = False) -> None:
        if self.on_progress is None:
            return
        now = time.monotonic()
        with self.lock:
            if (
                not force
                and now - self.last_write < 5
                and self.queries - self.last_write_query < 10
            ):
                return
            self.last_write = now
            self.last_write_query = self.queries
            snapshot = self.snapshot()
        self.on_progress(snapshot)


def _time_bound(exc: BaseException) -> bool:
    """True when an unannotated transport reports that this one query overran its bound."""
    text = str(exc).lower()
    return "exceeded" in text or "timed out" in text or "timeout" in text


class _Outcome:
    """One read's holder: rows as they arrive, its job cancel handle, and the failure."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.error: BaseException | None = None
        self.cut = False
        self.cancel = JobCancel()
        self.done = threading.Event()


def _cancel(outcome: _Outcome) -> None:
    """Cancel the read's Splunk job through the transport, without waiting for it."""

    def attempt() -> None:
        try:
            outcome.cancel.cancel()
        except Exception:  # noqa: BLE001 -- a cancel racing the read ending is not a failure
            return

    threading.Thread(target=attempt, daemon=True).start()


def _accepts_cancel(bounded: Any) -> bool:
    try:
        parameters = inspect.signature(bounded).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.name == "cancel" or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )


class HuntExecutor:
    """Every hunt Splunk read: one shared budget, one job deadline, one classification."""

    def __init__(self, search: Search, budget: HuntBudget) -> None:
        self.search = search
        self.budget = budget
        self._last_error: BaseException | None = None

    def read(
        self,
        query: str,
        start: float,
        end: float,
        *,
        kind: str,
        row_cap: int | None = None,
    ) -> Read:
        """Issue one bounded read. `row_cap` bounds a discovery sample; evidence and cell
        reads are bounded by the shared budget they spend."""
        timeout, cap, spend = self._reserve(query, row_cap)
        began = time.monotonic()
        reason: str | None = None
        rows: list[dict[str, Any]] = []
        try:
            rows, reason = self._collect(query, start, end, timeout, cap)
        finally:
            self.budget.add_kind(
                kind,
                time.monotonic() - began,
                query=query,
                query_start=start,
                query_end=end,
                censored=reason is not None,
            )
        self.budget.record_rows(spend, len(rows))
        return Read(rows, reason is not None, reason)

    def iter_post(self, query: str, start: float, end: float) -> Iterator[Mapping[str, Any]]:
        """Compatibility read for the engine and investigator: censored coverage raises."""
        read = self.read(
            query,
            start,
            end,
            kind=query_progress_kind(query, start, end),
            row_cap=per_sample_cap(query),
        )
        if read.reason == CENSORED:
            cause = self._last_error
            raise HuntCoverageError(
                str(cause),
                sid=getattr(cause, "sid", None),
                coverage=getattr(cause, "coverage", None),
            ) from cause
        yield from read.rows

    def stats(self) -> dict[str, dict[str, Any]]:
        with self.budget.lock:
            return {kind: dict(slot) for kind, slot in self.budget.kind_stats.items()}

    def delta(self, before: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
        """Per-kind cost this read path added since `before`."""
        found: dict[str, dict[str, Any]] = {}
        for kind, slot in self.stats().items():
            old = before.get(kind, {})
            requests = int(slot["requests"]) - int(old.get("requests", 0))
            if requests:
                found[kind] = {
                    "requests": requests,
                    "seconds": round(float(slot["seconds"]) - float(old.get("seconds", 0.0)), 3),
                    "censored": int(slot.get("censored", 0)) - int(old.get("censored", 0)),
                }
        return found

    def _reserve(self, query: str, row_cap: int | None) -> tuple[float, int | None, str]:
        budget = self.budget
        with budget.lock:
            if budget.exhausted:
                if budget.exhausted == "job_deadline_exceeded":
                    raise HuntDeadlineExceededError(budget.exhausted)
                raise HuntBudgetExceededError(budget.exhausted)
            if budget.remaining() <= 0:
                budget.exhausted = "job_deadline_exceeded"
                raise HuntDeadlineExceededError(budget.exhausted)
            if budget.queries >= budget.limits["requests"]:
                budget.exhausted = "request_budget_exhausted"
                raise HuntBudgetExceededError(budget.exhausted)
            spend = query_budget_kind(query, budget.phase)
            shared = {
                "events": budget.limits["events"] - budget.events,
                "cells": budget.limits["cells"] - budget.cells,
            }.get(spend)
            cap: int | None
            if shared is not None:
                if shared <= 0:
                    budget.exhausted = "result_budget_exhausted"
                    raise HuntBudgetExceededError(budget.exhausted)
                cap = int(shared)
            else:
                cap = row_cap
            budget.queries += 1
            return min(budget.limits["query_seconds"], budget.remaining()), cap, spend

    def _collect(
        self,
        query: str,
        start: float,
        end: float,
        timeout: float,
        cap: int | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        outcome = _Outcome()
        worker = threading.Thread(
            target=self._work,
            args=(query, start, end, timeout, cap, outcome),
            daemon=True,
        )
        worker.start()
        if not outcome.done.wait(timeout + CANCEL_WAIT_SECONDS):
            _cancel(outcome)
            if self.budget.remaining() <= 0:
                self.budget.exhausted = self.budget.exhausted or "job_deadline_exceeded"
                raise HuntDeadlineExceededError(self.budget.exhausted)
            return list(outcome.rows), QUERY_BOUND
        if outcome.error is not None:
            return list(outcome.rows), self._reason(outcome.error)
        if outcome.cut:
            return list(outcome.rows), ROW_CAP
        return list(outcome.rows), None

    def _work(
        self,
        query: str,
        start: float,
        end: float,
        timeout: float,
        cap: int | None,
        outcome: _Outcome,
    ) -> None:
        try:
            for row in self._produce(query, start, end, timeout, cap, outcome):
                outcome.rows.append(dict(row))
        except BaseException as exc:  # noqa: BLE001 -- re-raised in the reading thread
            outcome.error = exc
        finally:
            outcome.cancel.release()
            outcome.done.set()

    def _produce(
        self,
        query: str,
        start: float,
        end: float,
        timeout: float,
        cap: int | None,
        outcome: _Outcome,
    ) -> Iterator[Mapping[str, Any]]:
        bounded = getattr(self.search, "iter_post_bounded", None)
        if callable(bounded):
            options: dict[str, Any] = {"timeout_seconds": timeout, "max_results": cap}
            if _accepts_cancel(bounded):
                options["cancel"] = outcome.cancel
            stream: Iterable[Mapping[str, Any]] = bounded(query, start, end, **options)
        else:
            stream = self.search.iter_post(query, start, end)
        for index, row in enumerate(stream):
            if cap is not None and index >= cap:
                outcome.cut = True
                return
            yield row

    def _reason(self, exc: BaseException) -> str:
        if isinstance(exc, SearchBudgetExceededError):
            raise exc
        if isinstance(exc, SearchQueryBoundError):
            self._last_error = exc
            return QUERY_BOUND
        censored = getattr(exc, "censored", False)
        if isinstance(exc, SearchCoverageCensoredError) or censored:
            self._last_error = exc
            reason = str(getattr(exc, "reason", "") or "")
            if reason in {QUERY_BOUND, ROW_CAP, CENSORED}:
                return reason
            return QUERY_BOUND if _time_bound(exc) else CENSORED
        raise HuntSearchFailedError(f"bounded_search_failed:{type(exc).__name__}") from exc


def executor_for(search: Search) -> HuntExecutor:
    """The wrapped search's shared executor, or a private one for a bare adapter."""
    found = getattr(search, "executor", None)
    if isinstance(found, HuntExecutor):
        return found
    return HuntExecutor(search, HuntBudget(dict(DEFAULT_BUDGETS)))


__all__ = [
    "CENSORED",
    "DEFAULT_BUDGETS",
    "QUERY_BOUND",
    "ROW_CAP",
    "HuntBudget",
    "HuntBudgetExceededError",
    "HuntCoverageError",
    "HuntDeadlineExceededError",
    "HuntExecutor",
    "HuntSearchFailedError",
    "Read",
    "executor_for",
    "per_sample_cap",
    "query_budget_kind",
]
