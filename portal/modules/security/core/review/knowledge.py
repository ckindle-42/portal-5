"""review.knowledge -- what is KNOWN, and how close a unit is to it.

Knowledge plane: anchors are the one place a label may live (an ATT&CK id, a detection id, an
advisory, an analyst's "benign"), because they describe a known *thing*, never the thing under
review. Retrieval is cosine similarity of content cards (``intake.unit_card``) under whatever
embedder is configured -- the embedder's scale never decides anything: the funnel compares the
best similarity against a benign null distribution (``calibration``).

An anchor card is built by the SAME function that builds a unit card (an anchor is just a unit
somebody already understood), so retrieval compares like with like.

Pure compute apart from the injected embedder; brute-force cosine in numpy (anchors number in
the thousands, not millions).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

from ..bully import artifact_graph as ag
from ..bully import unit_relation

Vec = NDArray[np.float32]


class Embedder(Protocol):
    """Anything that turns texts into vectors and names itself (model + dimension + task)."""

    identity: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class AnchorCard:
    anchor_id: str
    kind: str
    label: str
    malice: str
    text: str
    record: Mapping[str, Any]


def record_from_unit(unit: ag.GradeableUnit, terms: Sequence[str], card: str) -> dict[str, Any]:
    """The record shape ``unit_relation.grade_unit_against_type`` grades against."""
    return {
        "action_sequence": list(unit.vocabulary),
        "event_graph": dict(unit.structural_signature),
        "parameter_families": list(unit.entities),
        "terms": list(terms),
        "card": card,
    }


def _fallback_text(record: Mapping[str, Any]) -> str:
    seq = " ".join(str(v) for v in record.get("action_sequence") or ())
    ctx = " ".join(f"{k} {v}" for k, v in (record.get("context") or {}).items())
    return f"{seq} {ctx}".strip()


def anchor_label(record: Mapping[str, Any], default: str) -> str:
    for key in ("label", "technique_ids", "techniques", "technique", "detection_id", "name"):
        value = record.get(key)
        if value:
            return (
                ", ".join(str(v) for v in value) if isinstance(value, (list, tuple)) else str(value)
            )
    return default


def cards_from_anchors(anchors: Sequence[Any]) -> list[AnchorCard]:
    """``AnchorCard`` per ``bully.anchors.Anchor``; quarantined anchors are not knowledge."""
    cards: list[AnchorCard] = []
    for anchor in anchors:
        if getattr(anchor, "quarantined", False):
            continue
        record = anchor.record
        text = str(record.get("card") or _fallback_text(record))
        if not text:
            continue
        cards.append(
            AnchorCard(
                anchor_id=anchor.anchor_id,
                kind=anchor.kind,
                label=anchor_label(record, anchor.anchor_id),
                malice=anchor.malice,
                text=text,
                record=record,
            )
        )
    return cards


def embed_texts(embedder: Embedder, texts: Sequence[str], *, batch: int = 64) -> Vec:
    """Embed ``texts`` and L2-normalize, so a dot product is a cosine."""
    rows: list[list[float]] = []
    for start in range(0, len(texts), batch):
        rows.extend(embedder.embed(list(texts[start : start + batch])))
    if not rows:
        return np.zeros((0, 0), dtype=np.float32)
    matrix = np.asarray(rows, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    out: Vec = matrix / norms
    return out


class AnchorIndex:
    def __init__(self, cards: Sequence[AnchorCard], matrix: Vec, embedder_id: str) -> None:
        if len(cards) != matrix.shape[0]:
            raise ValueError("cards and matrix disagree on population")
        self.cards = list(cards)
        self.matrix = matrix
        self.embedder_id = embedder_id

    @classmethod
    def build(cls, cards: Sequence[AnchorCard], embedder: Embedder) -> AnchorIndex:
        matrix = embed_texts(embedder, [c.text for c in cards])
        return cls(cards, matrix, embedder.identity)

    @property
    def population(self) -> int:
        return len(self.cards)

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted({c.kind for c in self.cards}))

    def search(
        self,
        queries: Vec,
        *,
        k: int = 5,
        exclude: Sequence[frozenset[str]] | None = None,
    ) -> list[list[tuple[AnchorCard, float]]]:
        """Top-``k`` anchors per query row, best first. ``exclude[i]`` lists anchor ids that
        may not answer query ``i`` (an anchor must never retrieve itself)."""
        if self.population == 0 or queries.shape[0] == 0:
            return [[] for _ in range(queries.shape[0])]
        sims = queries @ self.matrix.T
        out: list[list[tuple[AnchorCard, float]]] = []
        for row in range(sims.shape[0]):
            banned = exclude[row] if exclude is not None else frozenset()
            order = np.argsort(-sims[row])
            picked: list[tuple[AnchorCard, float]] = []
            for idx in order:
                card = self.cards[int(idx)]
                if card.anchor_id in banned:
                    continue
                picked.append((card, float(sims[row, idx])))
                if len(picked) >= k:
                    break
            out.append(picked)
        return out


def explain(
    unit: ag.GradeableUnit, anchor_record: Mapping[str, Any]
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """(structural relation, shares, diverges) for the explanation -- never the decision.

    The relation is ``unit_relation``'s EXACT / SIMILAR / ... on shape and vocabulary; it is
    structure-based and carries no embedder scale."""
    relation = unit_relation.grade_unit_against_type(unit, dict(anchor_record))
    shares = tuple(relation.shape.shared_tokens) + tuple(relation.vocabulary.shared_tokens)
    diverges = tuple(relation.shape.diverging_tokens) + tuple(relation.vocabulary.diverging_tokens)
    return str(relation.overall_relation), shares, diverges
