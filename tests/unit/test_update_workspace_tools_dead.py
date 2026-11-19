"""sync-config's dead-tools check: only tools on a dead server count as dead."""

from __future__ import annotations

from portal.platform.inference import owui_tools


def test_pipeline_only_tools_are_not_dead():
    # compliance tools have no OWUI toolId; the pipeline dispatches them.
    assert not owui_tools.all_tools_dead(["compliance_read", "compliance_context"])


def test_all_on_dead_server_is_dead(tmp_path):
    path = tmp_path / "servers.yaml"
    path.write_text("servers:\n  retired: [ace_generate]\ndead_servers: [retired]\n")
    assert owui_tools.all_tools_dead(["ace_generate"], path)


def test_retired_ace_tool_is_not_on_a_live_server():
    assert not owui_tools.all_tools_dead(["ace_generate"])


def test_one_live_tool_is_enough():
    assert not owui_tools.all_tools_dead(["ace_generate", "web_search"])


def test_no_tools_is_not_dead():
    assert not owui_tools.all_tools_dead([])


def test_tool_ids_come_from_the_server_config():
    assert owui_tools.compute_tool_ids(
        ["web_search", "kb_search", "ace_generate", "web_search", "compliance_read"]
    ) == ["server:mcp:portal_rag", "server:mcp:portal_research"]
