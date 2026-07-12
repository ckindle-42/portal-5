"""Portal 5 Reranker MCP Server.

Cross-encoder reranking via Qwen3-Reranker-0.6B-mxfp8 (MLX-native).
Pair with the embedding server (port 8917) for two-stage RAG retrieval.

Port: 8925 (RERANKER_MCP_PORT env override).

Tools:
- rerank: score (query, document) pairs and return top-N by relevance
"""

import logging
import os

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

# Lazy references — populated on first call to rerank().
# Declared at module level so unit tests can patch them.
try:
    import mlx.core as mx  # type: ignore[import-not-found]
    from mlx_embeddings import generate  # type: ignore[import-not-found]
except ImportError:
    mx = None  # type: ignore[assignment]
    generate = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)
mcp = FastMCP("reranker", host="0.0.0.0")

RERANKER_MODEL = os.environ.get("RERANKER_MODEL", "mlx-community/Qwen3-Reranker-0.6B-mxfp8")

_model = None
_processor = None


def _ensure_loaded() -> tuple:
    global _model, _processor
    if _model is None:
        from mlx_embeddings import load

        logger.info(f"Loading reranker model: {RERANKER_MODEL}")
        _model, _processor = load(RERANKER_MODEL)
        logger.info("Reranker model loaded")
    return _model, _processor


@mcp.tool()
def rerank(query: str, documents: list[str], top_n: int | None = None) -> list[dict]:
    """Score (query, document) pairs and return them sorted by relevance.

    Args:
        query: The query text.
        documents: Candidate document texts.
        top_n: If set, return only the top-N most relevant. Default: all.

    Returns:
        List of {document, score, original_index} sorted by score descending.
    """
    if not documents:
        return []

    import portal.modules.research.tools.reranker_mcp as _self  # noqa: PLC0415 — allows test patching

    model, processor = _ensure_loaded()

    if _self.generate is None:
        import mlx.core as _mx_mod  # noqa: PLC0415
        from mlx_embeddings import generate as _gen_mod  # noqa: PLC0415

        _self.mx = _mx_mod  # type: ignore[assignment]
        _self.generate = _gen_mod  # type: ignore[assignment]

    instruction = "Given a query and a document, judge whether the document is relevant."
    pairs = [f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}" for doc in documents]

    output = _self.generate(model, processor, texts=pairs)

    if hasattr(output, "scores"):
        scores = _self.mx.array(output.scores).tolist()
    elif hasattr(output, "text_embeds"):
        # Fallback: cosine similarity when scores attr not present
        embeds = output.text_embeds
        query_out = _self.generate(model, processor, texts=[query])
        query_embed = query_out.text_embeds[0]
        scores = _self.mx.matmul(embeds, query_embed).tolist()
    else:
        raise RuntimeError(
            f"Reranker output has neither .scores nor .text_embeds; got: {dir(output)}"
        )

    results = [
        {"document": doc, "score": float(score), "original_index": i}
        for i, (doc, score) in enumerate(zip(documents, scores, strict=False))
    ]
    results.sort(key=lambda r: r["score"], reverse=True)

    if top_n is not None:
        results = results[:top_n]
    return results


@mcp.custom_route("/health", methods=["GET"])
async def health(_request):
    return JSONResponse({"status": "ok", "model": RERANKER_MODEL, "loaded": _model is not None})


if __name__ == "__main__":
    port = int(os.environ.get("RERANKER_MCP_PORT", "8925"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info(f"Starting reranker MCP on port {port}")
    mcp.settings.port = port
    mcp.run(transport="streamable-http")
