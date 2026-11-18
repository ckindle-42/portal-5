"""Unit tests for preselect() — all Ollama calls mocked, no live backend
required. Covers every fallback branch in the §1.9 failure-mode table.
"""

from __future__ import annotations

import pytest

from portal.platform.inference.tool_preselect.preselector import preselect

_TOOLS_8 = {f"tool_{i}" for i in range(8)}


class TestBypassPaths:
    @pytest.mark.asyncio
    async def test_not_opted_in_bypasses(self) -> None:
        subset, outcome = await preselect(
            effective_tools=_TOOLS_8,
            user_turn_content="test",
            workspace_id="ws",
            workspace_config={},
        )
        assert subset == _TOOLS_8
        assert outcome.reason == "bypass_disabled"

    @pytest.mark.asyncio
    async def test_disabled_flag_bypasses(self) -> None:
        subset, outcome = await preselect(
            effective_tools=_TOOLS_8,
            user_turn_content="test",
            workspace_id="ws",
            workspace_config={"tool_preselect": {"enabled": False}},
        )
        assert subset == _TOOLS_8
        assert outcome.reason == "bypass_disabled"

    @pytest.mark.asyncio
    async def test_low_tool_count_bypasses(self) -> None:
        subset, outcome = await preselect(
            effective_tools={"a", "b", "c"},
            user_turn_content="test",
            workspace_id="ws",
            workspace_config={"tool_preselect": {"enabled": True}},
        )
        assert subset == {"a", "b", "c"}
        assert outcome.reason == "bypass_low_tools"
