"""Git-backed store for canonical knowledge units.

Units are stored as markdown files under `portal_wiki/canonical/`.
Git-versioned, portable, no DB lock-in.
"""

from __future__ import annotations

from pathlib import Path

from .schema import KnowledgeUnit

# Default store directory (relative to repo root)
_CANONICAL_DIR: Path | None = None


def _get_canonical_dir() -> Path:
    """Get the canonical store directory."""
    if _CANONICAL_DIR is not None:
        return _CANONICAL_DIR
    # Default: portal_wiki/canonical/ relative to repo root
    return Path(__file__).resolve().parent.parent / "canonical"


def set_canonical_dir(path: Path) -> None:
    """Override the canonical directory (for testing)."""
    global _CANONICAL_DIR
    _CANONICAL_DIR = path


def reset_canonical_dir() -> None:
    """Reset to default."""
    global _CANONICAL_DIR
    _CANONICAL_DIR = None


def _unit_path(unit_id: str) -> Path:
    """Get the file path for a unit ID."""
    return _get_canonical_dir() / f"{unit_id}.md"


def save_unit(unit: KnowledgeUnit) -> Path:
    """Save a unit to the canonical store."""
    canonical = _get_canonical_dir()
    canonical.mkdir(parents=True, exist_ok=True)
    path = _unit_path(unit.id)
    path.write_text(unit.to_markdown(), encoding="utf-8")
    return path


def load_unit(unit_id: str) -> KnowledgeUnit | None:
    """Load a unit by ID.  Returns None if not found."""
    path = _unit_path(unit_id)
    if not path.exists():
        return None
    return KnowledgeUnit.from_markdown(path.read_text(encoding="utf-8"))


def load_all() -> list[KnowledgeUnit]:
    """Load all units from the canonical store."""
    canonical = _get_canonical_dir()
    if not canonical.exists():
        return []
    units = []
    for path in sorted(canonical.glob("*.md")):
        try:
            units.append(KnowledgeUnit.from_markdown(path.read_text(encoding="utf-8")))
        except (ValueError, Exception):
            continue  # skip malformed files
    return units


def list_ids() -> list[str]:
    """List all unit IDs in the store."""
    canonical = _get_canonical_dir()
    if not canonical.exists():
        return []
    return sorted(p.stem for p in canonical.glob("*.md"))


def delete_unit(unit_id: str) -> bool:
    """Delete a unit by ID.  Returns True if deleted."""
    path = _unit_path(unit_id)
    if path.exists():
        path.unlink()
        return True
    return False
