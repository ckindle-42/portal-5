"""Per-turn tool exposure is bounded (BRIEF_TOOL_EXPOSURE_SCOPE_20261126).

Live QAT s5-route-kubernetes-rbac (2026-11-26): a conceptual Kubernetes RBAC
question on auto-coding exposed all 63 registered workspace schemas (~10k
prompt tokens of prefill, 86.7s TTFT). All 63 were workspace-declared; the
OWUI builtin/mirror drops held, but a later turn leaked an unprefixed
`list_memories` echo past the static denylist. A signal-free turn now offers
only the bounded default scope; explicit tool asks, file/sandbox asks,
attachments, prior tool use and client tool selections keep the full set.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest

import portal.platform.inference.router.streaming as st
from portal.platform.inference.router import eval_gate
from portal.platform.inference.router import non_streaming as ns
from portal.platform.inference.router.client_tools import merge_client_tools
from portal.platform.inference.router.tools import default_scope_tools
from portal.platform.inference.router.workspaces import WORKSPACES

WS = "test-exposure-scope-ws"

CORE_TOOLS = [
    "execute_python",
    "execute_bash",
    "execute_nodejs",
    "sandbox_status",
    "list_sessions",
    "reset_session",
    "read_pdf",
    "read_word_document",
    "remember",
    "recall",
]
DOMAIN_TOOLS = [
    "proxmox_vm_start",
    "proxmox_list_nodes",
    "proxmox_deploy_ctf_lab",
    "unifi_execute",
    "unifi_tool_index",
    "browser_navigate",
    "browser_snapshot",
    "git_push",
    "list_memories",
]
WS_TOOLS = CORE_TOOLS + DOMAIN_TOOLS
REGISTERED = sorted(set(WS_TOOLS) | {"forget", "clear_memories"})

RBAC_TURN_1 = (
    "We run Kubernetes 1.30 and need read-only access to pods in namespace staging. "
    "Propose the least-privilege Role and RoleBinding, explain the scope choice, "
    "and give a safe way to verify it."
)
RBAC_TURN_2 = (
    "Which permission does this avoid granting, and how would you test the binding "
    "as the target service account?"
)


def _schema(name: str) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {"name": name, "description": "d" * 40, "parameters": {"type": "object"}},
    }


def _names(tools: list[dict[str, Any]]) -> list[str]:
    return [t["function"]["name"] for t in tools]


@pytest.fixture
def scope_env(monkeypatch: pytest.MonkeyPatch) -> str:
    from portal.platform.inference import tool_registry as registry_mod

    monkeypatch.setitem(WORKSPACES, WS, {"model_hint": "m", "tools": list(WS_TOOLS)})
    monkeypatch.setattr(st, "_model_supports_tools", lambda _m: True)
    monkeypatch.setattr(st, "_inject_ollama_options", lambda body, _ws: body)

    async def _refresh() -> None:
        return None

    monkeypatch.setattr(registry_mod.tool_registry, "refresh", _refresh)
    monkeypatch.setattr(
        registry_mod.tool_registry, "get_openai_tools", lambda names: [_schema(n) for n in names]
    )
    monkeypatch.setattr(registry_mod.tool_registry, "list_tool_names", lambda: list(REGISTERED))
    return WS


async def _build(body: dict[str, Any]) -> tuple[dict[str, Any], list[str], bool]:
    engine_body, effective, has_tools, _no_tools = await st._build_streaming_request(
        body, SimpleNamespace(type="ollama"), "m", WS, ""
    )
    return engine_body, effective, has_tools


def _user(text: str) -> list[dict[str, Any]]:
    return [{"role": "user", "content": text}]


# ── the bounded default ──────────────────────────────────────────────────────


@pytest.mark.anyio
@pytest.mark.parametrize("turn", [RBAC_TURN_1, RBAC_TURN_2])
async def test_conceptual_coding_turn_exposes_only_the_bounded_scope(
    scope_env: str, turn: str
) -> None:
    engine_body, effective, has_tools = await _build({"model": WS, "messages": _user(turn)})
    exposed = _names(engine_body.get("tools", []))
    assert set(exposed) == set(default_scope_tools(effective)) == set(CORE_TOOLS)
    assert not set(exposed) & set(DOMAIN_TOOLS)
    assert has_tools is True
    assert engine_body.get("tool_choice") != "required"
    # the dispatch whitelist is untouched — only the schema offer is bounded
    assert set(effective) == set(WS_TOOLS)


def test_default_scope_is_bounded_and_declared_only() -> None:
    scoped = default_scope_tools(WS_TOOLS)
    assert set(scoped) == set(CORE_TOOLS)
    assert set(scoped) < set(WS_TOOLS)  # a proper subset: the domain schemas stay out


# ── the safe defaults: turns that need tools still get them ─────────────────


@pytest.mark.anyio
async def test_explicit_tool_ask_still_gets_the_needed_tools(scope_env: str) -> None:
    engine_body, _effective, _has_tools = await _build(
        {"model": WS, "messages": _user("Use execute_python to print SCHEMA_42 and quote it.")}
    )
    exposed = set(_names(engine_body["tools"]))
    assert {"execute_python", "sandbox_status", "list_sessions"} <= exposed
    assert engine_body["tool_choice"] == "required"


@pytest.mark.anyio
async def test_sandbox_ask_still_gets_the_needed_tools(scope_env: str) -> None:
    engine_body, _effective, _has_tools = await _build(
        {
            "model": WS,
            "messages": _user("Run this python and report the output: print(6 * 7)"),
        }
    )
    assert "execute_python" in _names(engine_body["tools"])


@pytest.mark.anyio
async def test_file_ask_with_attachment_keeps_the_full_set(scope_env: str) -> None:
    engine_body, _effective, _has_tools = await _build(
        {
            "model": WS,
            "messages": _user("Summarise the attached report in three bullets."),
            "files": [{"id": "f1"}],
        }
    )
    assert set(_names(engine_body["tools"])) == set(WS_TOOLS)


@pytest.mark.anyio
async def test_prior_tool_use_in_the_conversation_keeps_the_full_set(scope_env: str) -> None:
    messages = [
        {"role": "user", "content": "start the lab vm"},
        {"role": "assistant", "tool_calls": [{"function": {"name": "proxmox_vm_start"}}]},
        {"role": "tool", "content": "ok"},
        {"role": "user", "content": "and the second one too"},
    ]
    engine_body, _effective, _has_tools = await _build({"model": WS, "messages": messages})
    assert set(_names(engine_body["tools"])) == set(WS_TOOLS)


@pytest.mark.anyio
async def test_user_tool_selection_keeps_the_full_set_and_merges(scope_env: str) -> None:
    engine_body, _effective, _has_tools = await _build(
        {
            "model": WS,
            "messages": _user(RBAC_TURN_1),
            "tools": [_schema("custom_siem_query")],
        }
    )
    assert set(_names(engine_body["tools"])) == set(WS_TOOLS) | {"custom_siem_query"}


@pytest.mark.anyio
async def test_agentic_workspace_keeps_the_full_set(
    monkeypatch: pytest.MonkeyPatch, scope_env: str
) -> None:
    WORKSPACES[WS]["mode"] = "agentic"
    engine_body, _effective, _has_tools = await _build(
        {"model": WS, "messages": _user(RBAC_TURN_1)}
    )
    assert set(_names(engine_body["tools"])) == set(WS_TOOLS)


# ── OWUI-supplied schemas: only what the request asks for ───────────────────


@pytest.mark.anyio
async def test_unprefixed_registered_echo_is_dropped(scope_env: str) -> None:
    # Live 2026-11-26: OWUI injected a bare `list_memories` the workspace never
    # declared; the static builtin denylist did not cover it.
    engine_body, _effective, _has_tools = await _build(
        {"model": WS, "messages": _user(RBAC_TURN_1), "tools": [_schema("forget")]}
    )
    exposed = _names(engine_body.get("tools", []))
    assert "forget" not in exposed and "list_memories" not in exposed
    assert set(exposed) - {"list_memories"} == set(CORE_TOOLS)


def test_merge_drops_unprefixed_registered_echoes_and_keeps_external() -> None:
    offered = [_schema("recall")]
    client = [_schema("list_memories"), _schema("portal_memory_recall"), _schema("bench_probe")]
    merged = merge_client_tools(offered, client, REGISTERED)
    assert _names(merged) == ["recall", "bench_probe"]


# ── per-turn trace fields ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_trace_records_exposed_count_and_schema_token_estimate(
    monkeypatch: pytest.MonkeyPatch, scope_env: str
) -> None:
    notes: list[dict[str, Any]] = []
    monkeypatch.setattr(eval_gate, "trace_note", lambda **fields: notes.append(fields))
    await _build({"model": WS, "messages": _user(RBAC_TURN_1)})
    note = next(n for n in notes if "tools_exposed" in n)
    assert note["tools_exposed"] == len(CORE_TOOLS)
    assert note["tools_scope"] == "default"
    assert note["tool_schema_tokens_est"] > 0
    assert note["tools_offered"] == sorted(CORE_TOOLS)


# ── non-streaming path mirrors the streaming one ────────────────────────────


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


@pytest.fixture
def ns_scope_env(monkeypatch: pytest.MonkeyPatch, scope_env: str) -> _CapturingClient:
    from portal.platform.inference import tool_registry as registry_mod

    monkeypatch.setattr(ns, "registry", SimpleNamespace(request_timeout=5.0))
    monkeypatch.setattr(ns, "_model_supports_tools", lambda _m: True)
    monkeypatch.setattr(ns, "_resolve_persona_tools", lambda *_a: sorted(WS_TOOLS))

    async def _dispatch(tc: dict, *_a: Any, **_k: Any) -> dict[str, Any]:
        return {"role": "tool", "tool_call_id": tc.get("id"), "content": "ok"}

    monkeypatch.setattr(ns, "_dispatch_tool_call", _dispatch)
    client = _CapturingClient()
    monkeypatch.setattr(ns, "_http_client", client)
    assert registry_mod.tool_registry is not None
    return client


def _backend() -> Any:
    return SimpleNamespace(
        id="b",
        type="ollama",
        chat_url="http://engine/v1/chat/completions",
        models=["m"],
        resolve_model=lambda h: h if h == "m" else None,
    )


@pytest.mark.anyio
async def test_nonstream_conceptual_turn_exposes_only_the_bounded_scope(
    ns_scope_env: _CapturingClient,
) -> None:
    body = {"model": WS, "messages": _user(RBAC_TURN_1)}
    result = await ns._try_non_streaming(_backend(), body, WS, 0.0)
    assert result is not None
    assert set(_names(ns_scope_env.bodies[0]["tools"])) == set(CORE_TOOLS)
