"""Unit tests for preselect() — all Ollama calls mocked, no live backend
required. Covers every fallback branch in the §1.9 failure-mode table.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from portal.platform.inference.tool_preselect.preselector import preselect

_TOOLS_8 = {f"tool_{i}" for i in range(8)}


def _mock_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"response": text}
    resp.raise_for_status = MagicMock()
    return resp


class TestBypassPaths:
    @pytest.mark.asyncio
    async def test_not_opted_in_bypasses(self):
        subset, outcome = await preselect(
            effective_tools=_TOOLS_8,
            user_turn_content="test",
            workspace_id="ws",
            workspace_config={},
        )
        assert subset == _TOOLS_8
        assert outcome.reason == "bypass_disabled"

    @pytest.mark.asyncio
    async def test_disabled_flag_bypasses(self):
        subset, outcome = await preselect(
            effective_tools=_TOOLS_8,
            user_turn_content="test",
            workspace_id="ws",
            workspace_config={"tool_preselect": {"enabled": False}},
        )
        assert subset == _TOOLS_8
        assert outcome.reason == "bypass_disabled"

    @pytest.mark.asyncio
    async def test_low_tool_count_bypasses(self):
        subset, outcome = await preselect(
            effective_tools={"a", "b", "c"},
            user_turn_content="test",
            workspace_id="ws",
            workspace_config={"tool_preselect": {"enabled": True}},
        )
        assert subset == {"a", "b", "c"}
        assert outcome.reason == "bypass_low_tools"


class TestOllamaOutcomes:
    @pytest.mark.asyncio
    async def test_ok_path_returns_topk_subset(self):
        with patch(
            "portal.platform.inference.tool_preselect.preselector._client",
            new_callable=MagicMock,
        ) as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=_mock_response("1\n2\n3\n4\n5"))
            mock_client_fn.return_value = mock_client

            with patch("portal.platform.inference.tool_registry.tool_registry") as mock_reg:
                mock_reg.get.return_value = None
                subset, outcome = await preselect(
                    effective_tools=_TOOLS_8,
                    user_turn_content="test query",
                    workspace_id="ws",
                    workspace_config={"tool_preselect": {"enabled": True, "k": 3}},
                )
            assert outcome.reason == "ok"
            assert len(subset) == 3
            assert subset.issubset(_TOOLS_8)

    @pytest.mark.asyncio
    async def test_timeout_falls_back(self):
        with patch(
            "portal.platform.inference.tool_preselect.preselector._client",
            new_callable=MagicMock,
        ) as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_client_fn.return_value = mock_client

            with patch("portal.platform.inference.tool_registry.tool_registry") as mock_reg:
                mock_reg.get.return_value = None
                subset, outcome = await preselect(
                    effective_tools=_TOOLS_8,
                    user_turn_content="test",
                    workspace_id="ws",
                    workspace_config={"tool_preselect": {"enabled": True, "k": 3}},
                )
            assert subset == _TOOLS_8
            assert outcome.reason == "fallback_timeout"

    @pytest.mark.asyncio
    async def test_connection_error_falls_back(self):
        with patch(
            "portal.platform.inference.tool_preselect.preselector._client",
            new_callable=MagicMock,
        ) as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
            mock_client_fn.return_value = mock_client

            with patch("portal.platform.inference.tool_registry.tool_registry") as mock_reg:
                mock_reg.get.return_value = None
                subset, outcome = await preselect(
                    effective_tools=_TOOLS_8,
                    user_turn_content="test",
                    workspace_id="ws",
                    workspace_config={"tool_preselect": {"enabled": True, "k": 3}},
                )
            assert subset == _TOOLS_8
            assert outcome.reason == "fallback_timeout"

    @pytest.mark.asyncio
    async def test_unparseable_output_falls_back(self):
        with patch(
            "portal.platform.inference.tool_preselect.preselector._client",
            new_callable=MagicMock,
        ) as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=_mock_response("I cannot help with that."))
            mock_client_fn.return_value = mock_client

            with patch("portal.platform.inference.tool_registry.tool_registry") as mock_reg:
                mock_reg.get.return_value = None
                subset, outcome = await preselect(
                    effective_tools=_TOOLS_8,
                    user_turn_content="test",
                    workspace_id="ws",
                    workspace_config={"tool_preselect": {"enabled": True, "k": 3}},
                )
            assert subset == _TOOLS_8
            assert outcome.reason == "fallback_parse"

    @pytest.mark.asyncio
    async def test_low_confidence_falls_back(self):
        with patch(
            "portal.platform.inference.tool_preselect.preselector._client",
            new_callable=MagicMock,
        ) as mock_client_fn:
            mock_client = AsyncMock()
            # k=5 -> need >= 2 parsed (k//2); only 1 parsed => fallback_lowconf
            mock_client.post = AsyncMock(return_value=_mock_response("1"))
            mock_client_fn.return_value = mock_client

            with patch("portal.platform.inference.tool_registry.tool_registry") as mock_reg:
                mock_reg.get.return_value = None
                subset, outcome = await preselect(
                    effective_tools=_TOOLS_8,
                    user_turn_content="test",
                    workspace_id="ws",
                    workspace_config={"tool_preselect": {"enabled": True, "k": 5}},
                )
            assert subset == _TOOLS_8
            assert outcome.reason == "fallback_lowconf"

    @pytest.mark.asyncio
    async def test_unexpected_exception_never_raises(self):
        with patch(
            "portal.platform.inference.tool_preselect.preselector._client",
            new_callable=MagicMock,
        ) as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=ValueError("boom"))
            mock_client_fn.return_value = mock_client

            with patch("portal.platform.inference.tool_registry.tool_registry") as mock_reg:
                mock_reg.get.return_value = None
                subset, outcome = await preselect(
                    effective_tools=_TOOLS_8,
                    user_turn_content="test",
                    workspace_id="ws",
                    workspace_config={"tool_preselect": {"enabled": True, "k": 3}},
                )
            assert subset == _TOOLS_8
            assert outcome.reason == "fallback_parse"
