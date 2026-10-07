"""Async client for the EmbeddingGemma 2 platform service (:8946).

httpx only (see package docstring). Every call verifies the served identity
against the dimension it asked for, and ``expected_model`` (when given) against
the served model, so a consumer can never write vectors from a model it did not
ask for — the silent-swap class the :8917 dual-launch defect exhibited.
"""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from typing import Any

import httpx

from .contract import MRL_DIMS, NATIVE_DIM, Identity, Role, Task

DEFAULT_URL = "http://localhost:8946"
_IDENTITY_TTL_S = float(os.environ.get("EG2_IDENTITY_TTL", "300"))


def service_url() -> str:
    """Base URL from ``EG2_EMBEDDING_URL`` (containers set the
    host.docker.internal form; host processes use the loopback default)."""
    return os.environ.get("EG2_EMBEDDING_URL", DEFAULT_URL).rstrip("/")


class EmbeddingUnavailableError(Exception):
    """The service is down, not ready, or serving something other than asked."""


class EmbeddingClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 60.0,
        expected_model: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or service_url()).rstrip("/")
        self.timeout = timeout
        self.expected_model = expected_model or os.environ.get("EG2_EXPECTED_MODEL") or None
        self._transport = transport
        self._identity: Identity | None = None
        self._identity_at = 0.0

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, transport=self._transport)

    async def identity(self, *, refresh: bool = False) -> Identity:
        now = time.monotonic()
        if self._identity and not refresh and now - self._identity_at < _IDENTITY_TTL_S:
            return self._identity
        try:
            async with self._client() as c:
                r = await c.get(f"{self.base_url}/ready")
                body = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise EmbeddingUnavailableError(f"{self.base_url}/ready unreachable: {e}") from e
        if r.status_code != 200 or not body.get("ready"):
            raise EmbeddingUnavailableError(f"{self.base_url}/ready not ready: {body}")
        ident = Identity.from_dict(body.get("identity") or {})
        if self.expected_model and ident.model != self.expected_model:
            raise EmbeddingUnavailableError(
                f"service serves {ident.model!r}, consumer expects {self.expected_model!r}"
            )
        self._identity, self._identity_at = ident, now
        return ident

    async def version_tag(self, dim: int = NATIVE_DIM) -> str:
        return (await self.identity()).version_tag(dim)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with self._client() as c:
                r = await c.post(f"{self.base_url}{path}", json=payload)
        except httpx.HTTPError as e:
            raise EmbeddingUnavailableError(f"{self.base_url}{path} unreachable: {e}") from e
        if r.status_code != 200:
            raise EmbeddingUnavailableError(
                f"{self.base_url}{path} HTTP {r.status_code}: {r.text[:300]}"
            )
        body: dict[str, Any] = r.json()
        return body

    def _check(self, body: dict[str, Any], dim: int, n: int) -> list[list[float]]:
        vecs = body.get("embeddings") or []
        if len(vecs) != n:
            raise EmbeddingUnavailableError(f"asked for {n} embeddings, got {len(vecs)}")
        for v in vecs:
            if len(v) != dim:
                raise EmbeddingUnavailableError(f"asked for {dim}d, got {len(v)}d")
        served = str(body.get("model", ""))
        if self.expected_model and served and served != self.expected_model:
            raise EmbeddingUnavailableError(
                f"service answered with {served!r}, consumer expects {self.expected_model!r}"
            )
        return [list(map(float, v)) for v in vecs]

    async def embed_texts(
        self,
        texts: Sequence[str],
        *,
        task: Task,
        role: Role = Role.QUERY,
        dim: int = NATIVE_DIM,
        titles: Sequence[str | None] | None = None,
    ) -> list[list[float]]:
        """Embed text with the model-card prefix for ``task``/``role`` applied
        server-side. Returns L2-normalized vectors of length ``dim``."""
        if dim not in MRL_DIMS:
            raise ValueError(f"dim {dim} not in {MRL_DIMS}")
        if not texts:
            return []
        if titles is not None and len(titles) != len(texts):
            raise ValueError("titles must align with texts")
        inputs = [
            {"text": t, **({"title": titles[i]} if titles and titles[i] else {})}
            for i, t in enumerate(texts)
        ]
        body = await self._post(
            "/embed", {"inputs": inputs, "task": task.value, "role": role.value, "dim": dim}
        )
        return self._check(body, dim, len(texts))

    async def embed_items(
        self,
        items: Sequence[dict[str, Any]],
        *,
        task: Task = Task.SEARCH,
        role: Role = Role.DOCUMENT,
        dim: int = NATIVE_DIM,
    ) -> list[list[float]]:
        """Embed multimodal items. Each item may carry ``text``, ``title``,
        ``image_path``/``image_b64``, ``audio_path``, ``video_path``. Prefixes
        are applied to text-only items; media items are embedded raw."""
        if dim not in MRL_DIMS:
            raise ValueError(f"dim {dim} not in {MRL_DIMS}")
        if not items:
            return []
        body = await self._post(
            "/embed_items",
            {"items": list(items), "task": task.value, "role": role.value, "dim": dim},
        )
        return self._check(body, dim, len(items))
