"""Portal 5 — Qwen3-VL retrieval server (embedding + rerank, text & image).

The retrieval model for the RAG stack: one joint text+image space. Replaces the
RAG stack's use of the text embedder/reranker for *retrieval* (the shared text
embedder :8917 and reranker :8925 stay up for other subsystems — memory, the
Bully ORG projection). Lazy-load; sequential-safe.

Usage: python3 scripts/vl-retrieval-server.py --port 8942

The mlx-embeddings VL process()/scoring API differs across pinned versions —
the `_embed_one` / `_score_pair` helpers isolate the version-specific shape so
only they need adjusting. Downstream needs only: /embed -> vector,
/rerank -> ordered indices.

RUNTIME NOTE: mlx-embeddings 0.1.0 (the version pinned in `rag` extras) does
NOT recognise the Qwen3-VL-Embedding architecture — `load()` fails with
"'NoneType' object has no attribute 'model_type'", and there is no
pre-converted MLX build of Qwen3-VL-Embedding-2B on the Hub. Bringing this
server fully online is gated on an mlx-embeddings release with VL support (or
an alternative VL-embedding runtime / a local MLX conversion of
Qwen/Qwen3-VL-Embedding-2B) — the inference-runtime re-evaluation the MCP
Fleet Overhaul program explicitly deferred. Set VL_EMBED_MODEL / VL_RERANK_MODEL
once a working model exists; the seams above are the only code that changes.
"""

from __future__ import annotations

import argparse
import base64
import os
import tempfile

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

EMBED_MODEL = os.environ.get("VL_EMBED_MODEL", "Qwen/Qwen3-VL-Embedding-2B")
RERANK_MODEL = os.environ.get("VL_RERANK_MODEL", "Qwen/Qwen3-VL-Reranker-2B")

app = FastAPI(title="portal5-vl-retrieval")
_embed = {"m": None, "p": None}
_rerank = {"m": None, "p": None}


def _load_embed():
    if _embed["m"] is None:
        from mlx_embeddings import load

        _embed["m"], _embed["p"] = load(EMBED_MODEL)
    return _embed["m"], _embed["p"]


def _load_rerank():
    if _rerank["m"] is None:
        from mlx_embeddings import load

        _rerank["m"], _rerank["p"] = load(RERANK_MODEL)
    return _rerank["m"], _rerank["p"]


def _b64_to_path(b64: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".png")
    with os.fdopen(fd, "wb") as fh:
        fh.write(base64.b64decode(b64))
    return path


def _embed_one(model, proc, item: dict) -> list[float]:
    """Version-isolated embed. `item` has optional 'text'/'instruction'/'image'."""
    import mlx.core as mx

    out = model.process([item], processor=proc)
    mx.eval(out)
    row = out[0]
    return row.tolist() if hasattr(row, "tolist") else list(row)


def _score_pair(model, proc, query_item: dict, cand_item: dict) -> float:
    """Version-isolated relevance score for a (query, candidate) pair."""
    import mlx.core as mx

    out = model.process([query_item, cand_item], processor=proc)
    mx.eval(out)
    a, b = out[0], out[1]
    try:
        return float((a @ b.T).item())
    except Exception:  # noqa: BLE001
        return 0.0


class EmbedReq(BaseModel):
    text: str | None = None
    image_b64: str | None = None
    instruction: str | None = "Retrieve documents relevant to the query."


class RerankReq(BaseModel):
    query: str
    candidates: list
    top_n: int | None = None


@app.get("/health")
def health():
    return {"status": "ok", "service": "vl-retrieval", "embed_model": EMBED_MODEL}


@app.get("/ready")
def ready():
    """Whether the embed model actually loads on this runtime (see RUNTIME NOTE)."""
    try:
        _load_embed()
        return {"ready": True, "embed_model": EMBED_MODEL}
    except Exception as e:  # noqa: BLE001
        return {"ready": False, "embed_model": EMBED_MODEL, "error": f"{type(e).__name__}: {e}"}


@app.post("/embed")
def embed(req: EmbedReq):
    model, proc = _load_embed()
    item: dict = {}
    if req.text:
        item["text"] = req.text
        item["instruction"] = req.instruction
    if req.image_b64:
        item["image"] = _b64_to_path(req.image_b64)
    vec = _embed_one(model, proc, item)
    return {"embedding": vec, "dim": len(vec)}


@app.post("/rerank")
def rerank(req: RerankReq):
    model, proc = _load_rerank()
    q = {"instruction": "Retrieve documents relevant to the query.", "text": req.query}
    scored = []
    for i, c in enumerate(req.candidates):
        cand = (
            {"image": _b64_to_path(c["image_b64"])}
            if c.get("image_b64")
            else {"text": c.get("text", "")}
        )
        scored.append({"index": i, "score": _score_pair(model, proc, q, cand)})
    scored.sort(key=lambda s: -s["score"])
    return {"results": scored[: (req.top_n or len(scored))]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("VL_PORT", "8942")))
    ap.add_argument("--host", default="0.0.0.0")
    a = ap.parse_args()
    uvicorn.run(app, host=a.host, port=a.port)
