"""Unit coverage for Open WebUI browser-contract helpers."""

from __future__ import annotations

import pytest

from tests.uat.browser import _dismiss_startup_overlays
from tests.uat.owui_api import _assistant_message_text, owui_response_complete


class _FakeButton:
    def __init__(self, *, present: bool, visible: bool) -> None:
        self.present = present
        self.visible = visible
        self.clicks = 0

    @property
    def first(self) -> _FakeButton:
        return self

    async def count(self) -> int:
        return int(self.present)

    async def is_visible(self) -> bool:
        return self.visible

    async def click(self) -> None:
        self.clicks += 1


class _FakePage:
    def __init__(self, button: _FakeButton) -> None:
        self.button = button
        self.selectors: list[str] = []
        self.waits: list[int] = []

    def locator(self, selector: str) -> _FakeButton:
        self.selectors.append(selector)
        return self.button

    async def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)


@pytest.mark.asyncio
async def test_dismisses_visible_release_notes_overlay() -> None:
    button = _FakeButton(present=True, visible=True)
    page = _FakePage(button)

    await _dismiss_startup_overlays(page)

    assert page.selectors == ['button:has-text("Okay, Let\'s Go!")']
    assert button.clicks == 1
    assert page.waits == [250]


@pytest.mark.asyncio
async def test_ignores_absent_release_notes_overlay() -> None:
    button = _FakeButton(present=False, visible=False)
    page = _FakePage(button)

    await _dismiss_startup_overlays(page)

    assert button.clicks == 0
    assert page.waits == []


def test_extracts_responses_api_output_when_legacy_content_is_empty() -> None:
    message = {
        "role": "assistant",
        "content": "",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "First visible step."}],
            },
            {"type": "function_call", "name": "search", "arguments": "{}"},
            {
                "type": "function_call_output",
                "output": [{"type": "input_text", "text": "private tool payload"}],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Final visible answer."}],
            },
        ],
    }

    assert _assistant_message_text(message) == "First visible step.\nFinal visible answer."


def test_legacy_content_remains_authoritative() -> None:
    message = {
        "role": "assistant",
        "content": "Legacy answer",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Responses answer"}],
            }
        ],
    }

    assert _assistant_message_text(message) == "Legacy answer"


def test_response_complete_uses_explicit_done_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Response:
        def json(self) -> dict:
            return {
                "chat": {
                    "history": {
                        "messages": {
                            "user": {"role": "user", "content": "hello"},
                            "assistant": {
                                "role": "assistant",
                                "content": "",
                                "done": True,
                                "output": [
                                    {
                                        "type": "message",
                                        "role": "assistant",
                                        "content": [
                                            {"type": "output_text", "text": "Completed answer"}
                                        ],
                                    }
                                ],
                            },
                        }
                    }
                }
            }

    monkeypatch.setattr("tests.uat.owui_api.httpx.get", lambda *args, **kwargs: _Response())

    assert owui_response_complete("token", "chat-id") is True


def test_response_complete_rejects_inflight_or_missing_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Response:
        def json(self) -> dict:
            return {
                "chat": {
                    "history": {
                        "messages": {
                            "assistant": {
                                "role": "assistant",
                                "content": "Partial",
                                "done": False,
                            }
                        }
                    }
                }
            }

    monkeypatch.setattr("tests.uat.owui_api.httpx.get", lambda *args, **kwargs: _Response())

    assert owui_response_complete("token", "chat-id") is False
    assert owui_response_complete("token", "chat-id", min_messages=2) is False
