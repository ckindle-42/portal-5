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

    OWUI stores uploads as ``{uuid}_{original_filename}``.  Accepts:
    - Full stored filename (``ba61aacb-..._meeting.mp3``)
    - UUID prefix only (``ba61aacb-...``)
    - Original filename only (``meeting.mp3``)
    - Partial URL fragment (``/api/v1/files/{id}/content`` → extracts the id)

    Returns:
        Absolute Path if found, None otherwise.
    """
    uploads = get_uploads_dir()

    # Strip OWUI API URL wrapper if the model passes a full path like
    # "/api/v1/files/<id>/content" — extract just the id segment.
    import re as _re
    _url_match = _re.search(r"/files/([^/]+)/", file_id_or_name)
    if _url_match:
        file_id_or_name = _url_match.group(1)

    # Direct match (exact stored filename)
    direct = uploads / file_id_or_name
    if direct.is_file():
        return direct.resolve()

    # Prefix match — UUID prefix (``{uuid}`` matches ``{uuid}_{filename}``)
    candidates = list(uploads.glob(f"{file_id_or_name}*"))
    candidates = [c for c in candidates if c.is_file()]
    if candidates:
        candidates.sort(key=lambda c: c.stat().st_mtime, reverse=True)
        return candidates[0].resolve()

    # Suffix match — original filename only (``meeting.mp3`` matches ``{uuid}_meeting.mp3``)
    candidates = [f for f in uploads.iterdir() if f.is_file() and f.name.endswith(f"_{file_id_or_name}")]
    if candidates:
        candidates.sort(key=lambda c: c.stat().st_mtime, reverse=True)
        return candidates[0].resolve()

    return None
