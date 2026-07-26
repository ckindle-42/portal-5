"""Unit coverage for Open WebUI browser-contract helpers."""

from __future__ import annotations

import pytest

from tests.uat.browser import _dismiss_startup_overlays
from tests.uat.owui_api import _assistant_message_text


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
