#!/usr/bin/env python3
"""Deterministic surface snapshot for the Portal Surface Collapse program
(TASK_AGENT_LOOP_PLATFORM_V1's sibling: coding_task/BUILD_PROGRAM_COLLAPSE_V1.md).

Captures the counts every phase of that program changes, so each phase's
before/after diff is measured, not asserted. Read-only — never writes to
config/portal.yaml, config/personas/, or portal_wiki/.

Usage: python3 scripts/collapse_snapshot.py > snapshot.json
"""

from __future__ import annotations

import glob
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
_ENABLED_RE = re.compile(r"^\s*enabled:\s*(true|false)\s*$", re.MULTILINE | re.IGNORECASE)

ALL_MODULE_UNITS = (
    "cad",
    "coding",
    "compliance",
    "documents",
    "eval",
    "general",
    "media",
    "research",
    "security",
)


def _portal_yaml() -> dict:
    return yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text())


def _persona_files() -> list[Path]:
    return [Path(p) for p in sorted(glob.glob(str(REPO_ROOT / "config" / "personas" / "*.yaml")))]


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_snapshot() -> dict:
    cfg = _portal_yaml()
    workspaces: dict = cfg.get("workspaces", {}) or {}
    mcp_fleet: list = cfg.get("mcp_fleet", []) or []
    persona_files = _persona_files()

    personas = []
    for f in persona_files:
        d = yaml.safe_load(f.read_text()) or {}
        d["_file"] = f.name
        personas.append(d)

    # Duplicate system_prompt detection (byte-identical, non-empty).
    by_hash: dict[str, list[str]] = defaultdict(list)
    for p in personas:
        sp = (p.get("system_prompt") or "").strip()
        if not sp:
            continue
        h = hashlib.md5(sp.encode()).hexdigest()
        by_hash[h].append(p.get("slug", p["_file"]))
    duplicate_persona_prompts = [
        {"md5": h, "count": len(slugs), "personas": sorted(slugs)}
        for h, slugs in by_hash.items()
        if len(slugs) > 1
    ]

    enabled_field_present = {}
    unit_module_security_present = False
    for name in ALL_MODULE_UNITS:
        unit_path = REPO_ROOT / "portal_wiki" / "canonical" / f"unit-module-{name}.md"
        if name == "security":
            unit_module_security_present = unit_path.exists()
        if not unit_path.exists():
            enabled_field_present[name] = False
            continue
        enabled_field_present[name] = bool(_ENABLED_RE.search(unit_path.read_text()))

    snapshot = {
        "workspace_count": len(workspaces),
        "workspace_ids": sorted(workspaces.keys()),
        "persona_count": len(personas),
        "persona_slugs": sorted(p.get("slug", p["_file"]) for p in personas),
        "mcp_fleet_count": len(mcp_fleet),
        "mcp_ids": sorted(m["id"] for m in mcp_fleet),
        "workspaces_with_module_tag": sum(1 for w in workspaces.values() if w.get("module")),
        "personas_with_module_tag": sum(1 for p in personas if p.get("module")),
        "mcp_with_module_tag": sum(1 for m in mcp_fleet if m.get("module")),
        "duplicate_persona_prompts": duplicate_persona_prompts,
        "enabled_field_present": enabled_field_present,
        "unit_module_security_present": unit_module_security_present,
        "modules_generated_yaml_sha256": _sha256(REPO_ROOT / "config" / "modules.generated.yaml"),
    }
    return snapshot


def main() -> int:
    json.dump(build_snapshot(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
