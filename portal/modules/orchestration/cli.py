"""``portal arm`` commands for hand-written orchestration tasks."""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

orchestration_app = typer.Typer(help="Offline-first verified task orchestration.")
digests_app = typer.Typer(help="Host seat-digest file for the arm.")
orchestration_app.add_typer(digests_app, name="digests")


def register(app: typer.Typer) -> None:
    app.add_typer(orchestration_app, name="arm")


@orchestration_app.command("submit")
def submit(
    plan_file: Annotated[Path, typer.Argument(exists=True, readable=True)],
    tasks_dir: Annotated[Path | None, typer.Option("--tasks-dir")] = None,
    source_dir: Annotated[Path | None, typer.Option("--source-dir")] = None,
) -> None:
    """Submit a hand-written YAML or JSON plan and run ready bites."""
    _require_enabled()
    service = _service(tasks_dir)
    raw: Any = yaml.safe_load(plan_file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        typer.echo("plan must contain an object", err=True)
        raise typer.Exit(code=2)
    try:
        result = service.submit(raw, source_dir or plan_file.resolve().parent)
    except Exception as exc:
        typer.echo(f"arm submit failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(str(result / "receipt.json"))


@orchestration_app.command("goal")
def goal(
    task_id: Annotated[str, typer.Argument()],
    discipline: Annotated[str, typer.Argument()],
    goal_text: Annotated[str, typer.Argument()],
    tasks_dir: Annotated[Path | None, typer.Option("--tasks-dir")] = None,
    source_dir: Annotated[Path | None, typer.Option("--source-dir")] = None,
) -> None:
    """Plan and run a goal on the configured Deep and Fast seats."""
    _require_enabled()
    try:
        result = _service(tasks_dir).submit_goal(
            task_id=task_id,
            discipline=discipline,
            goal=goal_text,
            source_dir=source_dir or Path.cwd(),
            unattended=True,
        )
    except Exception as exc:
        typer.echo(f"arm goal failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(str(result / "receipt.json"))


@orchestration_app.command("resume")
def resume(
    task_id: Annotated[str, typer.Argument()],
    tasks_dir: Annotated[Path | None, typer.Option("--tasks-dir")] = None,
    override: Annotated[
        bool, typer.Option("--override", help="Adopt changed build or model identity.")
    ] = False,
) -> None:
    """Resume a task after checking its build and model digests."""
    _require_enabled()
    try:
        result = _service(tasks_dir).resume(task_id, override=override)
    except Exception as exc:
        typer.echo(f"arm resume failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(str(result / "receipt.json"))


@orchestration_app.command("status")
def status(
    task_id: Annotated[str, typer.Argument()],
    tasks_dir: Annotated[Path | None, typer.Option("--tasks-dir")] = None,
) -> None:
    """Print the task receipt or current ledger states."""
    task_dir = (tasks_dir or _tasks_dir()) / task_id
    receipt = task_dir / "receipt.json"
    if receipt.is_file():
        typer.echo(receipt.read_text(encoding="utf-8"))
        return
    ledger_path = task_dir / "ledger.db"
    if not ledger_path.is_file():
        typer.echo(f"no task: {task_id}", err=True)
        raise typer.Exit(code=1)
    import sqlite3

    with sqlite3.connect(ledger_path) as db:
        rows = db.execute("SELECT bite_id, state, attempts FROM bite ORDER BY rowid").fetchall()
    typer.echo(
        json.dumps([{"bite_id": x[0], "state": x[1], "attempts": x[2]} for x in rows], indent=2)
    )


@orchestration_app.command("shadow-summary")
def shadow_summary(
    task_id: Annotated[str | None, typer.Argument()] = None,
    tasks_dir: Annotated[Path | None, typer.Option("--tasks-dir")] = None,
) -> None:
    """Summarize one task's shadow comparisons, or all tasks when no id is given."""
    from portal.modules.orchestration.shadow import summarize_all, summarize_comparisons

    root = tasks_dir or _tasks_dir()
    try:
        summary = summarize_comparisons(root / task_id) if task_id else summarize_all(root)
    except OSError as exc:
        typer.echo(f"shadow summary unavailable: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(summary, indent=2))


@orchestration_app.command("enqueue")
def enqueue(
    plan_file: Annotated[Path, typer.Argument(exists=True, readable=True)],
    tasks_dir: Annotated[Path | None, typer.Option("--tasks-dir")] = None,
    source_dir: Annotated[Path | None, typer.Option("--source-dir")] = None,
) -> None:
    """Persist a hand-written plan for the overnight queue."""
    _require_enabled()
    from portal.modules.orchestration.planner import validate_execution_plan
    from portal.modules.orchestration.queue import QueueLedger
    from portal.modules.orchestration.service import load_arm_config

    try:
        raw = yaml.safe_load(plan_file.read_text(encoding="utf-8"))
        root = source_dir or plan_file.resolve().parent
        plan = validate_execution_plan(raw, load_arm_config(_arm_config_path()), root)
        with QueueLedger(tasks_dir or _tasks_dir()) as ledger:
            ledger.enqueue(plan, root)
    except Exception as exc:
        typer.echo(f"arm enqueue failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"queued {plan.task_id}")


@orchestration_app.command("enqueue-template")
def enqueue_template(
    task_id: Annotated[str, typer.Argument()],
    discipline: Annotated[str, typer.Argument()],
    template_key: Annotated[str, typer.Argument()],
    parameters: Annotated[list[str] | None, typer.Option("--param")] = None,
    tasks_dir: Annotated[Path | None, typer.Option("--tasks-dir")] = None,
    source_dir: Annotated[Path | None, typer.Option("--source-dir")] = None,
) -> None:
    """Instantiate a configured plan template and enqueue its validated plan."""
    _require_enabled()
    from portal.modules.orchestration.planner import instantiate_plan_template
    from portal.modules.orchestration.queue import QueueLedger
    from portal.modules.orchestration.service import load_arm_config

    try:
        values = _template_parameters(parameters or [])
        config = load_arm_config(_arm_config_path())
        plan = instantiate_plan_template(
            config,
            template_key=template_key,
            discipline_key=discipline,
            task_id=task_id,
            parameters=values,
            source_dir=source_dir or Path.cwd(),
        )
        with QueueLedger(tasks_dir or _tasks_dir()) as ledger:
            ledger.enqueue(plan, source_dir or Path.cwd())
    except Exception as exc:
        typer.echo(f"arm enqueue-template failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"queued {plan.task_id} from {discipline}/{template_key}")


@orchestration_app.command("enqueue-job")
def enqueue_job(
    spec_file: Annotated[Path, typer.Argument(exists=True, readable=True)],
    tasks_dir: Annotated[Path | None, typer.Option("--tasks-dir")] = None,
    source_dir: Annotated[Path | None, typer.Option("--source-dir")] = None,
) -> None:
    """Validate a long-run job spec and persist it for queue-run."""
    _require_enabled()
    from portal.modules.orchestration.jobs import parse_job_spec
    from portal.modules.orchestration.queue import QueueLedger

    try:
        raw = yaml.safe_load(spec_file.read_text(encoding="utf-8"))
        spec = parse_job_spec(raw, repo_root=_repo_root())
        with QueueLedger(tasks_dir or _tasks_dir()) as ledger:
            ledger.enqueue_job(spec, source_dir or spec_file.resolve().parent)
    except Exception as exc:
        typer.echo(f"arm enqueue-job failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"queued job {spec.job_id}")


@orchestration_app.command("job-status")
def job_status(
    job_id: Annotated[str, typer.Argument()],
    tasks_dir: Annotated[Path | None, typer.Option("--tasks-dir")] = None,
) -> None:
    """Print a job receipt, or its persisted state before the first run."""
    task_dir = (tasks_dir or _tasks_dir()) / job_id
    receipt = task_dir / "receipt.json"
    if receipt.is_file():
        typer.echo(receipt.read_text(encoding="utf-8"))
        return
    state = task_dir / "job_state.json"
    spec = task_dir / "job.json"
    if not state.is_file() and not spec.is_file():
        typer.echo(f"no job: {job_id}", err=True)
        raise typer.Exit(code=1)
    payload: dict[str, Any] = {"job_id": job_id}
    if spec.is_file():
        payload["spec"] = yaml.safe_load(spec.read_text(encoding="utf-8"))
    if state.is_file():
        payload["state"] = json.loads(state.read_text(encoding="utf-8"))
    typer.echo(json.dumps(payload, indent=2))


@orchestration_app.command("job-resume")
def job_resume(
    job_id: Annotated[str, typer.Argument()],
    rerun: Annotated[
        str | None, typer.Option("--rerun", help="Re-run this completed step once.")
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Allow rerunning a non-idempotent step.")
    ] = False,
    tasks_dir: Annotated[Path | None, typer.Option("--tasks-dir")] = None,
) -> None:
    """Resume a stopped job at its first incomplete step."""
    _require_enabled()
    from portal.modules.orchestration.jobs import JobRunner, parse_job_spec
    from portal.modules.orchestration.queue import QueueGate, QueueLedger
    from portal.modules.orchestration.service import load_arm_config
    from portal.modules.orchestration.telegram import TelegramNoticeSink

    root = tasks_dir or _tasks_dir()
    spec_path = root / job_id / "job.json"
    if not spec_path.is_file():
        typer.echo(f"no job: {job_id}", err=True)
        raise typer.Exit(code=1)
    try:
        spec = parse_job_spec(
            yaml.safe_load(spec_path.read_text(encoding="utf-8")), repo_root=_repo_root()
        )
        if rerun is not None:
            selected = next((step for step in spec.steps if step.step_id == rerun), None)
            if selected is None:
                raise ValueError(f"unknown step for --rerun: {rerun}")
            if not selected.idempotent and not force:
                raise ValueError(f"step {rerun} is non-idempotent; pass --force to rerun it")
        with QueueLedger(root) as ledger:
            active = ledger.active_other(job_id)
            if active:
                raise RuntimeError(active)
            if ledger.task(job_id) is not None:
                ledger.requeue(job_id)
        policy = load_arm_config(_arm_config_path()).get("queue", {})
        gate = QueueGate({}, policy if isinstance(policy, dict) else {})
        result = JobRunner(
            root,
            repo_root=_repo_root(),
            gate=gate,
            notices=TelegramNoticeSink(),
        ).run(spec, rerun=rerun, force=force)
        with QueueLedger(root) as ledger:
            if ledger.task(job_id) is not None:
                if result.status == "WAITING":
                    ledger.defer(job_id, result.reason or "preconditions not met")
                elif result.status == "PASS":
                    ledger.finish(job_id, "done", "PASS")
                else:
                    ledger.finish(job_id, "blocked", result.status, result.reason)
    except Exception as exc:
        typer.echo(f"arm job-resume failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(str(result.receipt_path))


@orchestration_app.command("queue-run")
def queue_run(
    tasks_dir: Annotated[Path | None, typer.Option("--tasks-dir")] = None,
    poll_seconds: Annotated[float, typer.Option("--poll-seconds", min=0.1)] = 30,
    override: Annotated[
        bool, typer.Option("--override", help="Adopt changed build or model identity.")
    ] = False,
    drain: Annotated[
        bool, typer.Option("--drain", help="Exit once the queue is empty instead of waiting.")
    ] = False,
) -> None:
    """Run queued tasks serially; poll while a gate yields or the queue is empty."""
    _require_enabled()
    from portal.modules.orchestration.queue import OvernightQueue, QueueGate

    root = tasks_dir or _tasks_dir()
    lock = _acquire_runner_lock(root)
    if lock is None:
        typer.echo("queue-run is already active in another process; exiting")
        return
    try:
        from portal.modules.orchestration.control import build_control_poller
        from portal.modules.orchestration.escalate import build_escalator
        from portal.modules.orchestration.service import load_arm_config
        from portal.modules.orchestration.telegram import TelegramNoticeSink

        sink = TelegramNoticeSink()
        service = _optional_service(root)
        policy = load_arm_config(_arm_config_path()).get("queue", {})
        if not isinstance(policy, dict):
            raise ValueError("orchestration queue config must be a mapping")
        engines = service.engines if service is not None else {}
        runner = OvernightQueue(
            root,
            service,
            QueueGate(engines, policy),
            notices=sink,
            escalation=build_escalator(root, _repo_root(), sink, policy),
        )
        control_poll = build_control_poller(root, _repo_root(), sink, policy)
        sink.runner_notice(
            "runner_started", "queue-runner", {"pid": os.getpid(), "poll_seconds": poll_seconds}
        )
        while True:
            _maybe_send_daily_digest(root, sink)
            if control_poll is not None and control_poll():
                time.sleep(poll_seconds)
                continue
            result = runner.run_next(override=override)
            if result.status == "EMPTY":
                if drain:
                    break
                time.sleep(poll_seconds)
                continue
            typer.echo(
                f"{result.status}: {result.task_id or ''}"
                f"{f' ({result.reason})' if result.reason else ''}"
            )
            if result.status in {"WAITING", "BUSY"}:
                time.sleep(poll_seconds)
    except Exception as exc:
        typer.echo(f"arm queue-run failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    finally:
        lock.unlink(missing_ok=True)


@orchestration_app.command("queue-digest")
def queue_digest(
    tasks_dir: Annotated[Path | None, typer.Option("--tasks-dir")] = None,
    no_send: Annotated[
        bool, typer.Option("--no-send", help="Print the digest without queueing it for Telegram.")
    ] = False,
) -> None:
    """Send today's queue digest to Telegram and print it."""
    _require_enabled()
    from portal.modules.orchestration.control import digest_inputs
    from portal.modules.orchestration.queue import build_queue_digest

    root = tasks_dir or _tasks_dir()
    try:
        digest = build_queue_digest(*digest_inputs(root))
        if not no_send:
            from portal.modules.orchestration.telegram import TelegramNoticeSink

            TelegramNoticeSink().digest(digest)
    except Exception as exc:
        typer.echo(f"arm queue-digest failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(digest)


def _acquire_runner_lock(root: Path) -> Path | None:
    """Exactly one queue runner: a second copy exits cleanly while a live one holds the lock."""
    from portal.modules.orchestration.jobs import (
        _foreign_lock_held,
        _read_run_lock,
        _write_run_lock,
    )

    root.mkdir(parents=True, exist_ok=True)
    lock = root / "queue-runner.lock"
    pid, started = _read_run_lock(lock)
    if _foreign_lock_held(pid, started):
        return None
    _write_run_lock(lock)
    return lock


def _maybe_send_daily_digest(root: Path, sink: Any) -> None:
    from portal.modules.orchestration.control import digest_inputs
    from portal.modules.orchestration.queue import build_queue_digest

    state_path = root / "queue-digest.json"
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        if json.loads(state_path.read_text(encoding="utf-8")).get("last_sent") == today:
            return
    except (OSError, ValueError):
        pass
    sink.digest(build_queue_digest(*digest_inputs(root)))
    state_path.write_text(json.dumps({"last_sent": today}) + "\n", encoding="utf-8")


@digests_app.command("refresh")
def digests_refresh(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print the digests without writing the file.")
    ] = False,
) -> None:
    """Recompute both seat digests from load_plan_models and rewrite arm_digests.env."""
    from portal.modules.orchestration.service import load_arm_config, refresh_arm_digests

    config_path = _arm_config_path()
    try:
        digests = refresh_arm_digests(
            load_arm_config(config_path), config_path=config_path, dry_run=dry_run
        )
    except Exception as exc:
        typer.echo(f"arm digests refresh failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    for seat in ("fast", "deep"):
        typer.echo(f"PORTAL_ARM_{seat.upper()}_DIGEST={digests[seat]}")
    if dry_run:
        typer.echo("dry-run: arm_digests.env not written")


@orchestration_app.command("queue-status")
def queue_status(tasks_dir: Annotated[Path | None, typer.Option("--tasks-dir")] = None) -> None:
    """Print the durable queue ledger and the last control requests."""
    _require_enabled()
    from portal.modules.orchestration.control import control_requests_text
    from portal.modules.orchestration.queue import QueueLedger

    with QueueLedger(tasks_dir or _tasks_dir()) as ledger:
        typer.echo(json.dumps(ledger.items(), indent=2))
    controls = control_requests_text()
    if controls:
        typer.echo("\nLast control requests:\n" + controls)


@orchestration_app.command("queue-cancel")
def queue_cancel(
    task_id: Annotated[str, typer.Argument()],
    reason: Annotated[str, typer.Option("--reason", help="Recorded on the queue event.")] = (
        "cancelled by operator"
    ),
    force: Annotated[
        bool,
        typer.Option("--force", help="Cancel a running task whose runner pid is dead."),
    ] = False,
    tasks_dir: Annotated[Path | None, typer.Option("--tasks-dir")] = None,
) -> None:
    """Mark a queued task blocked/CANCELLED. Refuses a live runner."""
    _require_enabled()
    from portal.modules.orchestration.control import cancel_job

    try:
        typer.echo(cancel_job(tasks_dir or _tasks_dir(), task_id, reason, force=force))
    except Exception as exc:
        typer.echo(f"arm queue-cancel failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@orchestration_app.command("queue-requeue")
def queue_requeue(
    task_id: Annotated[str, typer.Argument()],
    tasks_dir: Annotated[Path | None, typer.Option("--tasks-dir")] = None,
) -> None:
    """Requeue a blocked or done job from the spec in its job directory."""
    _require_enabled()
    from portal.modules.orchestration.control import requeue_job

    root = tasks_dir or _tasks_dir()
    try:
        typer.echo(requeue_job(root, task_id, _repo_root()))
    except Exception as exc:
        typer.echo(f"arm queue-requeue failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@orchestration_app.command("escalate")
def escalate_job(
    job_id: Annotated[str, typer.Argument()],
    tasks_dir: Annotated[Path | None, typer.Option("--tasks-dir")] = None,
) -> None:
    """Ask a cloud lane to repair one blocked job. Requires queue.escalation.enabled."""
    _require_enabled()
    from portal.modules.orchestration.control import escalate_blocked_job
    from portal.modules.orchestration.escalate import escalation_enabled
    from portal.modules.orchestration.service import load_arm_config

    policy = load_arm_config(_arm_config_path()).get("queue", {})
    if not escalation_enabled(policy):
        typer.echo("queue.escalation.enabled is false", err=True)
        raise typer.Exit(code=2)
    root = tasks_dir or _tasks_dir()
    try:
        outcome = escalate_blocked_job(root, job_id, _repo_root(), policy)
    except Exception as exc:
        typer.echo(f"arm escalate failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(outcome)


def _service(tasks_dir: Path | None) -> Any:
    service, error = _build_service(tasks_dir)
    if service is None:
        typer.echo(error, err=True)
        raise typer.Exit(code=2)
    return service


def _optional_service(tasks_dir: Path | None) -> Any | None:
    service, _error = _build_service(tasks_dir)
    return service


def _build_service(tasks_dir: Path | None) -> tuple[Any | None, str | None]:
    from portal.modules.orchestration.service import (
        ArmService,
        load_arm_config,
        resolve_seat_digest,
        seated_model_tags,
    )
    from portal.modules.orchestration.telegram import TelegramNoticeSink
    from portal.modules.orchestration.worker import Engine

    config_path = _arm_config_path()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    load_plan = config.get("load_plan_models", {}) if isinstance(config, dict) else {}
    pipeline_url = os.environ.get("PORTAL_ARM_PIPELINE_URL", "http://127.0.0.1:9099")
    api_key = os.environ.get("PIPELINE_API_KEY", "")
    if not api_key:
        return None, "set PIPELINE_API_KEY for the Pipeline chat and load-plan requests"
    tags = seated_model_tags(load_arm_config(config_path))
    engines = {}
    for seat in ("fast", "deep"):
        prefix = f"PORTAL_ARM_{seat.upper()}_"
        load_identity = load_plan.get(seat, {}) if isinstance(load_plan, dict) else {}
        digest = resolve_seat_digest(seat, load_identity)
        if (
            not digest
            or not isinstance(load_identity, dict)
            or not load_identity.get("model")
            or not load_identity.get("engine")
        ):
            return None, f"set {prefix}DIGEST and configure load_plan_models.{seat}"
        engines[seat] = Engine(
            tags[seat],
            digest,
            pipeline_url,
            api_key,
            str(load_identity.get("engine", "omlx")),
            str(load_identity.get("model", "")),
        )
    return (
        ArmService(tasks_dir or _tasks_dir(), engines, notices=TelegramNoticeSink()),
        None,
    )


def _template_parameters(values: list[str]) -> dict[str, str]:
    parameters: dict[str, str] = {}
    for item in values:
        key, separator, value = item.partition("=")
        if not separator or not key or key in parameters:
            raise ValueError("each --param must be a unique name=value pair")
        parameters[key] = value
    return parameters


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _arm_config_path() -> Path:
    return _repo_root() / "config" / "orchestration_arm.yaml"


def _tasks_dir() -> Path:
    from portal.platform.mcp_host.workspace import get_generated_dir

    return get_generated_dir("tasks")


def _require_enabled() -> None:
    from portal.modules.orchestration.service import module_is_enabled

    config_path = Path(__file__).resolve().parents[3] / "config" / "portal.yaml"
    if not module_is_enabled(config_path):
        typer.echo(
            "orchestration module is disabled; enable it with `portal module enable orchestration`",
            err=True,
        )
        raise typer.Exit(code=2)
