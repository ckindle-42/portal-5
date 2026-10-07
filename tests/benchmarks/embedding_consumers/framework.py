"""Framework: consumer ledger, probe registry, metrics, result writing.

A probe compares the INCUMBENT path (what Portal does today, called through the
real code where possible) with the CANDIDATE path (EmbeddingGemma 2 via
``portal.platform.embedding``) on the same fixture, and reports both. The
harness never decides adoption: ``hint`` is advisory input to the per-consumer
[GATE] in Phase 4.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_DIR = REPO_ROOT / "reports" / "embedding_consumers"

MEASURED, BLOCKED, ERROR, NOT_IMPLEMENTED = "MEASURED", "BLOCKED", "ERROR", "NOT_IMPLEMENTED"


@dataclass(frozen=True)
class Consumer:
    id: str
    area: str
    title: str
    incumbent: str
    primary_metric: str
    kind: str  # collapse | upgrade | new | fix-verify


#: The collapse ledger. Order is presentation order in the scorecard. Adding a
#: consumer here without a probe makes the run report NOT_IMPLEMENTED (gate FAIL).
CONSUMERS: tuple[Consumer, ...] = (
    Consumer(
        "router",
        "inference",
        "Workspace auto-routing",
        "keyword layer + pinned abliterated gemma-4-E4B LLM router",
        "accuracy",
        "collapse",
    ),
    Consumer(
        "harmful_intent",
        "inference",
        "Harmful-intent gate",
        "121-keyword substring gate + abliterated LLM posture field",
        "recall_harmful@fp_budget",
        "collapse",
    ),
    Consumer(
        "tool_preselect",
        "inference",
        "Tool-schema preselection",
        "dormant 1-2B LLM preselector (P5-TOOLPRESELECT-001, exhausted)",
        "recall@k",
        "collapse",
    ),
    Consumer(
        "memory_recall_floor",
        "inference",
        "Auto memory/RAG injection relevance floor",
        "top-4 recall injected every turn, no floor; AUTO_RAG off",
        "precision_injected",
        "upgrade",
    ),
    Consumer(
        "memory_salience",
        "inference",
        "Memory write-back salience",
        "_WRITEBACK_MARKERS (10 literal phrases)",
        "f1",
        "upgrade",
    ),
    Consumer(
        "memory_dedup",
        "inference",
        "Memory near-duplicate suppression",
        "none (memory_writeback_all comment assumes dedup that does not exist)",
        "dup_suppression_at_fp",
        "new",
    ),
    Consumer(
        "memory_entities",
        "inference",
        "Graph-memory entity resolution",
        "exact normalized name; stored entity vectors unused",
        "merge_precision/recall",
        "upgrade",
    ),
    Consumer(
        "memory_recall",
        "inference",
        "Graph-memory recall quality",
        ":8917 embedder (identity ambiguous: Qwen3 vs Harrier)",
        "recall@4",
        "collapse",
    ),
    Consumer(
        "rag_first_stage",
        "retrieval",
        "RAG MCP first-stage retrieval (text + page images)",
        "Qwen3-VL-Embedding-2B 2048d",
        "recall@20 + final nDCG",
        "collapse",
    ),
    Consumer(
        "compliance_retrieval",
        "retrieval",
        "Compliance findability + candidate links",
        "Qwen3-VL-Embedding-2B (cached) + VL rerank, calibrated threshold",
        "findability parity",
        "collapse",
    ),
    Consumer(
        "compliance_crosswalk",
        "retrieval",
        "Cross-framework crosswalk candidates",
        "35-row partial seed, hand-curated",
        "seed recall@k",
        "new",
    ),
    Consumer(
        "owui_attachment_rag",
        "retrieval",
        "Open WebUI attachment RAG + reranker",
        ":8917 embedder + bge-reranker-v2-m3 on CPU in the OWUI container",
        "recall@k",
        "collapse",
    ),
    Consumer(
        "unified_recall",
        "retrieval",
        "Unified recall over KBs, memory and ~/AI_Output",
        "none (generated media unindexed; memory and KB in separate spaces)",
        "cross-modal recall@5",
        "new",
    ),
    Consumer(
        "audio_recordings",
        "retrieval",
        "Audio retrieval: native audio + ASR fusion",
        "transcript-only (Qwen3-ASR)",
        "recall@5",
        "new",
    ),
    Consumer(
        "wiki_search",
        "retrieval",
        "wiki_search (Rule 13 discovery index)",
        "substring keyword score over canonical units",
        "self-retrieval recall@5",
        "upgrade",
    ),
    Consumer(
        "refusal_classifier",
        "security",
        "Refusal/spiral detection",
        "4 phrase lists (REFUSAL_PHRASES imported by 30+ files)",
        "f1",
        "collapse",
    ),
    Consumer(
        "field_journal",
        "security",
        "Field-journal episodic recall",
        "keyword substring count",
        "recall@5",
        "upgrade",
    ),
    Consumer(
        "attack_mapping",
        "security",
        "Behavior -> ATT&CK technique (Enterprise subset + ICS)",
        "ID lookup only; substring over SPL library descriptions",
        "recall@5",
        "new",
    ),
    Consumer(
        "spl_library",
        "security",
        "SPL library search + diff hypothesis",
        "substring match; word-set overlap",
        "recall@5",
        "upgrade",
    ),
    Consumer(
        "ics_advisories",
        "security",
        "ICS advisory <-> asset product matching",
        "vendor string match",
        "recall@5",
        "upgrade",
    ),
    Consumer(
        "bully_projection",
        "security",
        "Bully hunt-memory projection",
        "Arm A MLX Qwen3-Embedding-0.6B (adopted P0.4)",
        "discovery precision (identity diagnostic classified)",
        "collapse",
    ),
    Consumer(
        "bully_novelty",
        "security",
        "Novelty channel for ANOMALOUS_UNCLASSIFIED",
        "none",
        "AUC benign-vs-novel",
        "new",
    ),
    Consumer(
        "vuln_severity",
        "security",
        "classify_vulnerability severity",
        "CIRCL VLAI RoBERTa in the security MCP",
        "macro_f1",
        "collapse",
    ),
    Consumer(
        "binary_similarity", "security", "Decompiled-function similarity", "none", "recall@5", "new"
    ),
    Consumer(
        "media_alignment",
        "measurement",
        "Image/video/music prompt adherence + edit adherence",
        "HTTP 200 / job completed",
        "rank1_vs_shuffled",
        "new",
    ),
    Consumer(
        "cad_resemblance",
        "measurement",
        "CAD render resemblance axis",
        "compiles/watertight/volume only",
        "rank1_vs_shuffled",
        "new",
    ),
    Consumer(
        "assertion_coverage",
        "measurement",
        "Semantic coverage channel for phrase assertions",
        "phrase lists, quality_signals substrings, WFE transcript_contains",
        "agreement_with_judge",
        "upgrade",
    ),
    Consumer(
        "fleet_behavior",
        "measurement",
        "Behavioral overlap over WFE in-lane transcripts",
        "metadata net-new (arch/vendor/flags)",
        "evidence only (no verdict)",
        "new",
    ),
    Consumer(
        "failure_clustering",
        "measurement",
        "Failure-mode clustering + adaptive UAT diversity",
        "none",
        "cluster purity",
        "new",
    ),
    Consumer(
        "config_lint",
        "hygiene",
        "Confusable workspaces / personas / tools",
        "none",
        "flag precision",
        "new",
    ),
    Consumer(
        "doc_affinity",
        "hygiene",
        "Wiki units semantically bound to changed code + duplicate units",
        "cited-path binding only",
        "recall of known-stale units",
        "new",
    ),
    Consumer(
        "data_schema_linking",
        "companion",
        "Data MCP question -> table/column",
        "none (model reads schemas)",
        "recall@3",
        "new",
    ),
    Consumer(
        "generation_dedup",
        "companion",
        "Pre-generation near-duplicate check",
        "none",
        "precision@threshold",
        "new",
    ),
)
CONSUMER_IDS = tuple(c.id for c in CONSUMERS)


@dataclass
class ProbeResult:
    consumer: str
    status: str
    incumbent: dict[str, Any] = field(default_factory=dict)
    candidate: dict[str, Any] = field(default_factory=dict)
    hint: str = "INCONCLUSIVE"  # BETTER | PARITY | WORSE | INCONCLUSIVE
    notes: list[str] = field(default_factory=list)
    blocked_reason: str = ""
    fixture: dict[str, Any] = field(default_factory=dict)
    identity: str = ""
    seconds: float = 0.0


ProbeFn = Callable[["ProbeContext"], Awaitable[ProbeResult]]
_REGISTRY: dict[str, ProbeFn] = {}


def probe(consumer_id: str) -> Callable[[ProbeFn], ProbeFn]:
    if consumer_id not in CONSUMER_IDS:
        raise KeyError(f"{consumer_id!r} is not in the consumer ledger")

    def deco(fn: ProbeFn) -> ProbeFn:
        if consumer_id in _REGISTRY:
            raise KeyError(f"duplicate probe for {consumer_id!r}")
        _REGISTRY[consumer_id] = fn
        return fn

    return deco


def registry() -> dict[str, ProbeFn]:
    return dict(_REGISTRY)


@dataclass
class ProbeContext:
    client: Any  # EmbeddingClient (or a fake in unit tests)
    live: bool = False  # True: probes may call live services (Ollama, MCPs, OWUI)
    options: dict[str, Any] = field(default_factory=dict)

    def opt(self, key: str, default: Any = None) -> Any:
        return self.options.get(key, default)


def blocked(consumer: str, reason: str, **kw: Any) -> ProbeResult:
    return ProbeResult(consumer=consumer, status=BLOCKED, blocked_reason=reason, **kw)


# ── fixtures ────────────────────────────────────────────────────────────────
def fixture_digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ── metrics ─────────────────────────────────────────────────────────────────
def accuracy(pred: Sequence[Any], gold: Sequence[Any]) -> float:
    return sum(p == g for p, g in zip(pred, gold, strict=True)) / len(gold) if gold else 0.0


def macro_f1(pred: Sequence[Any], gold: Sequence[Any]) -> float:
    labels = sorted({g for g in gold if g is not None}, key=str)
    if not labels:
        return 0.0
    f1s = []
    for lab in labels:
        tp = sum(p == lab and g == lab for p, g in zip(pred, gold, strict=True))
        fp = sum(p == lab and g != lab for p, g in zip(pred, gold, strict=True))
        fn = sum(p != lab and g == lab for p, g in zip(pred, gold, strict=True))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
    return sum(f1s) / len(f1s)


def recall_at_k(
    ranked: Sequence[Sequence[Any]], relevant: Sequence[Iterable[Any]], k: int
) -> float:
    hits = 0
    for r, rel in zip(ranked, relevant, strict=True):
        if set(r[:k]) & set(rel):
            hits += 1
    return hits / len(relevant) if relevant else 0.0


def mrr(ranked: Sequence[Sequence[Any]], relevant: Sequence[Iterable[Any]]) -> float:
    total = 0.0
    for r, rel in zip(ranked, relevant, strict=True):
        rs = set(rel)
        for i, x in enumerate(r, 1):
            if x in rs:
                total += 1.0 / i
                break
    return total / len(relevant) if relevant else 0.0


def auc(pos_scores: Sequence[float], neg_scores: Sequence[float]) -> float:
    if not pos_scores or not neg_scores:
        return 0.0
    wins = sum((p > n) + 0.5 * (p == n) for p in pos_scores for n in neg_scores)
    return wins / (len(pos_scores) * len(neg_scores))


def percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, max(0, math.ceil(q / 100 * len(s)) - 1))]


def top_k_by_cosine(qvec: Sequence[float], docs: dict[str, Sequence[float]], k: int) -> list[str]:
    """Docs are L2-normalized service vectors, so dot == cosine. numpy when
    available (the project venv has it; this is harness code, not pipeline)."""
    ids = list(docs)
    try:
        import numpy as np

        m = np.asarray([docs[i] for i in ids], dtype=np.float32)
        order = np.argsort(-(m @ np.asarray(qvec, dtype=np.float32)), kind="stable")[:k]
        return [ids[int(j)] for j in order]
    except ImportError:
        scored = sorted(ids, key=lambda i: -sum(a * b for a, b in zip(qvec, docs[i], strict=True)))
        return scored[:k]


def compare(
    incumbent: float, candidate: float, *, parity_band: float = 0.02, higher_is_better: bool = True
) -> str:
    delta = (candidate - incumbent) if higher_is_better else (incumbent - candidate)
    if abs(delta) <= parity_band:
        return "PARITY"
    return "BETTER" if delta > 0 else "WORSE"


class Stopwatch:
    def __init__(self) -> None:
        self.samples_ms: list[float] = []

    def time(self) -> _Lap:
        return _Lap(self)

    def summary(self) -> dict[str, float]:
        return {
            "p50_ms": round(percentile(self.samples_ms, 50), 2),
            "p95_ms": round(percentile(self.samples_ms, 95), 2),
        }


class _Lap:
    def __init__(self, sw: Stopwatch) -> None:
        self.sw = sw

    def __enter__(self) -> _Lap:
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self.sw.samples_ms.append((time.perf_counter() - self.t0) * 1000)


# ── run + write ─────────────────────────────────────────────────────────────
async def run(ids: Sequence[str], ctx: ProbeContext) -> list[ProbeResult]:
    reg = registry()
    out: list[ProbeResult] = []
    for cid in ids:
        fn = reg.get(cid)
        t0 = time.perf_counter()
        if fn is None:
            res = ProbeResult(consumer=cid, status=NOT_IMPLEMENTED, notes=["no probe registered"])
        else:
            try:
                res = await fn(ctx)
            except Exception as e:  # noqa: BLE001 - a probe crash is a recorded ERROR, never a skip
                res = ProbeResult(consumer=cid, status=ERROR, notes=[f"{type(e).__name__}: {e}"])
        res.seconds = round(time.perf_counter() - t0, 2)
        out.append(res)
    return out


def gate_ok(results: Sequence[ProbeResult]) -> bool:
    """Phase-3 completion: every ledger consumer MEASURED or BLOCKED-with-reason."""
    by = {r.consumer: r for r in results}
    return all(
        cid in by
        and (by[cid].status == MEASURED or (by[cid].status == BLOCKED and by[cid].blocked_reason))
        for cid in CONSUMER_IDS
    )


def write(results: Sequence[ProbeResult], out_dir: Path | None = None) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    d = out_dir or REPORTS_DIR / stamp
    d.mkdir(parents=True, exist_ok=True)
    (d / "results.json").write_text(json.dumps([asdict(r) for r in results], indent=2, default=str))
    meta = {c.id: c for c in CONSUMERS}
    lines = [
        f"# EmbeddingGemma 2 consumer scorecard — {stamp}",
        "",
        f"Phase-3 gate (every consumer MEASURED or BLOCKED-with-reason): **{'PASS' if gate_ok(results) else 'FAIL'}**",
        "",
        "| consumer | area | kind | status | primary metric | incumbent | candidate | hint |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        c = meta.get(r.consumer)
        pm = c.primary_metric if c else "?"
        inc = r.incumbent.get("primary", "")
        cand = r.candidate.get("primary", "")
        status = r.status + (f" ({r.blocked_reason})" if r.blocked_reason else "")
        lines.append(
            f"| {r.consumer} | {c.area if c else '?'} | {c.kind if c else '?'} | {status} | {pm} | {inc} | {cand} | {r.hint} |"
        )
    (d / "SCORECARD.md").write_text("\n".join(lines) + "\n")
    return d
