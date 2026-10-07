#!/usr/bin/env python3
"""Portal 5 — EmbeddingGemma 2 platform embedding service (:8946).

TASK_EMBEDDINGGEMMA2_PLATFORM_V1. One embedder for every consumer: text, code,
images, audio and video in one 768-d space with Matryoshka truncation.

Surfaces (all on one port):

* ``GET  /health``        liveness, never loads the model.
* ``GET  /ready``         loads the model, runs the readiness probes (NaN-free,
                          prefix asymmetry, Matryoshka renormalization) and
                          returns the served ``identity``. 503 until all pass.
* ``POST /embed``         Portal contract: ``{inputs:[{text,title?}], task, role, dim}``.
                          Prefixes are applied HERE from ``portal.platform.embedding.contract``.
* ``POST /embed_items``   Portal contract, multimodal items (text/image/audio/video).
* ``POST /v1/embeddings`` OpenAI-compatible, RAW passthrough (callers such as Open
                          WebUI apply their own configured prefixes). ``dimensions``
                          selects a Matryoshka dim. A request naming a ``model`` other
                          than the served model (or a configured alias) is REJECTED
                          (409) — never silently answered from a different space.
* ``POST /v1/rerank``     Open WebUI external-reranker contract, forwarded to the
                          Qwen3-VL reranker (``VL_UPSTREAM_URL``); EG2 does not rerank.
* ``/vl/*``               VL-retrieval-compatible surface (``/vl/health``, ``/vl/ready``,
                          ``/vl/embed``, ``/vl/embed_batch``, ``/vl/rerank``) so the
                          retrieval seam (``portal.platform.retrieval.embedding``) can
                          be pointed here by env alone for shadow measurement.

Runs host-native in its own venv (``~/.portal5/eg2-venv``), never the project
``.venv`` (the fragile MLX runtime behind drift gate D1 stays untouched).
Precision: bfloat16 or float32 only — float16 NaNs this model (model card).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import math
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Protocol

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from portal.platform.embedding import contract as ec  # noqa: E402

MODEL_ID = os.environ.get("EG2_MODEL", "google/embeddinggemma-2")
MODEL_ALIASES = {
    a.strip() for a in os.environ.get("EG2_MODEL_ALIASES", "").split(",") if a.strip()
} | {MODEL_ID}
MODALITIES = tuple(
    m.strip()
    for m in os.environ.get("EG2_MODALITIES", "text,image,audio,video").split(",")
    if m.strip()
)
VL_UPSTREAM_URL = os.environ.get("VL_UPSTREAM_URL", "http://localhost:8942").rstrip("/")
VL_COMPAT_DIM = int(os.environ.get("EG2_VL_DIM", "768"))
MAX_BATCH = max(1, int(os.environ.get("EG2_MAX_BATCH", "32")))
STRICT_MODEL = os.environ.get("EG2_STRICT_MODEL", "1") != "0"


class Backend(Protocol):
    def identity(self) -> ec.Identity: ...
    def encode_texts(self, texts: list[str]) -> list[list[float]]: ...
    def encode_items(self, items: list[dict[str, Any]]) -> list[list[float]]: ...


def _config_kwargs(modalities: tuple[str, ...]) -> dict[str, Any]:
    """Selective encoder loading (model card "Selective Encoder Loading").
    Video rides the vision encoder."""
    kw: dict[str, Any] = {}
    if "image" not in modalities and "video" not in modalities:
        kw["vision_config"] = None
    if "audio" not in modalities:
        kw["audio_config"] = None
    return kw


class SentenceTransformersBackend:
    """sentence-transformers (>= 6.1.0, per the model card) on MPS/bf16 or CPU/fp32."""

    def __init__(self, model_id: str, modalities: tuple[str, ...]) -> None:
        import torch
        from sentence_transformers import SentenceTransformer

        if torch.backends.mps.is_available():
            device = "mps"
            dtype = (
                torch.bfloat16 if os.environ.get("EG2_DTYPE", "bf16") == "bf16" else torch.float32
            )
        else:
            device, dtype = "cpu", torch.float32
        if dtype == torch.float16:  # belt and braces: the card forbids it
            raise RuntimeError("float16 is forbidden for EmbeddingGemma 2 (NaN/degraded output)")
        self._model = SentenceTransformer(
            model_id,
            device=device,
            model_kwargs={"torch_dtype": dtype},
            config_kwargs=_config_kwargs(modalities),
        )
        self._identity = ec.Identity(
            model=model_id,
            revision=_resolve_revision(model_id),
            native_dim=ec.NATIVE_DIM,
            dtype=str(dtype).replace("torch.", ""),
            device=device,
            backend="sentence-transformers",
            modalities=modalities,
        )

    def identity(self) -> ec.Identity:
        return self._identity

    def encode_texts(self, texts: list[str]) -> list[list[float]]:
        out = self._model.encode(
            texts, batch_size=MAX_BATCH, normalize_embeddings=True, convert_to_numpy=True
        )
        return [list(map(float, row)) for row in out]

    def encode_items(self, items: list[dict[str, Any]]) -> list[list[float]]:
        rows = []
        for it in items:
            v = self._model.encode(
                _to_st_input(it), normalize_embeddings=True, convert_to_numpy=True
            )
            rows.append(list(map(float, v)))
        return rows


def _to_st_input(item: dict[str, Any]) -> Any:
    """Map one Portal item to sentence-transformers' multimodal input.

    VERIFY-AGAINST-INSTALLED-SOURCE (task Phase 2.4): this follows the model
    card's interleaving example (placeholder tokens in ``text`` filled in order
    from the ``image``/``audio``/``video`` keys). If the installed
    sentence-transformers documents a different canonical form for single-media
    inputs, this is the ONE function to change.
    """
    if not any(k in item for k in ("image", "audio", "video")):
        return item["text"]
    parts: list[str] = []
    payload: dict[str, Any] = {}
    if item.get("text"):
        parts.append(item["text"])
    for key, token in (("image", "<|image|>"), ("video", "<|video|>"), ("audio", "<|audio|>")):
        if key in item:
            parts.append(token)
            payload[key] = [item[key]] if key == "image" else item[key]
    payload["text"] = " ".join(parts)
    return payload


def _resolve_revision(model_id: str) -> str:
    try:
        from huggingface_hub import snapshot_download

        return Path(snapshot_download(model_id, local_files_only=True)).name
    except Exception:  # noqa: BLE001 - identity must never block serving; recorded as unknown
        return "unknown"


# ── state ───────────────────────────────────────────────────────────────────
_backend: Backend | None = None
_backend_factory: Any = None
_lock = asyncio.Lock()
_ready_report: dict[str, Any] | None = None
_STATS = {"requests": 0, "items": 0, "errors": 0, "started": time.time()}


def set_backend_factory(factory: Any) -> None:
    """Tests inject a fake backend factory; production uses sentence-transformers."""
    global _backend_factory, _backend, _ready_report
    _backend_factory, _backend, _ready_report = factory, None, None


async def _get_backend() -> Backend:
    global _backend
    if _backend is None:
        factory = _backend_factory or (lambda: SentenceTransformersBackend(MODEL_ID, MODALITIES))
        _backend = await asyncio.to_thread(factory)
    return _backend


def _finish(vecs: list[list[float]], dim: int) -> list[list[float]]:
    out = []
    for v in vecs:
        if ec.has_nan(v):
            raise ValueError("model produced NaN/Inf — check dtype (bf16/fp32 only)")
        out.append(ec.truncate(v, dim) if dim != len(v) else ec.l2_normalize(v))
    return out


async def _encode_texts(texts: list[str], dim: int) -> list[list[float]]:
    b = await _get_backend()
    vecs: list[list[float]] = []
    async with _lock:
        for i in range(0, len(texts), MAX_BATCH):
            vecs.extend(await asyncio.to_thread(b.encode_texts, texts[i : i + MAX_BATCH]))
    return _finish(vecs, dim)


async def _encode_items(items: list[dict[str, Any]], dim: int) -> list[list[float]]:
    b = await _get_backend()
    async with _lock:
        vecs = await asyncio.to_thread(b.encode_items, items)
    return _finish(vecs, dim)


def _decode_b64(data: str, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as fh:
        fh.write(base64.b64decode(data))
    return path


def _prepare_item(
    obj: dict[str, Any], task: ec.Task, role: ec.Role
) -> tuple[dict[str, Any], list[str]]:
    """Portal/VL transport item -> backend item. Text-only items get the
    contract prefix; media items are embedded raw (text, if any, interleaved)."""
    tmp: list[str] = []
    item: dict[str, Any] = {}
    for key, ext in (("image", ".png"), ("audio", ".wav"), ("video", ".mp4")):
        b64 = obj.get(f"{key}_b64")
        path = obj.get(f"{key}_path") or (obj.get(key) if isinstance(obj.get(key), str) else None)
        if b64:
            p = _decode_b64(b64, ext)
            tmp.append(p)
            item[key] = p
        elif path:
            if not Path(path).is_file():
                raise ValueError(f"{key} not found: {path}")
            if key not in MODALITIES:
                raise ValueError(
                    f"{key} encoder not loaded (EG2_MODALITIES={','.join(MODALITIES)})"
                )
            item[key] = path
    text = (obj.get("text") or "").strip()
    if text:
        has_media = any(k in item for k in ("image", "audio", "video"))
        item["text"] = text if has_media else ec.format_text(text, task, role, obj.get("title"))
    if not item:
        raise ValueError("item has no text, image, audio or video")
    return item, tmp


# ── app ─────────────────────────────────────────────────────────────────────
app = FastAPI(title="portal5-eg2-embedding")


def _err(status: int, msg: str) -> JSONResponse:
    _STATS["errors"] += 1
    return JSONResponse({"error": msg}, status_code=status)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "eg2-embedding",
        "model": MODEL_ID,
        "modalities": list(MODALITIES),
        "loaded": _backend is not None,
        "ready": bool(_ready_report and _ready_report.get("ready")),
    }


@app.get("/stats")
async def stats() -> dict[str, Any]:
    return {**_STATS, "uptime_s": round(time.time() - _STATS["started"], 1)}


async def _readiness() -> dict[str, Any]:
    probe = "The breaker tripped on overcurrent at the substation."
    checks: dict[str, Any] = {}
    b = await _get_backend()
    ident = b.identity()
    q, d = await _encode_texts(
        [
            ec.format_text(probe, ec.Task.SEARCH, ec.Role.QUERY),
            ec.format_text(probe, ec.Task.SEARCH, ec.Role.DOCUMENT),
        ],
        ec.NATIVE_DIM,
    )
    checks["native_dim"] = len(q) == ec.NATIVE_DIM
    checks["nan_free"] = not (ec.has_nan(q) or ec.has_nan(d))
    # Asymmetric prefixes must yield measurably different vectors for the same
    # text — if they don't, prefixes are not reaching the model.
    asym = ec.cosine(q, d)
    checks["prefix_asymmetry"] = asym < 0.999
    t = ec.truncate(q, 256)
    checks["mrl_renormalized"] = abs(math.sqrt(sum(x * x for x in t)) - 1.0) < 1e-6
    ok = all(bool(v) for v in checks.values())
    return {
        "ready": ok,
        "identity": ident.to_dict(),
        "version_tag": ident.version_tag(),
        "checks": checks,
        "prefix_asymmetry_cosine": round(asym, 6),
    }


@app.get("/ready")
async def ready() -> JSONResponse:
    global _ready_report
    try:
        _ready_report = await _readiness()
        return JSONResponse(_ready_report, status_code=200 if _ready_report["ready"] else 503)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ready": False, "error": f"{type(e).__name__}: {e}"}, status_code=503)


def _dim(value: Any) -> int:
    dim = int(value or ec.NATIVE_DIM)
    if dim not in ec.MRL_DIMS:
        raise ValueError(f"dim {dim} not in {ec.MRL_DIMS}")
    return dim


@app.post("/embed")
async def embed(req: dict[str, Any]) -> Any:
    try:
        task, role, dim = (
            ec.parse_task(req.get("task", "search result")),
            ec.parse_role(req.get("role", "query")),
            _dim(req.get("dim")),
        )
        inputs = req.get("inputs") or []
        texts = [ec.format_text(str(i["text"]), task, role, i.get("title")) for i in inputs]
        vecs = await _encode_texts(texts, dim)
    except (ValueError, KeyError) as e:
        return _err(400, str(e))
    _STATS["requests"] += 1
    _STATS["items"] += len(vecs)
    b = await _get_backend()
    return {
        "embeddings": vecs,
        "dim": dim,
        "model": MODEL_ID,
        "version": b.identity().version_tag(dim),
    }


@app.post("/embed_items")
async def embed_items(req: dict[str, Any]) -> Any:
    tmp: list[str] = []
    try:
        task, role, dim = (
            ec.parse_task(req.get("task", "search result")),
            ec.parse_role(req.get("role", "document")),
            _dim(req.get("dim")),
        )
        items = []
        for obj in req.get("items") or []:
            it, t = _prepare_item(obj, task, role)
            items.append(it)
            tmp.extend(t)
        vecs = await _encode_items(items, dim)
    except (ValueError, KeyError) as e:
        return _err(400, str(e))
    finally:
        for p in tmp:
            with contextlib.suppress(OSError):
                os.unlink(p)
    _STATS["requests"] += 1
    _STATS["items"] += len(vecs)
    b = await _get_backend()
    return {
        "embeddings": vecs,
        "dim": dim,
        "model": MODEL_ID,
        "version": b.identity().version_tag(dim),
    }


@app.post("/v1/embeddings")
async def openai_embeddings(req: dict[str, Any]) -> Any:
    asked = req.get("model")
    if STRICT_MODEL and asked and asked not in MODEL_ALIASES:
        return _err(
            409,
            f"this service serves {MODEL_ID!r}; request named {asked!r} (different vector space)",
        )
    raw = req.get("input")
    texts = [raw] if isinstance(raw, str) else [str(x) for x in (raw or [])]
    try:
        vecs = await _encode_texts(texts, _dim(req.get("dimensions")))
    except ValueError as e:
        return _err(400, str(e))
    _STATS["requests"] += 1
    _STATS["items"] += len(vecs)
    return {
        "object": "list",
        "model": MODEL_ID,
        "data": [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vecs)],
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }


async def _vl_rerank(query: Any, documents: list[Any], top_n: int | None) -> list[dict[str, Any]]:
    q = query if isinstance(query, dict) else {"text": str(query)}
    docs = [d if isinstance(d, dict) else {"text": str(d)} for d in documents]
    async with httpx.AsyncClient(timeout=300) as c:
        r = await c.post(
            f"{VL_UPSTREAM_URL}/rerank", json={"query": q, "documents": docs, "top_n": top_n}
        )
        r.raise_for_status()
        results: list[dict[str, Any]] = r.json()["results"]
        return results


@app.post("/v1/rerank")
async def owui_rerank(req: dict[str, Any]) -> Any:
    """Open WebUI ``RAG_RERANKING_ENGINE=external`` contract:
    ``{model, query, documents:[str], top_n}`` -> ``{results:[{index, relevance_score}]}``."""
    try:
        res = await _vl_rerank(
            req.get("query", ""), list(req.get("documents") or []), req.get("top_n")
        )
    except (httpx.HTTPError, KeyError, ValueError) as e:
        return _err(502, f"VL reranker upstream failed: {e}")
    return {"results": [{"index": r["index"], "relevance_score": r["score"]} for r in res]}


# ── VL-compatible surface (shadow measurement of RAG + compliance) ──────────
@app.get("/vl/health")
async def vl_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "eg2-vl-compat",
        "embed_model": f"{MODEL_ID}:{VL_COMPAT_DIM}d",
        "rerank_model": f"upstream:{VL_UPSTREAM_URL}",
        "embedding_dim": VL_COMPAT_DIM,
    }


@app.get("/vl/ready")
async def vl_ready() -> JSONResponse:
    r = await ready()
    body = dict(_ready_report or {})
    return JSONResponse(
        {
            "ready": bool(body.get("ready")),
            "embed_model": f"{MODEL_ID}:{VL_COMPAT_DIM}d",
            "dim": VL_COMPAT_DIM,
        },
        status_code=r.status_code,
    )


async def _vl_embed(objs: list[dict[str, Any]]) -> list[list[float]]:
    tmp: list[str] = []
    try:
        items = []
        for o in objs:
            role = ec.Role.QUERY if o.get("is_query") else ec.Role.DOCUMENT
            it, t = _prepare_item(o, ec.Task.SEARCH, role)
            items.append(it)
            tmp.extend(t)
        return await _encode_items(items, VL_COMPAT_DIM)
    finally:
        for p in tmp:
            with contextlib.suppress(OSError):
                os.unlink(p)


@app.post("/vl/embed")
async def vl_embed(req: dict[str, Any]) -> Any:
    try:
        vec = (await _vl_embed([req]))[0]
    except ValueError as e:
        return _err(400, str(e))
    return {"embedding": vec, "dim": len(vec)}


@app.post("/vl/embed_batch")
async def vl_embed_batch(req: dict[str, Any]) -> Any:
    try:
        vecs = await _vl_embed(list(req.get("items") or []))
    except ValueError as e:
        return _err(400, str(e))
    return {"embeddings": vecs, "dim": len(vecs[0]) if vecs else 0, "count": len(vecs)}


@app.post("/vl/rerank")
async def vl_rerank(req: dict[str, Any]) -> Any:
    try:
        return {
            "results": await _vl_rerank(
                req.get("query", ""), list(req.get("documents") or []), req.get("top_n")
            )
        }
    except (httpx.HTTPError, KeyError, ValueError) as e:
        return _err(502, f"VL reranker upstream failed: {e}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Portal 5 EmbeddingGemma 2 service")
    ap.add_argument("--host", default=os.environ.get("EG2_HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("EG2_PORT", "8946")))
    a = ap.parse_args()
    uvicorn.run(app, host=a.host, port=a.port, log_level="info")


if __name__ == "__main__":
    main()
