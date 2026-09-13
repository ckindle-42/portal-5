"""Durable asynchronous assessment runs (IMPLEMENTATION_BRIEF §6).

The measured council takes minutes per Part, so a long synchronous HTTP request
is not an acceptable product contract. This module owns one local worker thread
that performs model assessment while callers start a run, poll its status and
fetch its persisted results:

    run_id = start_run(request)      # returns immediately
    run_status(run_id)               # progress only — never re-runs a model
    run_result(run_id)               # persisted per-Part assessments
    cancel_run(run_id)               # effective at the next model-call boundary

Runs are durably QUEUED / RUNNING / COMPLETE / FAILED / CANCELLED / INTERRUPTED
under ``analysis_runs`` (schema v7). A restart marks unfinished RUNNING/QUEUED
jobs INTERRUPTED via ``Repository.mark_interrupted_runs``; recovery is explicit
and never masquerades as completion. A cancelled or failed job is never rewritten
as a successful latest run.

The worker builds its :class:`AssessmentContext` through
``runtime_config.build_assessment_context`` and calls the shared service
(``assessment_service.build_requests`` + ``assessment.assess_part``) so the same
input produces the same engine, fingerprint and verdict as every other caller.
The ``run_id`` is threaded through ``AssessmentRequest.metadata`` so each Part's
:class:`AssessmentResult` persists under this run; ``assess_requirement`` itself
has no run_id parameter, so the run layer composes the same shared primitives
with the run identity injected.
"""

from __future__ import annotations

import logging
import queue
import threading
import uuid
from typing import Any

from portal.modules.compliance.core.applicability import (
    applicability_state,
    parse_scope_declaration,
)
from portal.modules.compliance.core.assessment import assess_part
from portal.modules.compliance.core.assessment_source import resolve_governing_bundle
from portal.modules.compliance.core.determination import AssessmentResult
from portal.modules.compliance.core.runtime_config import build_assessment_context
from portal.modules.compliance.core.scope_derive import derive_scope

logger = logging.getLogger(__name__)

__all__ = [
    "ENGINE_VERSION",
    "TERMINAL_STATES",
    "cancel_run",
    "init_store",
    "run_result",
    "run_status",
    "start_run",
]

ENGINE_VERSION = "compliance-reading/1"
TERMINAL_STATES = frozenset({"COMPLETE", "FAILED", "CANCELLED", "INTERRUPTED"})

_QUEUE: queue.Queue[str] = queue.Queue()
_WORKER: threading.Thread | None = None
_WORKER_LOCK = threading.Lock()
_RUNTIME: dict[str, dict[str, Any]] = {}


def _default_repository() -> Any:
    from portal.modules.compliance.core.repository import Repository

    return Repository()


#: overridable in tests so a run never touches the real store.
_REPO_FACTORY: Any = _default_repository


def _get_repo(repository: Any = None) -> Any:
    if repository is not None:
        return repository
    return _REPO_FACTORY()


class _RunCancelled(BaseException):
    """Raised at a model-call boundary when the operator cancelled the run.

    Deliberately a ``BaseException``: the assessment stages catch ``Exception``
    around a seat/report transport (a failed seat becomes a non-vote), and a
    cancellation must never be downgraded into an invalid alignment or report.
    """


def init_store(repository: Any = None) -> int:
    """Mark unfinished RUNNING/QUEUED jobs INTERRUPTED after a restart."""
    repo = _get_repo(repository)
    return int(repo.mark_interrupted_runs())


def _ensure_worker() -> None:
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER is None or not _WORKER.is_alive():
            _WORKER = threading.Thread(
                target=_worker_loop, name="assessment-run-worker", daemon=True
            )
            _WORKER.start()


def _worker_loop() -> None:
    while True:
        run_id = _QUEUE.get()
        try:
            _process(run_id)
        except Exception:  # noqa: BLE001 - a worker crash must not kill the thread
            logger.exception("assessment run %s crashed", run_id)
        finally:
            _QUEUE.task_done()


