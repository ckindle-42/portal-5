"""review.calibration -- thresholds fit from benign data, never typed in.

The lab's lesson, three times over: a fixed constant (a distance cap, a 0.6 gate, a 0.05
identity threshold) ends up deciding the answer, and every embedder change silently moves the
scale under it. Here a threshold is a *quantile of a benign null distribution*:

    flag a unit iff its score exceeds the (1 - alpha) conformal quantile of the scores that
    BENIGN units from a held-out calibration slice obtained.

For exchangeable benign units the false-raise rate is then at most ``alpha`` by construction
(split-conformal; no distributional assumption). ``alpha`` is an operational setting -- how
much benign noise an analyst will accept -- and is recorded with every calibration. The
embedder's scale never matters: when the embedder identity changes the similarity calibration
is stale (``CalibrationSet.stale_for``) and is simply re-fit.

Pure compute; no I/O. Observation plane: must not mention label identifiers (see ``wall``).
"""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass, field
from math import ceil
from typing import Any

SCHEMA = "review-calibration-v1"


class CalibrationInsufficient(ValueError):  # noqa: N818 -- the name is the contract
    """Too few benign calibration scores to certify the requested alpha."""


def required_n(alpha: float) -> int:
    """Smallest calibration size that can certify ``alpha`` (``ceil(1/alpha) - 1``)."""
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha!r}")
    return ceil(1.0 / alpha) - 1


def conformal_threshold(null_scores: Sequence[float], alpha: float) -> float:
    """The split-conformal ``(1 - alpha)`` quantile: the ``ceil((n+1)(1-alpha))``-th smallest."""
    n = len(null_scores)
    if n < required_n(alpha):
        raise CalibrationInsufficient(
            f"{n} benign scores cannot certify alpha={alpha}; need at least {required_n(alpha)}"
        )
    k = ceil((n + 1) * (1.0 - alpha) - 1e-9)
    return sorted(null_scores)[min(max(k, 1), n) - 1]


def empirical_p(null_sorted: Sequence[float], score: float) -> float:
    """``(#{null >= score} + 1) / (n + 1)`` -- small means surprising. Never exactly zero."""
    n = len(null_sorted)
    count_ge = n - bisect_left(null_sorted, score)
    return (count_ge + 1) / (n + 1)


def digest_scores(scores: Sequence[float]) -> str:
    joined = ",".join(f"{s:.9g}" for s in sorted(scores))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class NullCalibration:
    calibration_id: str
    channel: str
    level: str
    alpha: float
    n: int
    threshold: float
    basis: str
    embedder_id: str
    scores_digest: str
    null_sorted: tuple[float, ...] = field(repr=False, default=())

    def exceeds(self, score: float) -> bool:
        return score > self.threshold

    def p_value(self, score: float) -> float:
        return empirical_p(self.null_sorted, score)


def fit_calibration(
    channel: str,
    level: str,
    null_scores: Sequence[float],
    alpha: float,
    *,
    basis: str,
    embedder_id: str = "",
) -> NullCalibration:
    """Fit one calibration. ``basis`` says where the benign scores came from (for example
    ``"benign_slice"``); ``"self_window"`` is permitted but is labelled as such, and callers
    report it as degraded because the window under review is not a held-out benign sample."""
    threshold = conformal_threshold(null_scores, alpha)
    digest = digest_scores(null_scores)
    ident = f"{channel}|{level}|{alpha!r}|{basis}|{embedder_id}|{digest}"
    return NullCalibration(
        calibration_id=hashlib.sha256(ident.encode("utf-8")).hexdigest()[:16],
        channel=channel,
        level=level,
        alpha=alpha,
        n=len(null_scores),
        threshold=threshold,
        basis=basis,
        embedder_id=embedder_id,
        scores_digest=digest,
        null_sorted=tuple(sorted(null_scores)),
    )


def _key(channel: str, level: str) -> str:
    return f"{channel}|{level}"


@dataclass
class CalibrationSet:
    items: dict[str, NullCalibration] = field(default_factory=dict)

    def put(self, cal: NullCalibration) -> None:
        self.items[_key(cal.channel, cal.level)] = cal

    def get(self, channel: str, level: str) -> NullCalibration | None:
        return self.items.get(_key(channel, level))

    def ids(self) -> list[str]:
        return sorted(c.calibration_id for c in self.items.values())

    def stale_for(self, embedder_id: str) -> list[str]:
        """Keys of calibrations fit under a different embedder (embedder-free ones never are)."""
        return sorted(
            key
            for key, cal in self.items.items()
            if cal.embedder_id and cal.embedder_id != embedder_id
        )

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "items": {
                key: {
                    "calibration_id": c.calibration_id,
                    "channel": c.channel,
                    "level": c.level,
                    "alpha": c.alpha,
                    "n": c.n,
                    "threshold": c.threshold,
                    "basis": c.basis,
                    "embedder_id": c.embedder_id,
                    "scores_digest": c.scores_digest,
                    "null_sorted": list(c.null_sorted),
                }
                for key, c in sorted(self.items.items())
            },
        }
        return json.dumps(payload, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> CalibrationSet:
        payload = json.loads(text)
        if payload.get("schema") != SCHEMA:
            raise ValueError(f"unknown calibration schema {payload.get('schema')!r}")
        out = cls()
        for raw in payload["items"].values():
            out.put(
                NullCalibration(
                    calibration_id=raw["calibration_id"],
                    channel=raw["channel"],
                    level=raw["level"],
                    alpha=float(raw["alpha"]),
                    n=int(raw["n"]),
                    threshold=float(raw["threshold"]),
                    basis=raw["basis"],
                    embedder_id=raw["embedder_id"],
                    scores_digest=raw["scores_digest"],
                    null_sorted=tuple(float(s) for s in raw["null_sorted"]),
                )
            )
        return out
