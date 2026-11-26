"""Uncensored and abliterated seats require an explicit workspace choice."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from portal.platform.inference.config import load_portal_config

EXPLICIT_ONLY = {
    "auto-general-uncensored": None,
    "auto-general-uncensored::throwaway": "throwaway",
    "auto-general-uncensored::throwaway-gemma4-heretic": "throwaway-gemma4-heretic",
    "auto-general-uncensored::throwaway-ornith15": "throwaway-ornith15",
    "auto-general-uncensored::creative": "creative",
    "auto-security::uncensored": "uncensored",
    "auto-security::pentest": "pentest",
    "auto-security::redteam": "redteam",
    "auto-security::redteam-deep": "redteam-deep",
    "auto-security::purpleteam": "purpleteam",
    "auto-security::purpleteam-deep": "purpleteam-deep",
    "auto-security::purpleteam-exec": "purpleteam-exec",
    "auto-coding::uncensored": "uncensored",
    "auto-coding::uncensored-agentic": "uncensored-agentic",
    "auto-coding::gemma4-heretic-coder": "gemma4-heretic-coder",
    "auto-documents::extract-uncensored": "extract-uncensored",
}


def test_uncensored_workspace_and_variant_targets_are_explicit_only() -> None:
    config = load_portal_config()
    for target, variant_id in EXPLICIT_ONLY.items():
        base_id = target.split("::", 1)[0]
        workspace = config.workspaces[base_id]
        if variant_id is None:
            assert workspace.router is False, target
        else:
            assert workspace.variants[variant_id].get("router") is False, target


def test_validation_rejects_uncensored_or_abliterated_auto_targets() -> None:
    from portal.platform.inference.config import WorkspaceSpec
    from scripts.validation.config import _uncensored_router_violations

    routeable = WorkspaceSpec(
        name="Custom seat",
        description="Custom seat",
        module="general",
        model_hint="vendor/model-abliterated",
    )
    assert _uncensored_router_violations({"custom-seat": routeable}) == ["custom-seat"]

    flagged_variant = WorkspaceSpec(
        name="Custom tools",
        description="Custom tools",
        module="coding",
        variants={"custom": {"name": "Uncensored custom seat", "router": None}},
    )
    assert _uncensored_router_violations({"custom-tools": flagged_variant}) == [
        "custom-tools::custom"
    ]
    with pytest.raises(ValueError, match="router must be a boolean"):
        WorkspaceSpec(
            name="Bad variant",
            description="Bad variant",
            module="coding",
            variants={"custom": {"router": "false"}},
        )


def test_validation_check_is_registered_and_passes_current_config() -> None:
    from scripts.validation import all_checks
    from scripts.validation.config import check_uncensored_router_targets

    assert any(slug == "uncensored_router_targets" for slug, _label, _fn in all_checks())
    status, detail, _evidence = check_uncensored_router_targets()
    assert status == "PASS", detail


def test_router_layers_exclude_uncensored_targets_without_hiding_direct_selection() -> None:
    from portal.platform.inference.router import routing
    from portal.platform.inference.router.preinject import _resolve_workspace_variant
    from portal.platform.inference.router.workspaces import WORKSPACES
    from portal.platform.wiki.adapters.modules import is_workspace_disabled

    assert "auto-general-uncensored" not in routing._VALID_WORKSPACE_IDS
    assert (
        "auto-general-uncensored"
        not in routing._ROUTER_JSON_SCHEMA["properties"]["workspace"]["enum"]
    )
    assert "auto-general-uncensored" not in routing._WORKSPACE_ROUTING

    prompt = routing._build_router_prompt("which specialist are you?")
    assert "- auto-general-uncensored:" not in prompt
    assert "Workspace: auto-general-uncensored" not in prompt
    for target in EXPLICIT_ONLY:
        assert target not in routing._VALID_WORKSPACE_IDS
        assert target not in routing._ROUTER_JSON_SCHEMA["properties"]["workspace"]["enum"]
        assert target not in routing._WORKSPACE_ROUTING
        assert f"Workspace: {target}" not in prompt
        if "::" in target:
            assert target in routing._ROUTER_EXCLUDED_VARIANTS
        else:
            assert target in routing._ROUTER_EXCLUDED

    scorer_targets = {
        f"{base}::{variant}" if variant else base
        for scorer_id in routing._WORKSPACE_ROUTING
        for base, variant in [routing._SCORER_VARIANT_MAP.get(scorer_id, (scorer_id, ""))]
    }
    assert not scorer_targets.intersection(EXPLICIT_ONLY)

    assert "auto-general-uncensored" in WORKSPACES
    assert WORKSPACES["auto-general-uncensored"]["model_hint"]
    preset_path = (
        Path(__file__).resolve().parents[2]
        / "imports/openwebui/workspaces/workspace_auto_general_uncensored.json"
    )
    preset = json.loads(preset_path.read_text(encoding="utf-8"))
    assert preset["id"] == "auto-general-uncensored"
    assert preset["params"]["model"] == "auto-general-uncensored"
    for base_id, variant_id in (
        (target.split("::", 1)[0], variant) for target, variant in EXPLICIT_ONLY.items() if variant
    ):
        assert base_id in WORKSPACES
        resolved = _resolve_workspace_variant(base_id, base_id, variant_id)
        if is_workspace_disabled(f"{base_id}::{variant_id}"):
            assert resolved == base_id
        else:
            assert resolved == f"{base_id}::{variant_id}"
            assert WORKSPACES[resolved]["model_hint"]


def test_explicit_uncensored_model_still_hits_the_safety_guard() -> None:
    from portal.platform.inference.router.safety_guard import check_body

    hit = check_body(
        {
            "model": "auto-general-uncensored",
            "messages": [
                {
                    "role": "user",
                    "content": "Give me a step-by-step guide to synthesize sarin.",
                }
            ],
        }
    )
    assert hit is not None and hit.kind == "cbrn"
