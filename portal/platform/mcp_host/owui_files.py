"""Publish a generated media file through Open WebUI's files API.

Portal's remote surface is Open WebUI (:8080) behind the tunnel — no other
port is exposed. So generated audio/music/3D files are handed to viewers as
``{PORTAL_PUBLIC_URL}/api/v1/files/{id}/content/{name}``: Open WebUI stores
the bytes and serves them on the one port the tunnel already carries, using
the viewer's existing session cookie for auth. MCP file ports stay loopback.

Requires ``OWUI_API_KEY`` (an Open WebUI API key, ``sk-...``). When it is
unset the helper returns ``None`` and the caller falls back to a local URL —
this keeps a no-Open-WebUI dev box working.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# Internal address for the upload POST; the returned link uses the public base.
_OWUI_URL = os.getenv("OPENWEBUI_URL", "http://open-webui:8080").rstrip("/")


def _public_base() -> str:
    return (os.getenv("PORTAL_PUBLIC_URL") or _OWUI_URL).rstrip("/")


async def publish_file(
    path: Path, *, content_type: str = "application/octet-stream"
) -> dict | None:
    """Upload ``path`` to Open WebUI and return ``{"id", "filename", "url"}``.

    Returns ``None`` if ``OWUI_API_KEY`` is unset or the upload fails — the
    caller should then fall back to its local file URL.
    """
    api_key = os.getenv("OWUI_API_KEY", "")
    if not api_key:
        return None
    try:
        data = path.read_bytes()
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{_OWUI_URL}/api/v1/files/",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (path.name, data, content_type)},
            )
        r.raise_for_status()
        fid = r.json()["id"]
    except Exception as e:  # noqa: BLE001 — degrade to local URL, never crash the tool
        logger.warning("Open WebUI file publish failed (%s); falling back to local URL", e)
        return None
    return {
        "id": fid,
        "filename": path.name,
        "url": f"{_public_base()}/api/v1/files/{fid}/content/{path.name}",
    }
