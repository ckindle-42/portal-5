"""``portal arm`` commands for hand-written orchestration tasks."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

orchestration_app = typer.Typer(help="Offline-first verified task orchestration.")


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


@orchestration_app.command("queue-run")
def queue_run(
    tasks_dir: Annotated[Path | None, typer.Option("--tasks-dir")] = None,
    poll_seconds: Annotated[float, typer.Option("--poll-seconds", min=0.1)] = 30,
    override: Annotated[
        bool, typer.Option("--override", help="Adopt changed build or model identity.")
    ] = False,
) -> None:
    """Run queued tasks serially, polling again when a yield gate is active."""
    _require_enabled()
    from portal.modules.orchestration.queue import OvernightQueue, QueueGate

    root = tasks_dir or _tasks_dir()
    try:
        service = _service(root)
        policy = service.arm_config.get("queue", {})
        if not isinstance(policy, dict):
            raise ValueError("orchestration queue config must be a mapping")
        runner = OvernightQueue(root, service, QueueGate(service.engines, policy))
        while True:
            result = runner.run_next(override=override)
            if result.status == "EMPTY":
                break
            typer.echo(
                f"{result.status}: {result.task_id or ''}"
                f"{f' ({result.reason})' if result.reason else ''}"
            )
            if result.status in {"WAITING", "BUSY"}:
                time.sleep(poll_seconds)
    except Exception as exc:
        typer.echo(f"arm queue-run failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@orchestration_app.command("queue-status")
def queue_status(tasks_dir: Annotated[Path | None, typer.Option("--tasks-dir")] = None) -> None:
    """Print the durable queue ledger."""
    _require_enabled()
    from portal.modules.orchestration.queue import QueueLedger

    with QueueLedger(tasks_dir or _tasks_dir()) as ledger:
        typer.echo(json.dumps(ledger.items(), indent=2))


def _service(tasks_dir: Path | None) -> Any:
    from portal.modules.orchestration.service import ArmService
    from portal.modules.orchestration.telegram import TelegramNoticeSink
    from portal.modules.orchestration.worker import Engine

    config_path = _arm_config_path()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    load_plan = config.get("load_plan_models", {}) if isinstance(config, dict) else {}
    pipeline_url = os.environ.get("PORTAL_ARM_PIPELINE_URL", "http://127.0.0.1:9099")
    api_key = os.environ.get("PIPELINE_API_KEY", "")
    if not api_key:
        typer.echo("set PIPELINE_API_KEY for the Pipeline chat and load-plan requests", err=True)
        raise typer.Exit(code=2)
    engines = {}
    for seat in ("fast", "deep"):
        prefix = f"PORTAL_ARM_{seat.upper()}_"
        digest = os.environ.get(prefix + "DIGEST")
        load_identity = load_plan.get(seat, {}) if isinstance(load_plan, dict) else {}
        if (
            digest is None
            or not isinstance(load_identity, dict)
            or not load_identity.get("model")
            or not load_identity.get("engine")
        ):
            typer.echo(f"set {prefix}DIGEST and configure load_plan_models.{seat}", err=True)
            raise typer.Exit(code=2)
        engines[seat] = Engine(
            f"auto-daily::{seat}",
            digest,
            pipeline_url,
            api_key,
            str(load_identity.get("engine", "omlx")),
            str(load_identity.get("model", "")),
        )
    return ArmService(tasks_dir or _tasks_dir(), engines, notices=TelegramNoticeSink())


def _template_parameters(values: list[str]) -> dict[str, str]:
    parameters: dict[str, str] = {}
    for item in values:
        key, separator, value = item.partition("=")
        if not separator or not key or key in parameters:
            raise ValueError("each --param must be a unique name=value pair")
        parameters[key] = value
    return parameters


def _arm_config_path() -> Path:
    return Path(__file__).resolve().parents[3] / "config" / "orchestration_arm.yaml"


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
