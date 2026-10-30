from __future__ import annotations

from typing import Any

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from portal.platform.inference.router.auth import PIPELINE_API_KEY
from portal.platform.inference.router.preinject import _inject_persona_system_prompt
from portal.platform.inference.router.workspaces import _PERSONA_MAP

_HEADERS = {"Authorization": f"Bearer {PIPELINE_API_KEY}"}
_ROLE_SLUG = "codereviewer"


@pytest.fixture
def client():
    import portal.platform.inference.router.handlers as handlers_mod
    from portal.platform.inference.router_pipe import app
    from tests.unit.test_pipeline import _make_fake_backend

    handlers_mod.registry = _make_fake_backend()
    with TestClient(app) as test_client:
        yield test_client
    handlers_mod.registry = None


def _post(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> dict[str, Any]:
    import portal.platform.inference.router.handlers as handlers_mod

    seen: dict[str, Any] = {}

    async def capture(*args: Any, **_kwargs: Any) -> JSONResponse:
        seen["body"] = args[1]
        workspace = args[2]
        return JSONResponse(
            {
                "id": "chatcmpl-test",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            },
            headers={"x-portal-route": f"{workspace};fake;m"},
        )

    monkeypatch.setattr(handlers_mod, "_try_non_streaming", capture)
    response = client.post("/v1/chat/completions", json=payload, headers=_HEADERS)
    assert response.status_code == 200, response.text
    return seen["body"]


def _system(body: dict[str, Any]) -> str:
    for message in body["messages"]:
        if message.get("role") == "system":
            content = message["content"]
            assert isinstance(content, str)
            return content
    raise AssertionError("no system message")


def test_persona_id_via_api_gets_the_prompt(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompt = _PERSONA_MAP["agenticheavy"].system_prompt
    text = _system(
        _post(
            client,
            monkeypatch,
            {"model": "agenticheavy", "messages": [{"role": "user", "content": "hi"}]},
        )
    )
    assert text.startswith(prompt)
    assert text.count(prompt) == 1
    assert text.index(prompt) < text.index("WORKING RULE")


def test_openwebui_duplicate_persona_prompt_is_not_doubled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompt = _PERSONA_MAP["agenticheavy"].system_prompt
    text = _system(
        _post(
            client,
            monkeypatch,
            {
                "model": "agenticheavy",
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "hi"},
                ],
            },
        )
    )
    assert text.startswith(prompt)
    assert text.count(prompt) == 1


