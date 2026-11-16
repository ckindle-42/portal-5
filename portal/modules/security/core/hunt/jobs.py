"""Hunt jobs for the analyst surface: start a blind hunt over an index, dig its top leads, keep
the result on disk, and hand back compact views an 8K-context model can read.

The job runs the same engine and investigator the measurements use -- there is no second path.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

from .engine import (
    HOUR,
    Lead,
    Search,
    SearchBudgetExceededError,
    SearchQueryBoundError,
    hunt,
)
from .executor import (
    DEFAULT_BUDGETS,
    HuntBudget,
    HuntBudgetExceededError,
    HuntCoverageError,
    HuntDeadlineExceededError,
    HuntExecutor,
    HuntSearchFailedError,
    query_budget_kind,
)
from .investigate import Investigator
from .judge import (
    DEFAULT_KEY_ENV,
    JudgeClient,
    OpenAICompatibleClient,
    chat_completions_endpoint,
)

_ROOT = Path(
    os.environ.get("PORTAL5_HUNT_DIR", str(Path.home() / "AI_Output" / "review" / "hunts"))
)
_lock = threading.Lock()


class BudgetedSearch:
    """The hunt's shared budget and checkpoint surface; every read is the executor's."""

    def __init__(self, search: Search, budget: HuntBudget) -> None:
        self.search = search
        self.budget = budget
        self.executor = HuntExecutor(search, budget)
        self.on_case_checkpoint: Callable[[str, dict[str, Any], list[Any]], None] | None = None

    def iter_post(self, query: str, start: float, end: float) -> Iterator[Mapping[str, Any]]:
        return self.executor.iter_post(query, start, end)

    def checkpoint(self, phase: str, **values: Any) -> None:
        cases = values.pop("cases", None)
        if cases is not None and self.on_case_checkpoint is not None:
            # persist current evidence first: a spent wall clock must not lose the case
            self.on_case_checkpoint(phase, self.budget.snapshot(), cases)
        if self.budget.remaining() <= 0:
            self.budget.exhausted = self.budget.expired_reason() or "job_deadline_exceeded"
            if self.budget.exhausted == "job_deadline_exceeded":
                raise HuntDeadlineExceededError(self.budget.exhausted)
            raise HuntBudgetExceededError(self.budget.exhausted)
        pivot_delta = int(values.pop("pivot_delta", 0))
        if pivot_delta:
            with self.budget.lock:
                self.budget.pivot_count += pivot_delta
        self.budget.update(phase=phase, **values)


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
    payload["risk"] = getattr(case, "risk", None)
    payload["acc_rank"] = getattr(case, "acc_rank", None)
    payload["p_yes"] = getattr(case, "p_yes", None)
    return payload


def _order_state(effort: HuntBudget) -> dict[str, Any]:
    block = dict(effort.judge_block) or {"configured": False}
    return {"host_hours": list(effort.host_hours), "judge": block}


def _copy_lead_rank(cases: list[Any], leads: list[Lead]) -> None:
    by_seed = {f"{lead.host}@{lead.hour}": lead for lead in leads}
    for case in cases:
        lead = by_seed.get(getattr(case, "seed", ""))
        if lead is None:
            continue
        case.risk = lead.risk
        case.acc_rank = lead.acc_rank
        case.p_yes = lead.p_yes


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
            completed_case_count=sum(1 for case in cases if not getattr(case, "partial", False)),
        )
        _write(job_id, state)


def _case_rows(cases: list[Any]) -> tuple[list[dict[str, Any]], int]:
    rows = [_case_payload(case) for case in cases]
    done = sum(1 for case in cases if not getattr(case, "partial", False))
    return rows, done


def _store_leads(
    job_id: str,
    state: dict[str, Any],
    state_lock: threading.RLock,
    effort: HuntBudget,
    leads: list[Lead],
) -> None:
    with state_lock:
        state.update(
            stage="investigating",
            leads=[_stripped(lead) for lead in leads],
            observations=list(effort.listed_observations),
            **_order_state(effort),
        )
        state["progress"] = effort.snapshot()
        _write(job_id, state)


def _close_success(
    cases: list[Any], effort: HuntBudget, progress: dict[str, Any], degraded: list[Any]
) -> dict[str, Any]:
    """COMPLETE only when observation coverage and every case are both complete."""
    rows, done = _case_rows(cases)
    complete = (
        bool(cases)
        and not effort.exhausted
        and progress["ranking_coverage_complete"]
        and all(bool(case.coverage) and _case_payload(case)["coverage_complete"] for case in cases)
    )
    progress["coverage_complete"] = complete
    ok = complete and not effort.exhausted
    return {
        "status": "COMPLETE" if ok else "PARTIAL",
        "stage": "done" if ok else "partial",
        "finished": time.time(),
        "cases": rows,
        "completed_case_count": done,
        "degraded": degraded,
        "coverage_complete": ok,
        "coverage_reason": None
        if ok
        else "indexed_and_verified_scope_does_not_cover_the_full_raw_index",
        "progress": progress,
        **_order_state(effort),
    }


def _close_partial(
    exc: BaseException, effort: HuntBudget, inv: Investigator | None
) -> dict[str, Any]:
    effort.exhausted = effort.exhausted or str(exc)
    progress = effort.snapshot()
    if isinstance(exc, HuntCoverageError) and exc.sid:
        progress["search_sid"] = exc.sid
    retained = inv.completed_cases if inv is not None else []
    rows, done = _case_rows(retained)
    return {
        "status": "PARTIAL",
        "stage": "partial",
        "finished": time.time(),
        "error": str(exc),
        "observations": list(getattr(effort, "listed_observations", [])),
        "cases": rows,
        "completed_case_count": done,
        "coverage_complete": False,
        "coverage_reason": str(exc),
        "degraded": inv.degraded if inv is not None else [],
        "progress": progress,
        **_order_state(effort),
    }


def _close_failed(
    exc: BaseException, effort: HuntBudget, inv: Investigator | None
) -> dict[str, Any]:
    failure = f"{type(exc).__name__}: {exc}"
    retained = inv.completed_cases if inv is not None else []
    rows, done = _case_rows(retained)
    return {
        "status": "FAILED",
        "stage": "failed",
        "finished": time.time(),
        "error": failure,
        "cases": rows,
        "completed_case_count": done,
        "coverage_complete": False,
        "coverage_reason": failure,
        "degraded": inv.degraded if inv is not None else [],
        "progress": effort.snapshot(),
        **_order_state(effort),
    }


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
    judge: JudgeClient | None = None,
    judge_model: str | None = None,
) -> None:
    inv: Investigator | None = None
    leads: list[Lead] = []
    effort.judge_block = {"configured": judge is not None and bool(judge_model)}
    try:
        leads = hunt(
            search,
            index,
            start,
            end,
            candidates=dig,
            judge=judge,
            judge_model=judge_model,
        )
        effort.update(phase="investigating", lead_count=len(leads))
        _store_leads(job_id, state, state_lock, effort, leads)
        inv = Investigator(search, index, start, end)
        cases = inv.investigate_all(leads, dig=dig)
        _copy_lead_rank(cases, leads)
        state.update(_close_success(cases, effort, effort.snapshot(), inv.degraded))
    except (SearchBudgetExceededError, HuntCoverageError, SearchQueryBoundError) as exc:
        if inv is not None:
            _copy_lead_rank(inv.completed_cases, leads)
        state.update(_close_partial(exc, effort, inv))
    except Exception as exc:  # noqa: BLE001 -- surface an unexpected job failure
        if inv is not None:
            _copy_lead_rank(inv.completed_cases, leads)
        state.update(_close_failed(exc, effort, inv))
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
    judge: JudgeClient | None = None,
    judge_model: str | None = None,
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
    _perform_hunt(
        job_id,
        state,
        state_lock,
        bounded_search,
        index,
        start,
        end,
        dig,
        effort,
        judge,
        judge_model,
    )


def _judge_from_env() -> tuple[JudgeClient, str] | None:
    """Read the Pipeline judge once. Core ordering never sees the environment."""
    url = os.environ.get("PORTAL_HUNT_JUDGE_URL")
    model = os.environ.get("PORTAL_HUNT_JUDGE_MODEL")
    if not url or not model:
        return None
    key_env = os.environ.get("PORTAL_HUNT_JUDGE_KEY_ENV", DEFAULT_KEY_ENV)
    api_key = os.environ.get(key_env) if key_env else None
    return OpenAICompatibleClient(chat_completions_endpoint(url), api_key), model


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
    target = _judge_from_env()
    client: JudgeClient | None = None
    model: str | None = None
    if target is not None:
        client, model = target
    with _lock:
        threading.Thread(
            target=_run,
            args=(job_id, search, index, start_t, end_t, dig, limits, client, model),
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
            "judge_requests",
            "judge_seconds",
        ):
            if key in progress:
                out[key] = progress[key]
    out["degraded_reasons"] = job.get("degraded", [])[:3]
    if "judge" in job:
        out["judge"] = job["judge"]
    hours = job.get("host_hours")
    if isinstance(hours, list):
        out["host_hours"] = hours
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
                "risk": lead.get("risk"),
                "acc_rank": lead.get("acc_rank"),
                "p_yes": lead.get("p_yes"),
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
            "risk": c.get("risk"),
            "acc_rank": c.get("acc_rank"),
            "p_yes": c.get("p_yes"),
            "pivots": [_pivot_view(p) for p in pivots],
            "core": [
                f"{_hm(e['time'])} {e['host']} {e['source']}: {e['raw'][:180]}" for e in core[:n]
            ],
            "coverage": {
                "complete": c.get("coverage_complete", False),
                "partial": bool(c.get("partial", False)),
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


__all__ = [
    "HOUR",
    "BudgetedSearch",
    "DEFAULT_BUDGETS",
    "HuntBudget",
    "HuntBudgetExceededError",
    "HuntCoverageError",
    "HuntDeadlineExceededError",
    "HuntSearchFailedError",
    "case_view",
    "compact",
    "leads_view",
    "load",
    "query_budget_kind",
    "start",
    "status",
]
