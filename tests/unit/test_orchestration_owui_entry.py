"""Offline tests for the Open WebUI entry point that queues an arm task."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from portal.modules.orchestration import owui_entry
from portal.platform.mcp_host.workspace import get_generated_dir
from portal.platform.wiki.adapters import modules as modules_adapter


@pytest.fixture()
def tasks_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    monkeypatch.setenv("AI_OUTPUT_DIR", str(tmp_path))
    return get_generated_dir("tasks")


class RecordingQueue:
    """Stands in for the overnight-queue slice's ``queue_task(...)``."""

    def __init__(self, *, writes_receipt: bool = True) -> None:
        self.calls: list[dict[str, Any]] = []
        self.writes_receipt = writes_receipt

    def __call__(self, **kwargs: Any) -> Path:
        self.calls.append(kwargs)
        task_dir = Path(kwargs["tasks_root"]) / kwargs["task_id"]
        task_dir.mkdir(parents=True)
        if self.writes_receipt:
            (task_dir / "receipt.json").write_text(
                json.dumps({"task_id": kwargs["task_id"], "status": "PASS"}), encoding="utf-8"
            )
        return task_dir


def _enabled(monkeypatch: pytest.MonkeyPatch, enabled: bool) -> None:
    monkeypatch.setattr(
        modules_adapter, "enabled_modules", lambda: ["orchestration"] if enabled else []
    )


def test_disabled_module_is_inert_and_never_queues(monkeypatch: pytest.MonkeyPatch) -> None:
    _enabled(monkeypatch, enabled=False)
    queue = RecordingQueue()
    monkeypatch.setattr(owui_entry, "resolve_queue_task", lambda: queue)

    result = owui_entry.arm_queue_task("t-1", "Fix the failing test", "test_fixing")

    assert result["error"] == "the orchestration module is disabled"
    assert "receipt_link" not in result
    assert queue.calls == []


