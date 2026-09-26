"""Shared gate for every raw-engine-bypass diagnostic switch in security's
core modules: ``agentic_blue_eval``/``exec_chain``'s ``CHAIN_DIRECT_OLLAMA``,
``blue.py``'s ``BLUE_DIRECT_OLLAMA``, ``refusal.py``'s
``REFUSAL_DIRECT_OLLAMA``, ``drift_gate.py``'s ``DRIFT_DIRECT_OLLAMA``.

TASK_AUTO_COUNCIL_PIPELINE_REVISIT_V1 P1.5: each of those was a bare
per-module env var — set it (even by accident: a stale ``.env`` line, a
copy-pasted CI config, a leftover shell export from a prior debugging
session) and that module silently took a "product"/qualification run off
the pipeline and onto raw Ollama, with none of strict-seat's route/tool/
receipt guarantees. Nothing here removes that raw-engine capability — it's
a legitimate diagnostic for isolating whether a failure is the harness or
the model — but every switch now ALSO requires this one loudly-named,
repo-wide gate, so a lone per-module var can never again silently satisfy
product acceptance. Both must be explicitly set; there is no default that
enables a bypass.
"""

from __future__ import annotations

import os

GATE_ENV_VAR = "PORTAL_SECURITY_DIRECT_ENGINE_DIAGNOSTIC"


def direct_engine_diagnostic_enabled(switch_env_var: str) -> bool:
    """True only when the caller's own module-specific switch AND this
    shared gate are both explicitly set to ``"true"`` (case-insensitive).

    Pass the switch's own env var name (e.g. ``"CHAIN_DIRECT_OLLAMA"``) so
    each call site stays self-documenting and so this stays a pure function
    of current environment state (no import-time caching to fight in tests).
    """
    switch = os.environ.get(switch_env_var, "").lower() == "true"
    gate = os.environ.get(GATE_ENV_VAR, "").lower() == "true"
    return switch and gate
