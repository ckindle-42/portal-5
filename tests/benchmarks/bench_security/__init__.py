"""bench_security — auto-register ported oracles on import."""

from __future__ import annotations

from .ability_port import register_ported_oracles

register_ported_oracles()

# Re-export public API for __main__ entry point and backward-compat shim
from ._config import BenchConfig  # noqa: F401, E402
from ._data import (  # noqa: F401, E402
    CHAIN_INHERITANCE,
    DEFAULT_WORKSPACES,
    DISCLAIMER_PATTERNS,
    EXEC_SEQUENCES,
    EXECUTION_WORKSPACES,
    MITRE_PATTERN,
    PER_WORKSPACE_TIMEOUT,
    PIPELINE_API_KEY,
    PIPELINE_URL,
    PROMPT_MAX_TOKENS,
    PROMPTS,
    REQUEST_TIMEOUT,
    RESULTS_DIR,
)
from .cli import main  # noqa: F401, E402
from .scoring import (  # noqa: F401, E402
    score_execution,
    score_handoff_quality,
    score_response,
)
