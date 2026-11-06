"""Tests for ToolRegistry refresh carry-forward and dispatch fixes."""

import time
from unittest.mock import patch

import httpx
import pytest

from portal.platform.inference import tool_registry as registry_module
from portal.platform.inference.tool_registry import (
    MCP_SERVERS,
    ToolDefinition,
    ToolRegistry,
)


class TestNativeDiscovery:
    """Discovery reads native ``tools/list`` entries (name/description/inputSchema)."""

    @pytest.mark.asyncio
    async def test_native_tools_are_discovered_with_meta_timeout(self):
        tr = ToolRegistry()
        tr._last_refresh = 0

        async def fake_list_tools(client, base_url, timeout_s):
            return [
                {
                    "name": "nerc_cip_requirement",
                    "description": "desc",
                    "inputSchema": {"type": "object", "properties": {}},
                    "_meta": {"portal5/timeout_s": 90},
                }
            ]

        with patch.object(registry_module, "list_tools", fake_list_tools):
            await tr.refresh(force=True)

        tool = tr.get("nerc_cip_requirement")
        assert tool is not None
        assert tool.custom_timeout_s == 90.0
        assert tr.get_openai_tools(["nerc_cip_requirement"])

    @pytest.mark.asyncio
    async def test_tool_without_meta_has_no_custom_timeout(self):
        tr = ToolRegistry()
        tr._last_refresh = 0

        async def fake_list_tools(client, base_url, timeout_s):
            return [{"name": "default-tool", "description": "d", "inputSchema": {}}]

        with patch.object(registry_module, "list_tools", fake_list_tools):
            await tr.refresh(force=True)

        tool = tr.get("default-tool")
        assert tool is not None
        assert tool.custom_timeout_s is None


