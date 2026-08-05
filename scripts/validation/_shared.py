"""Shared module-level helpers for the scripts/validation check family modules.

The checks moved into this package (TASK_PORTAL_SIMPLIFY_V1 C5) referenced
module-level names in validate_system.py (REPO_ROOT, stdlib imports, and
small helpers). Re-exporting them here keeps the family modules self-contained
without a validate_system <-> validation import cycle. The REPO_ROOT sys.path
insert mirrors what validate_system.py historically did at import time — family
checks that import ``scripts.*`` helpers or ``portal.*`` modules lazily at
runtime rely on the repo root being on sys.path.
"""

from __future__ import annotations

import asyncio  # noqa: F401  (re-export for family modules)
import importlib  # noqa: F401  (re-export for family modules)
import json  # noqa: F401  (re-export for family modules)
import os  # noqa: F401  (re-export for family modules)
import re
import subprocess  # noqa: F401  (re-export for family modules)
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _pyproject_duplicate_dep_contexts(pyproject: Path | None) -> list[str]:
    """Contexts in pyproject.toml whose dependency list pins a package twice.

    Case-insensitive, `-`/`_` folded, version specifier stripped, scoped per
    context (core vs each extra) — the semantic the retired CI guard enforced.
    """
    if pyproject is None or not pyproject.exists():
        return []
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

    try:
        data = tomllib.loads(pyproject.read_text())
    except Exception:  # noqa: BLE001
        return []

    def pkg(dep: str) -> str:
        return re.split(r"[><=!;[ ]", dep.strip())[0].lower().replace("-", "_")

    dup: list[str] = []
    contexts: list[tuple[str, list]] = [
        ("[project.dependencies]", data.get("project", {}).get("dependencies", []))
    ]
    for extra, deps in data.get("project", {}).get("optional-dependencies", {}).items():
        contexts.append((f"[project.optional-dependencies.{extra}]", deps))
    for name, deps in contexts:
        seen: set[str] = set()
        for dep in deps:
            key = pkg(dep)
            if key in seen:
                dup.append(name)
                break
            seen.add(key)
    return dup
