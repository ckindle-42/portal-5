"""Seed canonical knowledge from code sources (modules, configs, workspaces).

Phase W3 of BUILD_PROGRAM_SEC_RBP_WIKI_FIXES_V1.

Walks the repo for Python modules → WHAT units, each citing code path +
current commit.  Groups sensibly (a subsystem per unit, not one-per-file).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from portal.platform.wiki.schema import KnowledgeUnit, SourceRef
from portal.platform.wiki.store import save_unit

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _get_current_commit() -> str:
    """Get current git HEAD SHA."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()[:12]
    except Exception:
        return "unknown"


def seed_code(dry_run: bool = False) -> list[KnowledgeUnit]:
    """Seed WHAT units from code sources.

    Returns list of units created.
    """
    units: list[KnowledgeUnit] = []
    commit = _get_current_commit()

    # Group modules by subsystem
    subsystems: dict[str, list[Path]] = {}
    for py_file in sorted(_REPO_ROOT.rglob("*.py")):
        rel = py_file.relative_to(_REPO_ROOT)
        parts = rel.parts

        # Skip test results, __pycache__, .git
        if any(p.startswith(".") or p in ("__pycache__", "results", "node_modules") for p in parts):
            continue
        if py_file.stat().st_size == 0:
            continue

        # Group by top-level directory
        subsystem = parts[0] if len(parts) > 1 else "root"
        subsystems.setdefault(subsystem, []).append(py_file)

    # Create one unit per subsystem
    for subsystem, files in sorted(subsystems.items()):
        if len(files) < 2:
            continue  # skip single-file subsystems

        unit_id = f"unit-code-{subsystem}"
        file_list = []
        for f in files[:20]:  # cap at 20 files per unit
            rel = str(f.relative_to(_REPO_ROOT))
            file_list.append(f"- `{rel}`")

        body = f"# {subsystem} subsystem\n\n"
        body += f"**Files:** {len(files)}\n\n"
        body += "\n".join(file_list)
        if len(files) > 20:
            body += f"\n- ... and {len(files) - 20} more"

        sources = [
            SourceRef(type="code", path=str(f.relative_to(_REPO_ROOT)), commit=commit)
            for f in files[:5]  # cite first 5 files
        ]

        try:
            unit = KnowledgeUnit(
                id=unit_id,
                kind="what",
                title=f"{subsystem} subsystem ({len(files)} files)",
                sources=sources,
                body=body,
                tags=["code", subsystem],
            )
            units.append(unit)
            if not dry_run:
                save_unit(unit)
        except ValueError:
            continue

    return units
