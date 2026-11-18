"""Offline tests for the Open WebUI entry that enqueues an arm template."""

from __future__ import annotations

import pytest

from portal.modules.orchestration import owui_entry


def test_repository_directory_is_an_allowed_source_dir() -> None:
    resolved = owui_entry.resolve_source_dir(owui_entry._REPO_ROOT / "config")
    assert resolved == (owui_entry._REPO_ROOT / "config").resolve()


def test_plugin_seam_exposes_the_entry_point() -> None:
    """Platform reaches the tool through the plugin seam, never a module import."""
    from portal.platform.plugins import owui_tools

    assert owui_tools()["arm_queue_task"] is owui_entry.arm_queue_task


@pytest.mark.parametrize(
    "field",
    ["task_id", "discipline", "template_key", "parameters", "source_dir"],
)
def test_pipeline_mcp_tool_schema_names_every_accepted_argument(field: str) -> None:
    import asyncio

    from portal.platform.mcp_host import pipeline_mcp

    tools = {tool.name: tool for tool in asyncio.run(pipeline_mcp.mcp.list_tools())}
    assert field in tools["arm_queue_task"].input_schema["properties"]
