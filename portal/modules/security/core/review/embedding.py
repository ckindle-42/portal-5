"""review.embedding -- synchronous, fail-closed client for the platform EG2 service."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from portal.platform.embedding.contract import Role, Task, has_nan, parse_role, parse_task

from .knowledge import Embedder

DEFAULT_BATCH_SIZE = 64
DEFAULT_TIMEOUT_SECONDS = 60


class EmbeddingError(RuntimeError):
    """The embedding service failed or violated the requested contract."""


class PlatformEmbedder(Embedder):
    """Use ``/ready`` identity and ``/embed`` task formatting from the platform contract."""

    def __init__(
        self,
        *,
        task: Task | str,
        dim: int,
        role: Role | str = Role.QUERY,
        base_url: str = "http://127.0.0.1:8946",
        batch_size: int = DEFAULT_BATCH_SIZE,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.task = parse_task(task)
        self.dim = dim
        self.role = parse_role(role)
        self.base_url = base_url.rstrip("/")
        self.batch_size = batch_size
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        if dim <= 0:
            raise ValueError("dim must be positive")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self._model = self._fetch_model()
        self.identity = (
            f"{self._model};dim={self.dim};task={self.task.value};role={self.role.value}"
        )

    def _get(self, path: str) -> Mapping[str, Any]:
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.get(f"{self.base_url}{path}")
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EmbeddingError(f"embedding request {path} failed: {exc}") from exc
        if not isinstance(body, Mapping):
            raise EmbeddingError(f"embedding response {path} is not an object")
        return body

    def _fetch_model(self) -> str:
        ready = self._get("/ready")
        if not ready.get("ready"):
            raise EmbeddingError(f"embedding service is not ready: {ready}")
        identity = ready.get("identity")
        if not isinstance(identity, Mapping) or not identity.get("model"):
            raise EmbeddingError("embedding /ready response has no model identity")
        return str(identity["model"])

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._fetch_model()
        if model != self._model:
            raise EmbeddingError(
                f"embedding service changed from {self._model!r} to {model!r} during use"
            )
        output: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            chunk = list(texts[start : start + self.batch_size])
            try:
                with httpx.Client(
                    timeout=self.timeout_seconds,
                    transport=self.transport,
                ) as client:
                    response = client.post(
                        f"{self.base_url}/embed",
                        json={
                            "inputs": [{"text": text} for text in chunk],
                            "task": self.task.value,
                            "role": self.role.value,
                            "dim": self.dim,
                        },
                    )
                    response.raise_for_status()
                    body = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise EmbeddingError(f"embedding batch failed: {exc}") from exc
            if not isinstance(body, Mapping):
                raise EmbeddingError("embedding response is not an object")
            served = body.get("model")
            if served and str(served) != model:
                raise EmbeddingError(
                    f"embedding response served {served!r}, /ready reported {model!r}"
                )
            vectors = body.get("embeddings")
            if not isinstance(vectors, list) or len(vectors) != len(chunk):
                raise EmbeddingError(
                    f"asked for {len(chunk)} embeddings, got "
                    f"{len(vectors) if isinstance(vectors, list) else 'invalid response'}"
                )
            for vector in vectors:
                if not isinstance(vector, list) or len(vector) != self.dim:
                    raise EmbeddingError(f"asked for {self.dim} dimensions, got invalid vector")
                try:
                    row = [float(value) for value in vector]
                except (TypeError, ValueError) as exc:
                    raise EmbeddingError(
                        "embedding response contains a non-numeric vector"
                    ) from exc
                if has_nan(row):
                    raise EmbeddingError("embedding response contains a non-finite vector")
                output.append(row)
        return output
