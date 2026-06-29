"""Tests for ToolRegistry refresh carry-forward and dispatch fixes."""

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from portal_pipeline.tool_registry import (
    MCP_SERVERS,
    ToolDefinition,
    ToolRegistry,
)


class TestRefreshCarryForward:
    """TR1: Preserve tools of failed servers during refresh."""

    @pytest.mark.asyncio
    async def test_failed_server_retains_previous_tools(self):
        """Server A succeeds, server B's /tools raises → B's previously-known
        tools survive with breaker state intact, WARNING names B."""
        tr = ToolRegistry()

        # Seed the registry with known tools from server B
        tr._tools["tool-b"] = ToolDefinition(
            name="tool-b",
            description="desc",
            parameters={},
            server_id="execution",
            server_url=MCP_SERVERS["execution"],
            last_seen=time.time() - 3600,
            healthy=False,
            next_retry_at=time.time() + 600,
            consecutive_failures=3,
        )
        tr._last_refresh = 0

        # Mock client — server A succeeds, server B raises
        mock_client = MagicMock()

        async def mock_get(url):
            if "8914" in url or "execution" in url:
                raise httpx.ReadTimeout("timed out")
            # Server A (documents) succeeds
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = [{"name": "tool-a", "description": "a"}]
            return resp

        mock_client.get = mock_get

        with patch.object(tr, "_client", return_value=mock_client):
            n = await tr.refresh(force=True)

        # tool-b should survive from the failed execution server
        assert "tool-b" in tr._tools
        assert tr._tools["tool-b"].consecutive_failures == 3
        assert tr._tools["tool-b"].healthy is False
        assert "tool-a" in tr._tools
        assert n >= 2

    @pytest.mark.asyncio
    async def test_recovering_server_replaces_carried_forward(self):
        """B recovering on next refresh replaces the carried-forward set."""
        tr = ToolRegistry()

        # Seed with a carried-forward tool from a previously-failed server
        tr._tools["tool-b"] = ToolDefinition(
            name="tool-b",
            description="old",
            parameters={},
            server_id="execution",
            server_url=MCP_SERVERS["execution"],
            last_seen=time.time() - 7200,
            healthy=False,
            consecutive_failures=5,
        )
        tr._last_refresh = 0

        mock_client = MagicMock()

        call_count = 0

        async def mock_get(url):
            nonlocal call_count
            resp = MagicMock()
            resp.status_code = 200
            if "execution" in url or "8914" in url:
                # First refresh: fail; second: succeed
                if call_count == 0:
                    call_count += 1
                    raise httpx.ReadTimeout("timed out")
                resp.json.return_value = [{"name": "tool-b-new", "description": "new"}]
            else:
                resp.json.return_value = []
            return resp

        mock_client.get = mock_get

        with patch.object(tr, "_client", return_value=mock_client):
            # First refresh — execution fails, tool-b carried forward
            await tr.refresh(force=True)
            assert "tool-b" in tr._tools
            assert tr._tools["tool-b"].consecutive_failures == 5

            # Second refresh — execution succeeds, old carried-forward replaced
            await tr.refresh(force=True)
            assert "tool-b" not in tr._tools
            assert "tool-b-new" in tr._tools
            # Fresh tool starts healthy
            assert tr._tools["tool-b-new"].healthy is True

    @pytest.mark.asyncio
    async def test_successful_server_drops_removed_tool(self):
        """A successfully-probed server that drops a tool loses it."""
        tr = ToolRegistry()

        tr._tools["old-tool"] = ToolDefinition(
            name="old-tool",
            description="desc",
            parameters={},
            server_id="documents",
            server_url=MCP_SERVERS["documents"],
        )
        tr._last_refresh = 0

        mock_client = MagicMock()

        async def mock_get(url):
            resp = MagicMock()
            resp.status_code = 200
            # Server returns a different tool, old-tool is gone
            resp.json.return_value = [{"name": "new-tool", "description": "new"}]
            return resp

        mock_client.get = mock_get

        with patch.object(tr, "_client", return_value=mock_client):
            await tr.refresh(force=True)

        assert "old-tool" not in tr._tools
        assert "new-tool" in tr._tools


