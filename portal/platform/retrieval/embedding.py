"""VL retrieval-server client stage — moved verbatim from ``rag_multimodal``
(SEAM V1 P3).

Embedding + rerank + live-model identity against the Qwen3-VL retrieval server
(:8942). Single-flight discipline, the ``_MODEL_ID_CACHE`` TTL, the dim guard,
and the ``VLUnavailableError`` → 503 / everything-else → 500 error mapping are
all preserved. ``rag_multimodal`` keeps thin aliases for the transition.
"""

from __future__ import annotations

import contextlib
import os
import time

import httpx

VL_URL = os.environ.get("VL_RETRIEVAL_URL", "http://localhost:8942")
VL_DIM = int(os.environ.get("VL_EMBEDDING_DIM", "2048"))
VL_EMBED_MAX_ITEMS = max(1, int(os.environ.get("VL_EMBED_MAX_ITEMS", "24")))

_MODEL_ID_CACHE: dict = {"value": None, "at": 0.0}
_MODEL_ID_TTL = float(os.environ.get("VL_MODEL_ID_TTL", "300"))


class VLUnavailableError(Exception):
    """The VL retrieval server is not serving a working model (see :8942/ready)."""


def vl_error(exc: Exception) -> VLUnavailableError:
    detail = str(exc)
    if isinstance(exc, httpx.HTTPStatusError):
        with contextlib.suppress(Exception):
            detail = exc.response.json().get("error", exc.response.text)
    return VLUnavailableError(f"VL retrieval server unavailable: {detail} (check {VL_URL}/ready)")


async def vl_model_id() -> tuple[str, int]:
    """(embed_model, dim) the live VL server is serving. `vl_embed_batch`
    already guards dim; this catches a same-dim different-model swap (the `-6bit`
    flavour, a re-conversion, a changed VL_EMBED_MODEL default) that stored
    vectors and live queries would otherwise silently occupy different spaces.

    Cached for VL_MODEL_ID_TTL seconds: the model cannot change within a run
    without a server restart, and `/health` shares the server's single-threaded
    event loop with `model.process()` — probing it on every kb_search would
    stall behind an in-flight embed/rerank. `timeout` is generous for the same
    reason."""
    now = time.time()
    if _MODEL_ID_CACHE["value"] and now - _MODEL_ID_CACHE["at"] < _MODEL_ID_TTL:
        return _MODEL_ID_CACHE["value"]
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.get(f"{VL_URL}/health")
            r.raise_for_status()
            j = r.json()
        val = (str(j.get("embed_model", "?")), int(j.get("embedding_dim", VL_DIM)))
    except (httpx.HTTPError, ValueError) as e:
        raise vl_error(e) from e
    _MODEL_ID_CACHE.update(value=val, at=now)
    return val


async def vl_embed_batch(items: list[dict]) -> list[list[float]]:
    """items: list of {text?, image_path?, is_query?}. Instruction is applied
    server-side for is_query items only; chunk/page items carry none."""
    if not items:
        return []
    # Cap the POST body: a whole document's chunks (or every page image) in one
    # request is unbounded by construction. Split into <= VL_EMBED_MAX_ITEMS
    # requests, issued sequentially (the server serialises on one lock anyway),
    # and concatenate in order. The server also sub-chunks at VL_MAX_BATCH — the
    # two bounds are independent (request size vs. forward-pass memory).
    vecs: list[list[float]] = []
    try:
        async with httpx.AsyncClient(timeout=180) as c:
            for start in range(0, len(items), VL_EMBED_MAX_ITEMS):
                batch = items[start : start + VL_EMBED_MAX_ITEMS]
                r = await c.post(f"{VL_URL}/embed_batch", json={"items": batch})
                r.raise_for_status()
                vecs.extend(r.json()["embeddings"])
    except httpx.HTTPError as e:
        raise vl_error(e) from e
    for v in vecs:
        if len(v) != VL_DIM:
            raise VLUnavailableError(f"VL embedding dim {len(v)} != VL_EMBEDDING_DIM {VL_DIM}")
    return vecs


async def vl_embed(text: str | None = None, image_path: str | None = None, is_query: bool = False):
    item: dict = {"is_query": is_query}
    if text:
        item["text"] = text
    if image_path:
        item["image_path"] = image_path
    return (await vl_embed_batch([item]))[0]


async def vl_rerank(query: str, candidates: list, top_n: int) -> list:
    """candidates: list of {text?, image_path?}. One call; the server chunks it
    at VL_RERANK_CHUNK. Returns [{index, score}] ordered best-first."""
    try:
        async with httpx.AsyncClient(timeout=300) as c:
            r = await c.post(
                f"{VL_URL}/rerank",
                json={"query": {"text": query}, "documents": candidates, "top_n": top_n},
            )
            r.raise_for_status()
            return r.json()["results"]
    except httpx.HTTPError as e:
        raise vl_error(e) from e
