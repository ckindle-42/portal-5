"""Unit tests for per-tool dispatch timeout budgets (portal5/timeout_s + max bound)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from portal.platform.inference import tool_registry
from portal.platform.inference.config import load_portal_config
from portal.platform.inference.tool_registry import ToolDefinition, ToolRegistry, _tool_timeout


def test_undeclared_tool_uses_default_60s() -> None:
    assert _tool_timeout({"name": "fast_tool"}) is None
    assert _tool_timeout({"name": "fast_tool", "_meta": {}}) is None
    assert tool_registry.TOOL_DISPATCH_TIMEOUT_S == 60.0


def test_declared_portal5_timeout_is_honored_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool_registry, "TOOL_DISPATCH_MAX_TIMEOUT_S", 900.0)
    assert _tool_timeout({"name": "t1", "_meta": {"portal5/timeout_s": 300}}) == 300.0
    assert _tool_timeout({"name": "t2", "_meta": {"portal5/timeout_s": 2400}}) == 900.0
    assert _tool_timeout({"name": "t3", "_meta": {"portal5/timeout_s": 0}}) is None
    assert _tool_timeout({"name": "t4", "_meta": {"portal5/timeout_s": -10}}) is None
    assert _tool_timeout({"name": "t5", "_meta": {"portal5/timeout_s": True}}) is None
    assert _tool_timeout({"name": "t6", "_meta": {"portal5/timeout_s": float("nan")}}) is None
    assert _tool_timeout({"name": "t7", "_meta": {"portal5/timeout_s": float("inf")}}) is None


def test_portal_config_declares_tool_dispatch_max_timeout() -> None:
    cfg = load_portal_config(_force_reload=True)
    assert cfg.tool_dispatch_max_timeout_s > 60.0


@pytest.mark.asyncio
async def test_dispatch_passes_effective_timeout_bounded_by_max(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[tuple[str, float]] = []

    async def fake_call_tool(
        _client: Any,
        _url: str,
        name: str,
        _args: dict[str, Any],
        timeout_s: float,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        recorded.append((name, timeout_s))
        return {"structuredContent": {"ok": True}, "isError": False}

    monkeypatch.setattr(tool_registry, "call_tool", fake_call_tool)
    monkeypatch.setattr(tool_registry, "TOOL_DISPATCH_MAX_TIMEOUT_S", 750.0)

    reg = ToolRegistry()
    reg._tools = {
        "undeclared": ToolDefinition("undeclared", "d", {}, "s", "http://x:1"),
        "long_ok": ToolDefinition("long_ok", "d", {}, "s", "http://x:1", custom_timeout_s=300.0),
        "too_long": ToolDefinition("too_long", "d", {}, "s", "http://x:1", custom_timeout_s=5000.0),
    }

    await reg.dispatch("undeclared", {})
    await reg.dispatch("long_ok", {})
    await reg.dispatch("too_long", {})

    assert recorded == [
        ("undeclared", 60.0),
        ("long_ok", 300.0),
        ("too_long", 750.0),
    ]


@pytest.mark.asyncio
async def test_refresh_reads_portal5_timeout_meta_and_bounds_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch(_client: Any, base_url: str) -> list[dict[str, Any]]:
        if base_url == "http://m:1":
            return [
                {"name": "plain", "description": "d", "inputSchema": {"type": "object"}},
                {
                    "name": "declared",
                    "description": "d",
                    "inputSchema": {"type": "object"},
                    "_meta": {"portal5/timeout_s": 420},
                },
                {
                    "name": "excessive",
                    "description": "d",
                    "inputSchema": {"type": "object"},
                    "_meta": {"portal5/timeout_s": 9999},
                },
            ]
        return []

    monkeypatch.setattr(tool_registry, "MCP_SERVERS", {"m": "http://m:1"})
    monkeypatch.setattr(tool_registry, "_fetch_tools", fake_fetch)
    monkeypatch.setattr(tool_registry, "TOOL_DISPATCH_MAX_TIMEOUT_S", 1200.0)

    reg = ToolRegistry()
    await reg.refresh(force=True)
    assert reg.get("plain") is not None and reg.get("plain").custom_timeout_s is None  # type: ignore[union-attr]
    assert reg.get("declared") is not None and reg.get("declared").custom_timeout_s == 420.0  # type: ignore[union-attr]
    assert reg.get("excessive") is not None and reg.get("excessive").custom_timeout_s == 1200.0  # type: ignore[union-attr]


def test_media_mcps_declare_timeout_meta_for_long_tools() -> None:
    import portal.modules.media.tools.mflux_mcp as mflux_mcp
    import portal.modules.media.tools.music_minimax_mcp as music_mcp
    import portal.modules.media.tools.tts_mcp as tts_mcp
    import portal.modules.media.tools.video_mlx_mcp as video_mcp
    import portal.modules.media.tools.whisper_mcp as whisper_mcp

    for mod, names in (
        (mflux_mcp, {"generate_image", "edit_image", "image_status"}),
        (video_mcp, {"video_status"}),
        (music_mcp, {"minimax_status", "music_status"}),
        (tts_mcp, {"speak", "clone_voice"}),
        (whisper_mcp, {"transcribe_audio", "transcribe_with_speakers"}),
    ):
        tools = {t.name: t for t in asyncio.run(mod.mcp.list_tools())}
        for name in names:
            assert name in tools, f"{mod.__name__} missing {name}"
            meta = tools[name].meta or {}
            assert meta.get("portal5/timeout_s", 0) > 60, (mod.__name__, name, meta)
