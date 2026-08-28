#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "config/inference/cad_geometry_schema.json"
MANIFEST_PATH = ROOT / "config/inference/tools_manifest_cad_render_mcp.json"


def expected_manifest() -> list[dict]:
    schema = json.loads(SCHEMA_PATH.read_text())
    manifest = json.loads(MANIFEST_PATH.read_text())
    generated = copy.deepcopy(schema)
    generated.pop("$schema", None)
    generated.pop("title", None)
    generated.pop("examples", None)
    for tool in manifest:
        if tool["name"] == "generate_scad":
            tool["parameters"]["properties"]["geometry"] = generated
            break
    else:
        raise SystemExit("generate_scad missing from CAD tool manifest")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = json.dumps(expected_manifest(), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if MANIFEST_PATH.read_text() != expected:
            raise SystemExit("CAD manifest is stale; run scripts/sync_cad_geometry_schema.py")
        return 0
    MANIFEST_PATH.write_text(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
