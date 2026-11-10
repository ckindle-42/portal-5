"""Hunt jobs for the analyst surface: start a blind hunt over an index, dig its top leads, keep
the result on disk, and hand back compact views an 8K-context model can read.

The job runs the same engine and investigator the measurements use -- there is no second path.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .engine import HOUR, Lead, Search, hunt
from .investigate import Investigator

_ROOT = Path(
    os.environ.get("PORTAL5_HUNT_DIR", str(Path.home() / "AI_Output" / "review" / "hunts"))
)
_lock = threading.Lock()
DEFAULT_BUDGETS: dict[str, float] = {
    "query_seconds": 30.0,  # effort budget: server-side duration for one query
    "job_seconds": 720.0,  # effort budget: shared hunt wall time across every worker
    "requests": 2000,  # effort budget: total Splunk requests, including parallel calls
    "cells": 10000,  # effort budget: evidence location cells, not discovery aggregates
    "events": 5000,  # effort budget: raw evidence rows, not ranking samples
}


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


def _per_sample_cap(query: str) -> int | None:
    """A ranking read is bounded by the sample size its own query declares."""
    head = re.search(r"head (\d+)", query)
    return int(head.group(1)) if head else None


class HuntBudgetExceededError(RuntimeError):
    """A hunt ran out of its shared request, result, or wall-time effort."""


class HuntSearchFailedError(RuntimeError):
    """A bounded search could not run or return trustworthy results."""


class HuntCoverageError(RuntimeError):
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
    lock: threading.RLock = field(default_factory=threading.RLock)
    on_progress: Callable[[dict[str, Any]], None] | None = None

    @property
    def deadline(self) -> float:
        return self.started + self.limits["job_seconds"]

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def reserve_query(self, query: str) -> tuple[float, str, int | None]:
        """One shared decision per query, made under the lock: deadline, budget kind, and
        result cap. The phase cannot race active discovery workers -- a phase change only
        happens after `hunt()` returns (its pools joined), and each query keeps the kind
        decided here for both its limit and its row counting."""
        with self.lock:
            if self.remaining() <= 0:
                self.exhausted = "job_wall_time_budget_exhausted"
                raise HuntBudgetExceededError(self.exhausted)
            if self.queries >= self.limits["requests"]:
                self.exhausted = "request_budget_exhausted"
                raise HuntBudgetExceededError(self.exhausted)
            self.queries += 1
            kind = query_budget_kind(query, self.phase)
            if kind == "events":
                cap: int | None = int(self.limits["events"] - self.events)
            elif kind == "cells":
                cap = int(self.limits["cells"] - self.cells)
            else:
                cap = _per_sample_cap(query)
            if cap is not None and cap <= 0:
                self.exhausted = "result_budget_exhausted"
                raise HuntBudgetExceededError(self.exhausted)
            return min(self.limits["query_seconds"], self.remaining()), kind, cap

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

    def update(self, **values: Any) -> None:
        with self.lock:
            for key, value in values.items():
                setattr(self, key, value)
        self.publish(force=True)

    def snapshot(self) -> dict[str, Any]:
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


class BudgetedSearch:
    """Apply one deadline and shared work limits to all parallel hunt requests."""

    def __init__(self, search: Search, budget: HuntBudget) -> None:
        self.search = search
        self.budget = budget
        self.on_case_checkpoint: Callable[[str, dict[str, Any], list[Any]], None] | None = None

    def iter_post(self, query: str, start: float, end: float) -> Iterator[Mapping[str, Any]]:
        timeout, kind, max_results = self.budget.reserve_query(query)
        bounded = getattr(self.search, "iter_post_bounded", None)
        if not callable(bounded):
            raise HuntSearchFailedError("search_adapter_has_no_server_job_cancellation")
        try:
            for row in bounded(
                query,
                start,
                end,
                timeout_seconds=timeout,
                max_results=max_results,
            ):
                self.budget.record_rows(kind, 1)
                yield row
            if self.budget.remaining() <= 0:
                self.budget.exhausted = "job_wall_time_budget_exhausted"
                raise HuntBudgetExceededError(self.budget.exhausted)
        except HuntBudgetExceededError:
            raise
        except Exception as exc:  # noqa: BLE001 -- transport failures are incomplete hunt work
            if getattr(exc, "censored", False):
                raise HuntCoverageError(
                    str(exc),
                    sid=getattr(exc, "sid", None),
                    coverage=getattr(exc, "coverage", None),
                ) from exc
            raise HuntSearchFailedError(f"bounded_search_failed:{type(exc).__name__}") from exc

    def checkpoint(self, phase: str, **values: Any) -> None:
        if self.budget.remaining() <= 0:
            self.budget.exhausted = "job_wall_time_budget_exhausted"
            raise HuntBudgetExceededError(self.budget.exhausted)
        cases = values.pop("cases", None)
        pivot_delta = int(values.pop("pivot_delta", 0))
        if pivot_delta:
            with self.budget.lock:
                self.budget.pivot_count += pivot_delta
        self.budget.update(phase=phase, **values)
        if cases is not None and self.on_case_checkpoint is not None:
            self.on_case_checkpoint(phase, self.budget.snapshot(), cases)


def _path(job_id: str) -> Path:
    return _ROOT / f"{job_id}.json"


def _write(job_id: str, payload: dict[str, Any]) -> None:
    _ROOT.mkdir(parents=True, exist_ok=True)
    tmp = _path(job_id).with_suffix(".tmp")
    tmp.write_text(json.dumps(payload))
    tmp.replace(_path(job_id))


def load(job_id: str) -> dict[str, Any] | None:
    try:
        data: dict[str, Any] = json.loads(_path(job_id).read_text())
        return data
    except FileNotFoundError:
        return None


def _hm(t: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(t))


def _stripped(lead: Lead) -> dict[str, Any]:
    """Scalar fields, top 3 bursts without link lists, 5 novel templates: full list, bounded file."""
    out = lead.as_dict()
    out["bursts"] = [{k: v for k, v in b.items() if k != "links"} for b in out["bursts"][:3]]
    out["novel_templates"] = out["novel_templates"][:5]
    return out


def _pivot_view(pivot: dict[str, Any]) -> str:
    indexed = pivot.get("indexed_count")
    verified = pivot.get("verified_count")
    if indexed is not None:
        count = f"indexed estimate {indexed}"
    elif verified is not None:
        count = f"verified sample {verified}; global count unknown"
    else:
        count = "count unknown"
    return f"{pivot['token']} ({count}; observed hosts {pivot.get('hosts', 0)})"


def _limits(values: dict[str, float] | None) -> dict[str, float]:
    limits = dict(DEFAULT_BUDGETS)
    if values:
        if set(values) - set(limits):
            raise ValueError("unknown hunt effort budget")
        limits.update({key: float(value) for key, value in values.items()})
    if any(value <= 0 for value in limits.values()):
        raise ValueError("hunt effort budgets must be positive")
    if limits["query_seconds"] > limits["job_seconds"]:
        raise ValueError("query budget cannot exceed the job budget")
    return limits


def _case_payload(case: Any) -> dict[str, Any]:
    payload = {**case.summary(), "evidence": list(case.events.values())}
    payload["coverage_complete"] = bool(case.coverage) and all(
        row.get("coverage_complete", False) for row in case.coverage
    )
    return payload


def _persist_progress(
    job_id: str, state: dict[str, Any], lock: threading.RLock, snapshot: dict[str, Any]
) -> None:
    with lock:
        state.update(stage=snapshot["phase"], progress=snapshot)
        _write(job_id, state)


def _persist_cases(
    job_id: str,
    state: dict[str, Any],
    lock: threading.RLock,
    phase: str,
    snapshot: dict[str, Any],
    cases: list[Any],
) -> None:
    with lock:
        state.update(
            stage=phase,
            progress=snapshot,
            cases=[_case_payload(case) for case in cases],
            completed_case_count=len(cases),
        )
        _write(job_id, state)


def _perform_hunt(
    job_id: str,
    state: dict[str, Any],
    state_lock: threading.RLock,
    search: BudgetedSearch,
    index: str,
    start: float,
    end: float,
    dig: int,
    effort: HuntBudget,
) -> None:
    inv: Investigator | None = None
    try:
        leads = hunt(search, index, start, end)
        effort.update(phase="investigating", lead_count=len(leads))
        with state_lock:
            state.update(stage="investigating", leads=[_stripped(lead) for lead in leads])
            state["progress"] = effort.snapshot()
            _write(job_id, state)
        inv = Investigator(search, index, start, end)
        cases = inv.investigate_all(leads, dig=dig)
        complete = bool(cases) and all(
            bool(case.coverage) and _case_payload(case)["coverage_complete"] for case in cases
        )
        progress = effort.snapshot()
        progress["coverage_complete"] = complete and not effort.exhausted
        state.update(
            status="COMPLETE" if complete and not effort.exhausted else "PARTIAL",
            stage="done" if complete and not effort.exhausted else "partial",
            finished=time.time(),
            cases=[_case_payload(case) for case in cases],
            degraded=inv.degraded,
            coverage_complete=complete and not effort.exhausted,
            coverage_reason=None
            if complete and not effort.exhausted
            else "indexed_and_verified_scope_does_not_cover_the_full_raw_index",
            progress=progress,
        )
    except (HuntBudgetExceededError, HuntCoverageError) as exc:
        effort.exhausted = effort.exhausted or str(exc)
        progress = effort.snapshot()
        if isinstance(exc, HuntCoverageError) and exc.sid:
            progress["search_sid"] = exc.sid
        state.update(
            status="PARTIAL",
            stage="partial",
            finished=time.time(),
            error=str(exc),
            coverage_complete=False,
            coverage_reason=str(exc),
            degraded=inv.degraded if inv is not None else [],
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001 -- surface an unexpected job failure
        failure = f"{type(exc).__name__}: {exc}"
        state.update(
            status="FAILED",
            stage="failed",
            finished=time.time(),
            error=failure,
            coverage_complete=False,
            coverage_reason=failure,
            degraded=inv.degraded if inv is not None else [],
            progress=effort.snapshot(),
        )
    with state_lock:
        _write(job_id, state)


def _run(
    job_id: str,
    search: Search,
    index: str,
    start: float,
    end: float,
    dig: int,
    budgets: dict[str, float] | None = None,
) -> None:
    started = time.time()
    state: dict[str, Any] = {
        "job_id": job_id,
        "index": index,
        "status": "RUNNING",
        "stage": "leads",
        "started": started,
        "coverage_complete": False,
        "cases": [],
    }
    state_lock = threading.RLock()
    effort = HuntBudget(_limits(budgets), seed_budget=dig)
    state["progress"] = effort.snapshot()
    effort.on_progress = lambda snapshot: _persist_progress(job_id, state, state_lock, snapshot)
    bounded_search = BudgetedSearch(search, effort)
    bounded_search.on_case_checkpoint = lambda phase, snapshot, cases: _persist_cases(
        job_id, state, state_lock, phase, snapshot, cases
    )
    _write(job_id, state)
    _perform_hunt(job_id, state, state_lock, bounded_search, index, start, end, dig, effort)


def start(
    search: Search,
    index: str,
    start_t: float,
    end_t: float,
    dig: int,
    budgets: dict[str, float] | None = None,
) -> str:
    job_id = "hunt-" + uuid.uuid4().hex[:12]
    limits = _limits(budgets)
    with _lock:
        threading.Thread(
            target=_run,
            args=(job_id, search, index, start_t, end_t, dig, limits),
            daemon=True,
        ).start()
    return job_id


_MAX_CHARS = 6000  # an 8K-context seat


def _levenshtein(a: str, b: str) -> int:
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
    return row[-1]


def _all() -> list[dict[str, Any]]:
    """Every stored job, most recently started first."""
    found = [job for p in _ROOT.glob("hunt-*.json") if (job := load(p.stem)) is not None]
    found.sort(key=lambda j: j.get("started", 0.0), reverse=True)
    return found


def _recent(found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: j.get(k) for k in ("job_id", "index", "status", "started")} for j in found[:3]]


def _resolve(job_id: str | None, index: str | None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """The job to read: an exact id, else the newest hunt on the index, else a near-miss id
    (edit distance <= 3 -- a mis-copied id resolves instead of stranding the analyst)."""
    found = _all()
    if not job_id and not index:
        return None, {"error": "give job_id or index"}
    if job_id:
        job = next((j for j in found if j.get("job_id") == job_id), None)
        if job is not None:
            return job, {}
        near = [j for j in found if _levenshtein(str(j.get("job_id", "")), job_id) <= 3]
        if len(near) == 1:
            return near[0], {"resolved_from": job_id}
        return None, {"error": f"unknown hunt {job_id!r}", "recent": _recent(found)}
    job = next((j for j in found if j.get("index") == index), None)
    if job is None:
        return None, {"error": f"no hunt for index {index!r}", "recent": _recent(found)}
    return job, {}


def compact(out: dict[str, Any]) -> dict[str, Any]:
    """Trim the tail of the largest list field until the response fits an 8K-context seat."""
    trimmed = False
    while len(json.dumps(out)) >= _MAX_CHARS:
        sizes = {k: len(v) for k, v in out.items() if isinstance(v, list) and v}
        if not sizes:
            break
        big = max(sizes, key=lambda k: sizes[k])
        out[big] = out[big][:-1]
        trimmed = True
    if trimmed:
        out["truncated"] = True
    return out


def status(job_id: str | None = None, index: str | None = None) -> dict[str, Any]:
    job, out = _resolve(job_id, index)
    if job is None:
        return compact(out)
    keep = (
        "job_id",
        "index",
        "status",
        "stage",
        "started",
        "finished",
        "error",
        "coverage_complete",
        "coverage_reason",
    )
    out.update({k: job[k] for k in keep if k in job})
    out["elapsed_s"] = round(job.get("finished", time.time()) - job["started"], 1)
    out["cases"] = len(job.get("cases", []))
    progress = job.get("progress")
    if isinstance(progress, dict):
        out["progress"] = progress
        for key in (
            "phase",
            "seed_rank",
            "lead_count",
            "pivot_count",
            "query_count",
            "cell_count",
            "event_count",
            "discovery_row_count",
            "search_sid",
            "remaining_requests",
            "remaining_cells",
            "remaining_events",
            "remaining_seed_budget",
            "remaining_s",
            "exhausted_reason",
            "last_progress_utc",
        ):
            if key in progress:
                out[key] = progress[key]
    out["degraded_reasons"] = job.get("degraded", [])[:3]
    return compact(out)


def leads_view(job_id: str | None = None, index: str | None = None, n: int = 10) -> dict[str, Any]:
    job, out = _resolve(job_id, index)
    if job is None:
        return compact(out)
    rows = []
    for rank, lead in enumerate(job.get("leads", [])[: max(0, min(n, 25))], 1):
        top = lead["bursts"][0] if lead.get("bursts") else None
        rows.append(
            {
                "rank": rank,
                "start_utc": lead["hour_utc"],
                "span_s": lead.get("span", 3600),
                "host": lead["host"],
                "score": lead["score"],
                "template_novelty": lead["novelty"],
                "top_burst": None
                if top is None
                else f"{top['token']} {top['this_hour']} this bucket vs usual {top['prior_median']}",
            }
        )
    out["job_id"] = job["job_id"]
    out["leads"] = rows
    return compact(out)


def case_view(
    job_id: str | None = None, index: str | None = None, case_no: int = 1, n: int = 15
) -> dict[str, Any]:
    job, out = _resolve(job_id, index)
    if job is None:
        return compact(out)
    cases = job.get("cases", [])
    if not 1 <= case_no <= len(cases):
        out["error"] = f"case {case_no} not in 1..{len(cases)}"
        return compact(out)
    c = cases[case_no - 1]
    pivots = sorted(c["pivots"], key=lambda p: -p["weight"])[:10]
    core = c.get("core", c["picture"])
    out.update(
        {
            "job_id": job["job_id"],
            "case": case_no,
            "seeds": c["merged_from"],
            "core_events": c.get("core_events", c["events"]),
            "core_hosts": c.get("core_hosts", len(c["hosts"])),
            "span_hours": c["span_hours"],
            "pivots": [_pivot_view(p) for p in pivots],
            "core": [
                f"{_hm(e['time'])} {e['host']} {e['source']}: {e['raw'][:180]}" for e in core[:n]
            ],
            "coverage": {
                "complete": c.get("coverage_complete", False),
                "pivots": len(c.get("coverage", [])),
                "unknown": sum(
                    item.get("count_semantics") == "unknown"
                    or str(item.get("count_semantics", "")).endswith("global_unknown")
                    for item in c.get("coverage", [])
                ),
                "censored": sum(bool(item.get("censored")) for item in c.get("coverage", [])),
                "reasons": list(
                    dict.fromkeys(
                        item.get("reason") for item in c.get("coverage", []) if item.get("reason")
                    )
                )[:5],
            },
            "picture": [
                f"{_hm(e['time'])} {e['host']} {e['source']}: {e['raw'][:180]}"
                for e in c["picture"][:n]
            ],
        }
    )
    return compact(out)


__all__ = ["HOUR", "case_view", "compact", "leads_view", "load", "start", "status"]
