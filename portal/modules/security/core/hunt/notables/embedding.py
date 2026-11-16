"""Bounded embeddings through the authenticated Portal Pipeline route."""

from __future__ import annotations

import math
import os
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

import httpx

from ..judge import retry_after_seconds

EMBED_BATCH_SIZE = 64  # effort budget: maximum accepted by the Pipeline route
EMBED_CONCURRENCY = 4  # effort budget: the Pipeline embedder admits four batches
EMBED_WORK_SECONDS = 600.0  # effort budget: embedding work inside the 720-second hunt
EMBED_RETRIES = 8  # effort budget: retries for Pipeline back-pressure
EMBED_BACKOFF_SECONDS = 8.0  # effort budget: longest fallback wait between retries
EMBED_TIMEOUT_SECONDS = 120.0  # effort budget: Pipeline route timeout
THROTTLE_STATUSES = frozenset({429, 503})


class EmbeddingError(RuntimeError):
    """The Pipeline embedding route failed or returned invalid vectors."""


def _ordered_vectors(rows: Any, expected: int) -> list[list[float]]:
    """Validate and restore vectors to their request order."""
    if not isinstance(rows, list) or len(rows) != expected:
        raise EmbeddingError(f"asked for {expected} embeddings, got invalid response")
    ordered: list[list[float] | None] = [None] * expected
    for position, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise EmbeddingError("Pipeline embedding row is not an object")
        index = row.get("index", position)
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < expected:
            raise EmbeddingError("Pipeline embedding row has an invalid index")
        raw = row.get("embedding")
        if not isinstance(raw, list) or not raw:
            raise EmbeddingError("Pipeline returned an empty embedding")
        try:
            vector = [float(value) for value in raw]
        except (TypeError, ValueError) as exc:
            raise EmbeddingError("Pipeline returned a non-numeric embedding") from exc
        if not all(math.isfinite(value) for value in vector):
            raise EmbeddingError("Pipeline returned a non-finite embedding")
        if ordered[index] is not None:
            raise EmbeddingError("Pipeline returned a duplicate embedding index")
        ordered[index] = vector
    if any(vector is None for vector in ordered):
        raise EmbeddingError("Pipeline omitted an embedding index")
    return [vector for vector in ordered if vector is not None]


