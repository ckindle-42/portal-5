"""``portal arm`` commands for hand-written orchestration tasks."""

from __future__ import annotations

import json
import os
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


def _service(tasks_dir: Path | None) -> Any:
    from portal.modules.orchestration.service import ArmService
    from portal.modules.orchestration.telegram import TelegramNoticeSink
    from portal.modules.orchestration.worker import Engine

    config_path = Path(__file__).resolve().parents[3] / "config" / "orchestration_arm.yaml"
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
