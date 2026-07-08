"""Public surface for RBP evidence primitives.

Currently a facade over tests.benchmarks.bench_security.episode.
Migration target: move the primitives here in a future phase.
"""

from tests.benchmarks.bench_security.episode import (
    CAPABILITY_VERDICTS,
    REASON_CODES,
    DetectionCorrelation,
    Episode,
    _aggregate_detection_status,
    derive_detection_status,
    derive_verdict,
    new_episode_id,
)

__all__ = [
    "CAPABILITY_VERDICTS",
    "DetectionCorrelation",
    "Episode",
    "REASON_CODES",
    "_aggregate_detection_status",
    "derive_detection_status",
    "derive_verdict",
    "new_episode_id",
]
