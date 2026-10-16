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
