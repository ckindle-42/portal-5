from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import yaml

from portal.modules.cad.tools.scad_emitter import geometry_schema, validate_geometry

ROOT = Path(__file__).resolve().parents[2]


def _geometry_get_keys() -> set[str]:
    tree = ast.parse((ROOT / "portal/modules/cad/tools/scad_emitter.py").read_text())
    keys: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "geometry"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            keys.add(node.args[0].value)
    return keys


def test_schema_and_emitter_top_level_vocabulary_match():
    assert _geometry_get_keys() == set(geometry_schema()["properties"])


def test_manifest_geometry_is_derived_from_schema():
    manifest = json.loads(
        (ROOT / "config/inference/tools_manifest_cad_render_mcp.json").read_text()
    )
    actual = next(tool for tool in manifest if tool["name"] == "generate_scad")["parameters"][
        "properties"
    ]["geometry"]
    expected = copy.deepcopy(geometry_schema())
    for key in ("$schema", "title", "examples"):
        expected.pop(key, None)
    assert actual == expected


def test_schema_sync_script_reports_manifest_current():
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/sync_cad_geometry_schema.py"), "--check"],
        check=True,
    )


def test_auto_cad_prompt_example_validates_against_schema():
    portal = yaml.safe_load((ROOT / "config/portal.yaml").read_text())
    prompt = portal["workspaces"]["auto-cad"]["system_prompt_append"]
    marker = "Example: `"
    start = prompt.index(marker) + len(marker)
    example, _ = json.JSONDecoder().raw_decode(prompt[start:])
    jsonschema.validate(example, geometry_schema())
    assert validate_geometry(example) == []


def test_real_phase8_payloads_are_actionably_rejected():
    result_path = ROOT / "tests/benchmarks/results/cap_cad-overhaul_20260827T164110Z.moe-only.json"
    arms = json.loads(result_path.read_text())
    results = arms[0]["results"]
    t1 = next(result for result in results if result["task"] == "t1_enclosure")
    t2 = next(result for result in results if result["task"] == "t2_grommet_plate")
    t1_geometry = t1["tool_calls"][0]["args"]["geometry"]
    t2_geometry = t2["tool_calls"][0]["args"]["geometry"]

    t1_errors = " ".join(validate_geometry(t1_geometry))
    assert "features" in t1_errors
    assert "valid keys" in t1_errors
    assert "top_of_standoff_1" in json.dumps(t1_geometry)

    t2_errors = " ".join(validate_geometry(t2_geometry))
    assert "holes[0].pattern" in t2_errors
    assert "top-level key" in t2_errors
    assert "feature_kind + feature_index" in t2_errors
