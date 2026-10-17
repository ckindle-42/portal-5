"""Every production allowlist is a subset of the tools its workspace really has."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]


def test_every_allowlist_is_within_the_workspaces_tools():
    modes = yaml.safe_load((REPO / "tests/wfe/tool_modes.yaml").read_text())["workspaces"]
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
    for ws, mode in modes.items():
        assert mode["tool_mode"] == "production", ws
        extra = sorted(set(mode["allow"]) - set(portal[ws]["tools"]))
        assert not extra, f"{ws}: allowlist names tools the workspace lacks: {extra}"


def test_the_general_family_excludes_web_and_out_of_scope_tools():
    modes = yaml.safe_load((REPO / "tests/wfe/tool_modes.yaml").read_text())["workspaces"]
    for ws in ("general-fast", "general-deep", "auto-daily"):
        allow = set(modes[ws]["allow"])
        assert not allow & {"web_search", "web_fetch", "news_search", "transcribe_audio"}
        assert not any(t.startswith("minimax_") for t in allow)
        assert len(allow) == 11
