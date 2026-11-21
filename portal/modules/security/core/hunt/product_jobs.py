"""Durable background jobs for the R2 notables hunt product path."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .engine import Search
from .executor import DEFAULT_BUDGETS, HuntBudget, HuntBudgetExceededError
from .jobs import BudgetedSearch, compact
from .judge import BackpressureClient, JudgeClient, ThrottleBudgetExceededError
from .notables.embedding import PipelineEmbeddingClient, embedding_from_env, embedding_requirement
from .notables.pipeline import model_from_env, model_requirement, preflight
from .notables.receipt import progress_update, read_json
from .notables.relate import RELATE_FILE, relate_stage
from .notables.rerank import REPORT_FILE as RERANK_FILE
from .notables.run import (
    DEFAULT_GENERATORS,
    NOTABLES_FILE,
    SOURCES_FILE,
    STAGES,
    behaviours_stage,
    cards_stage,
    judge_stage,
    notables_stage,
    reset_ledger,
)
from .notables.similar import SIMILAR_GENERATOR

_ROOT = Path(
    os.environ.get("PORTAL5_HUNT_DIR", str(Path.home() / "AI_Output" / "review" / "hunts"))
)
_lock = threading.Lock()
R2_DEFAULT_BUDGETS = {**DEFAULT_BUDGETS, "job_seconds": 1260.0}
STAGE_ESTIMATES = {
    "cards": 60.0,
    "behaviours": 100.0,
    "notables": 350.0,
    "judge": 60.0,
    "relate": 120.0,
}
STAGE_ORDER = STAGES
LEADS_LIMIT = 10
LEADS_VIEW_LIMIT = 3
LEADS_VIEW_DEFAULT = 2
STATUS_WAIT_MAX_S = 45.0
STATUS_POLL_S = 1.0
TERMINAL_STATUSES = {"COMPLETE", "PARTIAL", "FAILED"}


class HuntJobClient:
    """Apply the shared hunt deadline to each Pipeline request."""

    def __init__(self, client: JudgeClient, effort: HuntBudget) -> None:
        self.client = client
        self.effort = effort

    def complete(self, **request: Any) -> Mapping[str, Any]:
        remaining = self.effort.remaining()
        if remaining <= 0:
            self.effort.exhausted = self.effort.expired_reason() or "job_deadline_exceeded"
            raise HuntBudgetExceededError(self.effort.exhausted)
        request["_timeout_seconds"] = remaining
        return self.client.complete(**request)


def _path(job_id: str) -> Path:
    if Path(job_id).name != job_id or not job_id.startswith("hunt-r2-"):
        raise ValueError("invalid R2 hunt job id")
    return _ROOT / f"{job_id}.json"


def _write(job_id: str, payload: dict[str, Any]) -> None:
    path = _path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload))
    temporary.replace(path)


def load(job_id: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(_path(job_id).read_text())
    except FileNotFoundError:
        return None
    return payload if isinstance(payload, dict) else None


def _limits(values: Mapping[str, float] | None) -> dict[str, float]:
    limits = dict(R2_DEFAULT_BUDGETS)
    if values:
        unknown = set(values) - set(limits)
        if unknown:
            raise ValueError("unknown hunt effort budget")
        limits.update({key: float(value) for key, value in values.items()})
    if any(value <= 0 for value in limits.values()):
        raise ValueError("hunt effort budgets must be positive")
    if limits["query_seconds"] > limits["job_seconds"]:
        raise ValueError("query budget cannot exceed the job budget")
    return limits


def _stage_receipts(out: Path) -> dict[str, Any]:
    stages = read_json(out / "progress.json").get("stages")
    stages = stages if isinstance(stages, dict) else {}
    relation = read_json(out / RELATE_FILE).get("receipt")
    if isinstance(relation, dict):
        stages["relate"] = relation
    rerank = read_json(out / RERANK_FILE).get("receipt")
    if isinstance(rerank, dict):
        stages["rerank"] = rerank
    return stages


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _cost(stages: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    preflight = _mapping(stages.get("preflight"))
    cards = _mapping(stages.get("cards"))
    judge = _mapping(stages.get("judge"))
    rerank = _mapping(stages.get("rerank"))
    council = _mapping(rerank.get("council"))
    council_basis = _mapping(council.get("budget_basis"))
    notables = _mapping(stages.get("notables"))
    similar = _mapping(notables.get(SIMILAR_GENERATOR))
    embedding = _mapping(similar.get("embedding"))
    return {
        "elapsed_s": snapshot.get("elapsed_s", 0),
        "remaining_s": snapshot.get("remaining_s", 0),
        "splunk_requests": snapshot.get("query_count", 0),
        "splunk_cells": snapshot.get("cell_count", 0),
        "splunk_events": snapshot.get("event_count", 0),
        "model_requests": (
            int(preflight.get("requests") or 0)
            + int(cards.get("model_requests") or 0)
            + int(judge.get("requests") or 0)
            + int(council_basis.get("derived_budget") or 0)
        ),
        "model_seconds": round(
            float(preflight.get("seconds") or 0)
            + float(cards.get("model_seconds") or 0)
            + float(judge.get("model_seconds") or 0)
            + float(council.get("model_seconds") or 0),
            3,
        ),
        "embedding_requests": int(embedding.get("requests") or 0),
        "embedding_seconds": float(embedding.get("seconds") or 0),
    }


def _stage_plan(
    stage: str,
    remaining_seconds: float,
    *,
    stage_order: Sequence[str] = STAGE_ORDER,
) -> dict[str, Any]:
    if stage not in stage_order:
        raise ValueError(f"unknown R2 hunt stage: {stage}")
    position = stage_order.index(stage)
    later = list(stage_order[position + 1 :])
    reserved = {name: STAGE_ESTIMATES[name] for name in later}
    reserve_total = sum(reserved.values())
    available = max(0.0, remaining_seconds - reserve_total)
    budget = min(STAGE_ESTIMATES[stage], available) if stage == "judge" else available
    plan = {
        "stage": stage,
        "remaining_s": round(max(0.0, remaining_seconds), 1),
        "estimate_s": STAGE_ESTIMATES[stage],
        "budget_s": round(budget, 1),
        "reserved_for_later": reserved,
        "reserved_s": round(reserve_total, 1),
        "shortfall_s": round(max(0.0, STAGE_ESTIMATES[stage] - budget), 1),
        "buffer_s": round(max(0.0, budget - STAGE_ESTIMATES[stage]), 1),
        "cut_policy": "stage1_order_annotation_limit"
        if stage == "judge" and budget < STAGE_ESTIMATES[stage]
        else None,
    }
    return plan


def _save_progress(
    job_id: str,
    state: dict[str, Any],
    state_lock: threading.RLock,
    out: Path,
    snapshot: dict[str, Any],
) -> None:
    with state_lock:
        stages = _stage_receipts(out)
        state["progress"] = {"current": snapshot, "stages": stages}
        state["cost"] = _cost(stages, snapshot)
        _write(job_id, state)


def _enter_stage(
    name: str,
    job_id: str,
    state: dict[str, Any],
    state_lock: threading.RLock,
    out: Path,
    effort: HuntBudget,
    stage_order: Sequence[str],
) -> dict[str, Any]:
    if effort.job_remaining() <= 0:
        effort.exhausted = "job_deadline_exceeded"
        raise HuntBudgetExceededError(effort.exhausted)
    plan = _stage_plan(name, effort.job_remaining(), stage_order=stage_order)
    effort.set_stage_deadline(name, plan["budget_s"])
    effort.phase = name
    effort.update(phase=name)
    with state_lock:
        state.setdefault("stage_plan", []).append(plan)
        state.update(
            stage=name, progress={"current": effort.snapshot(), "stages": _stage_receipts(out)}
        )
        state["cost"] = _cost(state["progress"]["stages"], state["progress"]["current"])
        _write(job_id, state)
    return plan


def _stage_client(client: JudgeClient, effort: HuntBudget) -> BackpressureClient:
    remaining = effort.remaining()
    if remaining <= 0:
        effort.exhausted = effort.expired_reason() or "job_deadline_exceeded"
        raise HuntBudgetExceededError(effort.exhausted)
    return BackpressureClient(HuntJobClient(client, effort), budget_seconds=remaining)


def _stage_actions(
    index: str,
    start: float,
    end: float,
    out: Path,
    search: BudgetedSearch,
    client: JudgeClient,
    model: str,
    knowledge_store: Path | None,
    knowledge_families: Sequence[str] | None,
    embedder: PipelineEmbeddingClient | None,
    effort: HuntBudget,
    judge_enabled: bool = False,
) -> tuple[tuple[str, Callable[[], Any]], ...]:
    generators = (*DEFAULT_GENERATORS, SIMILAR_GENERATOR) if knowledge_store else DEFAULT_GENERATORS
    actions: list[tuple[str, Callable[[], Any]]] = [
        (
            "cards",
            lambda: cards_stage(
                index=index,
                out=out,
                start=start,
                end=end,
                client=_stage_client(client, effort),
                model=model,
                search=search,
            ),
        ),
        ("behaviours", lambda: behaviours_stage(out=out, search=search)),
        (
            "notables",
            lambda: notables_stage(
                index=index,
                out=out,
                start=start,
                end=end,
                search=search,
                enabled=generators,
                knowledge_store=knowledge_store,
                knowledge_families=knowledge_families,
                embedder=embedder,
            ),
        ),
    ]
    actions.append(("relate", lambda: relate_stage(out=out, search=search)))
    if judge_enabled:
        actions.append(("judge", lambda: _judge_stage_action(out, client, model, effort)))
    return tuple(actions)


def _judge_stage_action(
    out: Path, client: JudgeClient, model: str, effort: HuntBudget
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    available = effort.remaining()
    bounded = _stage_client(client, effort) if available > 0 else client
    return judge_stage(
        out=out,
        client=bounded,
        model=model,
        deadline_seconds=available,
        request_budget=0 if available <= 0 else None,
        max_notables=LEADS_LIMIT,
        explain=True,
    )


def _execute_stages(
    actions: Sequence[tuple[str, Callable[[], Any]]],
    job_id: str,
    state: dict[str, Any],
    state_lock: threading.RLock,
    out: Path,
    effort: HuntBudget,
) -> None:
    stage_order = tuple(stage for stage, _run_stage in actions)
    for stage, run_stage in actions:
        plan = _enter_stage(stage, job_id, state, state_lock, out, effort, stage_order)
        stage_started = time.monotonic()
        result = run_stage()
        if stage == "judge" and isinstance(result, tuple) and len(result) == 2:
            receipt = _mapping(result[1])
            selection = receipt.get("selection")
            if isinstance(selection, Mapping):
                state["judge_selection"] = dict(selection)
        plan["elapsed_s"] = round(max(0.0, time.monotonic() - stage_started), 1)
        reason = effort.expired_reason() or effort.exhausted
        plan["complete"] = reason is None
        if reason is not None:
            plan["exhausted_reason"] = reason
            if reason == f"{stage}_stage_deadline_exceeded":
                effort.exhausted = None
        effort.clear_stage_deadline()
        _save_progress(job_id, state, state_lock, out, effort.snapshot())


def _finish(
    job_id: str,
    state: dict[str, Any],
    state_lock: threading.RLock,
    out: Path,
    effort: HuntBudget,
    embedder: PipelineEmbeddingClient | None,
) -> None:
    try:
        if embedder is not None:
            embedder.close()
    finally:
        snapshot = effort.snapshot()
        with state_lock:
            stages = _stage_receipts(out)
            state.update(
                finished=time.time(),
                cost=_cost(stages, snapshot),
                progress={"current": snapshot, "stages": stages},
            )
            _write(job_id, state)


def _run(
    job_id: str,
    search: Search,
    index: str,
    start: float,
    end: float,
    limits: dict[str, float],
    target: tuple[JudgeClient, str],
    knowledge_store: Path | None,
    knowledge_families: Sequence[str] | None,
    embedder: PipelineEmbeddingClient | None,
    judge_enabled: bool = False,
) -> None:
    out = _ROOT / job_id
    out.mkdir(parents=True, exist_ok=True)
    reset_ledger(out)
    state = load(job_id) or {}
    state.update(status="RUNNING", stage="cards", run_dir=str(out), judge_enabled=judge_enabled)
    state_lock = threading.RLock()
    with state_lock:
        _write(job_id, state)
    effort = HuntBudget(limits)
    if embedder is not None:
        embedder.set_job_deadline(lambda: effort.request_deadline)
    effort.on_progress = lambda snapshot: _save_progress(job_id, state, state_lock, out, snapshot)
    bounded_search = BudgetedSearch(search, effort)
    client, model = target
    bounded_client = HuntJobClient(client, effort)
    try:
        began = time.monotonic()
        rejected = preflight(bounded_client, model)
        progress_update(
            out,
            "preflight",
            {"requests": 1, "seconds": round(time.monotonic() - began, 3)},
        )
        _save_progress(job_id, state, state_lock, out, effort.snapshot())
        if rejected is not None:
            raise RuntimeError(f"Pipeline preflight failed for {rejected.model}: {rejected.detail}")
        _execute_stages(
            _stage_actions(
                index,
                start,
                end,
                out,
                bounded_search,
                bounded_client,
                model,
                knowledge_store,
                knowledge_families,
                embedder,
                effort,
                judge_enabled,
            ),
            job_id,
            state,
            state_lock,
            out,
            effort,
        )
        relation = read_json(out / RELATE_FILE).get("receipt")
        relation = relation if isinstance(relation, dict) else {}
        covered = bool(relation.get("coverage_complete"))
        incomplete = [
            plan
            for plan in state.get("stage_plan", [])
            if isinstance(plan, Mapping) and plan.get("complete") is False
        ]
        if incomplete:
            reasons = [
                f"{plan.get('stage')}: {plan.get('exhausted_reason') or 'stage_incomplete'}"
                for plan in incomplete
            ]
            if not covered and relation.get("seeds"):
                reasons.append("relate stage did not cover every notable seed")
            state.update(
                status="PARTIAL",
                stage="partial",
                coverage_complete=False,
                partial_reason="; ".join(reasons),
            )
        elif covered or not relation.get("seeds"):
            state.update(status="COMPLETE", stage="done", coverage_complete=covered)
        else:
            state.update(
                status="PARTIAL",
                stage="relate_partial",
                coverage_complete=covered,
                partial_reason="relate stage did not cover every notable seed",
            )
    except Exception as exc:
        budget_error = isinstance(exc, (HuntBudgetExceededError, ThrottleBudgetExceededError))
        deadline_expired = effort.remaining() <= 0
        if deadline_expired and not effort.exhausted:
            effort.exhausted = effort.expired_reason() or "job_deadline_exceeded"
        status = "PARTIAL" if effort.exhausted or budget_error or deadline_expired else "FAILED"
        if status == "PARTIAL" and not effort.exhausted:
            effort.exhausted = str(exc)
        state.update(
            status=status,
            stage="partial" if status == "PARTIAL" else "failed",
            error=f"{type(exc).__name__}: {exc}",
            coverage_complete=False,
        )
    finally:
        _finish(job_id, state, state_lock, out, effort, embedder)


def _configured_knowledge() -> tuple[Path | None, tuple[str, ...] | None]:
    value = os.environ.get("PORTAL_HUNT_KNOWLEDGE_STORE")
    store = Path(value).expanduser() if value else None
    families = tuple(
        name.strip()
        for name in os.environ.get("PORTAL_HUNT_KNOWLEDGE_FAMILIES", "").split(",")
        if name.strip()
    )
    return store, families or None


def start(
    search: Search,
    index: str,
    start_t: float,
    end_t: float,
    budgets: Mapping[str, float] | None = None,
    *,
    judge_enabled: bool = False,
) -> str:
    if not index.strip() or end_t <= start_t:
        raise ValueError("hunt index and a non-empty time window are required")
    limits = _limits(budgets)
    target = model_from_env()
    if target is None:
        raise RuntimeError(model_requirement())
    store, families = _configured_knowledge()
    if store is not None and not store.is_file():
        raise FileNotFoundError(f"configured hunt knowledge store not found: {store}")
    embedder = embedding_from_env() if store is not None else None
    if store is not None and embedder is None:
        raise RuntimeError(embedding_requirement())
    job_id = "hunt-r2-" + uuid.uuid4().hex[:12]
    state = {
        "job_id": job_id,
        "index": index,
        "status": "QUEUED",
        "stage": "queued",
        "started": time.time(),
        "start": start_t,
        "end": end_t,
        "coverage_complete": False,
        "judge_enabled": judge_enabled,
        "knowledge_store": str(store) if store is not None else None,
        "progress": {"current": {"phase": "queued"}, "stages": {}},
        "cost": {"elapsed_s": 0, "remaining_s": limits["job_seconds"]},
    }
    _write(job_id, state)
    with _lock:
        threading.Thread(
            target=_run,
            args=(
                job_id,
                search,
                index,
                start_t,
                end_t,
                limits,
                target,
                store,
                families,
                embedder,
                judge_enabled,
            ),
            daemon=True,
        ).start()
    return job_id


def _all() -> list[dict[str, Any]]:
    found = [job for path in _ROOT.glob("hunt-r2-*.json") if (job := load(path.stem))]
    return sorted(found, key=lambda job: job.get("started", 0), reverse=True)


def _resolve(job_id: str | None, index: str | None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    found = _all()
    if not job_id and not index:
        return None, {"error": "give job_id or index"}
    if job_id:
        job = next((item for item in found if item.get("job_id") == job_id), None)
    else:
        job = next((item for item in found if item.get("index") == index), None)
    if job is None:
        return None, {"error": f"no R2 hunt for {job_id or index!r}"}
    return job, {}


def _status_result(job: Mapping[str, Any], detail: bool = False) -> dict[str, Any]:
    if not detail:
        progress = _mapping(job.get("progress"))
        current = _mapping(progress.get("current"))
        stage_plan = job.get("stage_plan")
        stage_plan = stage_plan if isinstance(stage_plan, list) else []
        done = sum(bool(_mapping(item).get("complete")) for item in stage_plan)
        total = len(stage_plan) or len(STAGE_ORDER)
        phase = str(current.get("phase") or job.get("stage") or "unknown")
        activity = [phase]
        for key, label in (
            ("query_count", "queries"),
            ("cell_count", "cells"),
            ("event_count", "events"),
        ):
            if current.get(key) is not None:
                activity.append(f"{label}={current[key]}")
        started = float(job.get("started") or time.time())
        elapsed = float(job.get("finished") or time.time()) - started
        status = str(job.get("status") or "UNKNOWN")
        return compact(
            {
                "job_id": job.get("job_id"),
                "index": job.get("index"),
                "status": status,
                "stage": job.get("stage"),
                "stages_done": f"{done}/{total}",
                "elapsed_s": round(max(0.0, elapsed), 1),
                "last_progress": _short(" ".join(activity), 180),
                "partial_reason": _short(job.get("partial_reason"), 180),
                "next": (
                    "Check this job again after it advances."
                    if status.upper() not in TERMINAL_STATUSES
                    else "Read sources, leads, and case 1."
                ),
            }
        )
    result = {
        key: job[key]
        for key in (
            "job_id",
            "index",
            "status",
            "stage",
            "started",
            "finished",
            "error",
            "coverage_complete",
            "coverage_reason",
            "partial_reason",
            "judge_enabled",
            "progress",
            "cost",
            "knowledge_store",
            "stage_plan",
            "judge_selection",
        )
        if key in job
    }
    result["elapsed_s"] = round(job.get("finished", time.time()) - job["started"], 1)
    return compact(result)


def _running_view(job: Mapping[str, Any]) -> dict[str, Any]:
    return _status_result(job)


def _is_terminal(job: Mapping[str, Any]) -> bool:
    return str(job.get("status", "")).upper() in TERMINAL_STATUSES


def status(
    job_id: str | None = None,
    index: str | None = None,
    wait_seconds: float = 0.0,
    detail: bool = False,
) -> dict[str, Any]:
    wait_s = min(max(float(wait_seconds), 0.0), STATUS_WAIT_MAX_S)
    deadline = time.monotonic() + wait_s
    while True:
        job, out = _resolve(job_id, index)
        if job is None:
            return out
        remaining = deadline - time.monotonic()
        if _is_terminal(job) or remaining <= 0:
            return _status_result(job, detail=detail)
        time.sleep(min(STATUS_POLL_S, remaining))


def result_bytes(value: Any) -> int:
    """Size of a tool result under the reviewer's canonical compact JSON encoding."""
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _paginate(
    page: dict[str, Any],
    *,
    offset: int,
    total: int,
    returned: int,
    total_key: str | None,
    omitted_key: str,
    returned_key: str | None = None,
) -> None:
    if total_key is not None:
        page[total_key] = total
    if returned_key is not None:
        page[returned_key] = returned
    omitted = max(0, total - offset - returned)
    page[omitted_key] = omitted
    if omitted:
        page["truncated"] = True
    if offset + returned < total:
        page["next_offset"] = offset + returned


