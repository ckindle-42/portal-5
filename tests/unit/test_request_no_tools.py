"""An explicit no-tools request gets no tools, and a plain request is unchanged.

``tools: []`` used to be ignored: the workspace's own tools were merged into the
request anyway, and on the security seat that made the engine's parser swallow a
JSON-object answer (live, 2026-11-12). ``tool_choice: "none"`` keeps that promise
too, without touching callers that send neither field.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from portal.platform.inference.router import preinject, streaming
from portal.platform.inference.router.workspaces import WORKSPACES

WS = "test-no-tools-ws"


def _tool(name: str) -> dict:
    return {"type": "function", "function": {"name": name, "parameters": {}}}


@pytest.fixture
def workspace(monkeypatch):
    from portal.platform.inference import tool_registry as registry_mod

    monkeypatch.setitem(WORKSPACES, WS, {"model_hint": "m", "tools": ["workspace_tool"]})
    monkeypatch.setattr(streaming, "_model_supports_tools", lambda _model: True)
    monkeypatch.setattr(streaming, "_inject_ollama_options", lambda body, _ws: body)
    monkeypatch.setattr(streaming, "_select_explicit_required_tool", lambda *_args: None)

    async def refresh() -> None:
        return None

    monkeypatch.setattr(registry_mod.tool_registry, "refresh", refresh)
    monkeypatch.setattr(
        registry_mod.tool_registry,
        "get_openai_tools",
        lambda names: [_tool(name) for name in names],
    )
    return WS


async def _build(body: dict) -> tuple[dict, list[str], bool]:
    engine_body, effective, has_tools, _no_tools = await streaming._build_streaming_request(
        body, SimpleNamespace(type="ollama"), "m", WS, ""
    )
    return engine_body, effective, has_tools


def test_neither_field_is_left_alone() -> None:
    body = {"messages": []}
    assert preinject._apply_no_tools_request(body) is body
    assert "portal_no_tools" not in preinject._apply_no_tools_request(body)


def test_an_empty_tools_array_means_no_tools() -> None:
    body = preinject._apply_no_tools_request({"messages": [], "tools": []})
    assert body["portal_no_tools"] is True


def test_a_bite_body_is_untouched() -> None:
    body = {"messages": [], "tools": [], "portal_bite_tools": ["x"]}
    assert preinject._apply_no_tools_request(body) is body


@pytest.mark.anyio
async def test_explicit_empty_tools_gets_no_workspace_tools(workspace) -> None:
    prepared = preinject._apply_no_tools_request({"model": WS, "messages": [], "tools": []})
    engine_body, _effective, has_tools = await _build(prepared)
    assert has_tools is False
    assert "tools" not in engine_body
    assert "portal_no_tools" not in engine_body


@pytest.mark.anyio
async def test_tool_choice_none_excludes_workspace_tools(workspace) -> None:
    engine_body, effective, has_tools = await _build(
        {"model": WS, "messages": [], "tool_choice": "none"}
    )
    assert effective == [] and has_tools is False
    assert "tools" not in engine_body
    assert engine_body["tool_choice"] == "none"


@pytest.mark.anyio
async def test_tool_choice_none_keeps_the_callers_own_tools(workspace) -> None:
    engine_body, effective, _has_tools = await _build(
        {"model": WS, "messages": [], "tool_choice": "none", "tools": [_tool("client_tool")]}
    )
    assert effective == []
    assert [tool["function"]["name"] for tool in engine_body["tools"]] == ["client_tool"]


@pytest.mark.anyio
async def test_a_plain_request_still_gets_the_workspace_tools(workspace) -> None:
    engine_body, effective, has_tools = await _build({"model": WS, "messages": []})
    assert effective == ["workspace_tool"] and has_tools is True
    assert [tool["function"]["name"] for tool in engine_body["tools"]] == ["workspace_tool"]
