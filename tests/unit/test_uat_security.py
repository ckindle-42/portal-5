"""Unit tests for scripts/uat_security.py — the security lane's one-shot
speed/design UAT. Hermetic: a synthetic PortalConfig (no portal.yaml read)
and mocked httpx.AsyncClient (no network), per CLAUDE.md's tests/unit/ rule.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import uat_security as uat

from portal.platform.inference.config import (
    ModuleToggle,
    PortalConfig,
    WorkspaceAlias,
    WorkspaceSpec,
)


def _config() -> PortalConfig:
    return PortalConfig(
        mcp_fleet=[],
        modules={
            "security": ModuleToggle(enabled=True),
            "security_redteam": ModuleToggle(enabled=False),
            "general": ModuleToggle(enabled=True),
        },
        workspaces={
            "auto-security": WorkspaceSpec(
                name="Security",
                description="d",
                module="security",
                variants={
                    "blueteam": {"model_hint": "x"},
                    "purpleteam-deep": {
                        "model_hint": "p",
                        "chain": [
                            {
                                "model": "follow-up",
                                "label": "Follow-up",
                                "system": "Analyze.",
                                "user_template": "{hop_0}",
                            }
                        ],
                    },
                    "redteam": {"module": "security_redteam", "model_hint": "y"},
                },
            ),
            "security-reviewer": WorkspaceSpec(name="Review", description="d", module="security"),
            "auto-daily": WorkspaceSpec(
                name="Daily",
                description="d",
                module="general",
                variants={"quick": {"model_hint": "z"}},
            ),
        },
        aliases={
            "sec-alias": WorkspaceAlias(
                to="auto-security::blueteam", remove_after=date(2099, 1, 1), reason="test"
            ),
            "daily-alias": WorkspaceAlias(
                to="auto-daily::quick", remove_after=date(2099, 1, 1), reason="test"
            ),
        },
    )


def test_security_ids_finds_base_and_variants_with_enabled_state():
    ids = uat.security_ids(_config())
    assert ("auto-security", True) in ids
    assert ("auto-security::blueteam", True) in ids
    assert ("auto-security::redteam", False) in ids
    assert ("security-reviewer", True) in ids
    assert not any(wid == "auto-daily" for wid, _ in ids)


def test_security_ids_sorted_base_then_variants():
    ids = [wid for wid, _ in uat.security_ids(_config())]
    assert ids.index("auto-security") < ids.index("auto-security::blueteam")


def test_security_aliases_only_includes_security_targets():
    aliases = uat.security_aliases(_config())
    assert aliases == [("sec-alias", "auto-security::blueteam")]


def test_split_id_splits_variant():
    assert uat._split_id("auto-security::redteam") == ("auto-security", "redteam")
    assert uat._split_id("auto-security") == ("auto-security", None)


def test_chain_shot_gets_the_declared_chain_budget():
    assert uat._shot_timeout(_config(), "auto-security") == uat.TIMEOUT
    assert uat._shot_timeout(_config(), "auto-security::purpleteam-deep") == uat.CHAIN_TIMEOUT


def test_scrape_counter_sums_matching_labels():
    text = (
        'portal5_router_layer_total{layer="router_handoff_gate",workspace="auto-daily"} 3.0\n'
        'portal5_router_layer_total{layer="router_handoff_gate",workspace="auto-coding"} 9.0\n'
        'portal5_router_layer_total{layer="llm",workspace="auto-daily"} 1.0\n'
    )
    assert (
        uat._scrape_counter(
            text, "portal5_router_layer_total", layer="router_handoff_gate", workspace="auto-daily"
        )
        == 3.0
    )


def test_scrape_counter_no_match_is_zero():
    assert uat._scrape_counter("", "portal5_router_layer_total", layer="x", workspace="y") == 0.0


def test_shot_ok_for_enabled_requires_200_and_nonempty():
    assert uat.Shot(id="x", enabled=True, status=200, non_empty=True).ok
    assert not uat.Shot(id="x", enabled=True, status=200, non_empty=False).ok
    assert not uat.Shot(id="x", enabled=True, status=404, non_empty=True).ok


def test_shot_ok_for_disabled_requires_404_with_disabled_message():
    assert uat.Shot(
        id="x", enabled=False, status=404, error="Workspace 'x' is disabled (module not enabled)."
    ).ok
    assert not uat.Shot(id="x", enabled=False, status=200, error="").ok
    assert not uat.Shot(id="x", enabled=False, status=404, error="not found").ok
