"""Fusion stage — moved verbatim from ``rag_multimodal`` (SEAM V1 P3).

The RRF text/visual fusion with the gated visual boost (``text_gate``, the
default), the one-cross-encoder-pass alternative (``unified``), and plain RRF
(``rrf``). ``fused_score`` / ``reranker_prob`` semantics — including the
visual-row boost under ``text_gate`` — are unchanged.

The arms are searched here (``ttbl.search(qvec)``) but embedding and rerank are
injected as callables so a second composition can swap the service client.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

RRF_K = 60

# See rag_multimodal's original block for the full τ history. τ RE-FITTED to 0.72
# on the shipping stack (docling 2.99.0 pin); 0.75 is strictly dominated there.
VL_TEXT_GATE = float(os.environ.get("VL_TEXT_GATE", "0.72"))
# `absolute` = the cosine threshold above. `relative` = the top text hit's margin
# over the median of its own candidate pool. MEASURED AND REJECTED as a default:
# dominated on both axes because the margin is ANTI-correlated with need.
VL_TEXT_GATE_MODE = os.environ.get("VL_TEXT_GATE_MODE", "absolute")
VL_TEXT_MARGIN = float(os.environ.get("VL_TEXT_MARGIN", "0.08"))
# S3: rerank `VL_RERANK_DEPTH * top_k` page images (default 1.5).
VL_RERANK_DEPTH = float(os.environ.get("VL_RERANK_DEPTH", "1.5"))
# Fusion strategy. `text_gate` is the default; `unified` and `rrf` measured/kept
# for A/B — see rag_multimodal's original constant block.
FUSION = os.environ.get("VL_FUSION", "text_gate")
# Candidate depth for the TEXT arm under `unified`, as a multiple of top_k.
UNIFIED_TEXT_DEPTH = float(os.environ.get("VL_UNIFIED_TEXT_DEPTH", "3"))

RerankFn = Callable[[str, list, int], Awaitable[list]]


def text_arm_is_unconfident(top_text_sim: float, text_margin: float) -> bool:
    """Should the visual arm be promoted? i.e. does the text arm lack an answer.

    `absolute` is the cosine threshold (VL_TEXT_GATE, default 0.72).
    `relative` compares the top text hit to the SPREAD of its own candidate pool.
    The premise was that a text arm holding the answer has one chunk standing
    clear of the pack, making the feature scale-free and immune to the silent
    failure the absolute gate hit (dia r@1 1.000 -> 0.714 when docling replaced
    PyMuPDF). Measured: the premise is backwards. Diagram queries carry the
    LARGER margin (median 0.117 vs prose 0.055) — a figure page's one transcribed
    caption stands clear of an otherwise irrelevant pool. Dominated at every
    margin tried; kept for A/B, not a default."""
    if VL_TEXT_GATE_MODE == "relative":
        return text_margin < VL_TEXT_MARGIN
    return top_text_sim < VL_TEXT_GATE


async def search_unified(ttbl, vtbl, query: str, qvec, top_k: int, vl_rerank: RerankFn) -> list:
    """One cross-encoder pass over a mixed text+image candidate pool.

    Both arms contribute CANDIDATES only — their embedding ranks are used to
    shortlist, never to score. The reranker then scores every candidate, text and
    image alike, in one comparable probability space, and the final order is just
    that score. This is why it cannot regress the way `text_gate` did: nothing in
    the ranking depends on an absolute threshold or on how rich the text arm
    happens to be."""
    # Text and visual get INDEPENDENT candidate depths. The first cut of this
    # used VL_RERANK_DEPTH for both, which silently halved the text pool the RRF
    # path had been using (top_k*3) and cost recall upstream of any scoring.
    vdepth = max(1, round(VL_RERANK_DEPTH * top_k))
    tdepth = max(1, round(UNIFIED_TEXT_DEPTH * top_k))
    cands: list[dict] = []
    meta: list[dict] = []

    if ttbl is not None:
        for r in ttbl.search(qvec).limit(tdepth).to_list():
            cands.append({"text": r["text"]})
            meta.append(
                {
                    "chunk_id": r["chunk_id"],
                    "source_file": r["source_file"],
                    "chunk_index": r["chunk_index"],
                    "text": r["text"],
                    "kind": "text",
                }
            )
    if vtbl is not None:
        for r in vtbl.search(qvec).limit(vdepth).to_list():
            cands.append({"image_path": r["image_path"]})
            meta.append(
                {
                    "chunk_id": r["chunk_id"],
                    "source_file": r["source_file"],
                    "chunk_index": r["page"],
                    "page": r["page"],
                    "text": f"[page image {r['source_file']} p{r['page']}]",
                    "kind": "visual",
                }
            )
    if not cands:
        return []

    order = await vl_rerank(query, cands, min(len(cands), top_k))
    # The server returns these sorted, but the ranking is the whole product here
    # — sort explicitly rather than depend on a remote service's ordering.
    order = sorted(order, key=lambda o: -float(o["score"]))
    out = []
    for o in order[:top_k]:
        m = dict(meta[o["index"]])
        prob = round(float(o["score"]), 5)
        m["reranker_prob"] = prob
        m["fused_score"] = prob
        out.append(m)
    return out


async def rrf_fuse(ttbl, vtbl, query: str, qvec, top_k: int, vl_rerank: RerankFn) -> list:
    """Text-chunk RRF + page-image rerank, fused, with the gated visual boost.

    Extracted verbatim from ``_search``'s non-``unified`` body."""
    scores: dict = {}
    payload: dict = {}
    top_text_sim = 0.0
    text_margin = 0.0
    if ttbl is not None:
        trows = ttbl.search(qvec).limit(top_k * 3).to_list()
        if trows:
            # lancedb `_distance` is L2^2 between the unit query and unit
            # stored vector == 2*(1-cos); server guarantees normalize=True
            top_text_sim = max(0.0, 1.0 - trows[0].get("_distance", 2.0) / 2.0)
        if len(trows) >= 3:
            sims = [max(0.0, 1.0 - t.get("_distance", 2.0) / 2.0) for t in trows]
            _med = sorted(sims)[len(sims) // 2]
            text_margin = sims[0] - _med
        for rank, r in enumerate(trows):
            key = ("text", r["chunk_id"])
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
            payload[key] = {
                "chunk_id": r["chunk_id"],
                "source_file": r["source_file"],
                "chunk_index": r["chunk_index"],
                "text": r["text"],
                "kind": "text",
                "reranker_prob": None,
            }
    if vtbl is not None:
        # S3: rerank depth is the entire query cost (~1.7s/page image,
        # linear). The visual embedding recall is high — the target page is
        # in the top few of the cosine ranking — so reranking `VL_RERANK_DEPTH
        # * top_k` candidates rather than the `top_k*3` coarse set cuts
        # latency at no measured recall cost. Sweep 3/2/1.5/1: recall
        # identical at every depth (26.4s -> 8.8s); 1.5 keeps a margin.
        depth = max(1, round(VL_RERANK_DEPTH * top_k))
        coarse = vtbl.search(qvec).limit(depth).to_list()
        cands = [{"image_path": r["image_path"]} for r in coarse]
        order = await vl_rerank(query, cands, min(len(cands), top_k * 2)) if cands else []
        # Gate the visual boost on whether the text arm has a confident
        # answer. See VL_TEXT_GATE for the τ re-fit (0.67 -> 0.75) and why
        # `relative` lost.
        visual_boost = text_arm_is_unconfident(top_text_sim, text_margin)
        for rank, o in enumerate(order):
            r = coarse[o["index"]]
            key = ("visual", r["chunk_id"])
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
            if visual_boost:
                scores[key] += float(o["score"])
            payload[key] = {
                "chunk_id": r["chunk_id"],
                "source_file": r["source_file"],
                "chunk_index": r["page"],
                "page": r["page"],
                "text": f"[page image {r['source_file']} p{r['page']}]",
                "kind": "visual",
                "reranker_prob": round(float(o["score"]), 5),
            }
    fused = sorted(scores.items(), key=lambda kv: -kv[1])[:top_k]
    return [{**payload[k], "fused_score": round(s, 5)} for k, s in fused]


async def fuse(
    fusion_mode: str,
    ttbl,
    vtbl,
    query: str,
    qvec,
    top_k: int,
    vl_rerank: RerankFn,
) -> list:
    """Dispatch on the composition's fusion mode. ``rrf`` and ``text_gate`` share
    ``rrf_fuse`` — the difference is only whether ``text_arm_is_unconfident``
    ever fires, which ``VL_TEXT_GATE`` / ``VL_TEXT_GATE_MODE`` already control."""
    if fusion_mode == "unified":
        return await search_unified(ttbl, vtbl, query, qvec, top_k, vl_rerank)
    return await rrf_fuse(ttbl, vtbl, query, qvec, top_k, vl_rerank)
