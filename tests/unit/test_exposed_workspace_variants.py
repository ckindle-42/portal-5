"""Workspace variants marked expose_to_owui: model list, presets, serving resolution.

TASK_EXPOSE_WORKSPACE_VARIANTS: commit 4574ba310 turned auto-compliance::reading,
auto-coding::bigfix and auto-coding::cad into variants with expose_to_owui: true,
but neither the Pipeline /v1/models list nor sync-config exported them.
"""

from __future__ import annotations

from portal.platform.inference.config import load_portal_config
from portal.platform.inference.router.preinject import _resolve_workspace_variant
from portal.platform.inference.router.workspaces import WORKSPACES


def test_synthetic_variant_id_resolves_to_variant_serving_fields() -> None:
    resolved = _resolve_workspace_variant("probe", "auto-compliance", "reading")
    assert resolved == "auto-compliance::reading"
    expected_hint = (
        load_portal_config().workspaces["auto-compliance"].variants["reading"]["model_hint"]
    )
    assert WORKSPACES[resolved]["model_hint"] == expected_hint
    assert WORKSPACES[resolved]["name"] == "⚖️ Portal Compliance Reading"


def test_old_alias_addresses_the_synthetic_id() -> None:
    from portal.platform.inference.model_addressing import is_addressable, workspace_model_hint

    assert load_portal_config().aliases["compliance-reading"].to == "auto-compliance::reading"
    expected_hint = (
        load_portal_config().workspaces["auto-compliance"].variants["reading"]["model_hint"]
    )
    assert is_addressable("auto-compliance::reading")
    assert is_addressable("compliance-reading")
    assert workspace_model_hint("auto-compliance::reading") == expected_hint
