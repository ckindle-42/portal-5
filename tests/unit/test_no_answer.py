"""Who is reading determines the framings: a chat UI is told in words, a program keeps its status."""

from __future__ import annotations

import typing

import pytest

import portal.platform.inference.router.backend_introspect as bi
import portal.platform.inference.router.no_answer as no_answer

WS = "auto-daily"


HINT = str(no_answer.WORKSPACES.get(WS, {}).get("model_hint") or "gemma4:26b")


GUARD_DETAIL = (
    f"Cannot load {HINT}: projected memory 22.7 GiB would exceed host headroom "
    "10.0 GiB (oMLX headroom 8.0 + idle Ollama 2.0 - margin 2) with nothing in flight to wait for"
)


@pytest.fixture(autouse=True)
def _audience() -> typing.Iterator[None]:
    no_answer.set_chat_ui({})
    yield
    no_answer.set_chat_ui({})


def test_owui_aiohttp_user_agent_is_a_chat_ui() -> None:
    assert no_answer.is_chat_ui({"user-agent": "Python/3.11 aiohttp/3.14.3"})


def test_program_clients_are_not_a_chat_ui() -> None:
    for agent in ("python-httpx/0.28.1", "curl/8.7.1", "opencode/0.4.2", "", None):
        assert not no_answer.is_chat_ui({"user-agent": agent})


def test_forwarded_user_header_marks_owui() -> None:
    assert no_answer.is_chat_ui({"x-openwebui-user-id": "u-1"})


def test_explicit_client_header_wins_both_ways() -> None:
    assert no_answer.is_chat_ui({"x-portal-client": "chat", "user-agent": "python-httpx/0.28"})
    assert not no_answer.is_chat_ui(
        {"x-portal-client": "api", "user-agent": "Python/3.11 aiohttp/3.14"}
    )


def test_bite_body_is_always_an_api_request() -> None:
    headers = {"x-portal-client": "chat", "user-agent": "Python/3.11 aiohttp/3.14"}
    body = {"portal_bite_tools": ["finish"]}
    assert not no_answer.is_chat_ui(headers, body)
    no_answer.set_chat_ui(headers, body)
    assert not no_answer.chat_ui()


def test_reason_class_names_what_held_the_model_back() -> None:
    assert no_answer.reason_class([GUARD_DETAIL]) == "memory_refused"
    assert no_answer.reason_class(["m: timed out after 300s"]) == "timeout"
    assert no_answer.reason_class(["m: HTTP 500"]) == "engine_error"
    assert no_answer.reason_class([]) == "no_candidate"


def test_message_names_the_model_the_reason_and_the_retry() -> None:
    text = no_answer.message(HINT, [GUARD_DETAIL], None)
    assert HINT in text
    assert "could not be loaded" in text
    assert "would exceed host headroom" in text
    assert "retry in a minute" in text
    assert "switch to the" not in text


def test_message_wording_follows_the_reason() -> None:
    timeout = no_answer.message(HINT, [f"{HINT}: timed out after 300s"], None)
    assert "did not answer in time" in timeout and "retry in a moment" in timeout
    engine = no_answer.message(HINT, ["backend unreachable"], None)
    assert "could not be served" in engine and "retry in a moment" in engine


async def test_alternative_workspace_matches_a_case_only_resident(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        no_answer,
        "WORKSPACES",
        {WS: {"model_hint": HINT}, "auto-fast": {"model_hint": "qwen3:Q4_K_M"}},
    )
    monkeypatch.setattr(bi, "loaded_models", _loaded({"qwen3:q4_k_m"}))
    assert await no_answer.alternative_workspace(WS, HINT) == ("auto-fast", "qwen3:Q4_K_M")


def _loaded(names: set[str]) -> typing.Callable[[], typing.Awaitable[set[str]]]:
    async def _call() -> set[str]:
        return names

    return _call
