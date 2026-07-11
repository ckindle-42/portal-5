"""Public surface for security eval/bench/drift harnesses.

Same re-export-boundary pattern as knowledge/ — the RBP engine's eval
code stays in core/ (Slice 3), this exposes the stable entry points
other code should call rather than importing core.agentic_blue_eval,
core.candidate_eval, core.rescore_run internals directly.
"""

from portal.modules.security.core.agentic_blue_eval import run_eval
from portal.modules.security.core.candidate_eval import candidate_eval_main
from portal.modules.security.core.rescore_run import rescore
from portal.modules.security.core.scoring import (
    score_blue_detections,
    score_blue_detections_diagnostic,
)

__all__ = [
    "candidate_eval_main",
    "rescore",
    "run_eval",
    "score_blue_detections",
    "score_blue_detections_diagnostic",
]
