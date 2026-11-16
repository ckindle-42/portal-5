"""POST /v1/embeddings — OpenAI-compatible embeddings through the platform embedder.

The Pipeline forwards, bounds and records; it owns no vectors, applies no prefixes and
holds no conversation state. Model, URL, accepted aliases and limits come from the
``platform_embedder`` block of ``config/backends.yaml`` — the same operator-owned file
and env expansion the backends are found through.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse

from portal.platform.embedding.contract import MRL_DIMS
from portal.platform.inference.cluster_backends import DEFAULT_CONFIG_PATH, _expand_env
from portal.platform.inference.router import metrics
from portal.platform.inference.router.auth import _verify_key
from portal.platform.inference.router.concurrency import _SEMAPHORE_TIMEOUT

logger = logging.getLogger(__name__)

#: Upstream surface: EG2's raw OpenAI-compatible passthrough (no task prefixes applied).
UPSTREAM_PATH = "/v1/embeddings"
_DEFAULT_MAX_BATCH = 64
_DEFAULT_MAX_INPUT_CHARS = 8192
_DEFAULT_MAX_CONCURRENT = 4
_DEFAULT_TIMEOUT_S = 120.0


@dataclass(frozen=True)
class EmbedderConfig:
    """The configured platform embedder: what is accepted, and the bounds served."""

    model: str
    url: str
    aliases: tuple[str, ...]
    max_batch: int
    max_input_chars: int
    max_concurrent: int
    timeout_s: float

    @property
    def accepted_models(self) -> tuple[str, ...]:
        return (self.model, *self.aliases)


_CONFIG: tuple[str, EmbedderConfig | None] | None = None
_SEMAPHORE: asyncio.Semaphore | None = None
_SEMAPHORE_LIMIT = 0


def _positive_int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _read_config(path: str) -> EmbedderConfig | None:
    """Parse ``platform_embedder`` from a backends config, env placeholders expanded."""
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("platform embedder config unreadable (%s): %s", path, exc)
        return None
    block = _expand_env(raw.get("platform_embedder")) if isinstance(raw, dict) else None
    if not isinstance(block, dict):
        return None
    model = str(block.get("model") or "").strip()
    url = str(block.get("url") or "").strip().rstrip("/")
    if not model or not url:
        logger.warning("platform_embedder needs model: and url: in %s", path)
        return None
    aliases = tuple(
        str(alias).strip() for alias in block.get("aliases") or [] if str(alias).strip()
    )
    try:
        timeout_s = float(block.get("timeout_s") or _DEFAULT_TIMEOUT_S)
    except (TypeError, ValueError):
        timeout_s = _DEFAULT_TIMEOUT_S
    return EmbedderConfig(
        model=model,
        url=url,
        aliases=aliases,
        max_batch=_positive_int(block.get("max_batch"), _DEFAULT_MAX_BATCH),
        max_input_chars=_positive_int(block.get("max_input_chars"), _DEFAULT_MAX_INPUT_CHARS),
        max_concurrent=_positive_int(block.get("max_concurrent"), _DEFAULT_MAX_CONCURRENT),
        timeout_s=timeout_s if timeout_s > 0 else _DEFAULT_TIMEOUT_S,
    )


def load_embedder_config(path: str | Path | None = None) -> EmbedderConfig | None:
    """The configured platform embedder, cached per config path; ``None`` when undeclared."""
    global _CONFIG
    source = str(path or DEFAULT_CONFIG_PATH)
    if _CONFIG is not None and _CONFIG[0] == source:
        return _CONFIG[1]
    config = _read_config(source)
    _CONFIG = (source, config)
    return config


def _admission(config: EmbedderConfig) -> asyncio.Semaphore:
    """Embeddings' own semaphore: a batch never takes a chat slot, chat never takes one of ours."""
    global _SEMAPHORE, _SEMAPHORE_LIMIT
    if _SEMAPHORE is None or config.max_concurrent != _SEMAPHORE_LIMIT:
        _SEMAPHORE = asyncio.Semaphore(config.max_concurrent)
        _SEMAPHORE_LIMIT = config.max_concurrent
        logger.info("Embeddings semaphore created: limit=%d", config.max_concurrent)
    return _SEMAPHORE


def _requested_model(body: dict[str, Any], config: EmbedderConfig) -> str:
    """The caller's ``model`` (defaulting to the configured one) after validating it."""
    model = body.get("model") or config.model
    if not isinstance(model, str) or model not in config.accepted_models:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unknown embedding model {model!r}; this Pipeline accepts "
                f"{list(config.accepted_models)}"
            ),
        )
    return model


def _inputs(body: dict[str, Any], config: EmbedderConfig) -> list[str]:
    """``input`` as a bounded list of non-empty strings."""
    raw = body.get("input")
    if isinstance(raw, str):
        inputs = [raw]
    elif isinstance(raw, list) and raw and all(isinstance(item, str) for item in raw):
        inputs = list(raw)
    else:
        raise HTTPException(
            status_code=400,
            detail="input must be a non-empty string or a non-empty array of strings",
        )
    if len(inputs) > config.max_batch:
        raise HTTPException(
            status_code=413,
            detail=f"input has {len(inputs)} items; this Pipeline accepts at most "
            f"{config.max_batch} per request",
        )
    for index, text in enumerate(inputs):
        if not text.strip():
            raise HTTPException(status_code=400, detail=f"input[{index}] is empty")
        if len(text) > config.max_input_chars:
            raise HTTPException(
                status_code=413,
                detail=f"input[{index}] has {len(text)} characters; at most "
                f"{config.max_input_chars} are accepted",
            )
    return inputs