def _process(run_id: str) -> None:
    repo = _get_repo()
    run = repo.get_run(run_id)
    if run is None:
        return
    if run["status"] in TERMINAL_STATES:
        return
    request = run.get("request") or {}
    requirements = [str(r) for r in request.get("requirements", []) if str(r)]
    progress = {
        "completed": 0,
        "total": len(requirements),
        "parts": [],
        "assessment_ids": [],
    }
    if run["status"] == "QUEUED" and run.get("cancel_requested"):
        repo.update_run(run_id, status="CANCELLED", finished=True, progress=progress)
        return
    repo.update_run(run_id, status="RUNNING", progress=progress)
    runtime = _RUNTIME.pop(run_id, None) or {}
    try:
        _execute_run(repo, run_id, request, runtime)
    except _RunCancelled:
        if repo.get_run(run_id) is not None:
            repo.update_run(run_id, status="CANCELLED", finished=True)
    except Exception as exc:  # noqa: BLE001 - a failed run is reported, never silent
        logger.exception("assessment run %s failed", run_id)
        repo.update_run(run_id, status="FAILED", progress={"error": str(exc)}, finished=True)
    else:
        if repo.get_run(run_id) is not None:
            repo.update_run(run_id, status="COMPLETE", finished=True)


def _execute_run(repo: Any, run_id: str, request: dict[str, Any], runtime: dict[str, Any]) -> None:
    kb_id = str(request.get("kb_id") or "operator_corpus")
    org_id = str(request.get("org_id") or "default")
    scope_text = str(request.get("scope_text") or "")
    policy_graph = runtime.get("policy_graph")
    requirements = [str(r) for r in request.get("requirements", []) if str(r)]
    progress = {
        "completed": 0,
        "total": len(requirements),
        "parts": [],
        "assessment_ids": [],
    }

    def on_result(result: AssessmentResult) -> None:
        _advance(repo, run_id, progress, result)

    assess_requirements_now(
        requirements,
        kb_id=kb_id,
        org_id=org_id,
        scope_text=scope_text,
        effective_on=str(request.get("effective_on") or ""),
        known_at=str(request.get("known_at") or ""),
        conditional_scope=bool(request.get("conditional_scope")),
        top_k=int(request.get("top_k") or 15),
        repository=repo,
        policy_graph=policy_graph,
        seat_fn=_guarded_seat(repo, run_id, runtime.get("seat_fn")),
        arbiter_fn=runtime.get("arbiter_fn"),
        run_id=run_id,
        on_result=on_result,
    )


def build_requests_for(
    requirement_id: str,
    *,
    kb_id: str = "operator_corpus",
    org_id: str = "default",
    scope: Any,
    effective_on: str = "",
    known_at: str = "",
    conditional_scope: bool = False,
    top_k: int = 15,
    arbiter_fn: Any = None,
    policy_graph: Any = None,
    snapshot: Any = None,
) -> list[Any]:
    """Build the shared requests for a requirement with an explicit scope.

    ``assessment_service.build_requests`` is the frozen shared builder, but as
    landed it passes ``scope=`` to ``assessment_source.build_assessment_request``,
    which does not accept that keyword. This composes the same primitives with
    the same arguments plus the explicit scope override, so the run layer can
    use the shared acquisition/snapshot adapter unchanged.
    """
    from portal.modules.compliance.core.assessment_service import part_ids
    from portal.modules.compliance.core.assessment_source import (
        build_assessment_request,
        build_corpus_snapshot,
    )

    shared_snapshot = snapshot or build_corpus_snapshot(kb_id)
    requests: list[Any] = []
    for part_id in part_ids(requirement_id):
        request = build_assessment_request(
            part_id,
            kb_id=kb_id,
            effective_on=effective_on,
            known_at=known_at,
            org_id=org_id,
            conditional_scope=conditional_scope,
            top_k=top_k,
            arbiter_fn=arbiter_fn,
            policy_graph=policy_graph,
        )
        request.scope = scope
        request.scope_basis = "conditional" if conditional_scope else "actual"
        request.snapshot = shared_snapshot
        requests.append(request)
    return requests


