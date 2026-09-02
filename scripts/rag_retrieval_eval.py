"""RAG multimodal retrieval evaluation harness
(TASK_VL_RETRIEVAL_HARDENING_AND_CLOSEOUT_V2 P4/P5/P6).

Drives `portal.modules.research.tools.rag_multimodal` in-process against a
labelled corpus + query set, isolated to a scratch LanceDB dir and the live VL
retrieval server (:8942). Reports recall@1, recall@5 and MRR per query
category, and — for P5 — lets a fusion strategy be swapped so diagram-only and
prose-only recall can be compared for every option on the same corpus.

Usage:
  python scripts/rag_retrieval_eval.py CORPUS_DIR QUERIES.yaml [--fusion STRAT]
      [--lance-dir DIR] [--kb-id ID] [--reuse] [--out results.json]

  --fusion  rrf (default, current behaviour) | rerank_tiebreak | score_aware
  --reuse   skip ingest if the KB already exists in --lance-dir

The corpus dir holds PDFs (any nesting); QUERIES.yaml is the P4 query set.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

import yaml


def _patch_fusion(rm, strategy: str) -> None:  # noqa: C901, PLR0915
    """Replace rag_multimodal._search's fusion with a strategy under test (P5).

    rrf              — unchanged: sum of 1/(k+rank), text arm inserted first so a
                       0-0 tie is decided by insertion order (== text always).
    rerank_tiebreak  — RRF, but ties broken on the visual arm's calibrated
                       reranker_prob (text rows sort after any visual row at the
                       same fused score).
    score_aware      — the visual arm contributes reranker_prob directly instead
                       of its rank position; text arm keeps 1/(k+rank).
    embed_sim        — NO VLM reranker call at all. The visual arm is ordered by
                       the Qwen3-VL *embedding* cosine similarity (from the
                       lancedb `_distance`, already computed) and that similarity
                       is blended in like score_aware. Tests whether the
                       expensive reranker earns its keep over embedding-sim.
    """
    if strategy == "rrf":
        return

    from starlette.responses import JSONResponse

    import portal.modules.research.tools.rag_multimodal as _rm

    rrf_k = _rm._RRF_K

    async def _arms(kb_id, query, top_k):
        """(rrf, prob, payload) — the per-key RRF weight, the visual reranker
        probability, and the display row, collected the same way the real
        `_search` does before it fuses."""
        ttbl, vtbl = _rm._text_table(kb_id), _rm._visual_table(kb_id)
        if ttbl is None and vtbl is None:
            return None
        _rm._assert_embedding_space(kb_id, (await _rm._vl_model_id())[0])
        qvec = await _rm._vl_embed(text=query, is_query=True)
        rrf: dict = {}
        prob: dict = {}
        payload: dict = {}
        top_text_sim = 0.0
        if ttbl is not None:
            trows = ttbl.search(qvec).limit(top_k * 3).to_list()
            if trows:
                top_text_sim = max(0.0, 1.0 - trows[0].get("_distance", 2.0) / 2.0)
            for rank, r in enumerate(trows):
                key = ("text", r["chunk_id"])
                rrf[key] = rrf.get(key, 0.0) + 1.0 / (rrf_k + rank)
                payload[key] = {
                    **{k: r[k] for k in ("source_file", "chunk_index", "text")},
                    "kind": "text",
                    "reranker_prob": None,
                }
        if vtbl is not None:
            coarse = vtbl.search(qvec).limit(top_k * 3).to_list()
            if strategy == "embed_sim":
                # no reranker: order by embedding cosine sim (1 - L2^2/2 for unit
                # vectors == cosine); blend that sim in as the "prob"
                ordered = sorted(coarse, key=lambda r: r.get("_distance", 9e9))
                order = [
                    {"index": i, "score": max(0.0, 1.0 - r.get("_distance", 2.0) / 2.0)}
                    for i, r in enumerate(ordered)
                ][: min(len(coarse), top_k * 2)]
                coarse = ordered
            else:
                cands = [{"image_path": r["image_path"]} for r in coarse]
                order = (
                    await _rm._vl_rerank(query, cands, min(len(cands), top_k * 2)) if cands else []
                )
            for rank, o in enumerate(order):
                r = coarse[o["index"]]
                key = ("visual", r["chunk_id"])
                rrf[key] = rrf.get(key, 0.0) + 1.0 / (rrf_k + rank)
                prob[key] = float(o["score"])
                payload[key] = {
                    "source_file": r["source_file"],
                    "chunk_index": r["page"],
                    "page": r["page"],
                    "text": f"[page image {r['source_file']} p{r['page']}]",
                    "kind": "visual",
                    "reranker_prob": round(float(o["score"]), 5),
                }
        return rrf, prob, payload, top_text_sim

    gate = float(os.environ.get("VL_FUSION_GATE", "0.0"))
    text_gate = float(os.environ.get("VL_TEXT_GATE", "0.67"))

    def _fuse(rrf, prob, top_k, top_text_sim):
        if strategy == "rerank_tiebreak":
            # visual wins a tie only if its prob clears the gate (0.0 == always)
            return sorted(
                rrf.items(),
                key=lambda kv: (
                    -kv[1],
                    -(prob.get(kv[0], -1.0) if prob.get(kv[0], 0.0) >= gate else -1.0),
                ),
            )[:top_k]
        if strategy == "text_gate":
            # only let the visual arm's signal override text when the TEXT arm
            # has no confident answer (top_text_sim < text_gate). Prose queries
            # (top_text_sim ~0.75+) keep text first; diagram queries
            # (top_text_sim ~0.5) let the visual page win. The separating signal
            # is measured (prob_dump.out), not fitted to the acceptance set.
            w = 1.0 if top_text_sim < text_gate else 0.0
            blended = {k: v + (w * prob[k] if k in prob else 0.0) for k, v in rrf.items()}
            return sorted(blended.items(), key=lambda kv: -kv[1])[:top_k]
        if strategy in ("score_aware", "embed_sim"):
            # blend the visual signal (reranker prob, or embedding sim) into the
            # visual contribution — but only the part above the gate
            blended = {
                k: v + (max(0.0, prob[k] - gate) if k in prob else 0.0) for k, v in rrf.items()
            }
            return sorted(blended.items(), key=lambda kv: -kv[1])[:top_k]
        raise ValueError(strategy)

    async def _search(request):
        args = (await request.json()).get("arguments", {})
        kb_id, query = args.get("kb_id", ""), args.get("query", "")
        top_k = min(int(args.get("top_k", 5)), 20)
        try:
            arms = await _arms(kb_id, query, top_k)
            if arms is None:
                return JSONResponse({"error": f"unknown kb_id '{kb_id}'"}, status_code=404)
            rrf, prob, payload, top_text_sim = arms
            fused = _fuse(rrf, prob, top_k, top_text_sim)
            results = [{**payload[k], "fused_score": round(s, 5)} for k, s in fused]
            return JSONResponse(
                {"kb_id": kb_id, "query": query, "num_results": len(results), "results": results}
            )
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"error": str(e)}, status_code=503)

    rm._search = _search


class _Req:
    def __init__(self, args):
        self._a = {"arguments": args}

    async def json(self):
        return self._a


async def _ingest(rm, kb_id: str, corpus: Path) -> dict:
    r = await rm._ingest(_Req({"kb_id": kb_id, "source_dir": str(corpus), "rebuild": True}))
    return json.loads(r.body)


async def _search(rm, kb_id: str, query: str, top_k: int = 10) -> list[dict]:
    r = await rm._search(_Req({"kb_id": kb_id, "query": query, "top_k": top_k}))
    body = json.loads(r.body)
    if "results" not in body:
        raise RuntimeError(body.get("error", body))
    return body["results"]


def _rank_of(results: list[dict], targets: list[str], target_page, category: str) -> int | None:
    """1-indexed rank of the first result matching any accepted target. For
    diagram_only with a target_page, a text hit on the right file does NOT
    count — the figure page must come back.

    `targets` is `target_file` plus any `also_accept` entries. `also_accept` is
    ONLY for a query a second document genuinely answers (a NERC standard and
    the operator procedure that implements it both state the same requirement) —
    never to launder a wrong retrieval into a hit. Each use is justified inline
    in queries.yaml."""
    for i, r in enumerate(results, 1):
        if Path(r.get("source_file", "")).name not in targets:
            continue
        if category == "diagram_only" and target_page is not None:
            if r.get("kind") == "visual" and r.get("page") == target_page:
                return i
            continue
        return i
    return None


async def _run_query(rm, kb_id: str, q: dict, top_k: int) -> dict:
    t0 = time.time()
    for attempt in range(4):  # tolerate a VL-server restart mid-run
        try:
            results = await _search(rm, kb_id, q["query"], top_k=top_k)
            break
        except RuntimeError as e:
            if attempt == 3 or "unavailable" not in str(e):
                raise
            await asyncio.sleep(10)
    targets = [q["target_file"], *q.get("also_accept", [])]
    rank = _rank_of(results, targets, q.get("target_page"), q["category"])
    row = {
        "id": q["id"],
        "category": q["category"],
        "rank": rank,
        "hit@1": bool(rank == 1),
        "hit@5": bool(rank and rank <= 5),
        "rr": round(1.0 / rank if rank else 0.0, 3),
        "latency_s": round(time.time() - t0, 2),
        "top": [
            (r.get("kind"), Path(r.get("source_file", "")).name, r.get("page")) for r in results[:3]
        ],
    }
    print(json.dumps(row))
    return row


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("queries")
    ap.add_argument(
        "--fusion",
        default="rrf",
        choices=["rrf", "rerank_tiebreak", "score_aware", "embed_sim", "text_gate"],
    )
    ap.add_argument("--lance-dir", default="/tmp/portal5_rag_eval_lance")
    ap.add_argument("--kb-id", default="ragEval")
    ap.add_argument("--reuse", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument(
        "--top-k", type=int, default=10, help="search depth; drives coarse limit + rerank width"
    )
    ap.add_argument("--categories", default="", help="comma-list to restrict the query set")
    a = ap.parse_args()

    os.environ["PORTAL5_LANCE_DIR"] = a.lance_dir
    os.environ.setdefault("VL_RETRIEVAL_URL", "http://localhost:8942")
    Path(a.lance_dir).mkdir(parents=True, exist_ok=True)

    import portal.modules.research.tools.rag_multimodal as rm

    rm.LANCE_DIR = a.lance_dir
    rm.RAG_DIR = os.path.join(a.lance_dir, "rag")
    rm._PAGES_DIR = Path(a.lance_dir) / "rag_pages"
    rm._db = None
    _patch_fusion(rm, a.fusion)

    qset = yaml.safe_load(Path(a.queries).read_text())["queries"]
    if a.categories:
        want = set(a.categories.split(","))
        qset = [q for q in qset if q["category"] in want]

    ingest_info = {"skipped": True}
    if not a.reuse or not (Path(a.lance_dir) / "rag" / f"kb_{a.kb_id}.lance").exists():
        t0 = time.time()
        ingest_info = await _ingest(rm, a.kb_id, Path(a.corpus))
        ingest_info["_ingest_s"] = round(time.time() - t0, 1)
        print("ingest:", json.dumps(ingest_info))

    rows = [await _run_query(rm, a.kb_id, q, a.top_k) for q in qset]
    per_cat: dict[str, list] = {}
    for r in rows:
        per_cat.setdefault(r["category"], []).append(r)

    summary = {}
    for cat, rs in sorted(per_cat.items()):
        n = len(rs)
        lat = sorted(r.get("latency_s", 0.0) for r in rs)
        summary[cat] = {
            "n": n,
            "recall@1": round(sum(r["hit@1"] for r in rs) / n, 3),
            "recall@5": round(sum(r["hit@5"] for r in rs) / n, 3),
            "mrr": round(sum(r["rr"] for r in rs) / n, 3),
            "latency_s_median": lat[n // 2],
            "latency_s_mean": round(sum(lat) / n, 2),
        }
    out = {
        "fusion": a.fusion,
        "corpus": str(a.corpus),
        "n_docs": ingest_info.get("files_ingested"),
        "ingest": ingest_info,
        "summary": summary,
        "rows": rows,
    }
    print("\n" + json.dumps(summary, indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=2))
        print("wrote", a.out)


if __name__ == "__main__":
    asyncio.run(main())
