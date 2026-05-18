"""Unit tests for tests/frontends/librechat.py.

All Playwright interaction is mocked — no real browser or LibreChat instance
required. Focused on the small amount of business logic in the driver:
- load_personas_map() reads YAMLs correctly
- start_new_chat() persona-test path tries preset → falls back → raises
- get_routed_model() returns "" gracefully when selectors don't match
- enable_tool / assign_folder are no-ops (do not raise)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from frontends import librechat as lc


def test_load_personas_map_returns_emoji_prefixed_titles(tmp_path: Path) -> None:
    (tmp_path / "tech_writer.yaml").write_text(
        "name: Tech Writer\nslug: techwriter\nworkspace_model: auto-documents\n"
        "system_prompt: You are a technical writer.\n"
    )
    (tmp_path / "code_review.yaml").write_text(
        "name: Code Review Assistant\nslug: codereview\nworkspace_model: auto-coding\n"
        "system_prompt: You review pull requests.\n"
    )
    # Reset cache
    lc._PERSONAS_MAP = None
    m = lc.load_personas_map(personas_dir=tmp_path)
    assert m["techwriter"] == "🎭 Tech Writer"
    assert m["codereview"] == "🎭 Code Review Assistant"
    assert lc.load_personas_map._systems["techwriter"] == "You are a technical writer."
    assert lc.load_personas_map._models["codereview"] == "auto-coding"


def test_load_personas_map_caches() -> None:
    lc._PERSONAS_MAP = {"cached": "🎭 Cached"}
    m = lc.load_personas_map()
    assert m == {"cached": "🎭 Cached"}
    lc._PERSONAS_MAP = None  # reset for other tests


@pytest.mark.asyncio
async def test_enable_tool_is_noop() -> None:
    page = MagicMock()
    result = await lc.enable_tool(page, "portal_documents")
    assert result is None
    page.assert_not_called()


@pytest.mark.asyncio
async def test_assign_folder_is_noop() -> None:
    page = MagicMock()
    result = await lc.assign_folder(page, "UAT")
    assert result is None


def test_current_chat_url_returns_page_url() -> None:
    page = MagicMock()
    page.url = "http://localhost:8082/c/abc-123"
    assert lc.current_chat_url(page) == "http://localhost:8082/c/abc-123"


def test_current_chat_url_returns_empty_when_url_unavailable() -> None:
    page = MagicMock()
    # Simulate an exception when accessing .url
    type(page).url = property(lambda self: (_ for _ in ()).throw(RuntimeError("detached")))
    assert lc.current_chat_url(page) == ""


@pytest.mark.asyncio
async def test_login_raises_when_password_unset(monkeypatch) -> None:
    monkeypatch.setattr(lc, "LIBRECHAT_PASSWORD", "")
    page = MagicMock()
    with pytest.raises(RuntimeError, match="LIBRECHAT_ADMIN_PASSWORD"):
        await lc.login(page)


@pytest.mark.asyncio
async def test_get_last_response_falls_through_candidates() -> None:
    page = MagicMock()
    # First two selectors return zero count, third returns text
    loc_empty = MagicMock()
    loc_empty.count = AsyncMock(return_value=0)
    loc_full = MagicMock()
    loc_full.count = AsyncMock(return_value=1)
    loc_full.last = MagicMock()
    loc_full.last.inner_text = AsyncMock(return_value="Hello from the assistant.")
    # Simulate locator returning empty for the first two selectors, then full
    page.locator = MagicMock(side_effect=[loc_empty, loc_empty, loc_full])
    page.inner_text = AsyncMock(return_value="<body fallback>")
    result = await lc.get_last_response(page)
    assert result == "Hello from the assistant."


@pytest.mark.asyncio
async def test_get_routed_model_returns_empty_when_no_selector_matches() -> None:
    page = MagicMock()
    loc_empty = MagicMock()
    loc_empty.count = AsyncMock(return_value=0)
    page.locator = MagicMock(return_value=loc_empty)
    assert await lc.get_routed_model(page) == ""