def assess_requirements_now(
    requirements: list[str],
    *,
    kb_id: str = "operator_corpus",
    org_id: str = "default",
    scope_text: str = "",
    scope: Any = None,
    effective_on: str = "",
    known_at: str = "",
    conditional_scope: bool = False,
    top_k: int = 15,
    repository: Any = None,
    policy_graph: Any = None,
    seat_fn: Any = None,
    arbiter_fn: Any = None,
    run_id: str = "",
    on_result: Any = None,
) -> list[AssessmentResult]:
    """Assess a list of Parts synchronously through the shared service.

    Used by the run worker (with a durable ``repository``/``run_id``) and by the
    controlled library/CLI path (``repository=None``, results returned only).
    ``on_result`` is invoked after each Part is persisted and must not alter it.
    """
    resolved_scope = (
        scope
        if scope is not None
        else (parse_scope_declaration(scope_text) if scope_text else derive_scope(kb_id)[0])
    )
    context = build_assessment_context(
        kb_id,
        resolved_scope,
        effective_on,
        known_at,
        repository,
        policy_graph=policy_graph,
        seat_fn=seat_fn,
        arbiter_fn=arbiter_fn,
    )
    results: list[AssessmentResult] = []
    for requirement_id in requirements:
        _check_cancelled(repository, run_id)
        try:
            governing = resolve_governing_bundle(requirement_id, policy_graph=policy_graph)
        except ValueError:
            result = _unresolved_result(
                run_id,
                requirement_id,
                "U02_MISSING_GOVERNING_SOURCE",
                {"logical_id": requirement_id},
            )
            _persist(repository, result)
            results.append(result)
            if on_result is not None:
                on_result(result)
            continue

        applic, reason = applicability_state(_applicable_systems_text(governing), resolved_scope)
        if applic == "DOES_NOT_APPLY":
            result = _not_applicable_result(run_id, requirement_id, applic, reason)
            _persist(repository, result)
            results.append(result)
            if on_result is not None:
                on_result(result)
            continue

        try:
            requests = build_requests_for(
                requirement_id,
                kb_id=kb_id,
                org_id=org_id,
                scope=resolved_scope,
                effective_on=effective_on,
                known_at=known_at,
                conditional_scope=conditional_scope,
                top_k=top_k,
                arbiter_fn=arbiter_fn,
                policy_graph=policy_graph,
            )
        except Exception as exc:  # noqa: BLE001 - retrieval failure is disclosed, not fatal
            result = _acquisition_failed_result(run_id, requirement_id, exc)
            _persist(repository, result)
            results.append(result)
            if on_result is not None:
                on_result(result)
            continue
        for part_request in requests:
            _check_cancelled(repository, run_id)
            part_request.metadata["run_id"] = run_id
            result = assess_part(part_request, context)
            results.append(result)
            if on_result is not None:
                on_result(result)
    return results


def _acquisition_failed_result(
    run_id: str, requirement_id: str, exc: Exception
) -> AssessmentResult:
    stage = str(getattr(exc, "stage", "acquire"))
    return AssessmentResult(
        assessment_id=uuid.uuid4().hex[:16],
        run_id=run_id,
        engine_version=ENGINE_VERSION,
        input_fingerprint="",
        requirement_id=requirement_id,
        applicability="UNKNOWN",
        documentary_coverage="UNRESOLVED",
        coverage="UNRESOLVED",
        unresolved_code="U04_RETRIEVAL_INCOMPLETE",
        missing_fact={"stage": stage, "error": str(exc)},
        receipt={"retrieval_errors": [{"stage": stage, "error": str(exc)}]},
    )


