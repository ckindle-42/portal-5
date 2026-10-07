"""Anchor-set classifier over the platform embedding service.

An anchor set is operator-editable config (``config/embedding/anchors/*.json``):
labelled example texts per class. A query is scored against each label as the
mean of its top-``k`` cosine similarities to that label's anchors; the best
label wins unless the score is below ``min_score`` or the margin to the
runner-up is below ``min_margin``, in which case the classifier ABSTAINS and
the caller keeps its existing path. Abstention is a first-class outcome: it is
how a classifier stays a no-regression addition to a fallback chain.

Pure stdlib (pipeline image). Vectors come from ``EmbeddingClient`` with the
symmetric CLASSIFICATION task, so anchors and queries share one prefix.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contract import MRL_DIMS, Role, Task, dot, parse_task


@dataclass(frozen=True)
class AnchorSet:
    name: str
    task: Task
    dim: int
    labels: dict[str, list[str]]
    min_score: float = 0.0
    min_margin: float = 0.0
    top_k: int = 3
    notes: str = ""

    def all_texts(self) -> list[str]:
        return [t for exs in self.labels.values() for t in exs]


def load_anchor_set(path: str | Path) -> AnchorSet:
    raw: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    labels = {str(k): [str(x) for x in v] for k, v in (raw.get("labels") or {}).items()}
    if not labels or any(not v for v in labels.values()):
        raise ValueError(f"{path}: every label needs at least one anchor")
    dim = int(raw.get("dim", 256))
    if dim not in MRL_DIMS:
        raise ValueError(f"{path}: dim {dim} not in {MRL_DIMS}")
    abstain = raw.get("abstain") or {}
    return AnchorSet(
        name=str(raw.get("name") or Path(path).stem),
        task=parse_task(str(raw.get("task", Task.CLASSIFICATION.value))),
        dim=dim,
        labels=labels,
        min_score=float(abstain.get("min_score", 0.0)),
        min_margin=float(abstain.get("min_margin", 0.0)),
        top_k=int(raw.get("top_k", 3)),
        notes=str(raw.get("_notes", "")),
    )


_WS = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    return _WS.sub(" ", text.strip().lower())


def leakage(anchor_texts: Iterable[str], eval_texts: Iterable[str]) -> list[str]:
    """Eval texts that also appear (whitespace/case-normalized) among anchors.
    A non-empty result invalidates a measurement — anchors must never contain
    the held-out set."""
    anchors = {normalize_text(t) for t in anchor_texts}
    return sorted({t for t in eval_texts if normalize_text(t) in anchors})


@dataclass(frozen=True)
class Decision:
    label: str | None
    score: float
    runner_up: str | None
    runner_up_score: float
    abstained: bool
    reason: str
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def margin(self) -> float:
        return self.score - self.runner_up_score


class AnchorClassifier:
    def __init__(self, anchor_set: AnchorSet, vectors: dict[str, list[list[float]]], version: str):
        self.anchor_set = anchor_set
        self.vectors = vectors
        self.version = version

    @classmethod
    async def build(cls, anchor_set: AnchorSet, client: Any) -> AnchorClassifier:
        """Embed every anchor once. ``client`` is an ``EmbeddingClient`` (typed
        loosely so tests can pass a fake)."""
        vectors: dict[str, list[list[float]]] = {}
        for label, texts in anchor_set.labels.items():
            vectors[label] = await client.embed_texts(
                texts, task=anchor_set.task, role=Role.DOCUMENT, dim=anchor_set.dim
            )
        version = await client.version_tag(anchor_set.dim)
        return cls(anchor_set, vectors, version)

    def score_labels(self, qvec: Sequence[float]) -> dict[str, float]:
        k = max(1, self.anchor_set.top_k)
        out: dict[str, float] = {}
        for label, vecs in self.vectors.items():
            sims = sorted((dot(qvec, v) for v in vecs), reverse=True)[:k]
            out[label] = sum(sims) / len(sims)
        return out

    def classify(self, qvec: Sequence[float]) -> Decision:
        scores = self.score_labels(qvec)
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        best, best_s = ranked[0]
        second, second_s = ranked[1] if len(ranked) > 1 else (None, float("-inf"))
        runner_s = second_s if second is not None else 0.0
        if best_s < self.anchor_set.min_score:
            return Decision(None, best_s, second, runner_s, True, "below_min_score", scores)
        if second is not None and best_s - second_s < self.anchor_set.min_margin:
            return Decision(None, best_s, second, runner_s, True, "below_min_margin", scores)
        return Decision(best, best_s, second, runner_s, False, "ok", scores)

    async def classify_text(self, text: str, client: Any) -> Decision:
        [qvec] = await client.embed_texts(
            [text], task=self.anchor_set.task, role=Role.QUERY, dim=self.anchor_set.dim
        )
        return self.classify(qvec)
