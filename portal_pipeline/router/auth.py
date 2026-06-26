"""Pipeline auth — bearer-token verification for /v1/* and /admin/* endpoints."""
from __future__ import annotations

import hmac

from fastapi import HTTPException

import os

_raw_api_key = os.environ.get("PIPELINE_API_KEY", "")
PIPELINE_API_KEY: str = _raw_api_key
PORTAL5_ADMIN_KEY: str = os.environ.get("PORTAL5_ADMIN_KEY", _raw_api_key)

def _verify_key(authorization: str | None) -> None:
    """Validate the Authorization header against ``PIPELINE_API_KEY``.

    Uses ``hmac.compare_digest`` for constant-time comparison —
    naive ``==`` is vulnerable to timing attacks that can probe a
    remote API key byte-by-byte by measuring response latency.

    Accepts both ``"Bearer <key>"`` and bare ``"<key>"`` forms;
    ``removeprefix`` is a no-op if the prefix isn't present.

    Args:
        authorization: Raw ``Authorization`` header value, or
            ``None`` when the header is absent.

    Raises:
        HTTPException: 401 when the header is missing or the key
            doesn't match.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token.encode(), PIPELINE_API_KEY.encode()):
        raise HTTPException(status_code=401, detail="Invalid API key")


def _verify_admin_key(authorization: str | None) -> None:
    """Validate Authorization against ``PORTAL5_ADMIN_KEY``.

    Same contract as ``_verify_key`` but checks the admin key for
    write-side endpoints (currently ``/admin/refresh-tools``).

    ``PORTAL5_ADMIN_KEY`` defaults to ``PIPELINE_API_KEY`` if unset
    (line 1853), so single-user / single-key deployments don't have
    to set two env vars. Production with separated concerns sets
    them differently.

    Constant-time comparison via ``hmac.compare_digest``.

    Args:
        authorization: Raw ``Authorization`` header value.

    Raises:
        HTTPException: 401 when the header is missing or the key
            doesn't match.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token.encode(), PORTAL5_ADMIN_KEY.encode()):
        raise HTTPException(status_code=401, detail="Invalid admin key")


