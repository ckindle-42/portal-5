#!/usr/bin/env python3
"""
Portal 5 — Arm A MLX Embedding Server (SA3.2, TASK_BULLY_SA3_EMBEDDING_BAKEOFF_V1)

Serves an OpenAI-compatible /v1/embeddings endpoint via `mlx_embeddings`
(GPU-native MLX on Apple Silicon), mirroring the reranker's load/generate
pattern (portal/modules/research/tools/reranker_mcp.py). Same 0.6B size class
as the CPU sentence-transformers path it competes with, converted in-house to
mxfp8. The on-disk model at ~/.portal5/models/Qwen3-Embedding-0.6B-mxfp8 is
genuine MXFP8 (config `{'group_size': 32, 'bits': 8, 'mode': 'mxfp8'}`),
re-converted under mlx-embeddings 0.1.x — the command below needs a VL-capable
mlx-embeddings (>=0.1.0); 0.0.x's convert.py has no `--q-mode`:

    uv run python -m mlx_embeddings.convert \\
        --hf-path Qwen/Qwen3-Embedding-0.6B \\
        --mlx-path ~/.portal5/models/Qwen3-Embedding-0.6B-mxfp8 \\
        --quantize --q-mode mxfp8 --q-group-size 32 --q-bits 8

The OpenAI-compatible /v1/embeddings contract is identical to the CPU server so
`organ._embed` is unchanged. Concurrency deliberately avoids the
`run_in_executor` pattern that caused the original MPS thread-safety crash:
MLX generate() is called directly on the event loop, exactly as the reranker
calls it.

Managed by:
    ./launch.sh start-embedding-arm-a   # start in background
    ./launch.sh stop-embedding-arm-a    # stop
"""

import argparse
import logging
import os
import time

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("embedding-server-mlx")

DEFAULT_MODEL = os.path.expanduser("~/.portal5/models/Qwen3-Embedding-0.6B-mxfp8")

parser = argparse.ArgumentParser(description="Portal 5 Arm A MLX Embedding Server")
parser.add_argument("--port", type=int, default=8917)
parser.add_argument("--host", default="0.0.0.0")
parser.add_argument(
    "--model",
    default=os.environ.get("EMBEDDING_MODEL", DEFAULT_MODEL),
    help=f"HuggingFace repo or local MLX path (default: {DEFAULT_MODEL})",
)
args, _ = parser.parse_known_args()

_model = None
_processor = None


def _ensure_loaded():
    global _model, _processor
    if _model is None:
        from mlx_embeddings import load

        log.info(f"Loading MLX embedding model: {args.model}")
        _model, _processor = load(args.model)
        log.info("MLX embedding model loaded")
    return _model, _processor


app = FastAPI(title="Portal 5 Arm A MLX Embedding Server", version="1.0.0")


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    model: str = args.model
    encoding_format: str = "float"


@app.get("/health")
async def health():
    return {"status": "ok", "model": args.model, "loaded": _model is not None, "backend": "mlx"}


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [{"id": args.model, "object": "model", "owned_by": "portal5"}],
    }


@app.post("/v1/embeddings")
async def create_embeddings(req: EmbeddingRequest):
    texts = [req.input] if isinstance(req.input, str) else req.input
    if not texts:
        raise HTTPException(status_code=400, detail="input is empty")

    import mlx.core as mx  # noqa: PLC0415 — lazy runtime import mirrors reranker

    model, processor = _ensure_loaded()
    from mlx_embeddings import generate  # noqa: PLC0415

    t0 = time.perf_counter()
    try:
        # Direct call on the event loop -- NO run_in_executor (the pattern that
        # crashed MPS in the CPU server's thread pool).
        output = generate(model, processor, texts=texts)
        if hasattr(output, "text_embeds"):
            vectors = mx.array(output.text_embeds).tolist()
        elif hasattr(output, "last_hidden_state"):
            vectors = mx.array(output.last_hidden_state[:, -1, :]).tolist()
        else:
            raise RuntimeError(
                f"MLX embedding output has no text_embeds/last_hidden_state; got: {dir(output)}"
            )
    except Exception as e:
        log.error(f"Embedding error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e

    elapsed = time.perf_counter() - t0
    log.info(f"Embedded {len(texts)} text(s) in {elapsed:.3f}s")

    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)
        ],
        "model": req.model,
        "usage": {
            "prompt_tokens": sum(len(t.split()) for t in texts),
            "total_tokens": sum(len(t.split()) for t in texts),
        },
    }


@app.get("/")
async def root():
    return {
        "service": "Portal 5 Arm A MLX Embedding Server",
        "model": args.model,
        "port": args.port,
    }


if __name__ == "__main__":
    log.info(f"Starting Arm A MLX embedding server on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
