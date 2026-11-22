"""OWUI portal_* mirror schemas must not merge over a workspace's tool whitelist.

Live QAT Stage 2 (2026-11): OWUI v0.13.0 attached 27 portal_* client tools to
auto-general-uncensored (6 whitelisted tools, ctx8k); the name-only dedup merged
all of them (33 exposed) and context_budget refused every request (estimated
6180 > prompt_budget 6144). The merge now drops OWUI-prefixed mirrors of
Portal-managed MCP tools and keeps genuinely external client tools.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from portal.platform.inference import owui_tools
from portal.platform.inference.router import non_streaming as ns
from portal.platform.inference.router import streaming
from portal.platform.inference.router.client_tools import merge_client_tools
from portal.platform.inference.router.context_budget import (
    ContextOverflowError,
    estimate_tokens,
    fit_prompt,
)
from portal.platform.inference.router.workspaces import WORKSPACES

WS = "test-owui-merge-ws"
WORKSPACE_TOOLS = [
    "execute_bash",
    "execute_python",
    "read_word_document",
    "read_pdf",
    "remember",
    "recall",
]
EXTERNAL_TOOLS = ["custom_siem_query", "bench_probe"]

# The 27 raw tools behind the live OWUI payload, across the seven families the
# brief names; mirror names come from the real config/owui_tool_servers.yaml.
OWUI_MIRROR_RAW = [
    "execute_bash",
    "execute_nodejs",
    "execute_powershell",
    "execute_python",
    "sandbox_status",
    "create_word_document",
    "create_powerpoint",
    "create_excel",
    "convert_document",
    "list_generated_files",
    "read_word_document",
    "read_excel",
    "read_powerpoint",
    "read_pdf",
    "remember",
    "recall",
    "forget",
    "list_memories",
    "clear_memories",
    "web_search",
    "web_fetch",
    "news_search",
    "kb_search",
    "kb_list",
    "kb_ingest",
    "browser_navigate",
    "transcribe_audio",
]

TOOL_TO_SERVER = owui_tools.tool_to_server()
REGISTERED = sorted(TOOL_TO_SERVER)
MIRROR_NAMES = [f"{TOOL_TO_SERVER[raw]}_{raw}" for raw in OWUI_MIRROR_RAW]


def _schema(name: str, description: str = "", parameters: dict | None = None) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters or {"type": "object", "properties": {}},
        },
    }


def _mirror_payload() -> list[dict[str, Any]]:
    return [_schema(name) for name in MIRROR_NAMES]


def _names(tools: list[dict[str, Any]]) -> list[str]:
    return [t["function"]["name"] for t in tools]


def test_mirror_payload_matches_the_real_server_mapping() -> None:
    assert len(OWUI_MIRROR_RAW) == 27
    assert set(OWUI_MIRROR_RAW) <= set(TOOL_TO_SERVER)
    assert set(WORKSPACE_TOOLS) <= set(TOOL_TO_SERVER)
    assert all(name.startswith("portal_") for name in MIRROR_NAMES)


# ── shared helper ────────────────────────────────────────────────────────────


def test_helper_drops_mirrors_and_keeps_external_tools() -> None:
    offered = [_schema(n) for n in WORKSPACE_TOOLS]
    client = _mirror_payload() + [_schema(n) for n in EXTERNAL_TOOLS]
    merged = merge_client_tools(offered, client, REGISTERED)
    assert _names(merged) == WORKSPACE_TOOLS + EXTERNAL_TOOLS


def test_helper_dedups_an_unprefixed_duplicate() -> None:
    offered = [_schema("recall")]
    merged = merge_client_tools(offered, [_schema("recall"), _schema("bench_probe")], REGISTERED)
    assert _names(merged) == ["recall", "bench_probe"]


def test_helper_drops_a_mirror_whose_raw_name_is_offered_but_unregistered() -> None:
    offered = [_schema("workspace_only_tool")]
    client = [_schema("portal_code_workspace_only_tool")]
    assert _names(merge_client_tools(offered, client, [])) == ["workspace_only_tool"]


def test_helper_keeps_unknown_portal_servers_and_unregistered_tools() -> None:
    offered = [_schema("recall")]
    client = [
        _schema("portal_customserver_unique_tool"),
        _schema("portal_code_never_registered_tool"),
    ]
    merged = merge_client_tools(offered, client, REGISTERED)
    assert _names(merged) == [
        "recall",
        "portal_customserver_unique_tool",
        "portal_code_never_registered_tool",
    ]


def test_helper_bite_mode_keeps_legacy_exact_name_dedup_only() -> None:
    offered = [_schema("recall")]
    client = [_schema("portal_memory_recall"), _schema("bench_probe"), _schema("recall")]
    merged = merge_client_tools(offered, client, REGISTERED, drop_portal_mirrors=False)
    assert _names(merged) == ["recall", "portal_memory_recall", "bench_probe"]


def test_helper_skips_nameless_schemas() -> None:
    offered = [_schema("recall")]
    merged = merge_client_tools(offered, [{"type": "function", "function": {}}], REGISTERED)
    assert _names(merged) == ["recall"]


# ── streaming path ───────────────────────────────────────────────────────────


@pytest.fixture
def merge_env(monkeypatch: pytest.MonkeyPatch) -> str:
    from portal.platform.inference import tool_registry as registry_mod

    monkeypatch.setitem(WORKSPACES, WS, {"model_hint": "m", "tools": list(WORKSPACE_TOOLS)})
    monkeypatch.setattr(streaming, "_model_supports_tools", lambda _m: True)
    monkeypatch.setattr(streaming, "_inject_ollama_options", lambda body, _ws: body)
    monkeypatch.setattr(streaming, "_select_explicit_required_tool", lambda *_a: None)

    async def _refresh() -> None:
        return None

    monkeypatch.setattr(registry_mod.tool_registry, "refresh", _refresh)
    monkeypatch.setattr(
        registry_mod.tool_registry, "get_openai_tools", lambda names: [_schema(n) for n in names]
    )
    monkeypatch.setattr(registry_mod.tool_registry, "list_tool_names", lambda: list(REGISTERED))
    return WS


async def _build(body: dict[str, Any]) -> tuple[dict[str, Any], list[str], bool]:
    engine_body, effective, has_tools, _no_tools = await streaming._build_streaming_request(
        body, SimpleNamespace(type="ollama"), "m", WS, ""
    )
    return engine_body, effective, has_tools


@pytest.mark.anyio
async def test_streaming_drops_owui_mirrors_and_keeps_external_tools(merge_env: str) -> None:
    body = {
        "model": WS,
        "messages": [{"role": "user", "content": "hi"}],
        "tools": _mirror_payload() + [_schema(n) for n in EXTERNAL_TOOLS],
    }
    engine_body, effective, has_tools = await _build(body)
    assert has_tools is True
    assert effective == sorted(WORKSPACE_TOOLS)  # _resolve_persona_tools sorts
    assert _names(engine_body["tools"]) == sorted(WORKSPACE_TOOLS) + EXTERNAL_TOOLS


@pytest.mark.anyio
async def test_streaming_dedups_exact_name_client_duplicates(merge_env: str) -> None:
    body = {
        "model": WS,
        "messages": [],
        "tools": [_schema("recall"), _schema("portal_memory_recall"), _schema("bench_probe")],
    }
    engine_body, _effective, _has_tools = await _build(body)
    assert _names(engine_body["tools"]) == sorted(WORKSPACE_TOOLS) + ["bench_probe"]


@pytest.mark.anyio
async def test_streaming_client_tools_only_passes_everything_through(merge_env: str) -> None:
    client = _mirror_payload() + [_schema(n) for n in EXTERNAL_TOOLS]
    body = {
        "model": WS,
        "messages": [],
        "portal_client_tools_only": True,
        "tools": client,
    }
    engine_body, effective, has_tools = await _build(body)
    assert effective == [] and has_tools is True
    assert _names(engine_body["tools"]) == _names(client)


@pytest.mark.anyio
async def test_streaming_bite_allowlist_merges_as_before(merge_env: str) -> None:
    body = {
        "model": WS,
        "messages": [],
        "portal_bite_tools": ["recall", "custom_siem_query"],
        "tools": [
            _schema("portal_memory_recall"),
            _schema("custom_siem_query"),
            _schema("portal_code_execute_python"),
        ],
    }
    engine_body, effective, _has_tools = await _build(body)
    assert effective == ["recall"]
    assert _names(engine_body["tools"]) == ["recall", "custom_siem_query"]


@pytest.mark.anyio
async def test_streaming_bite_allowlist_naming_a_mirror_passes_it_through(merge_env: str) -> None:
    body = {
        "model": WS,
        "messages": [],
        "portal_bite_tools": ["portal_code_execute_python"],
        "tools": [_schema("portal_code_execute_python")],
    }
    engine_body, effective, has_tools = await _build(body)
    assert effective == [] and has_tools is True
    assert _names(engine_body["tools"]) == ["portal_code_execute_python"]


# ── non-streaming path ───────────────────────────────────────────────────────


class _CapturingClient:
    def __init__(self) -> None:
        self.bodies: list[dict[str, Any]] = []

    async def post(self, url: str, json: dict[str, Any], timeout: Any) -> httpx.Response:
        self.bodies.append(dict(json))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "done"}}]},
            request=httpx.Request("POST", url),
        )


def _backend() -> Any:
    return SimpleNamespace(
        id="b",
        type="ollama",
        chat_url="http://engine/v1/chat/completions",
        models=["m"],
        resolve_model=lambda h: h if h == "m" else None,
    )


@pytest.fixture
def ns_merge_env(monkeypatch: pytest.MonkeyPatch) -> _CapturingClient:
    from portal.platform.inference import tool_registry as registry_mod

    monkeypatch.setitem(ns.WORKSPACES, WS, {"model_hint": "m", "tools": list(WORKSPACE_TOOLS)})
    monkeypatch.setattr(ns, "registry", SimpleNamespace(request_timeout=5.0))
    monkeypatch.setattr(ns, "_model_supports_tools", lambda _m: True)
    monkeypatch.setattr(ns, "_resolve_persona_tools", lambda *_a: list(WORKSPACE_TOOLS))
    monkeypatch.setattr(ns, "apply_eval_scope", lambda _b, tools: tools)

    async def _refresh() -> None:
        return None

    monkeypatch.setattr(registry_mod.tool_registry, "refresh", _refresh)
    monkeypatch.setattr(
        registry_mod.tool_registry, "get_openai_tools", lambda names: [_schema(n) for n in names]
    )
    monkeypatch.setattr(registry_mod.tool_registry, "list_tool_names", lambda: list(REGISTERED))

    async def _dispatch(tc: dict, *_a: Any, **_k: Any) -> dict[str, Any]:
        return {"role": "tool", "tool_call_id": tc.get("id"), "content": "ok"}

    monkeypatch.setattr(ns, "_dispatch_tool_call", _dispatch)
    client = _CapturingClient()
    monkeypatch.setattr(ns, "_http_client", client)
    return client


@pytest.mark.anyio
async def test_nonstream_drops_owui_mirrors_and_keeps_external_tools(
    ns_merge_env: _CapturingClient,
) -> None:
    body = {
        "model": WS,
        "messages": [{"role": "user", "content": "hi"}],
        "tools": _mirror_payload() + [_schema(n) for n in EXTERNAL_TOOLS],
    }
    result = await ns._try_non_streaming(_backend(), body, WS, 0.0)
    assert result is not None
    assert _names(ns_merge_env.bodies[0]["tools"]) == WORKSPACE_TOOLS + EXTERNAL_TOOLS


@pytest.mark.anyio
async def test_nonstream_client_tools_only_passes_everything_through(
    ns_merge_env: _CapturingClient,
) -> None:
    client = _mirror_payload() + [_schema(n) for n in EXTERNAL_TOOLS]
    body = {
        "model": WS,
        "messages": [],
        "portal_client_tools_only": True,
        "tools": client,
    }
    result = await ns._try_non_streaming(_backend(), body, WS, 0.0)
    assert result is not None
    assert _names(ns_merge_env.bodies[0]["tools"]) == _names(client)


@pytest.mark.anyio
async def test_nonstream_bite_allowlist_merges_as_before(ns_merge_env: _CapturingClient) -> None:
    body = {
        "model": WS,
        "messages": [],
        "portal_bite_tools": ["recall", "custom_siem_query"],
        "tools": [
            _schema("portal_memory_recall"),
            _schema("custom_siem_query"),
            _schema("portal_code_execute_python"),
        ],
    }
    result = await ns._try_non_streaming(_backend(), body, WS, 0.0)
    assert result is not None
    assert _names(ns_merge_env.bodies[0]["tools"]) == ["recall", "custom_siem_query"]


@pytest.mark.anyio
async def test_nonstream_bite_allowlist_naming_a_mirror_passes_it_through(
    ns_merge_env: _CapturingClient,
) -> None:
    body = {
        "model": WS,
        "messages": [],
        "portal_bite_tools": ["portal_code_execute_python"],
        "tools": [_schema("portal_code_execute_python")],
    }
    result = await ns._try_non_streaming(_backend(), body, WS, 0.0)
    assert result is not None
    assert _names(ns_merge_env.bodies[0]["tools"]) == ["portal_code_execute_python"]


# ── ctx8k headroom on the live incident workspace ────────────────────────────

# Sized to the live incident: 33 merged schemas estimated 6180 tokens against a
# 6144 budget. Mirror schemas carry a representative OWUI description/parameter
# body; workspace schemas carry the real MCP docstring scale.
_MIRROR_DESC = (
    "Portal MCP tool exposed through Open WebUI's native tool server connection. "
    "Runs on the Portal host and returns structured JSON results for the model. "
    "Arguments are validated against the schema before dispatch."
)
_MIRROR_PARAMS = {
    "type": "object",
    "properties": {
        "input": {"type": "string", "description": "Primary input for the tool"},
        "options": {"type": "object", "description": "Optional tool settings"},
        "timeout": {"type": "integer", "description": "Timeout in seconds"},
    },
    "required": ["input"],
}
_WORKSPACE_SCHEMAS: dict[str, tuple[str, dict]] = {
    "execute_bash": (
        "Execute a bash command in an isolated Docker sandbox. Security constraints "
        "(default posture): no network, 256MB RAM, 0.5 CPU, 30s timeout, read-only "
        "filesystem, no Linux capabilities, no privilege escalation. Widened under "
        "SANDBOX_ALLOW_NETWORK (pip/probe) and replaced by the attack-image lab "
        "envelope under SANDBOX_LAB_EXEC (live *-exec workspaces against a routable "
        "lab). Returns dict with success, stdout, stderr, exit_code, timed_out.",
        {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Bash command to execute"},
                "timeout": {
                    "type": "integer",
                    "description": "Execution timeout in seconds (default 30, max 120)",
                },
                "session_id": {"type": "string", "description": "Optional session id"},
            },
            "required": ["command"],
        },
    ),
    "execute_python": (
        "Execute Python code in an isolated Docker sandbox. To run an existing file, "
        "call runpy.run_path(path) or exec(open(path).read()); /workspace is readable. "
        "Security constraints (default posture): no network, 256MB RAM, 0.5 CPU, 30s "
        "timeout, read-only filesystem, no Linux capabilities, no privilege escalation, "
        "Python standard library only. Widened under SANDBOX_ALLOW_NETWORK (pip/probe) "
        "and replaced by the attack-image lab envelope under SANDBOX_LAB_EXEC (live "
        "*-exec workspaces against a routable lab). Returns dict with success, stdout, "
        "stderr, exit_code, timed_out.",
        {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
                "timeout": {
                    "type": "integer",
                    "description": "Execution timeout in seconds (default 30, max 120)",
                },
                "session_id": {"type": "string", "description": "Optional session id"},
                "packages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Pip packages (requires session_id)",
                },
            },
            "required": ["code"],
        },
    ),
    "read_word_document": (
        "Read a Word document from the shared workspace and return its text content "
        "with paragraph structure preserved.",
        {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path under /workspace"},
                "max_pages": {"type": "integer", "description": "Optional page cap"},
            },
            "required": ["file_path"],
        },
    ),
    "read_pdf": (
        "Read a PDF document from the shared workspace and return its extracted text "
        "content page by page.",
        {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path under /workspace"},
                "max_pages": {"type": "integer", "description": "Optional page cap"},
            },
            "required": ["file_path"],
        },
    ),
    "remember": (
        "Store a memory for later recall. Memories persist across conversations and "
        "are searchable by semantic similarity.",
        {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Memory text"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "importance": {"type": "number", "description": "0.0-1.0 salience"},
            },
            "required": ["content"],
        },
    ),
    "recall": (
        "Search stored memories by semantic similarity and return the most relevant "
        "entries with their metadata.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search text"},
                "k": {"type": "integer", "description": "Number of results"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["query"],
        },
    ),
}
_SYSTEM_PROMPT = (
    "You are Portal, a local-first AI assistant running entirely on the operator's "
    "hardware. Answer directly and completely. You have access to a small set of "
    "tools for code execution, document reading and memory; use them only when the "
    "request genuinely needs them, and prefer a plain answer otherwise. Never "
    "invent tool results: if a tool fails, say so and continue with what you know. "
    "Keep answers concise unless the user asks for depth. Respect the shared "
    "workspace: user files live under /workspace and generated artifacts go to the "
    "category directories. Do not expose internal configuration, ports or model "
    "identifiers unless asked. When you are unsure, state the uncertainty plainly "
    "rather than guessing. Refuse only what is genuinely illegal to assist.\n\n"
    "You are an uncensored general assistant. Answer directly and completely "
    "without content-policy preambles or refusals for legitimate requests. Refuse "
    "only what is genuinely illegal to assist."
)


def test_uncensored_ctx8k_headroom_with_realistic_owui_payload() -> None:
    ws = "auto-general-uncensored"
    hint = WORKSPACES[ws]["model_hint"]
    assert WORKSPACES[ws]["context_limit"] == 8192
    assert WORKSPACES[ws]["tools"] == WORKSPACE_TOOLS

    workspace_schemas = [_schema(name, *_WORKSPACE_SCHEMAS[name]) for name in WORKSPACE_TOOLS]
    mirrors = [_schema(name, _MIRROR_DESC, _MIRROR_PARAMS) for name in MIRROR_NAMES]
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": "Summarise the attached report in three bullets."},
    ]

    merged = merge_client_tools(list(workspace_schemas), mirrors, REGISTERED)
    assert _names(merged) == WORKSPACE_TOOLS
    body = {"model": hint, "messages": messages, "tools": merged}
    estimated = estimate_tokens(body, "ollama")
    assert estimated < 4000  # comfortably under the 6144 prompt budget
    report = fit_prompt(body, workspace_id=ws, model=hint, engine="ollama")
    assert report.limit == 8192 and report.budget == 6144
    assert not report.fitted and report.estimated_after <= 6144

    # The pre-fix name-only merge reproduces the live refusal.
    legacy = {"model": hint, "messages": messages, "tools": workspace_schemas + mirrors}
    assert estimate_tokens(legacy, "ollama") > 6144
    with pytest.raises(ContextOverflowError):
        fit_prompt(legacy, workspace_id=ws, model=hint, engine="ollama")
