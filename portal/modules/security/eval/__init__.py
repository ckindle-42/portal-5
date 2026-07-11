"""Public surface for security scoring."""

from portal.modules.security.core.scoring import (
    score_blue_detections,
    score_blue_detections_diagnostic,
)

__all__ = ["score_blue_detections", "score_blue_detections_diagnostic"]
