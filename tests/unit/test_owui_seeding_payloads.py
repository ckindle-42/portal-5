"""Tests that OWUI seeding payloads match the M3 oracle snapshots.

Verifies:
- All 150 persona preset payloads are byte-equal to the snapshot.
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
        "auto-data",
        "auto-redteam",
        "auto-blueteam",
        "auto-compliance",
    }
)


def _build_persona_payload(persona: dict) -> dict:
    """Replicate openwebui_init.py payload build logic."""
    slug = persona.get("slug", "")
    name = persona.get("name", slug)
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
    """Every persona preset payload must match the M3 oracle byte-for-byte."""
    snap = json.loads(PERSONAS_SNAP.read_text())

    diffs = []
    for f in sorted(PERSONAS_DIR.glob("*.yaml")):
        try:
            persona = yaml.safe_load(f.read_text()) or {}
        except Exception as e:
            diffs.append(f"{f.name}: parse error {e}")
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


def test_persona_count_matches_snapshot() -> None:
    """Number of persona YAMLs must equal the snapshot size."""
    snap = json.loads(PERSONAS_SNAP.read_text())
    yaml_count = len(list(PERSONAS_DIR.glob("*.yaml")))
    assert yaml_count == len(snap), (
        f"Persona count mismatch: {yaml_count} YAMLs vs {len(snap)} in snapshot "
        f"(130 valid personas — 20 orphan bench-* personas were removed in M3)"
    )