def _dimensions(body: dict[str, Any]) -> int | None:
    """Optional Matryoshka ``dimensions``; anything else is a typed 400."""
    value = body.get("dimensions")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value not in MRL_DIMS:
        raise HTTPException(status_code=400, detail=f"dimensions must be one of {list(MRL_DIMS)}")
    return int(value)


def _checked(body: dict[str, Any], config: EmbedderConfig) -> tuple[str, list[str], int | None]:
    """Validate one OpenAI embeddings body; returns (model, inputs, dimensions)."""
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")
    if body.get("encoding_format") not in (None, "float"):
        raise HTTPException(status_code=400, detail="encoding_format must be 'float'")
    return (
        _requested_model(body, config),
        _inputs(body, config),
        _dimensions(body),
    )


def _fail(outcome: str) -> None:
    metrics._embeddings_requests_total.labels(outcome=outcome).inc()


async def _post_upstream(config: EmbedderConfig, payload: dict[str, Any]) -> dict[str, Any]:
    """Forward one batch; every failure becomes a typed status, never an empty 200."""
    try:
        async with httpx.AsyncClient(timeout=config.timeout_s) as client:
            response = await client.post(f"{config.url}{UPSTREAM_PATH}", json=payload)
    except httpx.TimeoutException as exc:
        _fail("timeout")
        raise HTTPException(
            status_code=504,
            detail=f"platform embedder did not answer within {config.timeout_s:.0f}s",
            headers={"Retry-After": "5"},
        ) from exc
    except httpx.HTTPError as exc:
        _fail("unreachable")
        raise HTTPException(
            status_code=503,
            detail=f"platform embedder unreachable at {config.url}: {exc}",
            headers={"Retry-After": "5"},
        ) from exc
    if response.status_code == 503:
        _fail("not_ready")
        raise HTTPException(
            status_code=503,
            detail="platform embedder is not ready (model still loading)",
            headers={"Retry-After": "30"},
        )
    if response.status_code != 200:
        _fail("upstream_error")
        raise HTTPException(
            status_code=502,
            detail=f"platform embedder HTTP {response.status_code}: {response.text[:300]}",
        )
    try:
        data = response.json()
    except ValueError as exc:
        _fail("upstream_error")
        raise HTTPException(
            status_code=502, detail="platform embedder returned a non-JSON body"
        ) from exc
    if not isinstance(data, dict):
        _fail("upstream_error")
        raise HTTPException(status_code=502, detail="platform embedder returned a non-object body")
    return data


def _checked_vectors(data: dict[str, Any], count: int, dimensions: int | None) -> list[list[float]]:
    """The upstream vectors, or a typed 502 — never a 200 carrying empty or short vectors."""
    rows = data.get("data")
    if not isinstance(rows, list) or len(rows) != count:
        _fail("malformed")
        raise HTTPException(
            status_code=502,
            detail=f"platform embedder returned {len(rows) if isinstance(rows, list) else 0} "
            f"embeddings for {count} inputs",
        )
    vectors: list[list[float]] = []
    for row in rows:
        vector = row.get("embedding") if isinstance(row, dict) else None
        if (
            not isinstance(vector, list)
            or not vector
            or len(vector) not in MRL_DIMS
            or (dimensions is not None and len(vector) != dimensions)
        ):
            _fail("malformed")
            raise HTTPException(
                status_code=502, detail="platform embedder returned a malformed embedding vector"
            )
        vectors.append([float(value) for value in vector])
    return vectors


def _completion(model: str, vectors: list[list[float]]) -> dict[str, Any]:
    """OpenAI embeddings response; usage is zero because the Pipeline has no tokenizer."""
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": index, "embedding": vector}
            for index, vector in enumerate(vectors)
        ],
        "model": model,
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }


async def embeddings(request: Request, authorization: str | None = Header(None)) -> Any:
    """POST /v1/embeddings — forward one bounded batch to the platform embedder."""
    _verify_key(authorization)
    config = load_embedder_config()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail="Platform embedder is not configured (config/backends.yaml platform_embedder)",
        )
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from None
    model, inputs, dimensions = _checked(body, config)

    semaphore = _admission(config)
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=_SEMAPHORE_TIMEOUT)
    except TimeoutError:
        _fail("busy")
        raise HTTPException(
            status_code=429,
            detail=f"Embeddings at concurrency limit ({config.max_concurrent}). Please retry.",
            headers={"Retry-After": "1"},
        ) from None

    payload: dict[str, Any] = {"model": model, "input": inputs}
    if dimensions is not None:
        payload["dimensions"] = dimensions
    started = time.monotonic()
    try:
        data = await _post_upstream(config, payload)
        vectors = _checked_vectors(data, len(inputs), dimensions)
    except HTTPException:
        metrics._embeddings_seconds.labels(outcome="error").observe(time.monotonic() - started)
        raise
    finally:
        semaphore.release()
    elapsed = time.monotonic() - started
    metrics._embeddings_requests_total.labels(outcome="ok").inc()
    metrics._embeddings_items_total.labels(model=model).inc(len(vectors))
    metrics._embeddings_seconds.labels(outcome="ok").observe(elapsed)
    logger.info(
        "embeddings: model=%s items=%d dim=%s seconds=%.3f",
        model,
        len(vectors),
        len(vectors[0]),
        elapsed,
    )
    return JSONResponse(content=_completion(model, vectors))