class TestDispatchTimeoutHandling:
    """TR2: dispatch timeout exceptions produce clean error messages."""

    @pytest.mark.asyncio
    async def test_httpx_read_timeout_produces_clean_error(self):
        """httpx.ReadTimeout from dispatch produces 'timed out after Xs' error
        dict and increments breaker."""
        tr = ToolRegistry()
        tr._tools["slow-tool"] = ToolDefinition(
            name="slow-tool",
            description="desc",
            parameters={},
            server_id="video",
            server_url=MCP_SERVERS["video"],
            healthy=True,
        )

        mock_client = MagicMock()

        async def mock_post(*args, **kwargs):
            raise httpx.ReadTimeout("Read timed out")

        mock_client.post = mock_post
        mock_client.is_closed = False

        with patch.object(tr, "_client", return_value=mock_client):
            result = await tr.dispatch("slow-tool", {}, "req1")

        assert "error" in result
        assert "timed out after" in result["error"]
        assert tr._tools["slow-tool"].consecutive_failures == 1
        assert tr._tools["slow-tool"].healthy is False

    @pytest.mark.asyncio
    async def test_asyncio_timeout_error_produces_clean_error(self):
        """asyncio.TimeoutError also caught and produces clean error."""
        tr = ToolRegistry()
        tr._tools["slow-tool"] = ToolDefinition(
            name="slow-tool",
            description="desc",
            parameters={},
            server_id="video",
            server_url=MCP_SERVERS["video"],
            healthy=True,
        )

        mock_client = MagicMock()

        async def mock_post(*args, **kwargs):
            raise TimeoutError()

        mock_client.post = mock_post
        mock_client.is_closed = False

        with patch.object(tr, "_client", return_value=mock_client):
            result = await tr.dispatch("slow-tool", {}, "req1")

        assert "error" in result
        assert "timed out after" in result["error"]


class TestCustomTimeoutFromDiscovery:
    """TR3: timeout_s in /tools entry populates custom_timeout_s."""

    @pytest.mark.asyncio
    async def test_timeout_s_populates_custom_timeout(self):
        """timeout_s in a /tools response populates custom_timeout_s."""
        tr = ToolRegistry()
        tr._last_refresh = 0

        mock_client = MagicMock()

        async def mock_get(url):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = [
                {"name": "generate-video", "description": "v", "timeout_s": 120}
            ]
            return resp

        mock_client.get = mock_get

        with patch.object(tr, "_client", return_value=mock_client):
            await tr.refresh(force=True)

        tool = tr.get("generate-video")
        assert tool is not None
        assert tool.custom_timeout_s == 120.0

    @pytest.mark.asyncio
    async def test_custom_timeout_used_as_dispatch_timeout(self):
        """custom_timeout_s is used as the dispatch timeout."""
        tr = ToolRegistry()
        tr._tools["slow-tool"] = ToolDefinition(
            name="slow-tool",
            description="desc",
            parameters={},
            server_id="video",
            server_url=MCP_SERVERS["video"],
            healthy=True,
            custom_timeout_s=120.0,
        )

        mock_client = MagicMock()

        received_timeout = None

        async def mock_post(url, json, timeout):
            nonlocal received_timeout
            received_timeout = timeout
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"result": "ok"}
            return resp

        mock_client.post = mock_post
        mock_client.is_closed = False

        with patch.object(tr, "_client", return_value=mock_client):
            await tr.dispatch("slow-tool", {}, "req1")

        assert received_timeout == 120.0

    @pytest.mark.asyncio
    async def test_no_timeout_s_uses_default(self):
        """When no timeout_s in discovery, custom_timeout_s remains None."""
        tr = ToolRegistry()
        tr._last_refresh = 0

        mock_client = MagicMock()

        async def mock_get(url):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = [{"name": "default-tool", "description": "d"}]
            return resp

        mock_client.get = mock_get

        with patch.object(tr, "_client", return_value=mock_client):
            await tr.refresh(force=True)

        tool = tr.get("default-tool")
        assert tool is not None
        assert tool.custom_timeout_s is None
