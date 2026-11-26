"""Rule 11 output directory shared by generators that do not call get_generated_dir directly."""

from __future__ import annotations

from pathlib import Path

from portal.platform.mcp_host.workspace import get_generated_dir


def category_output_dir(category: str, *, root: Path | None = None) -> Path:
    """``generated/<category>`` under the workspace. ``root`` is a service's workspace mount."""
    if root is None:
        return get_generated_dir(category)
    if root.name == category and root.parent.name == "generated":
        path = root
    else:
        path = root / "generated" / category
    path.mkdir(parents=True, exist_ok=True)
    return path