def test_enabled_module_queues_the_task_with_the_right_fields(
    tasks_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enabled(monkeypatch, enabled=True)
    queue = RecordingQueue()
    monkeypatch.setattr(owui_entry, "resolve_queue_task", lambda: queue)
    source = tasks_dir.parent.parent / "uploads"
    source.mkdir(parents=True, exist_ok=True)

    result = owui_entry.arm_queue_task(
        "t-2", "Fix the failing test", "test_fixing", source_dir=source
    )

    assert result["queued"] is True
    assert result["task_id"] == "t-2"
    assert result["discipline"] == "test_fixing"
    assert queue.calls == [
        {
            "task_id": "t-2",
            "goal": "Fix the failing test",
            "discipline": "test_fixing",
            "tasks_root": tasks_dir,
            "source_dir": source,
        }
    ]


def test_receipt_link_resolves_under_the_generated_tasks_dir(
    tasks_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enabled(monkeypatch, enabled=True)
    monkeypatch.setattr(owui_entry, "resolve_queue_task", lambda: RecordingQueue())

    result = owui_entry.arm_queue_task("t-3", "Fix the failing test", "test_fixing")

    link = Path(str(result["receipt_link"]))
    assert link.is_file()
    assert json.loads(link.read_text(encoding="utf-8"))["status"] == "PASS"
    assert link.is_relative_to(tasks_dir)


def test_queue_that_skips_the_receipt_still_links_the_task_dir(
    tasks_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enabled(monkeypatch, enabled=True)
    monkeypatch.setattr(
        owui_entry, "resolve_queue_task", lambda: RecordingQueue(writes_receipt=False)
    )

    result = owui_entry.arm_queue_task("t-4", "Fix the failing test", "test_fixing")

    assert Path(str(result["receipt_link"])).parent == tasks_dir / "t-4"


def test_build_without_the_queue_seam_reports_the_interface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enabled(monkeypatch, enabled=True)
    monkeypatch.setattr(owui_entry, "resolve_queue_task", lambda: None)

    result = owui_entry.arm_queue_task("t-5", "Fix the failing test", "test_fixing")

    assert "portal.modules.orchestration.queue.queue_task" in str(result["error"])
    assert "receipt_link" not in result


def test_queue_seam_is_absent_on_this_build() -> None:
    """The overnight-queue slice lands on a sibling branch; delete with the seam."""
    assert owui_entry.resolve_queue_task() is None


def test_queue_failure_is_reported_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    _enabled(monkeypatch, enabled=True)

    def boom(**kwargs: Any) -> Path:
        raise RuntimeError("no seated model")

    monkeypatch.setattr(owui_entry, "resolve_queue_task", lambda: boom)

    result = owui_entry.arm_queue_task("t-6", "Fix the failing test", "test_fixing")

    assert result["error"] == "queueing t-6 failed: RuntimeError: no seated model"


def test_queue_returning_a_directory_outside_the_task_root_is_refused(
    tasks_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enabled(monkeypatch, enabled=True)
    elsewhere = tasks_dir.parent / "elsewhere"
    monkeypatch.setattr(owui_entry, "resolve_queue_task", lambda: lambda **kwargs: elsewhere)

    result = owui_entry.arm_queue_task("t-7", "Fix the failing test", "test_fixing")

    assert result["error"].startswith("queue returned a task directory outside")


@pytest.mark.parametrize(
    ("task_id", "goal", "discipline"),
    [("", "goal", "test_fixing"), ("t-8", "", "test_fixing"), ("t-8", "goal", "  ")],
)
def test_missing_fields_are_refused_before_queueing(
    task_id: str, goal: str, discipline: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enabled(monkeypatch, enabled=True)
    queue = RecordingQueue()
    monkeypatch.setattr(owui_entry, "resolve_queue_task", lambda: queue)

    result = owui_entry.arm_queue_task(task_id, goal, discipline)

    assert result["error"] == "task_id, goal and discipline are all required"
    assert queue.calls == []


def test_plugin_seam_exposes_the_entry_point() -> None:
    """Platform reaches the tool through the plugin seam, never a module import."""
    from portal.platform.plugins import owui_tools

    assert owui_tools()["arm_queue_task"] is owui_entry.arm_queue_task


def test_pipeline_mcp_serves_the_entry_point() -> None:
    """The OWUI surface is one pipeline-MCP tool that delegates through the seam."""
    src = (
        Path(__file__).resolve().parents[2] / "portal" / "platform" / "mcp_host" / "pipeline_mcp.py"
    ).read_text(encoding="utf-8")
    assert 'owui_tools().get("arm_queue_task")' in src
    assert '@mcp.custom_route("/tools/arm_queue_task", methods=["POST"])' in src
    manifest = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "config"
            / "inference"
            / "pipeline_mcp_tools_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert "arm_queue_task" in {tool["name"] for tool in manifest}


def test_pipeline_mcp_route_queues_through_the_seam(
    tasks_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end over the tool's REST route: gate, seam, receipt link."""
    from starlette.testclient import TestClient

    from portal.platform.mcp_host import pipeline_mcp

    _enabled(monkeypatch, enabled=True)
    queue = RecordingQueue()
    monkeypatch.setattr(owui_entry, "resolve_queue_task", lambda: queue)

    client = TestClient(pipeline_mcp.mcp.streamable_http_app())
    response = client.post(
        "/tools/arm_queue_task",
        json={
            "arguments": {
                "task_id": "t-9",
                "goal": "Fix the failing test",
                "discipline": "test_fixing",
            }
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["queued"] is True
    assert Path(body["receipt_link"]).is_relative_to(tasks_dir)
    assert queue.calls[0]["task_id"] == "t-9"


def test_pipeline_mcp_route_is_inert_while_the_module_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from starlette.testclient import TestClient

    from portal.platform.mcp_host import pipeline_mcp

    _enabled(monkeypatch, enabled=False)
    queue = RecordingQueue()
    monkeypatch.setattr(owui_entry, "resolve_queue_task", lambda: queue)

    client = TestClient(pipeline_mcp.mcp.streamable_http_app())
    body = client.post(
        "/tools/arm_queue_task",
        json={
            "arguments": {
                "task_id": "t-10",
                "goal": "Fix the failing test",
                "discipline": "test_fixing",
            }
        },
    ).json()

    assert body["error"] == "the orchestration module is disabled"
    assert queue.calls == []
