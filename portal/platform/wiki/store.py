"""Git-backed store for canonical knowledge units.

Units are stored as markdown files under `portal_wiki/canonical/`.
Git-versioned, portable, no DB lock-in.
"""

from __future__ import annotations

from pathlib import Path

from .schema import KnowledgeUnit

# Default store directory (relative to repo root)
_CANONICAL_DIR: Path | None = None
_ARCHIVE_DIR: Path | None = None


def _get_canonical_dir() -> Path:
    """Get the canonical store directory."""
    if _CANONICAL_DIR is not None:
        return _CANONICAL_DIR
    # canonical/ data stays at portal_wiki/canonical/ (repo root sibling of portal/)
    return Path(__file__).resolve().parents[3] / "portal_wiki" / "canonical"


def set_canonical_dir(path: Path) -> None:
    """Override the canonical directory (for testing)."""
    global _CANONICAL_DIR
    _CANONICAL_DIR = path


def reset_canonical_dir() -> None:
    """Reset to default."""
    global _CANONICAL_DIR
    _CANONICAL_DIR = None


def _get_archive_dir() -> Path:
    """Get the archive store directory (archived units, retained on disk)."""
    if _ARCHIVE_DIR is not None:
        return _ARCHIVE_DIR
    return Path(__file__).resolve().parents[3] / "portal_wiki" / "archive"


def set_archive_dir(path: Path) -> None:
    """Override the archive directory (for testing)."""
    global _ARCHIVE_DIR
    _ARCHIVE_DIR = path


def reset_archive_dir() -> None:
    """Reset to default."""
    global _ARCHIVE_DIR
    _ARCHIVE_DIR = None


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


def load_archived() -> list[KnowledgeUnit]:
    """Load all archived units from the archive store.

    Archived units are retained on disk (catalog changes are additive-only)
    but are read-only history: `load_all()` never sees them, so search,
    coverage, drift, quality, and render all operate on the live set only.
    Explicit access for archaeology and for the archive command itself.
    """
    archive = _get_archive_dir()
    if not archive.exists():
        return []
    units = []
    for path in sorted(archive.glob("*.md")):
        try:
            units.append(KnowledgeUnit.from_markdown(path.read_text(encoding="utf-8")))
        except (ValueError, Exception):
            continue  # skip malformed files
    return units
