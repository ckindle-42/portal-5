"""review_eval.metrics -- metrics that can fail, and the paired tests that decide adoption.

Pure Python, no I/O. Conventions: a higher score means "more concerning"; a unit is *raised*
iff its score is strictly greater than the threshold (ties are not raised, so a constant scorer
raises nothing and cannot look good by accident).

Headline pair, never averaged together: recall at a stated false-raise rate (how much of what
matters is found at what benign cost), and false-raise per 1,000 benign units. Precision is
only meaningful with negatives present -- ``report`` refuses a precision-like metric over rows
with none.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from math import comb, floor, inf


def auroc(pos: Sequence[float], neg: Sequence[float]) -> float:
    """Probability a random positive outscores a random negative (ties count half)."""
    if not pos or not neg:
        return float("nan")
    ordered = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    n = len(ordered)
    rank_sum = 0.0
    i = 0
    while i < n:
        j = i
        while j < n and ordered[j][0] == ordered[i][0]:
            j += 1
        average_rank = (i + 1 + j) / 2.0
        rank_sum += average_rank * sum(label for _v, label in ordered[i:j])
        i = j
    n_pos, n_neg = len(pos), len(neg)
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def threshold_at_fpr(neg: Sequence[float], fpr: float) -> float:
    """Smallest threshold ``t`` with ``frac(neg > t) <= fpr`` (``-inf`` if everything may pass)."""
    if not neg:
        return -inf
    ordered = sorted(neg, reverse=True)
    k = floor(fpr * len(ordered) + 1e-9)
    return ordered[k] if k < len(ordered) else -inf


def recall_at_fpr(pos: Sequence[float], neg: Sequence[float], fpr: float) -> float:
    if not pos:
        return float("nan")
    t = threshold_at_fpr(neg, fpr)
    return sum(1 for p in pos if p > t) / len(pos)


def recall_fpr_curve(
    pos: Sequence[float], neg: Sequence[float], fprs: Sequence[float]
) -> list[tuple[float, float]]:
    return [(f, recall_at_fpr(pos, neg, f)) for f in fprs]


def precision_at_n(scores: Sequence[float], labels: Sequence[bool], n: int) -> float:
    if n <= 0 or len(scores) != len(labels):
        raise ValueError("precision_at_n needs n > 0 and aligned scores/labels")
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))[:n]
    return sum(1 for i in order if labels[i]) / len(order)


def false_raise_per_1k(raised_benign: int, benign_total: int) -> float:
    if benign_total <= 0:
        raise ValueError("false-raise rate needs benign units in the denominator")
    return 1000.0 * raised_benign / benign_total


def paired_discordant(a_hits: Sequence[bool], b_hits: Sequence[bool]) -> tuple[int, int]:
    """(only A hit, only B hit) over the same items."""
    if len(a_hits) != len(b_hits):
        raise ValueError("paired comparison needs the same items in both arms")
    a_only = sum(1 for a, b in zip(a_hits, b_hits, strict=True) if a and not b)
    b_only = sum(1 for a, b in zip(a_hits, b_hits, strict=True) if b and not a)
    return a_only, b_only


def exact_mcnemar_p(a_only: int, b_only: int) -> float:
    """Two-sided exact McNemar over the discordant pairs."""
    n = a_only + b_only
    if n == 0:
        return 1.0
    k = min(a_only, b_only)
    tail = sum(comb(n, i) for i in range(k + 1)) / (1 << n)
    return min(1.0, 2.0 * tail)


def bootstrap_ci(
    values: Sequence[float],
    *,
    stat: Callable[[Sequence[float]], float] | None = None,
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float]:
    """Seeded percentile bootstrap CI (the mean unless ``stat`` is given)."""
    if not values:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    fn = stat or (lambda xs: sum(xs) / len(xs))
    n = len(values)
    draws = sorted(fn([values[rng.randrange(n)] for _ in range(n)]) for _ in range(n_boot))
    lo = draws[floor((alpha / 2) * n_boot)]
    hi = draws[min(n_boot - 1, floor((1 - alpha / 2) * n_boot))]
    return (lo, hi)


def youden_point(points: Sequence[tuple[float, float]], *, max_fpr: float) -> tuple[float, float]:
    """The (fpr, recall) point maximizing recall - fpr subject to fpr <= max_fpr: a parameter-
    free operating point. Raises if no point is admissible."""
    admissible = [(f, r) for f, r in points if f <= max_fpr]
    if not admissible:
        raise ValueError(f"no operating point at or under fpr {max_fpr}")
    return max(admissible, key=lambda fr: (fr[1] - fr[0], -fr[0]))


def twin_aware_hit(
    predicted_anchor: str, truth_anchors: set[str], twin_groups: Mapping[str, str]
) -> bool:
    """A hit if the predicted anchor is a truth anchor OR an evidence twin of one (identical
    evidence under another label). Twins are reported separately by the caller."""
    group = twin_groups.get(predicted_anchor, predicted_anchor)
    return predicted_anchor in truth_anchors or any(
        twin_groups.get(t, t) == group for t in truth_anchors
    )
