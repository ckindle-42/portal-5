from __future__ import annotations

from typing import Any

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from portal.platform.inference.router.auth import PIPELINE_API_KEY
from portal.platform.inference.router.preinject import _inject_persona_system_prompt
from portal.platform.inference.router.workspaces import _PERSONA_MAP

_HEADERS = {"Authorization": f"Bearer {PIPELINE_API_KEY}"}


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
    assert text.index(prompt) < text.index("CRITICAL OUTPUT RULE")


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
    assert len(prompt) < text.index("CALLER_SENTINEL") < text.index("CRITICAL OUTPUT RULE")


def test_plain_workspace_id_is_unchanged(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages = [{"role": "user", "content": "hi"}]
    body = _post(client, monkeypatch, {"model": "auto-spl", "messages": messages})
    assert body["messages"] == messages


def test_prompt_template_persona_uses_the_template_file() -> None:
    from portal.platform.inference.config import _load_prompt_template

    persona = _PERSONA_MAP["bench-qwen36-abl-27b"]
    assert persona.prompt_template
    expected = _load_prompt_template(persona.prompt_template)
    out = _inject_persona_system_prompt(
        "bench-qwen36-abl-27b",
        {"messages": [{"role": "user", "content": "hi"}]},
    )
    assert out["messages"][0]["content"] == expected


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
