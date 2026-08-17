#!/usr/bin/env python3
"""
Portal 5 — Arm B llama.cpp Embedding Server (SA3.3, TASK_BULLY_SA3_EMBEDDING_BAKEOFF_V1)

Serves an OpenAI-compatible /v1/embeddings endpoint over `llama-server`
(EmbeddingGemma-300M Q8_0), applying EmbeddingGemma's asymmetric **task
prefixes**:

    documents:  "title: none | text: {content}"
    queries:    "task: search result | query: {content}"

The asymmetry is wired through two endpoints under the same OpenAI response
shape: `organ.upsert` (document embedding) posts to /v1/embeddings (default
document form), and `organ.prepare_knn`/`knn` (query embedding) post to
/v1/embeddings/query when an Arm-B query URL is configured. Both endpoints
return identical OpenAI-compatible payloads so the caller-facing contract is
unchanged.

EmbeddingGemma activations do not support fp16; llama.cpp's EmbeddingGemma
GGUF path runs in bf16/f32, so no fp16 precision is forced anywhere here.

The wrapper spawns `llama-server` as a child process (model weights from the
path given by `--model`), proxies /v1/embeddings to it, and applies the task
prefixes. `--embedding` restricts llama-server to the embedding use case;
`--pooling cls` and `--embd-normalize 2` match the model's expected pooling
(default EmbeddingGemma settings).

Managed by:
    ./launch.sh start-embedding-arm-b   # start in background
    ./launch.sh stop-embedding-arm-b    # stop
"""

import argparse
import logging
import os
import shutil
import signal
import subprocess
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("embedding-server-llamacpp")

DEFAULT_MODEL = os.path.expanduser(
    "~/.portal5/models/embeddinggemma-300m/embeddinggemma-300M-Q8_0.gguf"
)

# EmbeddingGemma task prefixes (SA3.3). Applied by the wrapper because the
# OpenAI contract carries no notion of "query" vs "document".
DOCUMENT_PREFIX = "title: none | text: "
QUERY_PREFIX = "task: search result | query: "

parser = argparse.ArgumentParser(description="Portal 5 Arm B llama.cpp Embedding Server")
parser.add_argument("--port", type=int, default=8943)
parser.add_argument("--host", default="0.0.0.0")
parser.add_argument(
    "--model",
    default=os.environ.get("EMBEDDING_MODEL_ARM_B", DEFAULT_MODEL),
    help=f"llama.cpp GGUF path (default: {DEFAULT_MODEL})",
)
parser.add_argument("--llama-bin", default=shutil.which("llama-server") or "llama-server")
parser.add_argument("--llama-port", type=int, default=8942)
args, _ = parser.parse_known_args()

_llama_proc: subprocess.Popen | None = None
_llama_base_url = f"http://127.0.0.1:{args.llama_port}"
_client = httpx.Client(timeout=300.0, base_url=_llama_base_url)


def _start_llama_server() -> None:
    global _llama_proc
    if _llama_proc is not None and _llama_proc.poll() is None:
        return
    if not Path(args.model).exists():
        raise RuntimeError(f"GGUF model not found: {args.model}")
    log.info(f"Spawning llama-server with {args.model}")
    _llama_proc = subprocess.Popen(
        [
            args.llama_bin,
            "-m",
            args.model,
            "--embedding",
            "--pooling",
            "cls",
            "-c",
            "4096",
            "--embd-normalize",
            "2",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.llama_port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(120):
        try:
            if httpx.get(f"{_llama_base_url}/health", timeout=1.0).status_code == 200:
                log.info("llama-server healthy")
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise RuntimeError("llama-server failed to become healthy")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _start_llama_server()
    yield
    global _llama_proc
    if _llama_proc is not None and _llama_proc.poll() is None:
        _llama_proc.send_signal(signal.SIGTERM)
        try:
            _llama_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _llama_proc.kill()
        _llama_proc = None
    _client.close()


app = FastAPI(
    title="Portal 5 Arm B llama.cpp Embedding Server",
    version="1.0.0",
    lifespan=lifespan,
)


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    model: str = args.model
    encoding_format: str = "float"


def _embed(texts: list[str], *, prefix: str) -> list[list[float]]:
    _start_llama_server()
    payload = {
        "input": [prefix + text for text in texts],
        "encoding_format": "float",
    }
    try:
        resp = _client.post("/v1/embeddings", json=payload)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"llama-server embed failed: {exc}") from exc
    data = resp.json().get("data")
    if not data:
        raise HTTPException(status_code=502, detail="llama-server returned no embeddings")
    return [item["embedding"] for item in sorted(data, key=lambda item: item["index"])]


def _respond(texts: list[str], vectors: list[list[float]], *, task: str) -> dict:
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)
        ],
        "model": args.model,
        "task": task,
        "usage": {
            "prompt_tokens": sum(len(t.split()) for t in texts),
            "total_tokens": sum(len(t.split()) for t in texts),
        },
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": args.model,
        "backend": "llamacpp",
        "task_prefixes": {"document": DOCUMENT_PREFIX.strip(), "query": QUERY_PREFIX.strip()},
        "llama_healthy": _llama_proc is not None and _llama_proc.poll() is None,
    }


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [{"id": args.model, "object": "model", "owned_by": "portal5"}],
    }


@app.post("/v1/embeddings")
async def create_embeddings(req: EmbeddingRequest):
    """Document-form embeddings (upsert path) -- `title: none | text: {content}`."""
    texts = [req.input] if isinstance(req.input, str) else req.input
    if not texts:
        raise HTTPException(status_code=400, detail="input is empty")
    vectors = _embed(texts, prefix=DOCUMENT_PREFIX)
    return _respond(texts, vectors, task="document")


@app.post("/v1/embeddings/query")
async def create_query_embeddings(req: EmbeddingRequest):
    """Query-form embeddings (knn path) -- `task: search result | query: {content}`."""
    texts = [req.input] if isinstance(req.input, str) else req.input
    if not texts:
        raise HTTPException(status_code=400, detail="input is empty")
    vectors = _embed(texts, prefix=QUERY_PREFIX)
    return _respond(texts, vectors, task="query")


@app.get("/")
async def root():
    return {
        "service": "Portal 5 Arm B llama.cpp Embedding Server",
        "model": args.model,
        "port": args.port,
    }


if __name__ == "__main__":
    log.info(f"Starting Arm B llama.cpp embedding server on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
