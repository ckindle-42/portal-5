"""Empty-prompt guard: /v1/chat/completions must 400 fast, never cold-load a model.

Pins the live QAT Stage 1 defect (s1-neg-empty-prompt): an empty user prompt was
forwarded to a GPU backend instead of rejected with an OpenAI-style 400.
"""

from __future__ import annotations

import typing
from unittest.mock import MagicMock

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from portal.platform.inference.router.auth import PIPELINE_API_KEY
from portal.platform.inference.router.validation import empty_prompt_error

ERROR_BODY = {
    "error": {
        "message": "Empty prompt: provide message content or an attachment.",
        "type": "invalid_request_error",
    }
}
HEADERS = {"Authorization": f"Bearer {PIPELINE_API_KEY}"}


def _user(content: typing.Any) -> dict[str, typing.Any]:
    return {"model": "auto", "messages": [{"role": "user", "content": content}]}


@pytest.mark.parametrize(
    "body",
    [
        _user(""),
        _user("   \n"),
        _user(None),
        _user([]),
        _user([{"type": "text", "text": ""}, {"type": "text", "text": "  \n"}]),
        {"model": "auto", "messages": []},
        {"model": "auto"},
        {"model": "auto", "messages": [{"role": "user"}]},
    ],
    ids=[
        "empty-string",
        "whitespace",
        "null-content",
        "empty-parts-list",
        "blank-text-parts",
        "empty-messages",
        "missing-messages",
        "missing-content",
    ],
)
def test_empty_prompt_error_rejects(body: dict[str, typing.Any]) -> None:
    assert empty_prompt_error(body) == ERROR_BODY["error"]


@pytest.mark.parametrize(
    "body",
    [
        _user("hello"),
        _user("  hello  "),
        _user([{"type": "text", "text": ""}, {"type": "image_url", "image_url": {"url": "x"}}]),
        _user(
            [{"type": "text", "text": " "}, {"type": "input_audio", "input_audio": {"data": "x"}}]
        ),
        _user([{"type": "file", "file": {"file_id": "f1"}}]),
        _user([{"type": "text", "text": "hi"}]),
        {"model": "auto", "messages": [{"role": "tool", "tool_call_id": "c1", "content": ""}]},
        {"model": "auto", "messages": [{"role": "assistant", "content": ""}]},
        {**_user(""), "files": [{"id": "f1", "name": "a.txt"}]},
        {**_user(""), "attachments": [{"id": "f1"}]},
        {**_user(""), "portal_attached_files": [{"id": "f1", "path": "/workspace/a.txt"}]},
        {
            "model": "auto",
            "messages": [{"role": "user", "content": "", "files": [{"id": "f1"}]}],
        },
        {
            "model": "auto",
            "messages": [{"role": "user", "content": "", "attachments": [{"id": "f1"}]}],
        },
        {
            "model": "auto",
            "messages": [{"role": "user", "content": "", "tool_calls": [{"id": "c1"}]}],
        },
    ],
    ids=[
        "plain-text",
        "padded-text",
        "image-url-part",
        "input-audio-part",
        "file-part",
        "text-part",
        "tool-role-last",
        "assistant-role-last",
        "top-level-files",
        "top-level-attachments",
        "portal-attached-files",
        "message-files",
        "message-attachments",
        "message-tool-calls",
    ],
)
def test_empty_prompt_error_passes(body: dict[str, typing.Any]) -> None:
    assert empty_prompt_error(body) is None


@pytest.fixture
def api() -> typing.Iterator[typing.Any]:
    """FastAPI TestClient over the real app with a fake backend registry."""
    import portal.platform.inference.router.handlers as handlers_mod
    from portal.platform.inference.router_pipe import app
    from tests.unit.test_pipeline import _make_fake_backend

    handlers_mod.registry = _make_fake_backend()
    with TestClient(app) as test_client:
        yield test_client
    handlers_mod.registry = None


@pytest.fixture
def no_backend(api: typing.Any, monkeypatch: pytest.MonkeyPatch) -> typing.Any:
    """Fail loudly if routing or dispatch reaches any backend call."""
    import portal.platform.inference.router.handlers as handlers_mod

    async def _forbidden(*_args: typing.Any, **_kwargs: typing.Any) -> typing.Any:
        raise AssertionError("empty prompt reached routing/dispatch")

    monkeypatch.setattr(handlers_mod, "_resolve_auto_routing", _forbidden)
    monkeypatch.setattr(handlers_mod, "_dispatch_council", _forbidden)
    monkeypatch.setattr(handlers_mod, "_dispatch_non_streaming", _forbidden)
    return api


@pytest.mark.parametrize("content", ["", "   \n", None], ids=["empty", "whitespace", "null"])
def test_http_empty_content_400_no_backend(no_backend: typing.Any, content: typing.Any) -> None:
    response = no_backend.post("/v1/chat/completions", json=_user(content), headers=HEADERS)
    assert response.status_code == 400, response.text
    assert response.json() == ERROR_BODY


def test_http_empty_messages_400_no_backend(no_backend: typing.Any) -> None:
    response = no_backend.post(
        "/v1/chat/completions", json={"model": "auto", "messages": []}, headers=HEADERS
    )
    assert response.status_code == 400, response.text
    assert response.json() == ERROR_BODY


@pytest.fixture
def served(api: typing.Any, monkeypatch: pytest.MonkeyPatch) -> tuple[typing.Any, MagicMock]:
    """Let routing run but stub dispatch, recording that the guard passed."""
    import portal.platform.inference.router.handlers as handlers_mod

    dispatch = MagicMock()

    async def _council(*_args: typing.Any, **_kwargs: typing.Any) -> None:
        return None

    async def _non_streaming(*_args: typing.Any, **_kwargs: typing.Any) -> JSONResponse:
        dispatch()
        return JSONResponse({"served": True})

    monkeypatch.setattr(handlers_mod, "_dispatch_council", _council)
    monkeypatch.setattr(handlers_mod, "_dispatch_non_streaming", _non_streaming)
    return api, dispatch


def test_http_image_part_with_empty_text_passes(served: tuple[typing.Any, MagicMock]) -> None:
    api, dispatch = served
    body = {
        "model": "auto-coding",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": ""},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,x"}},
                ],
            }
        ],
    }
    response = api.post("/v1/chat/completions", json=body, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json() == {"served": True}
    dispatch.assert_called_once()


def test_http_tool_result_continuation_passes(served: tuple[typing.Any, MagicMock]) -> None:
    api, dispatch = served
    body = {
        "model": "auto-coding",
        "messages": [
            {"role": "user", "content": "lookup"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": ""},
        ],
    }
    response = api.post("/v1/chat/completions", json=body, headers=HEADERS)
    assert response.status_code == 200, response.text
    dispatch.assert_called_once()


def test_http_top_level_files_with_empty_text_passes(
    served: tuple[typing.Any, MagicMock],
) -> None:
    api, dispatch = served
    body = {
        "model": "auto-coding",
        "messages": [{"role": "user", "content": ""}],
        "files": [{"id": "f1", "name": "a.txt", "type": "text/plain"}],
    }
    response = api.post("/v1/chat/completions", json=body, headers=HEADERS)
    assert response.status_code == 200, response.text
    dispatch.assert_called_once()
