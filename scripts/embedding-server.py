#!/usr/bin/env python3
"""
Portal 5 — Native ARM64 Embedding Server
Serves an OpenAI-compatible /v1/embeddings endpoint using sentence-transformers.
Replaces the TEI Docker service on Apple Silicon where the x86-only TEI image
has no ARM64 manifest.

Usage:
    python3 scripts/embedding-server.py
    python3 scripts/embedding-server.py --port 8917 --model microsoft/harrier-oss-v1-0.6b

Managed by:
    ./launch.sh start-embedding-cpu-arm   # start in background
    ./launch.sh stop-embedding-cpu-arm    # stop

Dependencies (install once):
    pip install sentence-transformers fastapi uvicorn
"""

import argparse
import asyncio
import logging
import time

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("embedding-server")

# ── CLI args ────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Portal 5 ARM64 Embedding Server")
parser.add_argument("--port", type=int, default=8917, help="Port to listen on (default: 8917)")
parser.add_argument(
    "--model",
    default="microsoft/harrier-oss-v1-0.6b",
    help="HuggingFace model ID (default: microsoft/harrier-oss-v1-0.6b)",
)
parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
args, _ = parser.parse_known_args()

# ── Model loading ────────────────────────────────────────────────────────────
log.info(f"Loading embedding model: {args.model}")
try:
    from sentence_transformers import SentenceTransformer

    # CPU is used intentionally: MPS (Metal) is not thread-safe and crashes when
    # encode() is called from a thread pool executor. For a 0.6B embedding model
    # CPU throughput (~20-50ms/batch) is sufficient and stable on Apple Silicon.
    _model = SentenceTransformer(args.model, device="cpu")
    log.info("Model loaded on CPU")
except Exception as e:
    log.error(f"Failed to load model: {e}")
    raise

# ── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(title="Portal 5 Embedding Server", version="1.0.0")


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    model: str = args.model
    encoding_format: str = "float"


@app.get("/health")
async def health():
    return {"status": "ok", "model": args.model}


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

    t0 = time.perf_counter()
    try:
        # Run in executor so async event loop isn't blocked
        loop = asyncio.get_event_loop()
        vectors = await loop.run_in_executor(None, lambda: _model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist())
    except Exception as e:
        log.error(f"Embedding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    elapsed = time.perf_counter() - t0
    log.info(f"Embedded {len(texts)} text(s) in {elapsed:.3f}s")

    return {
        "object": "list",
        "data": [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)],
        "model": req.model,
        "usage": {"prompt_tokens": sum(len(t.split()) for t in texts), "total_tokens": sum(len(t.split()) for t in texts)},
    }


@app.get("/")
async def root():
    return {"service": "Portal 5 ARM64 Embedding Server", "model": args.model, "port": args.port}


if __name__ == "__main__":
    log.info(f"Starting embedding server on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