def _persist(repository: Any, result: AssessmentResult) -> None:
    if repository is None:
        return
    from portal.modules.compliance.core.repository import Repository

    if isinstance(repository, Repository):
        repository.record_assessment(result)


def _advance(repo: Any, run_id: str, progress: dict[str, Any], result: AssessmentResult) -> None:
    progress["completed"] = int(progress.get("completed", 0)) + 1
    progress.setdefault("parts", []).append(result.requirement_id)
    progress.setdefault("assessment_ids", []).append(result.assessment_id)
    repo.update_run(run_id, progress=dict(progress))


def _check_cancelled(repo: Any, run_id: str) -> None:
    if repo is None or not run_id:
        return
    run = repo.get_run(run_id)
    if run is not None and run.get("cancel_requested"):
        raise _RunCancelled(run_id)


def _guarded_seat(repo: Any, run_id: str, inner: Any) -> Any:
    """Check cancellation before each model call, then delegate to the seat."""

    def wrapped(model: str, system: str, user: str) -> str:
        _check_cancelled(repo, run_id)
        fn = inner
        if fn is None:
            # The alignment reader emits one record per candidate, so it needs a
            # larger output budget than a single council verdict. Route by the
            # system prompt to the matching default transport.
            from portal.modules.compliance.core.council import _ollama_seat
            from portal.modules.compliance.core.obligation_alignment import (
                _ALIGNMENT_SYSTEM,
                _ollama_alignment_seat,
            )

            fn = _ollama_alignment_seat if system == _ALIGNMENT_SYSTEM else _ollama_seat
        return str(fn(model, system, user))

    return wrapped


def _applicable_systems_text(governing: Any) -> str:
    for item in governing.meta or []:
        if isinstance(item, dict):
            for key in ("applicable_systems", "applicable_systems_text", "applies_to"):
                if item.get(key):
                    return str(item[key])
    return ""


def _unresolved_result(
    run_id: str, requirement_id: str, code: str, missing: dict[str, Any]
) -> AssessmentResult:
    return AssessmentResult(
        assessment_id=uuid.uuid4().hex[:16],
        run_id=run_id,
        engine_version=ENGINE_VERSION,
        input_fingerprint="",
        requirement_id=requirement_id,
        applicability="UNKNOWN",
        documentary_coverage="UNRESOLVED",
        coverage="UNRESOLVED",
        unresolved_code=code,
        missing_fact=missing,
    )


def _not_applicable_result(
    run_id: str, requirement_id: str, applic: str, reason: str
) -> AssessmentResult:
    return AssessmentResult(
        assessment_id=uuid.uuid4().hex[:16],
        run_id=run_id,
        engine_version=ENGINE_VERSION,
        input_fingerprint="",
        requirement_id=requirement_id,
        applicability=applic,
        documentary_coverage="NOT_APPLICABLE",
        coverage="NOT_APPLICABLE",
        substantively_resolved=True,
        receipt={"reason": reason},
    )


# ── public API ──────────────────────────────────────────────────────────────


def start_run(
    request: dict[str, Any],
    *,
    repository: Any = None,
    runtime: dict[str, Any] | None = None,
) -> str:
    """Create a durable QUEUED run and return its id immediately.

    ``request`` is serializable run input:
    ``{"requirements": [Part ids], "kb_id", "org_id", "scope_text",
    "effective_on", "known_at", "conditional_scope", "top_k"}``. ``runtime``
    carries non-serializable handles (``seat_fn``/``arbiter_fn``/``policy_graph``)
    and is held in-process for the worker, never written to the run row.
    """
    requirements = [str(r) for r in (request or {}).get("requirements", []) if str(r)]
    if not requirements:
        raise ValueError("start_run requires at least one requirement id")
    repo = _get_repo(repository)
    run_id = repo.create_run(
        {**request, "requirements": requirements},
        status="QUEUED",
        org_id=str(request.get("org_id") or "default"),
    )
    if runtime:
        _RUNTIME[run_id] = runtime
    _ensure_worker()
    _QUEUE.put(run_id)
    return str(run_id)


