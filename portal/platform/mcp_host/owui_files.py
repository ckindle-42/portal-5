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
Host-native (launchd) services never source ``.env``, so these keys fall back
to a key-only read of the repo ``.env`` (os.environ wins; never exported).
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

_ENV_KEYS = ("OWUI_API_KEY", "OPENWEBUI_URL", "PORTAL_PUBLIC_URL")


def _repo_env_file() -> Path | None:
    """Walk up from this file to the repo .env — launchd services never source it."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    return None


def _dotenv_values() -> dict[str, str]:
    """Read only the publish keys from .env; never executed, never exported."""
    env_file = _repo_env_file()
    if env_file is None:
        return {}
    try:
        text = env_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            continue
        for key in _ENV_KEYS:
            if key not in values and line.startswith(f"{key}="):
                values[key] = line.partition("=")[2].strip().strip("\"'")
    return values


def _setting(key: str, dotenv: dict[str, str]) -> str:
    """os.environ wins over .env; a blank env value counts as absent."""
    value = os.environ.get(key)
    if value is None or not value.strip():
        return dotenv.get(key, "")
    return value


def _owui_url(dotenv: dict[str, str] | None = None) -> str:
    dotenv = _dotenv_values() if dotenv is None else dotenv
    # Host-native services have no OPENWEBUI_URL; PORTAL_PUBLIC_URL is the OWUI
    # address reachable from this machine. The container default stays last.
    url = (
        _setting("OPENWEBUI_URL", dotenv)
        or _setting("PORTAL_PUBLIC_URL", dotenv)
        or "http://open-webui:8080"
    )
    return url.rstrip("/")


def _public_base(dotenv: dict[str, str] | None = None) -> str:
    dotenv = _dotenv_values() if dotenv is None else dotenv
    return (_setting("PORTAL_PUBLIC_URL", dotenv) or _owui_url(dotenv)).rstrip("/")


def _upload(path: Path) -> dict[str, str]:
    """Upload one file to Open WebUI. Returns {"id","filename","url"} or {"error"}."""
    dotenv = _dotenv_values()
    api_key = _setting("OWUI_API_KEY", dotenv)
    if not api_key:
        return {"error": "OWUI_API_KEY is not set — cannot publish the generated file."}
    if not path.is_file():
        return {"error": f"generated file missing: {path}"}
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    try:
        with httpx.Client(timeout=60) as client:
            r = client.post(
                f"{_owui_url(dotenv)}/api/v1/files/",
                headers={"Authorization": f"Bearer {api_key}"},
                # process=false: this upload only mints a download link. With
                # OWUI's default (process=true) every generated audio file was
                # transcribed and every document chunked + embedded into OWUI's
                # vector store as a side effect (TASK_EMBEDDINGGEMMA2_PLATFORM_V1
                # F-PUBLISH).
                params={"process": "false"},
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
        "url": f"{_public_base(dotenv)}/api/v1/files/{fid}/content/{path.name}",
    }


def publish_file_sync(path: Path | str) -> dict[str, str]:
    """Publish a generated file from synchronous tool code.

    Returns ``{"id", "filename", "url"}`` on success, ``{"error": "..."}`` otherwise.
    """
    return _upload(Path(path))


async def publish_file(path: Path | str) -> dict[str, str]:
    """Publish a generated file from async tool code. See ``publish_file_sync``."""
    return await asyncio.to_thread(_upload, Path(path))
