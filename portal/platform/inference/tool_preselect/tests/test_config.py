"""Unit tests for config.py — env-var + per-workspace resolution."""

from __future__ import annotations

from portal.platform.inference.tool_preselect.config import (
    default_k,
    resolve_workspace_config,
)


class TestDefaultK:
    def test_bypass_at_low_count(self) -> None:
        assert default_k(5) == 0
        assert default_k(3) == 0

    def test_mid_range_default_5(self) -> None:
        assert default_k(6) == 5
        assert default_k(15) == 5

    def test_high_range_scales(self) -> None:
        assert default_k(16) == min(8, 7)  # ceil(16*0.4) = 7
        assert default_k(30) == 8  # ceil(30*0.4) = 12, capped at 8


class TestResolveWorkspaceConfig:
    def test_no_block_returns_none(self) -> None:
        assert resolve_workspace_config({}, 10) is None

    def test_not_enabled_returns_none(self) -> None:
        assert resolve_workspace_config({"tool_preselect": {"enabled": False}}, 10) is None

    def test_enabled_uses_default_k(self) -> None:
        result = resolve_workspace_config({"tool_preselect": {"enabled": True}}, 10)
        assert result is not None
        assert result.k == 5
        assert result.confidence_floor == 0.5

    def test_enabled_with_overrides(self) -> None:
        result = resolve_workspace_config(
            {"tool_preselect": {"enabled": True, "k": 3, "confidence_floor": 0.7}}, 10
        )
        assert result is not None
        assert result.k == 3
        assert result.confidence_floor == 0.7
