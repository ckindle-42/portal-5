"""review_eval.selftest -- a harness that cannot tell an oracle from a coin flip must not ship numbers.

No harness in this lab has ever passed a known-answer test. This one runs before any report is
written (``report.build_report`` refuses without a passing result bound to the same stamp):

* oracle        -- scores equal the labels            -> every metric must be perfect
* inverted      -- scores opposite the labels         -> AUROC must be zero
* constant      -- every unit scores the same         -> chance AUROC and nothing raised
* random        -- scores independent of the labels   -> chance, within a sampling bound
* planted       -- noise, plus a clear lift on needles -> the needles must be found
* benign-quiet  -- an alpha-calibrated threshold applied to fresh benign scores must not raise
                   more than alpha (plus sampling noise)

``measure`` is the harness's own metric function, so a broken or rigged ``measure`` fails here.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from math import sqrt
from typing import Any

from ..review import calibration as calibration_mod
from .metrics import auroc, precision_at_n, recall_at_fpr

Measure = Callable[[Sequence[float], Sequence[bool]], Mapping[str, float]]

EPS = 1e-12


def default_measure(scores: Sequence[float], labels: Sequence[bool]) -> dict[str, float]:
    pos = [s for s, lab in zip(scores, labels, strict=True) if lab]
    neg = [s for s, lab in zip(scores, labels, strict=True) if not lab]
    return {
        "auroc": auroc(pos, neg),
        "recall_at_5pct_fpr": recall_at_fpr(pos, neg, 0.05),
        "precision_at_npos": precision_at_n(scores, labels, len(pos)),
    }


@dataclass(frozen=True)
class SelfTestResult:
    passed: bool
    stamp_digest: str
    checks: dict[str, dict[str, Any]]


def _check(name: str, ok: bool, **detail: Any) -> tuple[str, dict[str, Any]]:
    return name, {"passed": bool(ok), **detail}


def run_selftest(
    measure: Measure = default_measure,
    *,
    stamp_digest: str,
    seed: int = 20261008,
    n_pos: int = 200,
    n_neg: int = 800,
) -> SelfTestResult:
    rng = random.Random(seed)
    labels = [True] * n_pos + [False] * n_neg
    prevalence = n_pos / (n_pos + n_neg)
    auc_sd = sqrt((n_pos + n_neg + 1) / (12.0 * n_pos * n_neg))
    prec_sd = sqrt(prevalence * (1 - prevalence) / n_pos)
    checks: list[tuple[str, dict[str, Any]]] = []

    m = measure([1.0] * n_pos + [0.0] * n_neg, labels)
    checks.append(
        _check(
            "oracle",
            m["auroc"] >= 1 - EPS
            and m["recall_at_5pct_fpr"] >= 1 - EPS
            and m["precision_at_npos"] >= 1 - EPS,
            measured=dict(m),
        )
    )

    m = measure([0.0] * n_pos + [1.0] * n_neg, labels)
    checks.append(_check("inverted", m["auroc"] <= EPS, measured=dict(m)))

    m = measure([0.5] * len(labels), labels)
    checks.append(
        _check(
            "constant",
            abs(m["auroc"] - 0.5) <= EPS and m["recall_at_5pct_fpr"] <= EPS,
            measured=dict(m),
        )
    )

    m = measure([rng.random() for _ in labels], labels)
    checks.append(
        _check(
            "random",
            abs(m["auroc"] - 0.5) <= 4 * auc_sd
            and abs(m["precision_at_npos"] - prevalence) <= 4 * prec_sd,
            measured=dict(m),
            auc_bound=4 * auc_sd,
        )
    )

    noise = [rng.gauss(0.0, 1.0) for _ in labels]
    planted = [v + (4.0 if lab else 0.0) for v, lab in zip(noise, labels, strict=True)]
    m = measure(planted, labels)
    checks.append(
        _check(
            "planted",
            m["auroc"] >= 0.99 and m["recall_at_5pct_fpr"] >= 0.95,
            measured=dict(m),
        )
    )

    alpha = 0.05
    null = [rng.random() for _ in range(2000)]
    threshold = calibration_mod.conformal_threshold(null[:1000], alpha)
    fresh = null[1000:]
    realized = sum(1 for s in fresh if s > threshold) / len(fresh)
    bound = alpha + 4 * sqrt(alpha * (1 - alpha) / len(fresh))
    checks.append(_check("benign_quiet", realized <= bound, realized=realized, bound=bound))

    result = dict(checks)
    return SelfTestResult(
        passed=all(c["passed"] for c in result.values()),
        stamp_digest=stamp_digest,
        checks=result,
    )