def _page_view(
    envelope: dict[str, Any],
    items_key: str,
    window: Sequence[Mapping[str, Any]],
    build: Callable[[Mapping[str, Any], int], dict[str, Any]],
    *,
    total: int,
    offset: int,
    total_key: str | None,
    omitted_key: str,
    returned_key: str | None = None,
    byte_limit: int | None = None,
) -> dict[str, Any]:
    """One page of items in rank order within byte_limit, or the single overflowing item."""
    if offset < 0:
        return {"error": "offset must be 0 or greater"}
    chosen: list[dict[str, Any]] = []
    overflow: dict[str, Any] | None = None
    for position, row in enumerate(window):
        item = build(row, offset + position)
        trial = {**envelope, items_key: [*chosen, item]}
        _paginate(
            trial,
            offset=offset,
            total=total,
            returned=len(chosen) + 1,
            total_key=total_key,
            omitted_key=omitted_key,
            returned_key=returned_key,
        )
        if byte_limit is not None and result_bytes(trial) > byte_limit:
            if not chosen:
                overflow = trial
            break
        chosen.append(item)
    if overflow is not None:
        return overflow
    page = {**envelope, items_key: chosen}
    _paginate(
        page,
        offset=offset,
        total=total,
        returned=len(chosen),
        total_key=total_key,
        omitted_key=omitted_key,
        returned_key=returned_key,
    )
    return page


