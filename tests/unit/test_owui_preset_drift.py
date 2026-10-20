"""The Open WebUI preset drift check: a prompt, name or tool binding changed in the seeded
files but not live (seed skips existing presets) must be reported, preset by preset."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "check_owui_preset_drift",
    Path(__file__).resolve().parents[2] / "scripts" / "check_owui_preset_drift.py",
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

FILE = {
    "id": "auto-documents",
    "name": "Docs",
    "params": {
        "model": "auto-documents",
        "system": "create and read",
        "function_calling": "native",
    },
    "meta": {"toolIds": ["server:mcp:portal_documents"]},
}


def test_identical_presets_have_no_drift():
    assert mod.drift(FILE, json.loads(json.dumps(FILE))) == []


def test_a_stale_system_prompt_is_reported():
    live = json.loads(json.dumps(FILE))
    live["params"]["system"] = "create only"
    (d,) = mod.drift(FILE, live)
    assert d.startswith("params.system") and "create only" in d


def test_a_changed_name_tool_binding_or_missing_preset_is_reported():
    live = json.loads(json.dumps(FILE))
    live["name"], live["meta"]["toolIds"] = "Old", []
    assert len(mod.drift(FILE, live)) == 2
    assert mod.drift(FILE, None) == ["missing from Open WebUI"]


def test_check_reads_each_workspace_file_but_not_the_bundle(tmp_path):
    (tmp_path / "workspace_a.json").write_text(json.dumps(FILE))
    (tmp_path / "workspaces_all.json").write_text(json.dumps([FILE]))
    stale = json.loads(json.dumps(FILE))
    stale["params"]["system"] = "old"
    assert mod.check(lambda _id: stale, tmp_path).keys() == {"auto-documents"}
    assert mod.check(lambda _id: FILE, tmp_path) == {}


def test_persona_expectation_follows_the_seeder_rules():
    import yaml

    personas = {p["id"]: p for p in mod.expected_personas()}
    persona_dir = Path(__file__).resolve().parents[2] / "config" / "personas"
    raws = [yaml.safe_load(f.read_text()) or {} for f in sorted(persona_dir.glob("*.yaml"))]
    roles = {raw.get("slug", "") for raw in raws if raw.get("delivery") == "role"}
    assert roles
    assert roles.isdisjoint(personas)
    assert len(personas) + len(roles) == len(raws)
    sample = next(iter(personas.values()))
    assert sample["base_model_id"] == sample["params"]["model"] and sample["params"]["system"]


def test_a_persona_sharing_a_workspace_id_is_reported_not_drift():
    exp = [
        {
            "id": "auto-documents",
            "name": "x",
            "base_model_id": "b",
            "params": {"system": "s", "model": "b"},
            "meta": {"toolIds": []},
        }
    ]
    assert mod.shadowed_personas(exp) == ["auto-documents"]
    assert mod.check_personas(lambda _id: None, exp) == {}  # never seeded, so never "missing"
    other = [{**exp[0], "id": "some-persona-xyz"}]
    assert list(mod.check_personas(lambda _id: None, other)) == ["some-persona-xyz"]