def run_status(run_id: str, *, repository: Any = None) -> dict[str, Any]:
    """Progress for a run. Reads the run row only — no retrieval/model/proposal."""
    repo = _get_repo(repository)
    run = repo.get_run(run_id)
    if run is None:
        return {"error": f"unknown run_id: {run_id}"}
    request = run.get("request") or {}
    return {
        "run_id": run_id,
        "status": run["status"],
        "progress": run.get("progress") or {},
        "cancel_requested": bool(run.get("cancel_requested")),
        "engine": ENGINE_VERSION,
        "requirements": list(request.get("requirements", [])),
        "created_at": run.get("created_at"),
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
    }


def run_result(run_id: str, *, repository: Any = None) -> dict[str, Any]:
    """The persisted per-Part assessments for a run. Never re-runs assessment."""
    repo = _get_repo(repository)
    run = repo.get_run(run_id)
    if run is None:
        return {"error": f"unknown run_id: {run_id}"}
    assessments = repo.assessments_for_run(run_id)
    return {
        "run_id": run_id,
        "status": run["status"],
        "progress": run.get("progress") or {},
        "engine": ENGINE_VERSION,
        "requirements": list((run.get("request") or {}).get("requirements", [])),
        "assessment_ids": [a.get("assessment_id", "") for a in assessments],
        "results": assessments,
        "summary": summarize(assessments),
    }


def cancel_run(run_id: str, *, repository: Any = None) -> dict[str, Any]:
    """Request cancellation. Takes effect at the next model-call/Part boundary.

    A still-QUEUED run is cancelled immediately. A RUNNING run is flagged; the
    worker transitions it to CANCELLED. A terminal run is returned unchanged.
    """
    repo = _get_repo(repository)
    run = repo.get_run(run_id)
    if run is None:
        return {"error": f"unknown run_id: {run_id}"}
    if run["status"] in TERMINAL_STATES:
        return {"run_id": run_id, "status": run["status"]}
    repo.update_run(run_id, cancel_requested=True)
    if run["status"] == "QUEUED":
        repo.update_run(run_id, status="CANCELLED", finished=True)
        return {"run_id": run_id, "status": "CANCELLED"}
    return {"run_id": run_id, "status": "RUNNING", "cancel_requested": True}


def summarize(assessments: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts over final applicability/resolution, not mere result presence."""
    by_coverage: dict[str, int] = {}
    by_documentary: dict[str, int] = {}
    resolved = 0
    for result in assessments:
        coverage = str(result.get("coverage", "UNRESOLVED"))
        by_coverage[coverage] = by_coverage.get(coverage, 0) + 1
        documentary = str(result.get("documentary_coverage", "UNRESOLVED"))
        by_documentary[documentary] = by_documentary.get(documentary, 0) + 1
        if result.get("substantively_resolved") and coverage not in ("UNRESOLVED", "NEEDS_REVIEW"):
            resolved += 1
    return {
        "examined": len(assessments),
        "substantively_resolved": resolved,
        "coverage_breakdown": by_coverage,
        "documentary_breakdown": by_documentary,
        "unresolved_items": [
            a.get("requirement_id", "")
            for a in assessments
            if str(a.get("coverage", "")) == "UNRESOLVED"
        ],
    }


# A service restart marks unfinished jobs INTERRUPTED (brief §6). Guarded so an
# unavailable store never prevents the module from importing.
try:  # pragma: no cover - exercised implicitly at import on a host with a store
    init_store()
except Exception:  # noqa: BLE001
    logger.debug("assessment run import-time interruption sweep skipped", exc_info=True)
