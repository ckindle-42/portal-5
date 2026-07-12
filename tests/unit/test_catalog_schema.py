"""Tests for persona catalog schema validation.

Verifies that:
- A persona referencing a non-existent workspace_model raises at strict-load.
- All 150 production personas have valid workspace_model references.
- No persona has a browser_policy field (retired in M3).
- resolve_preset_tools invariant: matches the M3 oracle snapshot.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from portal.platform.inference.config import (
    PersonaSpec,
    load_persona_map,
    load_portal_config,
    resolve_preset_tools,
    validate_persona_parents,
)
from portal.platform.inference.router.workspaces import (
    _PERSONA_MAP,
    WORKSPACES,
    _resolve_persona_tools,
)

REPO = Path(__file__).resolve().parent.parent.parent
SNAPSHOT = REPO / "tests" / "fixtures" / "preset_resolution_snapshot.json"


@pytest.fixture(autouse=True)
def _restore_config_cache():
    """Restore the real config cache after any test that swaps the yaml."""
    yield
    load_portal_config(_force_reload=True)


# ── Schema validation ─────────────────────────────────────────────────────────


def test_persona_with_unknown_workspace_raises(tmp_path: Path) -> None:
    """validate_persona_parents raises when a persona's workspace_model is unknown."""
    p = tmp_path / "orphan.yaml"
    p.write_text(
        "name: Orphan\nslug: orphan\ncategory: test\nmodule: general\n"
        "workspace_model: does-not-exist\nsystem_prompt: test prompt\n"
    )
    personas = load_persona_map(personas_dir=tmp_path)
    with pytest.raises(ValueError, match="does-not-exist"):
        validate_persona_parents(personas)


def test_persona_missing_workspace_model_raises(tmp_path: Path) -> None:
    """PersonaSpec requires workspace_model — missing field raises pydantic ValidationError."""
    p = tmp_path / "bad.yaml"
    p.write_text("name: Bad\nslug: bad\ncategory: test\n")
    with pytest.raises(Exception, match="workspace_model"):
        PersonaSpec.model_validate(yaml.safe_load(p.read_text()))


def test_all_production_personas_have_valid_parents() -> None:
    """All 150 production personas reference an existing workspace."""
    personas = load_persona_map()
    assert len(personas) == 130, f"Expected 130 personas, got {len(personas)}"
    validate_persona_parents(personas)  # raises if any parent is invalid


def test_no_persona_has_browser_policy() -> None:
    """After M3, no persona YAML may contain a browser_policy field."""
    personas_dir = REPO / "config" / "personas"
    with_policy = [
        f.name for f in sorted(personas_dir.glob("*.yaml")) if "browser_policy" in f.read_text()
    ]
    assert not with_policy, f"browser_policy found in retired persona YAMLs: {with_policy}"


# ── Resolution invariant ──────────────────────────────────────────────────────


def test_persona_tool_resolution_matches_snapshot(monkeypatch) -> None:
    """resolve_preset_tools output must match the M3 oracle for all 150 personas.

    module: eval workspaces (bench-*) are gated off the module-level
    WORKSPACES dict by default (BUILD_PROGRAM_COLLAPSE_V1.md Phase 4), so
    bench personas' workspace_model lookups would otherwise resolve to no
    tools. Fill in the full (eval-enabled) set for the duration of this
    test — WORKSPACES aliases the same dict object every importer sees.
    """
    from portal.platform.inference.config import get_workspace_dict, load_portal_config

    monkeypatch.setenv("PORTAL_ENABLE_EVAL", "1")
    all_ws = get_workspace_dict(load_portal_config())
    for ws_id, ws_cfg in all_ws.items():
        monkeypatch.setitem(WORKSPACES, ws_id, ws_cfg)

    snap = json.loads(SNAPSHOT.read_text())
    failures = []
    for slug, spec in _PERSONA_MAP.items():
        ws_id = (
            spec.workspace_model
            if isinstance(spec, PersonaSpec)
            else spec.get("workspace_model", "")
        )
        effective = _resolve_persona_tools(spec, ws_id)
        key = f"persona::{slug}"
        if key in snap and snap[key]["effective_tools"] != effective:
            failures.append(f"{slug}: got {effective}, want {snap[key]['effective_tools']}")
    assert not failures, "Tool resolution drifted from snapshot:\n" + "\n".join(failures[:10])


def test_workspace_tools_match_snapshot() -> None:
    """WORKSPACES default tool lists must match the M3 oracle for all 90 workspaces."""
    snap = json.loads(SNAPSHOT.read_text())
    failures = []
    for ws_id, ws in WORKSPACES.items():
        tools = sorted(ws.get("tools", []))
        key = f"workspace::{ws_id}"
        if key in snap and snap[key]["effective_tools"] != tools:
            failures.append(f"{ws_id}: got {tools}, want {snap[key]['effective_tools']}")
    assert not failures, "Workspace tools drifted from snapshot:\n" + "\n".join(failures[:10])


def test_resolve_preset_tools_typed_path() -> None:
    """resolve_preset_tools with PersonaSpec gives same result as dict path."""
    persona_spec = PersonaSpec(
        name="Test",
        slug="test",
        category="general",
        module="general",
        workspace_model="auto",
        tools_allow=["memory", "rag"],
    )
    result = resolve_preset_tools(persona_spec, ["memory", "rag", "research"])
    assert result == ["memory", "rag"]


def test_resolve_preset_tools_deny() -> None:
    """tools_deny removes entries from the effective set."""
    persona_spec = PersonaSpec(
        name="Test",
        slug="test",
        category="general",
        module="general",
        workspace_model="auto",
        tools_deny=["research"],
    )
    result = resolve_preset_tools(persona_spec, ["memory", "rag", "research"])
    assert "research" not in result
    assert "memory" in result


def test_resolve_preset_tools_no_persona() -> None:
    """None persona returns workspace tools unchanged."""
    result = resolve_preset_tools(None, ["memory", "rag"])
    assert result == ["memory", "rag"]
