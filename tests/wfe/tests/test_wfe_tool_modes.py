"""Every production allowlist is a subset of the tools its workspace really has."""

from __future__ import annotations

from pathlib import Path

import yaml

from portal.platform.inference.config import effective_workspace

REPO = Path(__file__).resolve().parents[3]


def test_every_allowlist_is_within_the_workspaces_tools():
    modes = yaml.safe_load((REPO / "tests/wfe/tool_modes.yaml").read_text())["workspaces"]
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
    for ws, mode in modes.items():
        assert mode["tool_mode"] == "production", ws
        workspace = effective_workspace(portal, ws)
        extra = sorted(set(mode["allow"]) - set(workspace["tools"]))
        assert not extra, f"{ws}: allowlist names tools the workspace lacks: {extra}"


def test_only_the_realuse_fast_lane_offers_live_web_search():
    modes = yaml.safe_load((REPO / "tests/wfe/tool_modes.yaml").read_text())["workspaces"]
    for ws in ("auto-daily::fast", "auto-daily::deep", "auto-daily"):
        allow = set(modes[ws]["allow"])
        if ws == "auto-daily::fast":
            assert "web_search" in allow
        else:
            assert "web_search" not in allow
        assert not allow & {"web_fetch", "news_search", "transcribe_audio"}
        assert not any(t.startswith("minimax_") for t in allow)
        assert len(allow) == (12 if ws == "auto-daily::fast" else 11)
