"""Tests for duplicate-tool precedence across MCP servers.

When multiple servers advertise the same tool name, the one with the higher
fleet order in ``config/portal.yaml`` wins. This is deterministic and independent
of the ``asyncio.gather`` scheduling order.
"""

from __future__ import annotations

import logging
import unittest.mock

import pytest

from portal.platform.inference import tool_registry as registry_module
from portal.platform.inference.tool_registry import MCP_SERVERS, ToolRegistry

# The two colliding servers. In the real fleet, mlx_transcribe comes after
# whisper, so it wins by fleet-order precedence.
_COLLIDING_S1 = "whisper"
_COLLIDING_S2 = "mlx_transcribe"
_COLLIDING_TOOLS = ("transcribe_audio", "transcribe_with_speakers")


class TestDuplicateToolPrecedence:
    """Fleet order makes the winner deterministic, not scheduling."""

    @pytest.mark.asyncio
    async def test_winner_is_later_fleet_entry_regardless_of_discovery_order(self):
        """Mirrors the real fleet: whisper (:8915) then mlx_transcribe (:8924).
        The registry must always select the later entry, even if the gather
        calls return in the opposite order."""
        for ordering_name, _order in [
            ("whisper-first", [_COLLIDING_S1, _COLLIDING_S2]),
            ("mlx-first", [_COLLIDING_S2, _COLLIDING_S1]),
        ]:

            async def fake_list_tools(_client, base_url, _timeout_s):
                # Only return tools for the two colliding servers; all other
                # servers return empty so they don't interfere with the win.
                if base_url == MCP_SERVERS[_COLLIDING_S1] or base_url == MCP_SERVERS[_COLLIDING_S2]:
                    winner = _COLLIDING_S2
                    return [
                        {
                            "name": tool,
                            "description": f"{winner}:{tool}",
                            "inputSchema": {"type": "object"},
                        }
                        for tool in _COLLIDING_TOOLS
                    ]
                return []

            tr = ToolRegistry()
            tr._last_refresh = 0

            with unittest.mock.patch.object(registry_module, "list_tools", fake_list_tools):
                await tr.refresh(force=True)

            for tool in _COLLIDING_TOOLS:
                reg = tr.get(tool)
                assert reg is not None, f"{ordering_name}: {tool} missing"
                assert reg.server_id == _COLLIDING_S2, (
                    f"{ordering_name}: expected {_COLLIDING_S2} to win over "
                    f"{_COLLIDING_S1} for {tool}, got {reg.server_id}"
                )

    @pytest.mark.asyncio
    async def test_warning_logged_on_duplicate(self, caplog):
        """A WARNING is emitted when two servers advertise the same tool."""
        tr = ToolRegistry()
        tr._last_refresh = 0

        async def fake_list_tools(_client, base_url, _timeout_s):
            if base_url == MCP_SERVERS[_COLLIDING_S1]:
                return [{"name": "dup-tool", "description": "s1", "inputSchema": {}}]
            if base_url == MCP_SERVERS[_COLLIDING_S2]:
                return [{"name": "dup-tool", "description": "s2", "inputSchema": {}}]
            return []

        with (
            unittest.mock.patch.object(registry_module, "list_tools", fake_list_tools),
            caplog.at_level(logging.WARNING, logger=registry_module.__name__),
        ):
            await tr.refresh(force=True)

        assert any("Duplicate tool" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_no_warning_when_no_duplicate(self):
        """No warning when each tool lives on a single server."""
        tr = ToolRegistry()
        tr._last_refresh = 0

        async def fake_list_tools(_client, base_url, _timeout_s):
            if base_url == MCP_SERVERS[_COLLIDING_S1]:
                return [{"name": "only-s1", "description": "s1", "inputSchema": {}}]
            if base_url == MCP_SERVERS[_COLLIDING_S2]:
                return [{"name": "only-s2", "description": "s2", "inputSchema": {}}]
            return []

        with unittest.mock.patch.object(registry_module, "list_tools", fake_list_tools):
            await tr.refresh(force=True)

        assert "only-s1" in tr._tools
        assert "only-s2" in tr._tools
