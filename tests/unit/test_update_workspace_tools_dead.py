"""sync-config's dead-tools check: only tools on a dead server count as dead."""

from __future__ import annotations

from scripts import update_workspace_tools as uwt


def test_pipeline_only_tools_are_not_dead():
    # compliance tools have no OWUI toolId; the pipeline dispatches them.
    assert not uwt.all_tools_dead(["compliance_read", "compliance_context"])


def test_all_on_dead_server_is_dead(monkeypatch):
    monkeypatch.setitem(uwt.TOOL_TO_SERVER, "gen_song", "portal_music_ace")
    assert uwt.all_tools_dead(["gen_song"])


def test_one_live_tool_is_enough(monkeypatch):
    monkeypatch.setitem(uwt.TOOL_TO_SERVER, "gen_song", "portal_music_ace")
    assert not uwt.all_tools_dead(["gen_song", "web_search"])


def test_no_tools_is_not_dead():
    assert not uwt.all_tools_dead([])
