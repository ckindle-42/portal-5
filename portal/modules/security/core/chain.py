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

from portal.platform.data_loader import load_data

from .exec_chain import (  # noqa: F401
    _CHAIN_ROLES as _CHAIN_ROLES,
)
from .exec_chain import (
    _CVE_DEFAULT_HIT as _CVE_DEFAULT_HIT,
)
from .exec_chain import (
    _CVE_DEFAULT_MISS as _CVE_DEFAULT_MISS,
)
from .exec_chain import (
    _CVE_RESPONSES as _CVE_RESPONSES,
)
from .exec_chain import (
    _DYNAMIC_CVE_DB as _DYNAMIC_CVE_DB,
)
from .exec_chain import (
    _REFUSAL_PATTERNS as _REFUSAL_PATTERNS,
)
from .exec_chain import (
    _STEP_GROUPS as _STEP_GROUPS,
)
from .exec_chain import (
    _WEB_SEARCH_CHAIN_TOOL as _WEB_SEARCH_CHAIN_TOOL,
)
from .exec_chain import (
    AUDIT_TOOL as AUDIT_TOOL,
)
from .exec_chain import (
    CHAIN_INITIAL_PROMPT_DEFAULT as CHAIN_INITIAL_PROMPT_DEFAULT,
)
from .exec_chain import (
    CHAIN_TOOLS_BASE as CHAIN_TOOLS_BASE,
)
from .exec_chain import (
    INLINE_TOOLS as INLINE_TOOLS,
)
from .exec_chain import (
    OLLAMA_URL as OLLAMA_URL,
)
from .exec_chain import (
    SCENARIOS as SCENARIOS,
)
from .exec_chain import (
    _assign_steps as _assign_steps,
)
from .exec_chain import (
    _call_via_pipeline as _call_via_pipeline,
)
from .exec_chain import (
    _is_pipeline_model as _is_pipeline_model,
)
from .exec_chain import (
    _prepare_scenario as _prepare_scenario,
)
from .exec_chain import (
    _resolve_step_model as _resolve_step_model,
)
from .exec_chain import (
    _run_blue_defender as _run_blue_defender,
)
from .exec_chain import (
    _run_blue_turn as _run_blue_turn,
)
from .exec_chain import (
    _run_chain_test as _run_chain_test,
)
from .exec_chain import (
    _run_exec_chain as _run_exec_chain,
)
from .exec_chain import (
    _run_model_turn as _run_model_turn,
)
from .exec_chain import (
    _run_multimodel_chain as _run_multimodel_chain,
)
from .exec_chain import (
    _synthetic_tool_result as _synthetic_tool_result,
)
from .exec_chain import (
    _synthetic_web_search as _synthetic_web_search,
)
from .exec_chain import (
    run_chain_tests as run_chain_tests,
)
from .intake import (  # noqa: F401
    PULL_TIMEOUT_S as PULL_TIMEOUT_S,
)
from .intake import (
    TPS_FLOOR as TPS_FLOOR,
)
from .intake import (
    _pull_model as _pull_model,
)
from .intake import (
    _tps_warmup as _tps_warmup,
)
from .intake import (
    run_candidate_intake as run_candidate_intake,
)
from .refusal import (  # noqa: F401
    _audit_tools_probe as _audit_tools_probe,
)
from .refusal import (
    _run_refusal_test as _run_refusal_test,
)
from .refusal import (
    run_audit_tools as run_audit_tools,
)

__all__ = load_data("config/security", "chain_all")
