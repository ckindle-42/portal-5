"""Tests that OWUI seeding payloads match the M3 oracle snapshots.

Verifies:
- All persona preset payloads are byte-equal to the snapshot.
- All existing workspace preset IDs are present in imports/openwebui/workspaces/.
- No new preset IDs have appeared that aren't in either the snapshot or the
  21 previously-missing non-bench workspaces.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent
PERSONAS_SNAP = REPO / "tests" / "fixtures" / "owui_persona_presets_snapshot.json"
WS_SNAP = REPO / "tests" / "fixtures" / "owui_workspace_presets_snapshot.json"
WS_DIR = REPO / "imports" / "openwebui" / "workspaces"
PERSONAS_DIR = REPO / "config" / "personas"

# Workspace models for which OWUI enables web search
_WEB_SEARCH_MODELS = frozenset(
    {
        "auto",
        "auto-research",
        "auto-security",
        "auto-reasoning",
        "auto-redteam",
        "auto-blueteam",
        "auto-compliance",
    }
)


def _build_persona_payload(persona: dict) -> dict:
    """Replicate openwebui_init.py payload build logic.

    Resolves prompt_template: the same way load_persona_map() does
    (BUILD_PROGRAM_COLLAPSE_V1.md Phase 8 dedupes bench personas onto
    shared template files instead of an inline system_prompt).
    """
    slug = persona.get("slug", "")
    name = persona.get("name", slug)
    if persona.get("prompt_template"):
        from portal.platform.inference.config import _load_prompt_template

        system_prompt = _load_prompt_template(persona["prompt_template"])
    else:
        system_prompt = persona.get("system_prompt", "")
    workspace_model = persona.get("workspace_model") or "dolphin-llama3:8b"
    payload: dict = {
        "id": slug,
        "name": name,
        "base_model_id": workspace_model,
        "meta": {
            "description": f"Portal persona: {name}",
            "profile_image_url": "",
            "tags": [{"name": persona.get("category", "general")}],
        },
        "params": {
            "system": system_prompt,
            "model": workspace_model,
        },
    }
    if workspace_model in _WEB_SEARCH_MODELS:
        payload["params"]["enable_web_search"] = True
    return payload


def test_persona_presets_match_snapshot() -> None:
    """Every non-role persona preset payload must match the M3 oracle byte-for-byte."""
    snap = json.loads(PERSONAS_SNAP.read_text())

    diffs = []
    for f in sorted(PERSONAS_DIR.glob("*.yaml")):
        try:
            persona = yaml.safe_load(f.read_text()) or {}
        except Exception as e:
            diffs.append(f"{f.name}: parse error {e}")
            continue
        if persona.get("delivery") == "role":
            continue
        slug = persona.get("slug", f.stem)
        payload = _build_persona_payload(persona)
        if slug in snap:
            if snap[slug] != payload:
                diffs.append(f"{slug}: payload changed")
        else:
            diffs.append(f"{slug}: new slug not in snapshot")

    assert not diffs, "Persona preset payload changes:\n" + "\n".join(diffs[:10])


def test_workspace_presets_cover_snapshot_ids() -> None:
    """Every workspace id in the snapshot must still have a preset JSON file."""
    snap = json.loads(WS_SNAP.read_text())
    present = {
        json.loads(f.read_text()).get("id", "") for f in sorted(WS_DIR.glob("workspace_*.json"))
    }
    missing = set(snap.keys()) - present
    assert not missing, f"Snapshot workspace ids missing from preset files: {sorted(missing)}"


def test_no_orphan_preset_points_at_missing_slug() -> None:
    """No workspace_*.json preset may reference a persona slug that no longer exists."""
    persona_slugs = {
        yaml.safe_load(f.read_text()).get("slug", f.stem)
        for f in sorted(PERSONAS_DIR.glob("*.yaml"))
    }
    snap = json.loads(PERSONAS_SNAP.read_text())
    orphan_slugs = set(snap.keys()) - persona_slugs
    assert not orphan_slugs, f"Persona snapshot entries with no YAML: {sorted(orphan_slugs)}"


_BEHAVIOUR_KEYS = (
    "tools_allow",
    "tools_deny",
    "tool_choice",
    "variant",
    "workspace",
    "model_pin",
)


def _raw_personas() -> list[dict]:
    loaded = []
    for path in sorted(PERSONAS_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text()) or {}
        raw.setdefault("slug", path.stem)
        loaded.append(raw)
    return loaded


def _has_behaviour(raw: dict) -> bool:
    # preferred_models is dead config and does not count.
    return any(key in raw and raw[key] not in (None, [], "") for key in _BEHAVIOUR_KEYS)


def _seeder():
    import importlib.util
    import os

    os.environ.setdefault("OPENWEBUI_ADMIN_PASSWORD", "test-not-used")
    spec = importlib.util.spec_from_file_location(
        "openwebui_init_role_seed", REPO / "scripts" / "openwebui_init.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_roles_are_prompt_seeds_not_model_presets() -> None:
    """Role personas seed prompts even when they select a named workspace variant."""
    raws = _raw_personas()
    prompt_only = {raw["slug"] for raw in raws if not _has_behaviour(raw)}
    roles = {raw["slug"] for raw in raws if raw.get("delivery") == "role"}
    kept = {raw["slug"] for raw in raws if raw.get("delivery", "persona") == "persona"}
    assert prompt_only <= roles
    assert roles.isdisjoint(kept)
    assert roles | kept == {raw["slug"] for raw in raws}
    seeder = _seeder()
    seeded = [seeder.role_prompt_payload(raw) for raw in raws if seeder.persona_is_role(raw)]
    assert {item["command"] for item in seeded} == roles
    by_slug = {raw["slug"]: raw for raw in raws}
    for item in seeded:
        raw = by_slug[item["command"]]
        assert item["name"] == raw["name"]
        assert item["content"] == f"/{raw['slug']} "
    assert all(not seeder.persona_is_role(raw) for raw in raws if raw["slug"] in kept)


def test_persona_count_matches_snapshot() -> None:
    """Number of persona YAMLs must equal the snapshot size."""
    snap = json.loads(PERSONAS_SNAP.read_text())
    yaml_count = len(list(PERSONAS_DIR.glob("*.yaml")))
    assert yaml_count == len(snap), (
        f"Persona count mismatch: {yaml_count} YAMLs vs {len(snap)} in snapshot "
        "(snapshot must include every current persona)"
    )
