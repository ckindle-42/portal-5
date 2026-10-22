"""Regression tests for the orchestration arm's real router seams."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from fastapi import HTTPException

from portal.modules.orchestration import cli as arm_cli
from portal.modules.orchestration import service as arm_service
from portal.platform.inference import tool_registry
from portal.platform.inference.router import streaming, validation


def test_cli_loads_arm_and_module_config_from_repo_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = Path(__file__).resolve().parents[2]
    enabled_paths: list[Path] = []
    monkeypatch.setattr(
        arm_service,
        "module_is_enabled",
        lambda path: enabled_paths.append(path) or True,
    )
    arm_cli._require_enabled()
    assert enabled_paths == [root / "config" / "portal.yaml"]

    monkeypatch.setenv("PIPELINE_API_KEY", "test-key")
    monkeypatch.setenv("PORTAL_ARM_FAST_DIGEST", "fast-test")
    monkeypatch.setenv("PORTAL_ARM_DEEP_DIGEST", "deep-test")
    captured: dict[str, Any] = {}
    sentinel = object()

    def make_service(task_root, engines, **kwargs):
        captured["task_root"] = task_root
        captured["engines"] = engines
        captured["service_kwargs"] = kwargs
        return sentinel

    monkeypatch.setattr(arm_service, "ArmService", make_service)
    assert arm_cli._service(tmp_path) is sentinel
    config = yaml.safe_load((root / "config" / "orchestration_arm.yaml").read_text())
    assert (
        captured["engines"]["fast"].load_plan_model == config["load_plan_models"]["fast"]["model"]
    )


def _tool_schema(name: str) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "parameters": {}}}


class _StreamResponse:
    status_code = 200

    def __init__(self, lines: list[str]) -> None:
        self.lines = lines

    async def aiter_lines(self):
        for line in self.lines:
            yield line

    async def aread(self) -> bytes:
        return b""


class _StreamContext:
    def __init__(self, response: _StreamResponse) -> None:
        self.response = response

    async def __aenter__(self) -> _StreamResponse:
        return self.response

    async def __aexit__(self, *_args: Any) -> None:
        return None


class _StreamClient:
    def __init__(self, responses: list[_StreamResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def stream(self, _method: str, _url: str, *, json: dict[str, Any]):
        self.requests.append(json)
        return _StreamContext(self.responses.pop(0))


def _tool_response(name: str, call_id: str = "call-1") -> _StreamResponse:
    call = {
        "index": 0,
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": "{}"},
    }
    frame = {
        "choices": [{"index": 0, "delta": {"tool_calls": [call]}, "finish_reason": "tool_calls"}]
    }
    return _StreamResponse([f"data: {json.dumps(frame)}", "data: [DONE]"])


def _answer_response(answer: str = "done") -> _StreamResponse:
    frames = [
        {"choices": [{"index": 0, "delta": {"content": answer}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
    ]
    return _StreamResponse([*(f"data: {json.dumps(frame)}" for frame in frames), "data: [DONE]"])


async def _prepare_request(
    monkeypatch: pytest.MonkeyPatch,
    *,
    bite_tools: list[str] | None,
    max_hops: Any = 2,
    client_tools: list[dict[str, Any]] | None = None,
    workspace_tools: list[str] | None = None,
    refresh_calls: list[bool] | None = None,
) -> tuple[dict[str, Any], list[str], bool]:
    monkeypatch.setattr(
        streaming, "_resolve_persona_tools", lambda *_args: workspace_tools or ["lookup"]
    )
    monkeypatch.setattr(streaming, "_model_supports_tools", lambda _model: True)

    async def refresh() -> None:
        if refresh_calls is not None:
            refresh_calls.append(True)

    monkeypatch.setattr(tool_registry.tool_registry, "refresh", refresh)
    monkeypatch.setattr(
        tool_registry.tool_registry,
        "get_openai_tools",
        lambda names: [_tool_schema(name) for name in names],
    )
    body: dict[str, Any] = {
        "messages": [{"role": "user", "content": "run the bite"}],
        "tools": client_tools or [_tool_schema("finish"), _tool_schema("unrequested")],
        "tool_choice": "auto",
    }
    if bite_tools is not None:
        body["portal_bite_tools"] = bite_tools
    if max_hops is not None:
        body["portal_bite_max_hops"] = max_hops
    prepared = await streaming._build_streaming_request(
        body, SimpleNamespace(type="omlx"), "model", "arm-test", ""
    )
    return prepared[:3]


@pytest.mark.anyio
async def test_bite_trace_records_the_final_tools_offered_to_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notes: list[dict[str, Any]] = []
    monkeypatch.setattr(streaming, "trace_note", lambda **fields: notes.append(fields))
    body, effective, has_tools = await _prepare_request(
        monkeypatch,
        bite_tools=["lookup", "finish"],
        workspace_tools=["lookup", "document_read"],
    )

    assert has_tools and effective == ["lookup"]
    assert [schema["function"]["name"] for schema in body["tools"]] == ["lookup", "finish"]
    assert notes[-1]["tools_offered"] == ["finish", "lookup"]


def _payloads(chunks: list[bytes]) -> list[dict[str, Any]]:
    return [
        json.loads(line[6:])
        for chunk in chunks
        for line in chunk.decode().splitlines()
        if line.startswith("data: ") and line[6:] != "[DONE]"
    ]


def _tool_names(chunks: list[bytes]) -> list[str]:
    return [
        call["function"]["name"]
        for payload in _payloads(chunks)
        for choice in payload.get("choices", [])
        for call in (choice.get("delta") or {}).get("tool_calls", [])
    ]


async def _run_tool_loop(
    monkeypatch: pytest.MonkeyPatch,
    body: dict[str, Any],
    effective_tools: list[str],
    responses: list[_StreamResponse],
    dispatched: list[str],
) -> list[bytes]:
    client = _StreamClient(responses)
    monkeypatch.setattr(streaming, "_http_client", client)
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda _url: "omlx")

    async def dispatch(call: dict[str, Any], *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        name = call["function"]["name"]
        dispatched.append(name)
        return {"role": "tool", "tool_call_id": call.get("id"), "name": name, "content": "ok"}

    monkeypatch.setattr(streaming, "_dispatch_tool_call", dispatch)
    return [
        chunk
        async for chunk in streaming._tool_loop_frames(
            "http://fake/v1/chat/completions",
            body,
            "arm-test",
            "model",
            "",
            set(effective_tools),
        )
    ]


@pytest.mark.anyio
async def test_bite_finish_is_returned_on_last_hop_but_workspace_tool_is_not_dispatched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, effective, has_tools = await _prepare_request(
        monkeypatch, bite_tools=["lookup", "finish"], max_hops=2
    )
    assert has_tools
    dispatched: list[str] = []
    chunks = await _run_tool_loop(
        monkeypatch,
        body,
        effective,
        [_tool_response("lookup"), _tool_response("finish")],
        dispatched,
    )
    assert _tool_names(chunks) == ["finish"]
    assert dispatched == ["lookup"]

    # The JSON repair request has one remaining hop; finish is still returned.
    body, effective, has_tools = await _prepare_request(
        monkeypatch, bite_tools=["lookup", "finish"], max_hops=1
    )
    chunks = await _run_tool_loop(
        monkeypatch, body, effective, [_tool_response("finish")], dispatched
    )
    assert _tool_names(chunks) == ["finish"]

    dispatched.clear()
    body, effective, has_tools = await _prepare_request(
        monkeypatch, bite_tools=["lookup", "finish"], max_hops=1
    )
    assert has_tools
    chunks = await _run_tool_loop(
        monkeypatch, body, effective, [_tool_response("lookup")], dispatched
    )
    assert dispatched == []
    assert not _tool_names(chunks)
    assert "Tool-use limit (1 hops)" in "".join(
        (choice.get("delta") or {}).get("content") or ""
        for payload in _payloads(chunks)
        for choice in payload.get("choices", [])
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("emitted_name", "expected_dispatch"),
    [("outside", []), ("lookup", ["lookup"])],
)
async def test_bite_allowlist_gates_real_stream_dispatch(
    monkeypatch: pytest.MonkeyPatch, emitted_name: str, expected_dispatch: list[str]
) -> None:
    body, effective, has_tools = await _prepare_request(
        monkeypatch,
        bite_tools=["lookup", "finish"],
        max_hops=2,
        workspace_tools=["lookup", "outside"],
    )
    assert has_tools and effective == ["lookup"]
    responses = [_tool_response(emitted_name)]
    if emitted_name == "lookup":
        responses.append(_answer_response())
    dispatched: list[str] = []
    chunks = await _run_tool_loop(monkeypatch, body, effective, responses, dispatched)
    assert dispatched == expected_dispatch
    if emitted_name == "outside":
        assert _tool_names(chunks) == ["outside"]


@pytest.mark.anyio
async def test_empty_workspace_intersection_keeps_only_finish_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, effective, has_tools = await _prepare_request(
        monkeypatch,
        bite_tools=["finish"],
        max_hops=1,
        workspace_tools=["lookup"],
    )
    assert has_tools and effective == []
    assert [tool["function"]["name"] for tool in body["tools"]] == ["finish"]


@pytest.mark.anyio
async def test_ordinary_last_hop_keeps_existing_client_tool_limit_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(streaming, "MAX_TOOL_HOPS", 1)
    body = {"messages": [], "tools": [_tool_schema("client_lookup")]}
    dispatched: list[str] = []
    chunks = await _run_tool_loop(
        monkeypatch, body, [], [_tool_response("client_lookup")], dispatched
    )
    assert not _tool_names(chunks)
    assert "Tool-use limit (1 hops)" in "".join(
        (choice.get("delta") or {}).get("content") or ""
        for payload in _payloads(chunks)
        for choice in payload.get("choices", [])
    )
    assert dispatched == []


@pytest.mark.anyio
async def test_invalid_bite_hop_limit_fails_before_tool_setup_or_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refresh_calls: list[bool] = []
    with pytest.raises(HTTPException) as caught:
        await _prepare_request(
            monkeypatch,
            bite_tools=["finish"],
            max_hops=0,
            refresh_calls=refresh_calls,
        )
    assert caught.value.status_code == 400
    assert refresh_calls == []


@pytest.mark.anyio
async def test_configured_nonpositive_global_hops_keeps_empty_loop_for_ordinary_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(streaming, "MAX_TOOL_HOPS", 0)
    client = _StreamClient([_tool_response("client_lookup")])
    monkeypatch.setattr(streaming, "_http_client", client)
    chunks = [
        chunk
        async for chunk in streaming._tool_loop_frames(
            "http://fake/v1/chat/completions",
            {"messages": [], "tools": [_tool_schema("client_lookup")]},
            "arm-test",
            "model",
            "",
            set(),
        )
    ]
    assert chunks == []
    assert client.requests == []


def test_bite_thinking_survives_both_engine_injectors(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = "arm-thinking-test"
    monkeypatch.setitem(validation.WORKSPACES, workspace, {"think": False})
    body = {
        "portal_bite_tools": ["finish"],
        "chat_template_kwargs": {"enable_thinking": True},
    }
    ollama = validation._inject_ollama_options(body, workspace)
    omlx = validation._inject_omlx_options(body, workspace)
    assert ollama["think"] is True
    assert ollama.get("reasoning_effort") != "none"
    assert omlx["chat_template_kwargs"]["enable_thinking"] is True


def test_production_fast_and_deep_seats_remain_think_off() -> None:
    config = yaml.safe_load(Path("config/portal.yaml").read_text(encoding="utf-8"))
    variants = config["workspaces"]["auto-daily"]["variants"]
    assert variants["fast"]["think"] is False
    assert variants["deep"]["think"] is False
