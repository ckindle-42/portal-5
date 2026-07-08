"""Public surface for security scoring."""

from tests.benchmarks.bench_security.scoring import (
    score_blue_detections,
    score_blue_detections_diagnostic,
)

__all__ = ["score_blue_detections", "score_blue_detections_diagnostic"]
