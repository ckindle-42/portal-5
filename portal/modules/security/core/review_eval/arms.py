"""review_eval.arms -- pre-registered, immutable review arms and reader default."""

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
    "no_reader": ArmSpec("no_reader", config=REVIEW_D0_CONFIG),
}

# T3's reader comparisons are inconclusive without an alpha curve and workload B.
# Keep the deterministic product path explicit until a reader arm is adopted.
DEFAULT_READER_ARM = "no_reader"


def get_arm(name: str) -> ArmSpec:
    try:
        return ARMS[name]
    except KeyError as exc:
        raise ValueError(f"unknown evaluation arm {name!r}; expected one of {tuple(ARMS)}") from exc
