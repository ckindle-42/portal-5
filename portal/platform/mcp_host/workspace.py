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
_VALID_CATEGORIES = frozenset(
    {"transcripts", "documents", "images", "videos", "music", "speech", "models3d"}
)


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
        category: One of: transcripts, documents, images, videos, music, speech, models3d.

    Raises:
        ValueError: if category is not in the canonical set.
    """
    if category not in _VALID_CATEGORIES:
        raise ValueError(f"Unknown category {category!r}. Valid: {sorted(_VALID_CATEGORIES)}")
    p = get_workspace_root() / "generated" / category
    p.mkdir(parents=True, exist_ok=True)
    return p


def assert_public_http_url(url: str) -> None:
    """Reject URLs resolving to loopback/link-local/private/reserved addresses.

    Media MCPs (comfyui, video, whisper, ...) let an LLM tool call pass a
    remote URL (image_url, audio_url, ...) that gets server-side fetched — a
    prompt-injected model could otherwise be steered into requesting
    http://169.254.169.254/... (cloud metadata SSRF) or any other internal-only
    service reachable from the container. Callers must also leave
    httpx.AsyncClient's default follow_redirects=False in place; this check
    only covers the request URL itself, not any redirect target.
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL must be http(s), got: {url!r}")
    if not parsed.hostname:
        raise ValueError(f"URL has no hostname: {url!r}")
    try:
        addrs = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as e:
        raise ValueError(f"URL hostname does not resolve: {parsed.hostname!r} ({e})") from e
    for _family, _type, _proto, _canonname, sockaddr in addrs:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError(f"URL resolves to a non-public address: {parsed.hostname} -> {ip}")


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

    # Reduce to a bare filename before any lookup. Without this, an absolute
    # path (e.g. "/etc/passwd") silently discards `uploads` entirely when
    # joined with `/` (pathlib: Path("/a") / "/b" == Path("/b")), and a
    # "../"-laden argument could escape the uploads dir via glob/iterdir too
    # — this is an LLM-controlled tool argument (prompt injection can steer
    # what gets passed here), so treat it as untrusted input, not a trusted
    # identifier.
    file_id_or_name = os.path.basename(file_id_or_name)
    if not file_id_or_name:
        return None

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
    candidates = [
        f for f in uploads.iterdir() if f.is_file() and f.name.endswith(f"_{file_id_or_name}")
    ]
    if candidates:
        candidates.sort(key=lambda c: c.stat().st_mtime, reverse=True)
        return candidates[0].resolve()

    return None
