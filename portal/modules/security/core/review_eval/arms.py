"""review_eval.arms -- pre-registered, immutable arm selection for the T1 measurement."""

from __future__ import annotations

from dataclasses import dataclass

from portal.modules.security.core.review.funnel import FunnelPolicy
from portal.modules.security.core.review.pipeline import ReviewConfig


@dataclass(frozen=True)
class ArmSpec:
    name: str
    config: ReviewConfig | None
    legacy: bool = False


# These are the review package's installed test defaults, frozen before any answer-key run.
# Phase F chooses only the workload budget B from validation data; it does not alter this config.
REVIEW_D0_CONFIG = ReviewConfig(
    policy=FunnelPolicy(
        alpha_unusual=0.2,
        alpha_similar=0.2,
        levels=("L2_ENTITY", "L3_CHAIN"),
    ),
    suppress_benign="exact_only",
    top_k_anchors=3,
    judge_max=None,
)

ARMS: dict[str, ArmSpec] = {
    "legacy_funnel": ArmSpec("legacy_funnel", config=None, legacy=True),
    "review_d0": ArmSpec("review_d0", config=REVIEW_D0_CONFIG),
}


def get_arm(name: str) -> ArmSpec:
    try:
        return ARMS[name]
    except KeyError as exc:
        raise ValueError(f"unknown evaluation arm {name!r}; expected one of {tuple(ARMS)}") from exc