def leads_view(
    job_id: str | None = None,
    index: str | None = None,
    n: int = LEADS_VIEW_DEFAULT,
    offset: int = 0,
    byte_limit: int | None = None,
) -> dict[str, Any]:
    job, out = _resolve(job_id, index)
    if job is None:
        return out
    if not _is_terminal(job):
        return _running_view(job)
    rows = _ranked_rows(Path(str(job["run_dir"])))
    want = max(0, min(n, LEADS_VIEW_LIMIT))
    return compact(
        _page_view(
            {"job_id": job["job_id"], "index": job["index"]},
            "leads",
            rows[offset : offset + want],
            lambda row, position: _lead(row, position + 1),
            total=len(rows),
            offset=offset,
            total_key="total_leads",
            omitted_key="omitted_leads",
            returned_key="returned_leads",
            byte_limit=byte_limit,
        )
    )


def _ranked_rows(run_dir: Path) -> list[dict[str, Any]]:
    rows = _read_rows(run_dir / NOTABLES_FILE)
    report = read_json(run_dir / RERANK_FILE)
    order = report.get("order")
    if not isinstance(order, list):
        return rows
    receipt = _mapping(report.get("receipt"))
    keys = receipt.get("content_keys")
    keys = keys if isinstance(keys, list) else []
    indices = [
        index
        for index in order
        if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(rows)
    ]
    indices = list(dict.fromkeys(indices))
    indices.extend(index for index in range(len(rows)) if index not in indices)
    ranked = [dict(rows[index]) for index in indices]
    for index, row in zip(indices, ranked, strict=True):
        if not row.get("content_key") and index < len(keys):
            row["content_key"] = keys[index]
    return ranked


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
    return rows


