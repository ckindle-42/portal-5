"""Shared probe helpers: fixtures, legacy-embedder access, threshold sweeps, retrieval A/B."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Sequence
from typing import Any

from portal.platform.embedding.contract import Role, Task

from ..framework import (
    REPO_ROOT,
    ProbeContext,
    mrr,
    recall_at_k,
    top_k_by_cosine,
)

DATA = REPO_ROOT / "tests" / "data" / "embedding_consumers"
_WORD = re.compile(r"[a-z0-9']+")

# The :8917 (MLX Qwen3-Embedding-0.6B) incumbent arm was retired at the EG2 cutover
# (launchd service removed; EG2_CUTOVER.md "Retired"). Its recorded results are frozen
# here from the committed scorecards so the probes still run -- and still report the
# historical comparison -- without a live :8917 call. A probe side-by-side against a
# fresh candidate run is therefore a same-fixture comparison against a FIXED arm, not a
# fresh paired run; the original paired runs are cited per entry.
HISTORICAL_ARMS: dict[str, dict[str, Any]] = {
    # reports/embedding_consumers/20261007T224205Z/results.json (EG2_CUTOVER.md "Switched")
    "memory_recall": {
        "primary": 0.95,
        "recall@1": 0.8,
        "recall@4": 0.95,
        "recall@5": 0.975,
        "mrr": 0.8696,
        "provenance": "reports/embedding_consumers/20261007T224205Z (live :8917 arm)",
    },
    # reports/embedding_consumers/20261007T220949Z/results.json memory_dedup candidate block
    "memory_dedup": {
        "legacy_8917_at_fp<=2pct": {"recall": 0.75, "fp_rate": 0.0, "threshold": 0.8893},
        "legacy_8917_auc": 0.9838,
        "provenance": "reports/embedding_consumers/20261007T220949Z (live :8917 arm)",
    },
    # reports/embedding_consumers/20261008T021720Z/results.json qwen3_8917 arm
    "owui_attachment_rag": {
        "primary": 0.6383,
        "dense_only": {"recall@3": 0.7021},
        "hybrid_no_rerank": {"recall@3": 0.6383},
        "hybrid_bge": {"recall@3": 0.6383},
        "hybrid_vl_rerank": {"recall@3": 0.7021},
        "provenance": "reports/embedding_consumers/20261008T021720Z (live :8917 arm)",
    },
    # reports/embedding_consumers/20261008T164221Z/results.json arm-a (V3, blind)
    "bully_projection": {
        "primary": 139,
        "status": "VALID",
        "discovery_precision": 0.403846,
        "discovery_recall_proxy": 1.0,
        "controls_passed": True,
        "provenance": "reports/embedding_consumers/20261008T164221Z (live :8917 arm)",
    },
}


def historical_incumbent(probe: str) -> dict[str, Any]:
    """The retired :8917 arm's recorded block for `probe`, provenance-stamped."""
    block = dict(HISTORICAL_ARMS[probe])
    block["historical"] = True
    return block


_STOP = frozenset(
    [
        "the",
        "a",
        "an",
        "of",
        "to",
        "for",
        "and",
        "or",
        "in",
        "on",
        "at",
        "is",
        "are",
        "my",
        "i",
        "me",
        "what",
        "how",
        "do",
        "does",
        "it",
        "with",
        "that",
        "this",
        "be",
        "can",
        "should",
        "you",
        "your",
        "from",
        "by",
        "as",
        "was",
        "were",
        "has",
        "have",
        "had",
        "not",
        "no",
    ]
)


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((DATA / name).read_text())


def content_words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2}


def overlap(query: str, target: str) -> float:
    q = content_words(query)
    return len(q & content_words(target)) / len(q) if q else 0.0


def cos(a: Sequence[float], b: Sequence[float]) -> float:
    d = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return d / (na * nb) if na and nb else 0.0


def threshold_sweep(
    pos: Sequence[float], neg: Sequence[float], *, fp_budget: float
) -> dict[str, float]:
    """Best recall on ``pos`` while the false-positive rate on ``neg`` stays <= fp_budget."""
    best = {"recall": 0.0, "fp_rate": 0.0, "threshold": float("inf")}
    for t in sorted(set(pos) | set(neg), reverse=True):
        fp = sum(n >= t for n in neg) / len(neg) if neg else 0.0
        if fp > fp_budget:
            continue
        rec = sum(p >= t for p in pos) / len(pos) if pos else 0.0
        if rec > best["recall"] or (
            rec == best["recall"] and t > best["threshold"] and fp <= best["fp_rate"]
        ):
            best = {"recall": rec, "fp_rate": fp, "threshold": t}
    return {k: round(v, 4) for k, v in best.items()}


def best_f1(scores: Sequence[float], gold: Sequence[bool]) -> dict[str, float]:
    best = {"f1": 0.0, "precision": 0.0, "recall": 0.0, "threshold": 0.0}
    for t in sorted(set(scores)):
        tp = sum(s >= t and g for s, g in zip(scores, gold, strict=True))
        fp = sum(s >= t and not g for s, g in zip(scores, gold, strict=True))
        fn = sum(s < t and g for s, g in zip(scores, gold, strict=True))
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f = 2 * p * r / (p + r) if p + r else 0.0
        if f > best["f1"]:
            best = {"f1": f, "precision": p, "recall": r, "threshold": t}
    return {k: round(v, 4) for k, v in best.items()}


def binary_prf(pred: Sequence[bool], gold: Sequence[bool]) -> dict[str, float]:
    tp = sum(p and g for p, g in zip(pred, gold, strict=True))
    fp = sum(p and not g for p, g in zip(pred, gold, strict=True))
    fn = sum((not p) and g for p, g in zip(pred, gold, strict=True))
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
    return {"f1": round(f1, 4), "precision": round(pr, 4), "recall": round(rc, 4)}


def auc_roc(pos: Sequence[float], neg: Sequence[float]) -> float:
    if not pos or not neg:
        return 0.0
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 4)


async def retrieval_ab(
    ctx: ProbeContext,
    queries: Sequence[str],
    gold: Sequence[Sequence[str]],
    doc_ids: Sequence[str],
    doc_texts: Sequence[str],
    *,
    incumbent_rank: Callable[[int], list[str]] | None = None,
    dim: int = 768,
    task: Task = Task.SEARCH,
    k: int = 10,
) -> dict[str, Any]:
    """Recall@1/5 and MRR for the EG2 SEARCH path (the only live embedder) plus an optional
    non-embedding incumbent (``incumbent_rank``, e.g. a lexical baseline; the retired :8917
    embedder arm is frozen in ``HISTORICAL_ARMS`` instead of computed)."""
    dvecs = await ctx.client.embed_texts(list(doc_texts), task=task, role=Role.DOCUMENT, dim=dim)
    docs = dict(zip(doc_ids, dvecs, strict=True))
    qvecs = await ctx.client.embed_texts(list(queries), task=task, role=Role.QUERY, dim=dim)
    cand = [top_k_by_cosine(v, docs, k) for v in qvecs]
    inc = [incumbent_rank(i) for i in range(len(queries))] if incumbent_rank else None
    rel = [list(g) for g in gold]

    def m(ranked: list[list[str]]) -> dict[str, float]:
        return {
            "recall@1": round(recall_at_k(ranked, rel, 1), 4),
            "recall@4": round(recall_at_k(ranked, rel, 4), 4),
            "recall@5": round(recall_at_k(ranked, rel, 5), 4),
            "mrr": round(mrr(ranked, rel), 4),
        }

    return {"candidate": m(cand), **({"incumbent": m(inc)} if inc is not None else {})}
