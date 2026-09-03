"""Portal 5 — Qwen3-VL retrieval server (embedding + rerank, text & image).

One joint text+image space for the RAG stack's *retrieval* path. The shared text
embedder (:8917) and reranker (:8925) stay up for other subsystems (memory, the
Bully ORG projection).

Usage: python3 scripts/vl-retrieval-server.py --port 8942

Runtime (TASK_VL_RUNTIME_LANDING_V4): served by mlx-embeddings >=0.1.0's
`qwen3_vl` module. Loads once transformers 5.x's torchvision-backed `vision`
backend is importable (torchvision is a declared apple-silicon dep purely to
satisfy that class-level gate on `AutoImageProcessor`; preprocessing itself runs
on the PIL path — `Qwen2VLImageProcessorPil` — so the torchvision version is
inert to output). Video is NOT supported on this runtime
(`_UnsupportedVideoProcessor.__call__` raises).

Verified Qwen3-VL API (mlx_embeddings/models/qwen3_vl/{model,processor}.py):
  * `model.process(list_of_items, processor=p)`      -> embed  -> mx (N, dim)
  * `model.process({"query":..,"documents":[..]}, p)` -> rerank -> mx (N,)
  * embedding item keys: instruction, text, image, video, fps, max_frames
    (NOT image_path / image_b64 — those are transport, mapped to `image` here)
  * an item with no content is silently embedded as the literal "NULL" — the
    server rejects such items instead of relying on the library
  * instruction goes on the QUERY only; documents/chunks fall back to
    DEFAULT_EMBEDDING_INSTRUCTION (getting this wrong degrades retrieval silently)
  * pooling is last-non-padding-token; `text_embeds` is already normalized when
    `model.args.normalize` is True — read it at load, never double-normalize
  * rerank scores are sigmoid(logit[yes]-logit[no]) in (0,1); 0.5 == undecided
  * `_prepare_from_conversations` pads to the longest batch member, so text items
    and image items are embedded in SEPARATE batches
  * rerank builds one VLM forward per document — chunked at VL_RERANK_CHUNK

Threading (TASK_VL_RETRIEVAL_HARDENING_AND_CLOSEOUT_V2, O2/A4): one asyncio.Lock
serialises every model call AND every MLX touch runs on a single persistent
worker thread (`_mx_pool`, max_workers=1) via `_run_mx`. The precedent that
banned `run_in_executor` here (mlx-speech.py / reranker_mcp.py) was a
*multi-worker* pool — concurrent Metal command-buffer encoding is what crashes
AGXG16XFamilyCommandBuffer. One worker keeps the same serialisation the inline
path had while freeing the event loop, which otherwise held the GIL through
`mx.eval` and blocked /health and /ready for the length of a rerank (measured
8-27 s). Set `VL_MX_EXECUTOR=0` to revert to the inline path.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import concurrent.futures
import contextlib
import os
import tempfile
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

EMBED_MODEL = os.environ.get("VL_EMBED_MODEL", "mlx-community/Qwen3-VL-Embedding-2B-mxfp8")
RERANK_MODEL = os.environ.get("VL_RERANK_MODEL", "mlx-community/Qwen3-VL-Reranker-2B-mxfp8")
EMBEDDING_DIM = int(os.environ.get("VL_EMBEDDING_DIM", "2048"))
RERANK_CHUNK = int(os.environ.get("VL_RERANK_CHUNK", "4"))
# One VLM forward per item, padded to the longest member. `_embed_items`
# sub-chunks each of the text/image batches at this bound, preserving order.
# A5 sweep (reports/runtime/HARDENING_V2_P4_MEASUREMENTS.md): 1..48 page images
# per forward on an M4 Pro 64GB with Ollama holding ~5.4GB — per-item latency
# flat at ~1.85s, no failure, no OOM at any size. RSS is not a usable pressure
# signal here (MLX Metal buffers are off-RSS). 24 is well below the tested-clean
# ceiling and still bounds the pathological case (a 500-page PDF -> 21 forwards
# of 24, not one 500-wide forward).
MAX_BATCH = max(1, int(os.environ.get("VL_MAX_BATCH", "24")))
# S1 (TASK_VL_RETRIEVAL_HARDENING_AND_CLOSEOUT_V2). MLX's buffer cache is not
# released back to the OS between requests; on a long-lived server it grows and
# per-call latency drifts up (ml-explore/mlx#1192, 10-24x throughput loss). Free
# the cache after every request's model calls, and optionally cap the cache /
# wired budget at startup. Sized from the S1 stress measurement.
MX_CLEAR_CACHE = os.environ.get("VL_MX_CLEAR_CACHE", "1") not in ("0", "false", "")
MX_CACHE_LIMIT_MB = int(os.environ.get("VL_MX_CACHE_LIMIT_MB", "0"))  # 0 == MLX default
QUERY_INSTRUCTION = os.environ.get(
    "VL_QUERY_INSTRUCTION", "Given a search query, retrieve relevant passages that answer it."
)

# tokenizer_config forwarded into arch.Processor.from_pretrained — pops
# max_pixels / min_pixels / embedding_max_length / reranking_max_length.
# retrieval.pages.render_pages renders US-Letter at dpi=150 == ~2.10M px, above
# the default MAX_PIXELS (1800*32*32 == 1.84M) — pages get silently downscaled.
# Raise the cap here (and lower the render DPI) coherently; measured in P8.
_TOKENIZER_CONFIG = {
    k: int(os.environ[e])
    for k, e in (
        ("max_pixels", "VL_MAX_PIXELS"),
        ("min_pixels", "VL_MIN_PIXELS"),
        ("embedding_max_length", "VL_EMBEDDING_MAX_LENGTH"),
        ("reranking_max_length", "VL_RERANKING_MAX_LENGTH"),
    )
    if os.environ.get(e)
}

app = FastAPI(title="portal5-vl-retrieval")
_lock = asyncio.Lock()
_embed: dict = {"model": None, "proc": None, "normalize": None}
_rerank: dict = {"model": None, "proc": None}
_REQUESTS_SERVED = 0
_INFLIGHT = 0  # O2/A4: model calls currently holding or waiting on _lock

# O2/A4: ONE persistent worker thread for every MLX touch. The precedent that
# banned `run_in_executor` here was a *multi-worker* pool — concurrent Metal
# command-buffer encoding is what crashes AGXG16XFamilyCommandBuffer. With
# max_workers=1 every mx call still happens on exactly one thread, in order, so
# the Metal stream sees the same serialisation it did inline; what changes is
# that the event loop is no longer the thread holding the GIL through mx.eval,
# so /health and /ready answer during a rerank. `_lock` is kept: it guards the
# lazy `_load()` state and preserves FIFO fairness across callers.
# `VL_MX_EXECUTOR=0` reverts to the inline path without a code change.
MX_EXECUTOR = os.environ.get("VL_MX_EXECUTOR", "1") not in ("0", "false", "")
_mx_pool: concurrent.futures.ThreadPoolExecutor | None = (
    concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="vl-mlx")
    if MX_EXECUTOR
    else None
)


async def _run_mx(fn, *args):
    """Run one MLX unit of work. On the single-worker pool when enabled, inline
    otherwise. Never call this with two units that must not interleave — the
    caller holds `_lock` for that."""
    if _mx_pool is None:
        return fn(*args)
    return await asyncio.get_running_loop().run_in_executor(_mx_pool, fn, *args)


# O1: recycle the process after this many model requests so the MLX runtime drift
# can never compound past one window (0 == never). launchd/keepalive restarts it.
MAX_REQUESTS = int(os.environ.get("VL_MAX_REQUESTS", "0"))


def _resolve_repo(repo: str) -> str:
    """mlx_embeddings.load() fetches a restrictive allow_patterns set that omits
    `chat_template.jinja`, and its download fallback is unreliable — the Qwen3-VL
    processor then dies with "this processor does not have a chat template".
    Pull the full snapshot first (a local dir is returned as-is)."""
    if os.path.isdir(repo):
        return repo
    from huggingface_hub import snapshot_download

    return snapshot_download(repo)


def _load(slot: dict, repo: str) -> tuple:
    if slot["model"] is None:
        from mlx_embeddings import load

        slot["model"], slot["proc"] = load(
            _resolve_repo(repo), tokenizer_config=dict(_TOKENIZER_CONFIG)
        )
        if "normalize" in slot:
            slot["normalize"] = bool(getattr(slot["model"].args, "normalize", True))
    return slot["model"], slot["proc"]


def _decode_b64_to_tempfile(b64: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".png")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(base64.b64decode(b64, validate=True))
    except (binascii.Error, ValueError):
        with contextlib.suppress(OSError):
            os.unlink(path)
        raise
    return path


def _item_from_transport(obj: dict, *, is_query: bool) -> tuple[dict, list[str]]:
    """Map a transport payload -> a verified Qwen3-VL item. Returns (item, tempfiles)."""
    item: dict = {}
    tempfiles: list[str] = []
    text = (obj.get("text") or "").strip()
    if text:
        item["text"] = text
    img_path = obj.get("image_path") or obj.get("image")
    if obj.get("image_b64"):
        p = _decode_b64_to_tempfile(obj["image_b64"])
        tempfiles.append(p)
        item["image"] = p
    elif img_path:
        if not Path(img_path).is_file():
            raise ValueError(f"image not found: {img_path}")
        item["image"] = img_path
    if is_query and "instruction" not in item:
        item["instruction"] = obj.get("instruction") or QUERY_INSTRUCTION
    if "text" not in item and "image" not in item:
        raise ValueError("item has neither text nor image")
    return item, tempfiles


def _reset_vl_state(model) -> None:
    """mlx-embeddings 0.1.0 / mlx-vlm 0.6.17: `compute_qwen3_vl_hidden_states`
    only clears `language_model._position_ids` / `._rope_deltas` when a call has
    pixel_values. Two consecutive text-only `process()` calls with different
    sequence lengths then crash with "Too many indices for array with 2
    dimensions". Clear the cached rope state before every call. See
    KNOWN_LIMITATIONS.md (TASK_VL_RUNTIME_LANDING_V4)."""
    seen = set()
    for obj in (
        model,
        getattr(model, "model", None),
        getattr(model, "language_model", None),
        getattr(getattr(model, "model", None), "language_model", None),
    ):
        if obj is None or id(obj) in seen:
            continue
        seen.add(id(obj))
        for attr in ("_position_ids", "_rope_deltas"):
            if hasattr(obj, attr):
                setattr(obj, attr, None)


def _mx_rows(out) -> list[list[float]]:
    import mlx.core as mx

    mx.eval(out)
    return [r.tolist() if hasattr(r, "tolist") else list(r) for r in out]


def _mx_after_request() -> None:
    """S1/O1: free MLX's buffer cache after each request, count it, and recycle
    the process past MAX_REQUESTS so runtime drift never compounds."""
    global _REQUESTS_SERVED
    _REQUESTS_SERVED += 1
    if MX_CLEAR_CACHE:
        with contextlib.suppress(Exception):
            import mlx.core as mx

            mx.clear_cache()
    if MAX_REQUESTS and _REQUESTS_SERVED >= MAX_REQUESTS:
        import sys

        print(f"[vl-retrieval] recycling after {_REQUESTS_SERVED} requests", flush=True)
        sys.stdout.flush()
        os._exit(0)  # noqa: SLF001 — a clean supervisor restart is the point


def _mx_mem() -> dict:
    with contextlib.suppress(Exception):
        import mlx.core as mx

        return {
            "active_mb": round(mx.get_active_memory() / 1e6),
            "cache_mb": round(mx.get_cache_memory() / 1e6),
            "peak_mb": round(mx.get_peak_memory() / 1e6),
        }
    return {}


@contextlib.asynccontextmanager
async def _model_lock():
    """O2/A4: `_lock` serialises every model call, so concurrent callers form a
    FIFO queue (measured: N reranks take N x single-call latency, all succeed).
    Track the depth so `/health` can surface it without touching the MLX runtime."""
    global _INFLIGHT
    _INFLIGHT += 1
    try:
        async with _lock:
            yield
    finally:
        _INFLIGHT -= 1


async def _embed_items(objs: list[dict]) -> list[list[float]]:
    """Embed a list of transport payloads. Text items and image items are run in
    separate batches (padding is to the longest batch member)."""
    prepared: list[tuple[int, dict]] = []
    tempfiles: list[str] = []
    try:
        for idx, obj in enumerate(objs):
            item, tf = _item_from_transport(obj, is_query=bool(obj.get("is_query")))
            tempfiles.extend(tf)
            prepared.append((idx, item))
        text_batch = [(i, it) for i, it in prepared if "image" not in it]
        image_batch = [(i, it) for i, it in prepared if "image" in it]

        def _work() -> dict[int, list[float]]:
            out: dict[int, list[float]] = {}
            model, proc = _load(_embed, EMBED_MODEL)
            for batch in (text_batch, image_batch):
                for start in range(0, len(batch), MAX_BATCH):
                    sub = batch[start : start + MAX_BATCH]
                    _reset_vl_state(model)
                    rows = _mx_rows(model.process([it for _, it in sub], processor=proc))
                    for (orig_i, _), vec in zip(sub, rows, strict=True):
                        out[orig_i] = vec
            _mx_after_request()
            return out

        async with _model_lock():
            results = await _run_mx(_work)
        return [results[i] for i in range(len(objs))]
    finally:
        for p in tempfiles:
            with contextlib.suppress(OSError):
                os.unlink(p)


async def _score_documents(query: dict, documents: list[dict]) -> list[float]:
    """One process(dict) call per VL_RERANK_CHUNK documents. Each document scores
    independently, so chunking does not change results."""
    q_item, q_tf = _item_from_transport(query, is_query=True)
    tempfiles = list(q_tf)
    # rerank payload takes `instruction` at the top level, not inside `query`
    instruction = q_item.pop("instruction", QUERY_INSTRUCTION)
    try:
        doc_items: list[dict] = []
        for obj in documents:
            it, tf = _item_from_transport(obj, is_query=False)
            tempfiles.extend(tf)
            doc_items.append(it)

        def _work() -> list[float]:
            acc: list[float] = []
            model, proc = _load(_rerank, RERANK_MODEL)
            for start in range(0, len(doc_items), RERANK_CHUNK):
                chunk = doc_items[start : start + RERANK_CHUNK]
                _reset_vl_state(model)
                out = model.process(
                    {"instruction": instruction, "query": q_item, "documents": chunk},
                    processor=proc,
                )
                chunk_scores = _flatten_scores(out)
                if len(chunk_scores) != len(chunk):
                    raise ValueError(
                        f"rerank returned {len(chunk_scores)} scores for {len(chunk)} documents"
                    )
                acc.extend(chunk_scores)
            _mx_after_request()
            return acc

        async with _model_lock():
            scores = await _run_mx(_work)
        assert len(scores) == len(documents), (len(scores), len(documents))
        return scores
    finally:
        for p in tempfiles:
            with contextlib.suppress(OSError):
                os.unlink(p)


def _flatten_scores(out) -> list[float]:
    import mlx.core as mx

    mx.eval(out)
    flat = out.reshape(-1) if hasattr(out, "reshape") else out
    return [float(x) for x in (flat.tolist() if hasattr(flat, "tolist") else list(flat))]


# ── transport models ────────────────────────────────────────────────────────
class EmbedBatchReq(BaseModel):
    items: list[dict]


class RerankReq(BaseModel):
    query: str | dict
    documents: list[dict]
    top_n: int | None = None


@app.get("/health")
def health():
    """O2/A4: constant-time, no MLX-runtime call — a model call in flight holds
    the GIL through `mx.eval`, so anything that touches `mx.*` here (memory
    counters included) would queue behind it. Liveness must stay cheap. MLX
    memory moved to `/stats`."""
    return {
        "status": "ok",
        "service": "vl-retrieval",
        "embed_model": EMBED_MODEL,
        "rerank_model": RERANK_MODEL,
        "embedding_dim": EMBEDDING_DIM,
        "rerank_chunk": RERANK_CHUNK,
        "max_batch": MAX_BATCH,
        "embed_loaded": _embed["model"] is not None,
        "rerank_loaded": _rerank["model"] is not None,
        "requests_served": _REQUESTS_SERVED,
        "inflight": _INFLIGHT,
    }


@app.get("/stats")
def stats():
    return {"requests_served": _REQUESTS_SERVED, "inflight": _INFLIGHT, "mx_mem": _mx_mem()}


@app.get("/ready")
async def ready():
    try:
        async with _model_lock():
            # the model must be *created* on the same thread that will run it
            await _run_mx(_load, _embed, EMBED_MODEL)
        dim = len((await _embed_items([{"text": "ready probe", "is_query": True}]))[0])
        ok = dim == EMBEDDING_DIM
        return JSONResponse(
            {
                "ready": ok,
                "embed_model": EMBED_MODEL,
                "dim": dim,
                "expected_dim": EMBEDDING_DIM,
                "normalize": _embed["normalize"],
            },
            status_code=200 if ok else 503,
        )
    except Exception as e:  # noqa: BLE001
        return JSONResponse(
            {"ready": False, "embed_model": EMBED_MODEL, "error": f"{type(e).__name__}: {e}"},
            status_code=503,
        )


@app.post("/embed")
async def embed(req: dict):
    try:
        vec = (await _embed_items([{**req, "is_query": bool(req.get("is_query"))}]))[0]
        return {"embedding": vec, "dim": len(vec)}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/embed_batch")
async def embed_batch(req: EmbedBatchReq):
    try:
        vecs = await _embed_items(req.items)
        return {"embeddings": vecs, "dim": len(vecs[0]) if vecs else 0, "count": len(vecs)}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/rerank")
async def rerank(req: RerankReq):
    try:
        query = req.query if isinstance(req.query, dict) else {"text": req.query}
        scores = await _score_documents(query, req.documents)
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        if req.top_n:
            order = order[: req.top_n]
        return {"results": [{"index": i, "score": scores[i]} for i in order]}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("VL_PORT", "8942")))
    ap.add_argument("--host", default="0.0.0.0")
    a = ap.parse_args()
    if MX_CACHE_LIMIT_MB > 0:
        with contextlib.suppress(Exception):
            import mlx.core as mx

            mx.set_cache_limit(MX_CACHE_LIMIT_MB * 1024 * 1024)
    uvicorn.run(app, host=a.host, port=a.port)