def _mark_cut(item: dict[str, Any], key: str, raw: Any) -> None:
    value = item.get(key)
    if isinstance(raw, str) and value is not None and value != raw:
        item[f"{key}_truncated"] = True


def _lead(row: Mapping[str, Any], rank: int) -> dict[str, Any]:
    evidence = [item for item in row.get("evidence", []) if isinstance(item, Mapping)]
    lead = {
        "rank": rank,
        "notable_id": _one_line(row.get("notable_id"), 48),
        "generator": _one_line(row.get("generator"), 32),
        "source": _one_line(row.get("source_id"), 60),
        "why": _one_line(row.get("why"), 80),
        "evidence_query": _one_line(evidence[0].get("query"), 100) if evidence else None,
    }
    _mark_cut(lead, "notable_id", row.get("notable_id"))
    _mark_cut(lead, "generator", row.get("generator"))
    _mark_cut(lead, "source", row.get("source_id"))
    _mark_cut(lead, "why", row.get("why"))
    if evidence:
        _mark_cut(lead, "evidence_query", evidence[0].get("query"))
    return lead


def lead_detail(job_id: str | None, index: str | None, notable_id: str) -> dict[str, Any]:
    job, out = _resolve(job_id, index)
    if job is None:
        return out
    if not _is_terminal(job):
        return _running_view(job)
    rows = _ranked_rows(Path(str(job["run_dir"])))
    rank = 0
    row: dict[str, Any] | None = None
    for position, item in enumerate(rows, 1):
        if item.get("notable_id") == notable_id:
            rank, row = position, item
            break
    if row is None:
        return {"job_id": job["job_id"], "error": f"no lead {notable_id!r}"}
    evidence = [entry for entry in row.get("evidence", []) if isinstance(entry, Mapping)]
    return compact(
        {
            "job_id": job["job_id"],
            "rank": rank,
            "notable_id": row.get("notable_id"),
            "generator": row.get("generator"),
            "source": row.get("source_id"),
            "why": row.get("why"),
            "evidence_query": evidence[0].get("query") if evidence else None,
        }
    )


