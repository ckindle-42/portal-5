"""Unit tests for config.py — env-var + per-workspace resolution."""

from __future__ import annotations

import os
from unittest.mock import patch

from portal.platform.inference.tool_preselect.config import (
    default_k,
    global_preselect_enabled,
    is_preselect_enabled,
    preselect_model,
    resolve_workspace_config,
)


class TestGlobalFlag:
    def test_default_off(self):
        with patch.dict(os.environ, {}, clear=True):
            assert global_preselect_enabled() is False

    def test_explicit_on(self):
        with patch.dict(os.environ, {"PORTAL5_TOOL_PRESELECT": "1"}):
            assert global_preselect_enabled() is True

    def test_explicit_off(self):
        with patch.dict(os.environ, {"PORTAL5_TOOL_PRESELECT": "0"}):
            assert global_preselect_enabled() is False


class TestPreselectModel:
    def test_default_model(self):
        with patch.dict(os.environ, {}, clear=True):
            assert "MiniCPM5" in preselect_model()

    def test_env_override(self):
        with patch.dict(os.environ, {"PORTAL5_TOOL_PRESELECT_MODEL": "custom:tag"}):
            assert preselect_model() == "custom:tag"


class TestDefaultK:
    def test_bypass_at_low_count(self):
        assert default_k(5) == 0
        assert default_k(3) == 0

    def test_mid_range_default_5(self):
        assert default_k(6) == 5
        assert default_k(15) == 5

    def test_high_range_scales(self):
        assert default_k(16) == min(8, 7)  # ceil(16*0.4) = 7
        assert default_k(30) == 8  # ceil(30*0.4) = 12, capped at 8


class TestResolveWorkspaceConfig:
    def test_no_block_returns_none(self):
        assert resolve_workspace_config({}, 10) is None

    def test_not_enabled_returns_none(self):
        assert resolve_workspace_config({"tool_preselect": {"enabled": False}}, 10) is None

    def test_enabled_uses_default_k(self):
        result = resolve_workspace_config({"tool_preselect": {"enabled": True}}, 10)
        assert result is not None
        assert result.k == 5
        assert result.confidence_floor == 0.5

    def test_enabled_with_overrides(self):
        result = resolve_workspace_config(
            {"tool_preselect": {"enabled": True, "k": 3, "confidence_floor": 0.7}}, 10
        )
        assert result.k == 3
        assert result.confidence_floor == 0.7


class TestIsPreselectEnabled:
    def test_global_off_disables_regardless_of_workspace(self):
        with patch.dict(os.environ, {"PORTAL5_TOOL_PRESELECT": "0"}):
            cfg = {"tool_preselect": {"enabled": True}, "tools": list(range(10))}
            assert is_preselect_enabled("ws", cfg) is False

    def test_global_on_but_no_workspace_optin(self):
        with patch.dict(os.environ, {"PORTAL5_TOOL_PRESELECT": "1"}):
            assert is_preselect_enabled("ws", {}) is False

    def test_both_on_enables(self):
        with patch.dict(os.environ, {"PORTAL5_TOOL_PRESELECT": "1"}):
            cfg = {"tool_preselect": {"enabled": True}, "tools": list(range(10))}
            assert is_preselect_enabled("ws-both-on", cfg) is True

    def test_auto_disabled_workspace_returns_false(self):
        from portal.platform.inference.tool_preselect import state

        state.reset("ws-autodisabled")
        for _ in range(100):
            state.record_outcome("ws-autodisabled", was_miss=True)
        try:
            with patch.dict(os.environ, {"PORTAL5_TOOL_PRESELECT": "1"}):
                cfg = {"tool_preselect": {"enabled": True}, "tools": list(range(10))}
                assert is_preselect_enabled("ws-autodisabled", cfg) is False
        finally:
            state.reset("ws-autodisabled")
