"""Open WebUI entry point for the orchestration arm: queue a task, link its receipt.

Open WebUI reaches this through the pipeline MCP server (tool
``arm_queue_task``) — the channel the repo already uses for the server's other
operator actions (``trigger_backend_warmup``, ``write_file``). No Open WebUI
source, port or workspace config changes are involved, and queueing goes
through the arm's own queue interface rather than a new path.

The tool is inert while the module is off: it answers an error and queues
nothing. The overnight queue itself is another slice's seam; this entry point
only calls it.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Protocol, cast


class QueueTask(Protocol):
    """The overnight-queue seam. Returns the task directory it queued."""

    def __call__(
        self,
        *,
        task_id: str,
        goal: str,
        discipline: str,
        tasks_root: Path,
        source_dir: Path | None = ...,
    ) -> Path: ...


def tasks_root() -> Path:
    """The arm's task root — the same default ``portal arm`` uses."""
    from portal.platform.mcp_host.workspace import get_generated_dir

    return get_generated_dir("tasks")


def resolve_queue_task() -> QueueTask | None:
    """Load the queue seam, or None on a build that carries no overnight queue."""
    try:
        module = importlib.import_module("portal.modules.orchestration.queue")
    except ImportError:
        return None
    handler = getattr(module, "queue_task", None)
    return cast("QueueTask", handler) if handler is not None else None


def arm_queue_task(
    task_id: str,
    goal: str,
    discipline: str,
    *,
    source_dir: Path | None = None,
) -> dict[str, str | bool]:
    """Queue one arm task and return the link to the receipt it will write."""
    if not task_id.strip() or not goal.strip() or not discipline.strip():
        return {"error": "task_id, goal and discipline are all required"}
    from portal.platform.wiki.adapters.modules import enabled_modules

    if "orchestration" not in enabled_modules():
        return {"error": "the orchestration module is disabled"}
    queue = resolve_queue_task()
    if queue is None:
        return {
            "error": "this build has no overnight queue "
            "(portal.modules.orchestration.queue.queue_task)"
        }
    root = tasks_root()
    try:
        task_dir = Path(
            queue(
                task_id=task_id,
                goal=goal,
                discipline=discipline,
                tasks_root=root,
                source_dir=source_dir,
            )
        )
    except Exception as exc:  # noqa: BLE001 — the tool reports, it never raises
        return {"error": f"queueing {task_id} failed: {type(exc).__name__}: {exc}"}
    if not task_dir.resolve().is_relative_to(root.resolve()):
        return {"error": f"queue returned a task directory outside {root}: {task_dir}"}
    return {
        "queued": True,
        "task_id": task_id,
        "discipline": discipline,
        "receipt_link": str(task_dir / "receipt.json"),
    }
