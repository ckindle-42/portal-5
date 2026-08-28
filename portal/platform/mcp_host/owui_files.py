"""The single path for handing a generated file back to the user.

Portal's only remote surface is Open WebUI on :8080. Every generator —
speech, music, 3D, documents, spreadsheets, images, transcripts — writes its
file locally, then calls ``publish_file`` (async) or ``publish_file_sync``.
The bytes go to Open WebUI's files API and the caller gets back one link:

    {PORTAL_PUBLIC_URL}/api/v1/files/{id}/content/{name}

Open WebUI stores and serves the file on the port the tunnel already
carries, authorised by the viewer's existing session. No MCP serves files,
no per-service ports or ingress rules exist.

Config (``.env``): ``OWUI_API_KEY`` (an Open WebUI key, ``sk-...``, from
Settings -> Account) and, when reached remotely, ``PORTAL_PUBLIC_URL``.
On any failure the helpers return ``{"error": "..."}`` — a tool should pass
that straight back so the operator sees what to fix.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


def _owui_url() -> str:
    return os.getenv("OPENWEBUI_URL", "http://open-webui:8080").rstrip("/")


def _public_base() -> str:
    return (os.getenv("PORTAL_PUBLIC_URL") or _owui_url()).rstrip("/")


def _upload(path: Path) -> dict:
    """Upload one file to Open WebUI. Returns {"id","filename","url"} or {"error"}."""
    api_key = os.getenv("OWUI_API_KEY", "")
    if not api_key:
        return {"error": "OWUI_API_KEY is not set — cannot publish the generated file."}
    if not path.is_file():
        return {"error": f"generated file missing: {path}"}
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    try:
        with httpx.Client(timeout=60) as client:
            r = client.post(
                f"{_owui_url()}/api/v1/files/",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (path.name, path.read_bytes(), ctype)},
            )
        r.raise_for_status()
        fid = r.json()["id"]
    except Exception as e:  # noqa: BLE001 — report, never crash the tool
        logger.warning("Open WebUI file publish failed: %s", e)
        return {"error": f"Open WebUI file publish failed: {e}"}
    return {
        "id": fid,
        "filename": path.name,
        "url": f"{_public_base()}/api/v1/files/{fid}/content/{path.name}",
    }


def publish_file_sync(path: Path | str) -> dict:
    """Publish a generated file from synchronous tool code.

    Returns ``{"id", "filename", "url"}`` on success, ``{"error": "..."}`` otherwise.
    """
    return _upload(Path(path))


async def publish_file(path: Path | str) -> dict:
    """Publish a generated file from async tool code. See ``publish_file_sync``."""
    return await asyncio.to_thread(_upload, Path(path))
