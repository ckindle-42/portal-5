"""Re-export shim — implementation split into exec_chain/refusal/intake.py.

M6-B1+A3: chain.py is now a thin facade; all implementation lives in the
focused sub-modules listed below.  Imports from this module continue to
work unchanged.

Sub-modules
-----------
exec_chain  Multi-turn execution chain, scenarios, synthetic results, A3 helpers
refusal     Refusal tests and audit-tools probe
intake      Candidate intake pipeline (pull → TPS gate → tool probe)
"""

from __future__ import annotations

from .exec_chain import (
    _CHAIN_ROLES,
    _CVE_DEFAULT_HIT,
    _CVE_DEFAULT_MISS,
    _CVE_RESPONSES,
    _DYNAMIC_CVE_DB,
    _REFUSAL_PATTERNS,
    _STEP_GROUPS,
    _WEB_SEARCH_CHAIN_TOOL,
    AUDIT_TOOL,
    CHAIN_INITIAL_PROMPT_DEFAULT,
    CHAIN_TOOLS_BASE,
    INLINE_TOOLS,
    OLLAMA_URL,
    SCENARIOS,
    _assign_steps,
    _call_via_pipeline,
    _is_workspace_slug,
    _resolve_step_model,
    _run_blue_defender,
    _run_blue_turn,
    _run_chain_test,
    _run_exec_chain,
    _run_model_turn,
    _run_multimodel_chain,
    _synthetic_tool_result,
    _synthetic_web_search,
    run_chain_tests,
)
from .intake import (
    PULL_TIMEOUT_S,
    TPS_FLOOR,
    _pull_model,
    _tps_warmup,
    run_candidate_intake,
)
from .refusal import (
    _audit_tools_probe,
    _run_refusal_test,
    run_audit_tools,
)

__all__ = [
    # ── exec_chain ────────────────────────────────────────────────────────────
    "OLLAMA_URL",
    "AUDIT_TOOL",
    "CHAIN_TOOLS_BASE",
    "CHAIN_INITIAL_PROMPT_DEFAULT",
    "INLINE_TOOLS",
    "SCENARIOS",
    "_CHAIN_ROLES",
    "_STEP_GROUPS",
    "_REFUSAL_PATTERNS",
    "_DYNAMIC_CVE_DB",
    "_CVE_RESPONSES",
    "_CVE_DEFAULT_MISS",
    "_CVE_DEFAULT_HIT",
    "_WEB_SEARCH_CHAIN_TOOL",
    "_assign_steps",
    "_is_workspace_slug",
    "_call_via_pipeline",
    "_run_blue_turn",
    "_run_blue_defender",
    "_run_exec_chain",
    "_run_chain_test",
    "_run_model_turn",
    "run_chain_tests",
    "_resolve_step_model",
    "_run_multimodel_chain",
    "_synthetic_web_search",
    "_synthetic_tool_result",
    # ── refusal ───────────────────────────────────────────────────────────────
    "_run_refusal_test",
    "_audit_tools_probe",
    "run_audit_tools",
    # ── intake ────────────────────────────────────────────────────────────────
    "TPS_FLOOR",
    "PULL_TIMEOUT_S",
    "_pull_model",
    "_tps_warmup",
    "run_candidate_intake",
]