def test_different_caller_system_message_follows_persona_prompt(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompt = _PERSONA_MAP["agenticheavy"].system_prompt
    text = _system(
        _post(
            client,
            monkeypatch,
            {
                "model": "agenticheavy",
                "messages": [
                    {"role": "system", "content": "CALLER_SENTINEL"},
                    {"role": "user", "content": "hi"},
                ],
            },
        )
    )
    assert text.startswith(prompt)
    assert text.count(prompt) == 1
    assert len(prompt) < text.index("CALLER_SENTINEL") < text.index("WORKING RULE")


def test_plain_workspace_id_is_unchanged(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages = [{"role": "user", "content": "hi"}]
    body = _post(client, monkeypatch, {"model": "auto-spl", "messages": messages})
    assert body["messages"] == messages


def test_prompt_template_persona_uses_the_template_file(monkeypatch) -> None:
    from portal.platform.inference.config import _load_prompt_template
    from portal.platform.inference.router import workspaces as ws_mod

    # Load the bench persona with the bench workspace catalog.
    monkeypatch.setenv("PORTAL_BENCH_WORKSPACES", "1")
    ws_mod._load_persona_map()

    persona = _PERSONA_MAP["bench-qwen36-abl-27b"]
    assert persona.prompt_template
    expected = _load_prompt_template(persona.prompt_template)
    out = _inject_persona_system_prompt(
        "bench-qwen36-abl-27b",
        {"messages": [{"role": "user", "content": "hi"}]},
    )
    assert out["messages"][0]["content"] == expected


def _post_route(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    import portal.platform.inference.router.handlers as handlers_mod

    seen: dict[str, Any] = {}

    async def capture(*args: Any, **_kwargs: Any) -> JSONResponse:
        seen["body"] = args[1]
        workspace = args[2]
        return JSONResponse(
            {
                "id": "chatcmpl-test",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            },
            headers={"x-portal-route": f"{workspace};fake;m"},
        )

    monkeypatch.setattr(handlers_mod, "_try_non_streaming", capture)
    response = client.post("/v1/chat/completions", json=payload, headers=_HEADERS)
    assert response.status_code == 200, response.text
    return seen["body"], response.headers["x-portal-route"]


def test_role_slash_keeps_the_engine_and_injects_the_prompt(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompt = _PERSONA_MAP[_ROLE_SLUG].system_prompt
    body, route = _post_route(
        client,
        monkeypatch,
        {
            "model": "auto-daily",
            "messages": [{"role": "user", "content": f"/{_ROLE_SLUG} hello"}],
        },
    )
    assert route.startswith("auto-daily;")
    assert body["model"] == "auto-daily"
    assert _system(body).startswith(prompt)
    user = next(message for message in body["messages"] if message["role"] == "user")
    assert user["content"] == "hello"


def test_unknown_slash_is_untouched(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    messages = [{"role": "user", "content": "/not-a-persona hello"}]
    body = _post(client, monkeypatch, {"model": "auto-spl", "messages": messages})
    assert body["messages"] == messages


def test_slash_without_the_separating_space_is_untouched(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages = [{"role": "user", "content": f"/{_ROLE_SLUG}"}]
    body = _post(client, monkeypatch, {"model": "auto-spl", "messages": messages})
    assert body["messages"] == messages


def test_variant_persona_slash_is_not_a_role(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages = [{"role": "user", "content": "/proofreader hello"}]
    body, route = _post_route(
        client,
        monkeypatch,
        {
            "model": "auto-spl",
            "messages": messages,
        },
    )
    assert route.startswith("auto-spl;")
    assert body["messages"] == messages


def test_role_slash_streams_on_the_same_engine(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import portal.platform.inference.router.handlers as handlers_mod

    prompt = _PERSONA_MAP[_ROLE_SLUG].system_prompt
    seen: dict[str, Any] = {}

    async def capture_build(
        body: dict[str, Any],
        _backend: Any,
        _target_model: str,
        workspace_id: str,
        _persona: str,
    ) -> tuple[dict[str, Any], list[str], bool, bool]:
        seen["body"] = body
        seen["workspace"] = workspace_id
        return body, [], False, True

    def select_backend(_workspace_id: str, candidates: list[Any]) -> tuple[Any, ...]:
        return candidates[0], "m", "", [], "", ""

    async def chunks(*_args: Any, **_kwargs: Any) -> Any:
        yield b"data: [DONE]\n\n"

    monkeypatch.setattr(handlers_mod, "_build_streaming_request", capture_build)
    monkeypatch.setattr(handlers_mod, "_select_streaming_backend", select_backend)
    monkeypatch.setattr(handlers_mod, "_select_stream_fn", lambda *_a, **_k: chunks())
    monkeypatch.setattr(handlers_mod, "_stream_with_fallback", chunks)
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto-daily",
            "stream": True,
            "messages": [{"role": "user", "content": f"/{_ROLE_SLUG} hello"}],
        },
        headers=_HEADERS,
    )
    assert response.status_code == 200, response.text
    assert seen["workspace"] == "auto-daily"
    assert seen["body"]["model"] == "auto-daily"
    assert _system(seen["body"]).startswith(prompt)
    user = next(message for message in seen["body"]["messages"] if message["role"] == "user")
    assert user["content"] == "hello"


def test_follow_up_keeps_the_role_prompt_and_strips_history() -> None:
    from portal.platform.inference.router.preinject import _inject_requested_prompts

    prompt = _PERSONA_MAP[_ROLE_SLUG].system_prompt
    out = _inject_requested_prompts(
        "auto-spl",
        {
            "messages": [
                {"role": "user", "content": f"/{_ROLE_SLUG} fix: teh cat"},
                {"role": "assistant", "content": "fixed"},
                {"role": "user", "content": "and the title"},
            ]
        },
    )
    assert out["messages"][0]["content"].startswith(prompt)
    assert out["messages"][1]["content"] == "fix: teh cat"
    assert out["messages"][2]["content"] == "fixed"
    assert out["messages"][3]["content"] == "and the title"


def test_role_slash_strips_a_text_part() -> None:
    from portal.platform.inference.router.preinject import _inject_requested_prompts

    out = _inject_requested_prompts(
        "auto-spl",
        {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": f"/{_ROLE_SLUG} hello"}],
                }
            ]
        },
    )
    assert out["messages"][1]["content"][0]["text"] == "hello"


def test_list_system_content_keeps_caller_after_the_persona_prompt() -> None:
    prompt = _PERSONA_MAP["agenticheavy"].system_prompt
    out = _inject_persona_system_prompt(
        "agenticheavy",
        {
            "messages": [
                {"role": "system", "content": [{"type": "text", "text": "CALLER_SENTINEL"}]}
            ]
        },
    )
    content = out["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": prompt}
    assert content[1]["text"] == "CALLER_SENTINEL"


def test_role_slash_selects_its_variant_on_its_parent_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from portal.platform.inference.router.preinject import _role_variant_for_workspace

    monkeypatch.setitem(
        _PERSONA_MAP,
        "variantrole",
        SimpleNamespace(delivery="role", workspace_model="engine", variant="seat"),
    )
    body = {"messages": [{"role": "user", "content": "/variantrole work"}]}
    assert _role_variant_for_workspace(body, "engine") == "seat"
    assert _role_variant_for_workspace(body, "other-engine") is None


def test_role_slash_routes_the_parent_engine_to_its_variant(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import portal.platform.inference.router.handlers as handlers_mod

    seen: dict[str, Any] = {}

    async def capture(*args: Any, **_kwargs: Any) -> JSONResponse:
        seen["body"] = args[1]
        seen["workspace"] = args[2]
        return JSONResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(handlers_mod, "_try_non_streaming", capture)
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto-coding",
            "messages": [{"role": "user", "content": "/agenticheavy do the work"}],
        },
        headers=_HEADERS,
    )
    assert response.status_code == 200, response.text
    assert seen["workspace"] == "auto-coding::heavy"
    assert _system(seen["body"]).startswith(_PERSONA_MAP["agenticheavy"].system_prompt)


def test_role_prefix_is_removed_before_auto_routing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import portal.platform.inference.router.handlers as handlers_mod

    seen: dict[str, Any] = {}

    async def route(_workspace: str, messages: list[dict[str, Any]]) -> str:
        seen["messages"] = messages
        return "auto-daily"

    async def capture(*args: Any, **_kwargs: Any) -> JSONResponse:
        return JSONResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(handlers_mod, "_resolve_auto_routing", route)
    monkeypatch.setattr(handlers_mod, "_try_non_streaming", capture)
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "/itexpert help me"}],
        },
        headers=_HEADERS,
    )
    assert response.status_code == 200, response.text
    assert seen["messages"] == [{"role": "user", "content": "help me"}]


def test_behavioural_persona_slash_is_untouched(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only delivery: role personas ride on another engine; a behavioural one keeps its tools."""
    messages = [{"role": "user", "content": "/dailydriver hello"}]
    body = _post(client, monkeypatch, {"model": "auto-spl", "messages": messages})
    assert body["messages"] == messages