class TestRefreshCarryForward:
    """TR1: Preserve tools of failed servers during refresh."""

    @pytest.mark.asyncio
    async def test_failed_server_retains_previous_tools(self):
        """Server A succeeds, server B's tools/list raises → B's previously-known
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

        async def fake_list_tools(client, base_url, timeout_s):
            if base_url == MCP_SERVERS["execution"]:
                raise httpx.ReadTimeout("timed out")
            return [{"name": "tool-a", "description": "a", "inputSchema": {}}]

        with patch.object(registry_module, "list_tools", fake_list_tools):
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

        calls = 0

        async def fake_list_tools(client, base_url, timeout_s):
            nonlocal calls
            if base_url == MCP_SERVERS["execution"]:
                calls += 1
                # First refresh: fail; second: succeed
                if calls == 1:
                    raise httpx.ReadTimeout("timed out")
                return [{"name": "tool-b-new", "description": "new", "inputSchema": {}}]
            return []

        with patch.object(registry_module, "list_tools", fake_list_tools):
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

        async def fake_list_tools(client, base_url, timeout_s):
            return [{"name": "new-tool", "description": "new", "inputSchema": {}}]

        with patch.object(registry_module, "list_tools", fake_list_tools):
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
            server_url=MCP_SERVERS["music-minimax"],
            healthy=True,
        )

        async def fake_call_tool(*args, **kwargs):
            raise httpx.ReadTimeout("Read timed out")

        with patch.object(registry_module, "call_tool", fake_call_tool):
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
            server_url=MCP_SERVERS["music-minimax"],
            healthy=True,
        )

        async def fake_call_tool(*args, **kwargs):
            raise TimeoutError()

        with patch.object(registry_module, "call_tool", fake_call_tool):
            result = await tr.dispatch("slow-tool", {}, "req1")

        assert "error" in result
        assert "timed out after" in result["error"]


class TestCustomTimeoutFromDiscovery:
    """TR3: timeout metadata on the native tool populates custom_timeout_s."""

    @pytest.mark.asyncio
    async def test_timeout_meta_populates_custom_timeout(self):
        tr = ToolRegistry()
        tr._last_refresh = 0

        async def fake_list_tools(client, base_url, timeout_s):
            return [
                {
                    "name": "generate-video",
                    "description": "v",
                    "inputSchema": {},
                    "_meta": {"portal5/timeout_s": 120},
                }
            ]

        with patch.object(registry_module, "list_tools", fake_list_tools):
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
            server_url=MCP_SERVERS["music-minimax"],
            healthy=True,
            custom_timeout_s=120.0,
        )

        received_timeout = None

        async def fake_call_tool(client, base_url, name, arguments, timeout_s, metadata=None):
            nonlocal received_timeout
            received_timeout = timeout_s
            return {"content": [{"type": "text", "text": '{"result": "ok"}'}]}

        with patch.object(registry_module, "call_tool", fake_call_tool):
            await tr.dispatch("slow-tool", {}, "req1")

        assert received_timeout == 120.0


class TestDispatchMissRefresh:
    """A dispatch miss forces one rate-limited refresh before the not-in-registry error."""

    @pytest.mark.asyncio
    async def test_cold_registry_first_dispatch_succeeds_after_one_refresh(self, monkeypatch):
        reg = ToolRegistry()
        refreshes = 0
        real_refresh = reg.refresh

        async def counting_refresh(force: bool = False) -> int:
            nonlocal refreshes
            refreshes += 1
            return await real_refresh(force=force)

        async def fake_list_tools(client, base_url, timeout_s):
            return [
                {
                    "name": "recall",
                    "description": "r",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                    },
                }
            ]

        async def fake_call_tool(client, base_url, name, arguments, timeout_s, metadata=None):
            return {"content": [{"type": "text", "text": '{"result": "hit"}'}]}

        monkeypatch.setattr(registry_module, "list_tools", fake_list_tools)
        monkeypatch.setattr(registry_module, "call_tool", fake_call_tool)
        monkeypatch.setattr(reg, "refresh", counting_refresh)

        result = await reg.dispatch("recall", {"query": "q"}, "req1")

        assert "error" not in result
        assert reg.get("recall") is not None
        assert refreshes == 1

    @pytest.mark.asyncio
    async def test_unknown_tool_errors_and_refreshes_at_most_once_per_ttl(self, monkeypatch):
        reg = ToolRegistry()
        refreshes = 0
        real_refresh = reg.refresh

        async def counting_refresh(force: bool = False) -> int:
            nonlocal refreshes
            refreshes += 1
            return await real_refresh(force=force)

        async def fake_list_tools(client, base_url, timeout_s):
            return []

        monkeypatch.setattr(registry_module, "list_tools", fake_list_tools)
        monkeypatch.setattr(registry_module, "TOOL_REGISTRY_REFRESH_S", 3600.0)
        monkeypatch.setattr(registry_module, "TOOL_REGISTRY_RETRY_S", 30.0)
        monkeypatch.setattr(reg, "refresh", counting_refresh)

        first = await reg.dispatch("nonexistent", {}, "req1")
        second = await reg.dispatch("nonexistent", {}, "req2")

        assert "not in registry" in first["error"]
        assert "not in registry" in second["error"]
        assert refreshes == 1
        assert reg._last_miss_refresh > 0

    @pytest.mark.asyncio
    async def test_transient_list_failure_keeps_server_tools(self, monkeypatch):
        reg = ToolRegistry()
        reg._tools["remember"] = ToolDefinition(
            name="remember",
            description="m",
            parameters={},
            server_id="memory",
            server_url=MCP_SERVERS["memory"],
            healthy=False,
            next_retry_at=time.time() + 600,
            consecutive_failures=2,
        )

        async def fake_list_tools(client, base_url, timeout_s):
            if base_url == MCP_SERVERS["memory"]:
                raise httpx.ReadTimeout("timed out")
            return []

        monkeypatch.setattr(registry_module, "list_tools", fake_list_tools)

        result = await reg.dispatch("recall", {"query": "q"}, "req1")

        assert "not in registry" in result["error"]
        carried = reg.get("remember")
        assert carried is not None
        assert carried.healthy is False
        assert carried.consecutive_failures == 2