class PipelineEmbeddingClient:
    """Embed bounded batches using only ``POST /v1/embeddings`` on the Pipeline."""

    def __init__(
        self,
        *,
        url: str,
        model: str,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = EMBED_TIMEOUT_SECONDS,
        sleep: Any = time.sleep,
        clock: Any = time.monotonic,
    ) -> None:
        if not url or not model or not api_key:
            raise ValueError("Pipeline URL, accepted model, and API key are required")
        root = url.rstrip("/")
        self.endpoint = root if root.endswith("/v1/embeddings") else root + "/v1/embeddings"
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = httpx.Client(timeout=timeout_seconds, transport=transport)
        self._job_deadline: Callable[[], float] | None = None
        self._sleep = sleep
        self._clock = clock
        self._lock = threading.Lock()
        self._stats: dict[str, Any] = {
            "requests": 0,
            "items": 0,
            "batches": 0,
            "throttles": 0,
            "retries": 0,
            "wait_seconds": 0.0,
            "seconds": 0.0,
        }

    def close(self) -> None:
        self._client.close()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._stats)

    def set_job_deadline(self, deadline: Callable[[], float]) -> None:
        self._job_deadline = deadline

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return vectors in input order, splitting requests at the Pipeline cap."""
        vectors: list[list[float]] = []
        for _start, batch in self.embed_batches(texts):
            vectors.extend(batch)
        return vectors

    def embed_batches(self, texts: Sequence[str]) -> Iterator[tuple[int, list[list[float]]]]:
        """Yield bounded results in input order while keeping at most four batches in memory."""
        if any(not text.strip() for text in texts):
            raise EmbeddingError("embedding input contains an empty statement")
        if any(len(text) > 8192 for text in texts):
            raise EmbeddingError("embedding statement exceeds the Pipeline input limit")
        if not texts:
            return
        deadline = self._clock() + EMBED_WORK_SECONDS
        if self._job_deadline is not None:
            deadline = min(deadline, self._job_deadline())
        if deadline <= self._clock():
            raise EmbeddingError("hunt job deadline exceeded")
        with ThreadPoolExecutor(max_workers=EMBED_CONCURRENCY) as pool:
            pending: list[tuple[int, Future[list[list[float]]]]] = []
            offset = 0
            while offset < len(texts) or pending:
                while offset < len(texts) and len(pending) < EMBED_CONCURRENCY:
                    start = offset
                    batch = list(texts[start : start + EMBED_BATCH_SIZE])
                    pending.append((start, pool.submit(self._embed_batch, batch, deadline)))
                    offset += len(batch)
                start, future = pending.pop(0)
                yield start, future.result()

    def _embed_batch(self, texts: list[str], deadline: float) -> list[list[float]]:
        began = self._clock()
        for attempt in range(EMBED_RETRIES + 1):
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise EmbeddingError("hunt job deadline exceeded")
            try:
                response = self._client.post(
                    self.endpoint,
                    headers=self._headers,
                    json={"input": texts, "model": self.model},
                    timeout=min(self.timeout_seconds, remaining),
                )
            except httpx.HTTPError as exc:
                raise EmbeddingError(f"Pipeline embedding request failed: {exc}") from exc
            if response.status_code not in THROTTLE_STATUSES:
                return self._vectors(response, len(texts), began)
            self._record_throttle()
            wait = retry_after_seconds(response)
            wait = wait if wait is not None else min(EMBED_BACKOFF_SECONDS, 2**attempt)
            if attempt >= EMBED_RETRIES or self._clock() + wait >= deadline:
                raise EmbeddingError(
                    f"Pipeline embedding back-pressure budget exhausted ({response.status_code})"
                )
            self._record_retry(wait)
            self._sleep(wait)
        raise EmbeddingError("Pipeline embedding retry loop ended unexpectedly")

    def _vectors(self, response: httpx.Response, expected: int, began: float) -> list[list[float]]:
        try:
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            detail = response.text[:500]
            raise EmbeddingError(
                f"Pipeline embedding response failed ({response.status_code}): {detail}"
            ) from exc
        if not isinstance(body, Mapping):
            raise EmbeddingError("Pipeline embedding response is not an object")
        served = str(body.get("model") or self.model)
        if served != self.model:
            raise EmbeddingError(f"Pipeline served {served!r}, requested {self.model!r}")
        ordered = _ordered_vectors(body.get("data"), expected)
        with self._lock:
            self._stats["requests"] += 1
            self._stats["items"] += expected
            self._stats["batches"] += 1
            self._stats["seconds"] = round(float(self._stats["seconds"]) + self._clock() - began, 3)
        return ordered

    def _record_throttle(self) -> None:
        with self._lock:
            self._stats["throttles"] += 1

    def _record_retry(self, wait: float) -> None:
        with self._lock:
            self._stats["retries"] += 1
            self._stats["wait_seconds"] = round(float(self._stats["wait_seconds"]) + wait, 3)


def embedding_from_env() -> PipelineEmbeddingClient | None:
    """Build the Pipeline client from explicit route, model and key environment settings."""
    url = os.environ.get("PORTAL_HUNT_EMBEDDING_URL")
    model = os.environ.get("PORTAL_HUNT_EMBEDDING_MODEL")
    key_name = os.environ.get("PORTAL_HUNT_EMBEDDING_KEY_ENV", "PIPELINE_API_KEY")
    api_key = os.environ.get(key_name)
    if not url or not model or not api_key:
        return None
    return PipelineEmbeddingClient(url=url, model=model, api_key=api_key)


def embedding_requirement() -> str:
    """Return the environment settings required to call the local Pipeline."""
    return (
        "set PORTAL_HUNT_EMBEDDING_URL to the Pipeline route, "
        "PORTAL_HUNT_EMBEDDING_MODEL to its accepted model, and the key variable named by "
        "PORTAL_HUNT_EMBEDDING_KEY_ENV (default PIPELINE_API_KEY)"
    )


def embed_batches(embedder: Any, texts: Sequence[str]) -> Iterator[tuple[int, list[list[float]]]]:
    """Use a bounded streaming interface when available and keep small test clients simple."""
    method = getattr(embedder, "embed_batches", None)
    if callable(method):
        yield from method(texts)
    elif texts:
        yield 0, embedder.embed(texts)