def _short(value: Any, limit: int) -> Any:
    if not isinstance(value, str):
        return value
    return value[:limit]


def _one_line(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    return " ".join(value.split())[:limit] or None


def _case(job: Mapping[str, Any], case_no: int) -> tuple[Mapping[str, Any], dict[str, Any] | None]:
    cases = read_json(Path(str(job["run_dir"])) / RELATE_FILE).get("cases")
    cases = cases if isinstance(cases, list) else []
    if not 1 <= case_no <= len(cases):
        return {}, {"job_id": job["job_id"], "error": f"case {case_no} not in 1..{len(cases)}"}
    return _mapping(cases[case_no - 1]), None


def case_view(
    job_id: str | None = None,
    index: str | None = None,
    case_no: int = 1,
    n: int = 2,
    offset: int = 0,
    byte_limit: int | None = None,
) -> dict[str, Any]:
    job, out = _resolve(job_id, index)
    if job is None:
        return out
    if not _is_terminal(job):
        return _running_view(job)
    case, failure = _case(job, case_no)
    if failure is not None:
        return failure
    evidence = case.get("evidence")
    evidence = evidence if isinstance(evidence, list) else []
    want = max(0, min(n, LEADS_VIEW_LIMIT))
    return compact(
        _page_view(
            {
                "job_id": job["job_id"],
                "case": case_no,
                "case_id": _one_line(case.get("case_id"), 48),
                "anchor": _one_line(case.get("anchor_entity"), 96),
                "score": case.get("score"),
                "seed_count": len(case.get("seed_notables") or []),
                "related_count": len(case.get("related_notables") or []),
            },
            "evidence",
            evidence[offset : offset + want],
            _case_evidence,
            total=len(evidence),
            offset=offset,
            total_key="evidence_count",
            omitted_key="evidence_omitted",
            byte_limit=byte_limit,
        )
    )


def _case_evidence(row: Mapping[str, Any], _position: int) -> dict[str, Any]:
    item = _mapping(row)
    shown = {
        "source": _one_line(item.get("source"), 48),
        "line": _one_line(item.get("line"), 150),
    }
    _mark_cut(shown, "source", item.get("source"))
    _mark_cut(shown, "line", item.get("line"))
    return shown


def evidence_detail(
    job_id: str | None, index: str | None, case_no: int, evidence_index: int
) -> dict[str, Any]:
    job, out = _resolve(job_id, index)
    if job is None:
        return out
    if not _is_terminal(job):
        return _running_view(job)
    case, failure = _case(job, case_no)
    if failure is not None:
        return failure
    evidence = case.get("evidence")
    evidence = evidence if isinstance(evidence, list) else []
    if not 0 <= evidence_index < len(evidence):
        return {
            "job_id": job["job_id"],
            "case": case_no,
            "error": f"evidence {evidence_index} not in 0..{len(evidence) - 1}",
        }
    row = _mapping(evidence[evidence_index])
    return compact(
        {
            "job_id": job["job_id"],
            "case": case_no,
            "evidence_index": evidence_index,
            "source": row.get("source"),
            "line": row.get("line"),
        }
    )


def sources_view(
    job_id: str | None = None,
    index: str | None = None,
    n: int = 3,
    offset: int = 0,
    byte_limit: int | None = None,
) -> dict[str, Any]:
    job, out = _resolve(job_id, index)
    if job is None:
        return out
    if not _is_terminal(job):
        return _running_view(job)
    payload = read_json(Path(str(job["run_dir"])) / SOURCES_FILE)
    cards = payload.get("cards")
    cards = cards if isinstance(cards, list) else []
    unknown = [
        card for card in cards if isinstance(card, Mapping) and not bool(card.get("understood"))
    ]
    totals = _mapping(payload.get("totals"))
    understood = sum(
        1 for card in cards if isinstance(card, Mapping) and bool(card.get("understood"))
    )
    want = max(0, min(n, LEADS_VIEW_LIMIT))
    return compact(
        _page_view(
            {
                "job_id": job["job_id"],
                "index": job["index"],
                "counts": {
                    "sources": totals.get("sources", 0),
                    "cards": totals.get("cards", len(cards)),
                    "understood": totals.get("understood", understood),
                    "not_understood": len(unknown),
                },
            },
            "not_understood",
            unknown[offset : offset + want],
            _source_card,
            total=len(unknown),
            offset=offset,
            total_key=None,
            omitted_key="not_understood_omitted",
            byte_limit=byte_limit,
        )
    )


def _source_card(row: Mapping[str, Any], _position: int) -> dict[str, Any]:
    item = {
        "source": _one_line(row.get("source_id"), 64),
        "kind": _one_line(row.get("kind"), 24),
        "reason": _one_line(row.get("reason"), 96),
    }
    _mark_cut(item, "source", row.get("source_id"))
    _mark_cut(item, "kind", row.get("kind"))
    _mark_cut(item, "reason", row.get("reason"))
    return item


def card_detail(job_id: str | None, index: str | None, source: str) -> dict[str, Any]:
    job, out = _resolve(job_id, index)
    if job is None:
        return out
    if not _is_terminal(job):
        return _running_view(job)
    cards = read_json(Path(str(job["run_dir"])) / SOURCES_FILE).get("cards")
    cards = cards if isinstance(cards, list) else []
    matches = _matching_cards(cards, source)
    if not matches:
        return {"job_id": job["job_id"], "error": f"no source card {source!r}"}
    return compact(
        {
            "job_id": job["job_id"],
            "cards": [
                {
                    "source": row.get("source_id"),
                    "kind": row.get("kind"),
                    "reason": row.get("reason"),
                    "understood": bool(row.get("understood")),
                }
                for row in matches
            ],
        }
    )


def _matching_cards(cards: Sequence[Any], source: str) -> list[Mapping[str, Any]]:
    named = [
        card for card in cards if isinstance(card, Mapping) and card.get("source_id") == source
    ]
    if named:
        return named
    return [
        card
        for card in cards
        if isinstance(card, Mapping)
        and isinstance(card.get("source_id"), str)
        and card["source_id"].startswith(source)
    ]


def indexes_view(
    rows: Sequence[Mapping[str, Any]],
    n: int = 3,
    offset: int = 0,
    byte_limit: int | None = None,
) -> dict[str, Any]:
    want = max(0, min(n, LEADS_VIEW_LIMIT))
    return compact(
        _page_view(
            {},
            "indexes",
            rows[offset : offset + want],
            _index_item,
            total=len(rows),
            offset=offset,
            total_key="total_indexes",
            omitted_key="indexes_omitted",
            byte_limit=byte_limit,
        )
    )


def _index_item(row: Mapping[str, Any], _position: int) -> dict[str, Any]:
    name = str(row.get("index") or "")
    item = {"index": name[:80], "events": row.get("count")}
    if len(name) > 80:
        item["index_truncated"] = True
    return item
