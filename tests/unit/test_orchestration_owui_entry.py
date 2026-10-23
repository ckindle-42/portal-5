"""Offline tests for the Open WebUI entry that enqueues an arm template."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from portal.modules.orchestration import owui_entry
from portal.modules.orchestration.queue import QueueLedger
from portal.platform.mcp_host.workspace import get_generated_dir
from portal.platform.wiki.adapters import modules as modules_adapter


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    monkeypatch.setenv("AI_OUTPUT_DIR", str(tmp_path))
    return tmp_path


def _enabled(monkeypatch: pytest.MonkeyPatch, *, enabled: bool) -> None:
    monkeypatch.setattr(
        modules_adapter, "enabled_modules", lambda: ["orchestration"] if enabled else []
    )


def _inputs(directory: Path) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / "module.py"
    tests = directory / "test_module.py"
    source.write_text("def value():\n    return 1\n", encoding="utf-8")
    tests.write_text("def test_value():\n    assert value() == 2\n", encoding="utf-8")
    return {
        "source_file": source.name,
        "test_file": tests.name,
        "expected_behavior": "value returns 2",
    }


def _queue(
    task_id: str, parameters: dict[str, str], source_dir: Path | None = None
) -> dict[str, Any]:
    return owui_entry.arm_queue_task(
        task_id,
        "test_fixing",
        "repair_with_tests",
        parameters,
        source_dir=source_dir,
    )


def _queued_ids(tasks_dir: Path) -> list[str]:
    if not (tasks_dir / "queue.sqlite3").is_file():
        return []
    with QueueLedger(tasks_dir) as ledger:
        return [str(item["task_id"]) for item in ledger.items()]


def test_disabled_module_is_inert_and_never_queues(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enabled(monkeypatch, enabled=False)

    result = _queue("t-1", _inputs(workspace / "uploads"))

    assert result["error"] == "the orchestration module is disabled"
    assert "receipt_link" not in result
    assert _queued_ids(get_generated_dir("tasks")) == []


def test_enabled_module_enqueues_through_the_queue_ledger(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enabled(monkeypatch, enabled=True)
    uploads = workspace / "uploads"
    uploads.mkdir()
    parameters = _inputs(uploads)

    result = _queue("t-2", parameters, source_dir=uploads)

    tasks_dir = get_generated_dir("tasks")
    assert result["queued"] is True
    assert result["task_id"] == "t-2"
    assert result["discipline"] == "test_fixing"
    assert result["template_key"] == "repair_with_tests"
    link = Path(str(result["receipt_link"]))
    assert link == tasks_dir / "t-2" / "receipt.json"
    assert link.is_relative_to(tasks_dir)
    with QueueLedger(tasks_dir) as ledger:
        item = ledger.items()[0]
        plan = json.loads(
            ledger.db.execute(
                "SELECT plan_json FROM queue_task WHERE task_id = ?", ("t-2",)
            ).fetchone()["plan_json"]
        )
    assert item["task_id"] == "t-2"
    assert item["state"] == "queued"
    assert Path(str(item["source_dir"])) == uploads.resolve()
    assert plan["task_id"] == "t-2"
    assert plan["bites"][0]["inputs"] == ["module.py", "test_module.py"]


def test_omitted_source_dir_defaults_to_the_uploads_directory(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enabled(monkeypatch, enabled=True)
    from portal.platform.mcp_host.workspace import get_uploads_dir

    parameters = _inputs(get_uploads_dir())

    result = _queue("t-3", parameters)

    assert result["queued"] is True
    with QueueLedger(get_generated_dir("tasks")) as ledger:
        assert Path(str(ledger.items()[0]["source_dir"])) == get_uploads_dir().resolve()


@pytest.mark.parametrize(
    "source_name",
    ["missing", "file"],
)
def test_source_dir_must_be_an_existing_directory(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, source_name: str
) -> None:
    _enabled(monkeypatch, enabled=True)
    uploads = workspace / "uploads"
    uploads.mkdir()
    parameters = _inputs(uploads)
    if source_name == "missing":
        source = workspace / "missing"
    else:
        source = workspace / "notes.txt"
        source.write_text("x", encoding="utf-8")

    result = _queue("t-4", parameters, source_dir=source)

    assert result["error"] == "source_dir must be an existing directory"
    assert _queued_ids(get_generated_dir("tasks")) == []


def test_source_dir_outside_the_workspace_and_repository_is_refused(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enabled(monkeypatch, enabled=True)
    monkeypatch.setenv("AI_OUTPUT_DIR", str(workspace / "ws"))
    outside = workspace / "outside"
    parameters = _inputs(outside)

    result = _queue("t-5", parameters, source_dir=outside)

    assert result["error"] == "source_dir must stay under the workspace root or the repository"
    assert _queued_ids(get_generated_dir("tasks")) == []


def test_repository_directory_is_an_allowed_source_dir() -> None:
    resolved = owui_entry.resolve_source_dir(owui_entry._REPO_ROOT / "config")
    assert resolved == (owui_entry._REPO_ROOT / "config").resolve()


def test_absolute_parameter_path_outside_the_allowlist_is_not_queued(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enabled(monkeypatch, enabled=True)
    monkeypatch.setenv("AI_OUTPUT_DIR", str(workspace / "ws"))
    uploads = workspace / "ws" / "uploads"
    parameters = _inputs(uploads)
    secret = workspace / "secret-key"
    secret.mkdir()
    key = secret / "id_ed25519"
    key.write_text("secret", encoding="utf-8")
    parameters["source_file"] = str(key)

    result = _queue("t-6", parameters, source_dir=uploads)

    assert "template parameter path" in str(result["error"])
    assert _queued_ids(get_generated_dir("tasks")) == []


def test_relative_parameter_path_that_escapes_the_source_dir_is_not_queued(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enabled(monkeypatch, enabled=True)
    monkeypatch.setenv("AI_OUTPUT_DIR", str(workspace / "ws"))
    uploads = workspace / "ws" / "uploads"
    parameters = _inputs(uploads)
    secret = workspace / "secret-rel"
    secret.mkdir()
    escaped = secret / "id_ed25519"
    escaped.write_text("secret", encoding="utf-8")
    parameters["source_file"] = "../../secret-rel/id_ed25519"

    result = _queue("t-7", parameters, source_dir=uploads)

    assert "template parameter path" in str(result["error"])
    assert _queued_ids(get_generated_dir("tasks")) == []


def test_symlink_input_that_resolves_outside_the_allowlist_is_not_queued(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enabled(monkeypatch, enabled=True)
    monkeypatch.setenv("AI_OUTPUT_DIR", str(workspace / "ws"))
    uploads = workspace / "ws" / "uploads"
    parameters = _inputs(uploads)
    secret = workspace / "secret-link"
    secret.mkdir()
    target = secret / "id_ed25519"
    target.write_text("secret", encoding="utf-8")
    link = uploads / "module.py"
    link.unlink()
    link.symlink_to(target)

    result = _queue("t-8", parameters, source_dir=uploads)

    assert "input path escapes source directory" in str(result["error"])
    assert _queued_ids(get_generated_dir("tasks")) == []


def test_duplicate_task_id_is_reported_not_raised(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enabled(monkeypatch, enabled=True)
    uploads = workspace / "uploads"
    uploads.mkdir()
    parameters = _inputs(uploads)
    assert _queue("t-9", parameters, source_dir=uploads)["queued"] is True

    result = _queue("t-9", parameters, source_dir=uploads)

    assert "already queued" in str(result["error"])


@pytest.mark.parametrize(
    ("task_id", "discipline", "template_key"),
    [
        ("", "test_fixing", "repair_with_tests"),
        ("t-10", " ", "repair_with_tests"),
        ("t-10", "test_fixing", ""),
    ],
)
def test_missing_fields_are_refused_before_queueing(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    task_id: str,
    discipline: str,
    template_key: str,
) -> None:
    _enabled(monkeypatch, enabled=True)
    uploads = workspace / "uploads"
    uploads.mkdir()

    result = owui_entry.arm_queue_task(
        task_id, discipline, template_key, _inputs(uploads), source_dir=uploads
    )

    assert "must be a non-empty string" in str(result["error"])
    assert _queued_ids(get_generated_dir("tasks")) == []


def test_unsafe_task_id_is_refused_by_the_plan_contract(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enabled(monkeypatch, enabled=True)
    uploads = workspace / "uploads"
    uploads.mkdir()

    result = _queue("../escape", _inputs(uploads), source_dir=uploads)

    assert "task_id" in str(result["error"])
    assert _queued_ids(get_generated_dir("tasks")) == []


def test_plugin_seam_exposes_the_entry_point() -> None:
    """Platform reaches the tool through the plugin seam, never a module import."""
    from portal.platform.plugins import owui_tools

    assert owui_tools()["arm_queue_task"] is owui_entry.arm_queue_task


def test_pipeline_mcp_serves_the_entry_point() -> None:
    """The OWUI surface is one pipeline-MCP tool that delegates through the seam."""
    import asyncio

    from portal.platform.mcp_host import pipeline_mcp

    src = (
        Path(__file__).resolve().parents[2] / "portal" / "platform" / "mcp_host" / "pipeline_mcp.py"
    ).read_text(encoding="utf-8")
    assert 'owui_tools().get("arm_queue_task")' in src
    assert "asyncio.to_thread(" in src
    tools = {tool.name: tool for tool in asyncio.run(pipeline_mcp.mcp.list_tools())}
    assert sorted(tools["arm_queue_task"].input_schema["required"]) == [
        "discipline",
        "task_id",
        "template_key",
    ]


def test_pipeline_mcp_route_enqueues_off_the_event_loop(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Native queueing goes through asyncio.to_thread and the real ledger."""
    import asyncio

    from portal.platform.mcp_host import pipeline_mcp

    _enabled(monkeypatch, enabled=True)
    uploads = workspace / "uploads"
    uploads.mkdir()
    parameters = _inputs(uploads)
    seen: list[str] = []

    async def spy(fn: Any, /, *args: Any, **kwargs: Any) -> Any:
        seen.append(getattr(fn, "__name__", ""))
        return fn(*args, **kwargs)

    monkeypatch.setattr(pipeline_mcp.asyncio, "to_thread", spy)
    body = asyncio.run(
        pipeline_mcp.arm_queue_task(
            "t-11", "test_fixing", "repair_with_tests", parameters, str(uploads)
        )
    )

    assert body["queued"] is True
    assert seen == ["arm_queue_task"]
    assert Path(body["receipt_link"]).is_relative_to(get_generated_dir("tasks"))
    assert _queued_ids(get_generated_dir("tasks")) == ["t-11"]


def test_pipeline_mcp_route_is_inert_while_the_module_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from portal.platform.mcp_host import pipeline_mcp

    _enabled(monkeypatch, enabled=False)
    body = asyncio.run(pipeline_mcp.arm_queue_task("t-12", "test_fixing", "repair_with_tests"))

    assert body["error"] == "the orchestration module is disabled"


@pytest.mark.parametrize(
    "field",
    ["task_id", "discipline", "template_key", "parameters", "source_dir"],
)
def test_pipeline_mcp_tool_schema_names_every_accepted_argument(field: str) -> None:
    import asyncio

    from portal.platform.mcp_host import pipeline_mcp

    tools = {tool.name: tool for tool in asyncio.run(pipeline_mcp.mcp.list_tools())}
    assert field in tools["arm_queue_task"].input_schema["properties"]
