"""Open WebUI entry: enqueue a stored plan template and link its receipt.

Open WebUI reaches this through the pipeline MCP tool ``arm_queue_task``.
Queueing uses ``instantiate_plan_template`` and ``QueueLedger.enqueue``, the
same path as ``portal arm enqueue-template``. The tool is inert while the
module is off.
"""

from __future__ import annotations

from pathlib import Path

from portal.modules.orchestration.contracts import TaskPlan

_REPO_ROOT = Path(__file__).resolve().parents[3]


def tasks_root() -> Path:
    """The arm's task root — the same default ``portal arm`` uses."""
    from portal.platform.mcp_host.workspace import get_generated_dir

    return get_generated_dir("tasks")


def resolve_source_dir(source_dir: Path | None) -> Path:
    """Default to uploads, and refuse a directory outside the allowed roots."""
    from portal.platform.mcp_host.workspace import get_uploads_dir

    if source_dir is None:
        candidate = get_uploads_dir()
    else:
        candidate = source_dir.expanduser()
        if not candidate.is_dir():
            raise ValueError("source_dir must be an existing directory")
    resolved = candidate.resolve()
    if not _inside_allowlist(resolved):
        raise ValueError("source_dir must stay under the workspace root or the repository")
    return resolved


def arm_queue_task(
    task_id: str,
    discipline: str,
    template_key: str,
    parameters: dict[str, str] | None = None,
    *,
    source_dir: Path | None = None,
) -> dict[str, str | bool]:
    """Enqueue one stored template and return the receipt path the runner will write."""
    from portal.platform.wiki.adapters.modules import enabled_modules

    if "orchestration" not in enabled_modules():
        return {"error": "the orchestration module is disabled"}
    try:
        return _enqueue_template(task_id, discipline, template_key, parameters, source_dir)
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — the tool reports, it never raises
        return {"error": f"queueing {task_id} failed: {type(exc).__name__}: {exc}"}


def _enqueue_template(
    task_id: str,
    discipline: str,
    template_key: str,
    parameters: dict[str, str] | None,
    source_dir: Path | None,
) -> dict[str, str | bool]:
    checked_id = _required_text(task_id, "task_id")
    checked_discipline = _required_text(discipline, "discipline")
    checked_template = _required_text(template_key, "template_key")
    checked_parameters = _string_parameters(parameters)
    checked_source = resolve_source_dir(source_dir)
    _reject_parameter_paths(checked_parameters, checked_source)
    plan = _render_template(
        checked_id, checked_discipline, checked_template, checked_parameters, checked_source
    )
    _reject_plan_inputs(plan, checked_source)
    return _commit_plan(plan, checked_discipline, checked_template, checked_source)


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _string_parameters(parameters: dict[str, str] | None) -> dict[str, str]:
    if parameters is None:
        return {}
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be a mapping of strings")
    checked: dict[str, str] = {}
    for key, value in parameters.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("parameters must be a mapping of strings")
        checked[key] = value
    return checked


def _allow_roots() -> tuple[Path, Path]:
    from portal.platform.mcp_host.workspace import get_workspace_root

    return (get_workspace_root().resolve(), _REPO_ROOT)


def _inside_allowlist(path: Path) -> bool:
    resolved = path.resolve()
    return any(resolved == root or resolved.is_relative_to(root) for root in _allow_roots())


def _explicit_host_path(value: str, source_dir: Path) -> Path | None:
    expanded = Path(value).expanduser()
    if expanded.is_absolute():
        return expanded
    if ".." in expanded.parts:
        return source_dir / expanded
    return None


def _reject_parameter_paths(parameters: dict[str, str], source_dir: Path) -> None:
    for value in parameters.values():
        candidate = _explicit_host_path(value, source_dir)
        if candidate is not None and not _inside_allowlist(candidate):
            raise ValueError(
                "template parameter path must stay under the workspace root or the repository"
            )


def _render_template(
    task_id: str,
    discipline: str,
    template_key: str,
    parameters: dict[str, str],
    source_dir: Path,
) -> TaskPlan:
    from portal.modules.orchestration.planner import instantiate_plan_template
    from portal.modules.orchestration.service import load_arm_config

    config = load_arm_config(_REPO_ROOT / "config" / "orchestration_arm.yaml")
    return instantiate_plan_template(
        config,
        template_key=template_key,
        discipline_key=discipline,
        task_id=task_id,
        parameters=parameters,
        source_dir=source_dir,
    )


def _reject_plan_inputs(plan: TaskPlan, source_dir: Path) -> None:
    bite_ids = {bite.bite_id for bite in plan.bites}
    for bite in plan.bites:
        for reference in bite.inputs:
            if reference in bite_ids:
                continue
            path = Path(reference).expanduser()
            resolved = path if path.is_absolute() else source_dir / path
            if not _inside_allowlist(resolved):
                raise ValueError(f"input path is outside the allowed roots: {reference}")


def _commit_plan(
    plan: TaskPlan, discipline: str, template_key: str, source_dir: Path
) -> dict[str, str | bool]:
    from portal.modules.orchestration.queue import QueueLedger

    root = tasks_root()
    task_dir = (root / plan.task_id).resolve()
    if not task_dir.is_relative_to(root.resolve()):
        raise ValueError(f"task directory escapes {root}")
    with QueueLedger(root) as ledger:
        ledger.enqueue(plan, source_dir)
    return {
        "queued": True,
        "task_id": plan.task_id,
        "discipline": discipline,
        "template_key": template_key,
        "receipt_link": str(root / plan.task_id / "receipt.json"),
    }
