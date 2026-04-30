"""Shared workspace path helpers (TASK-WORKSPACE-001).

Canonical paths:
  - Workspace root: $WORKSPACE_DIR (default /workspace) inside containers,
    or $AI_OUTPUT_DIR (default ~/AI_Output) on the host.
  - Uploads:        <root>/uploads/
  - Generated:      <root>/generated/<category>/

Categories:
  transcripts, documents, images, videos, music, speech

Use these helpers instead of hardcoding paths so that a future remap (e.g.,
mounting at a different container path) requires no code changes.
"""

from __future__ import annotations

import os
from pathlib import Path

# Container default; on host, callers can pass a path or set AI_OUTPUT_DIR.
_DEFAULT_WORKSPACE = "/workspace"
_VALID_CATEGORIES = frozenset({"transcripts", "documents", "images", "videos", "music", "speech"})


def get_workspace_root() -> Path:
    """Return the workspace root for the current process.

    Resolution order:
      1. WORKSPACE_DIR env var (set in Docker compose for participating MCPs)
      2. AI_OUTPUT_DIR env var (host-native services)
      3. /workspace (container default)
      4. ~/AI_Output (host fallback)
    """
    candidate = os.getenv("WORKSPACE_DIR") or os.getenv("AI_OUTPUT_DIR")
    if candidate:
        return Path(candidate)
    container_default = Path(_DEFAULT_WORKSPACE)
    if container_default.is_dir():
        return container_default
    return Path.home() / "AI_Output"


def get_uploads_dir() -> Path:
    """Return the uploads directory, creating it if missing."""
    p = get_workspace_root() / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_generated_dir(category: str) -> Path:
    """Return a category-specific generated output directory.

    Args:
        category: One of: transcripts, documents, images, videos, music, speech.

    Raises:
        ValueError: if category is not in the canonical set.
    """
    if category not in _VALID_CATEGORIES:
        raise ValueError(f"Unknown category {category!r}. Valid: {sorted(_VALID_CATEGORIES)}")
    p = get_workspace_root() / "generated" / category
    p.mkdir(parents=True, exist_ok=True)
    return p


def resolve_upload_path(file_id_or_name: str) -> Path | None:
    """Resolve an OWUI upload reference to an absolute path on disk.

    Args:
        file_id_or_name: Either a bare file ID (UUID-like, no extension) as
            OWUI stores it, or a full filename. Tries direct match first,
            then prefix match against entries in the uploads directory.

    Returns:
        Absolute Path if found, None otherwise.
    """
    uploads = get_uploads_dir()

    # Direct match
    direct = uploads / file_id_or_name
    if direct.is_file():
        return direct.resolve()

    # Prefix match (file_id without extension)
    candidates = list(uploads.glob(f"{file_id_or_name}*"))
    candidates = [c for c in candidates if c.is_file()]
    if len(candidates) == 1:
        return candidates[0].resolve()
    if len(candidates) > 1:
        # Ambiguous — prefer exact prefix + most recent
        candidates.sort(key=lambda c: c.stat().st_mtime, reverse=True)
        return candidates[0].resolve()

    return None
