"""Bearer auth for the oMLX engine.

oMLX can require an API key (``auth.api_key`` in ``~/.omlx/settings.json``). The key
lives in ``OMLX_API_KEY`` (``.env``); with it unset nothing is added, so a keyless oMLX
keeps working. Only requests to the oMLX server (``OMLX_URL``, default
``host.docker.internal``/``localhost`` :8085) carry it; Ollama and the MCP servers never see it.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path
from urllib.parse import urlsplit

import httpx

_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
_DEFAULT_NETLOCS = frozenset({"host.docker.internal:8085", "localhost:8085", "127.0.0.1:8085"})


def _omlx_netlocs() -> frozenset[str]:
    url = os.environ.get("OMLX_URL")
    return frozenset({urlsplit(url).netloc.lower()}) if url else _DEFAULT_NETLOCS


def omlx_api_key() -> str:
    """``OMLX_API_KEY`` from the environment, else from the repo ``.env`` (host tools run
    from launchd/cron have no exported env). Empty when oMLX is keyless."""
    key = os.environ.get("OMLX_API_KEY", "")
    if key or not _ENV_FILE.is_file():
        return key
    for line in _ENV_FILE.read_text().splitlines():
        if line.startswith("OMLX_API_KEY="):
            return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def omlx_headers() -> dict[str, str]:
    key = omlx_api_key()
    return {"Authorization": f"Bearer {key}"} if key else {}


class OmlxKeyAuth(httpx.Auth):
    """Adds ``Authorization: Bearer $OMLX_API_KEY`` to requests bound for oMLX."""

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        key = os.environ.get("OMLX_API_KEY", "")
        if (
            key
            and "authorization" not in request.headers
            and request.url.netloc.decode().lower() in _omlx_netlocs()
        ):
            request.headers["Authorization"] = f"Bearer {key}"
        yield request


def omlx_post(url: str, **kwargs: object) -> httpx.Response:
    """``httpx.post`` that carries the oMLX key when ``url`` is the oMLX server."""
    return httpx.post(url, auth=OmlxKeyAuth(), **kwargs)  # type: ignore[arg-type]
