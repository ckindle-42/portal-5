"""Shared constants and workspace registry for persona-matrix harness.

Extracted from tests/portal5_persona_matrix.py. Module-level state
that was previously at the top of the monolithic script.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[4]


def _load_data(name: str) -> Any:
    """Load a data file that was a module-level literal before V1."""
    path = _REPO / "config" / "inference" / f"{name}.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


sys.path.insert(0, str(_REPO))

# Workspace registry — maps a workspace_id to its matrix configuration.
# Each entry references its own assertion library and fixture loader.
# Add a new workspace here; no other driver changes required.
_TUPLE_KEYS = (
    "persona_categories",
    "persona_slugs_explicit",
    "models_explicit",
    "models_reference_only",
)
WORKSPACE_REGISTRY = {
    k: {ik: (tuple(iv) if ik in _TUPLE_KEYS else iv) for ik, iv in v.items()}
    for k, v in _load_data("persona_matrix_workspace_registry").items()
}

# Module-level aliases reassigned by run_sweep() based on --workspace.
# Default to compliance modules so any direct importer of run_cell() (e.g.,
# from a test) gets the prior behavior unchanged.
ca = importlib.import_module("tests.lib.compliance_assertions")
cf = importlib.import_module("tests.lib.compliance_fixtures")


# Re-export _load_workspace_modules (now defined here since it references WORKSPACE_REGISTRY)
def _load_workspace_modules(workspace_id: str):
    """Resolve (assertions, fixtures) modules for a workspace."""
    cfg = WORKSPACE_REGISTRY.get(workspace_id)
    if not cfg:
        raise SystemExit(
            f"workspace '{workspace_id}' not registered in WORKSPACE_REGISTRY. "
            f"Known: {list(WORKSPACE_REGISTRY.keys())}"
        )
    return (
        importlib.import_module(cfg["assertions_module"]),
        importlib.import_module(cfg["fixtures_module"]),
        cfg["persona_categories"],
    )


OLLAMA_URL = "http://localhost:11434"
RESULTS_DIR = _REPO / "tests" / "benchmarks" / "results"

# System prompt cap for matrix driver direct calls. Sized so the largest
# current compliance persona (complianceanalyst at ~5000 chars) has 60%
# headroom. Raise if a persona legitimately exceeds; do not silently
# truncate. See TASK_MATRIX_DRIVER_REMEDIATION_V1 §RC-1.
SYSTEM_PROMPT_CAP_CHARS = 8000

REQUEST_TIMEOUT = 240.0
EVICT_BACKOFF_S = 5.0

# ── Audit-tools mode fixture ──────────────────────────────────────────────
# Sample tool used by --audit-tools to verify per-model tool-call support.
# A single, simple tool definition is sufficient — we're testing whether the
# Ollama API accepts the request and the model emits a structured tool_calls
# response, not whether the model picks the right arguments.
# See TASK_TOOL_SUPPORT_AUDIT_V1 §A14.

AUDIT_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_current_time",
        "description": "Get the current time for a city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "The name of the city"},
            },
            "required": ["city"],
        },
    },
}

AUDIT_PROMPT = "What time is it in Paris right now?"


# ── Backend enumeration ───────────────────────────────────────────────────
