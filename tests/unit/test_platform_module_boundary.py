"""Guard the platform's plugin seam from direct module imports."""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLUGIN_SEAM = REPO / "portal" / "platform" / "plugins.py"


def test_platform_imports_no_module_code() -> None:
    offenders = []
    for path in sorted((REPO / "portal" / "platform").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [
                    f"portal.{alias.name}" if node.module == "portal" else node.module
                    for alias in node.names
                ]
            else:
                continue
            for name in names:
                if path == PLUGIN_SEAM and name == "portal.modules":
                    continue
                if name == "portal.modules" or name.startswith("portal.modules."):
                    offenders.append(f"{path.relative_to(REPO)}:{node.lineno} imports {name}")
    assert not offenders, "platform imports module code through the plugin seam:\n" + "\n".join(
        offenders
    )
