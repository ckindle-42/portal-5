"""Shared constants and workspace registry for persona-matrix harness.

Extracted from tests/portal5_persona_matrix.py. Module-level state
that was previously at the top of the monolithic script.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO))

# Workspace registry — maps a workspace_id to its matrix configuration.
# Each entry references its own assertion library and fixture loader.
# Add a new workspace here; no other driver changes required.
WORKSPACE_REGISTRY: dict[str, dict[str, str]] = {
    "auto-compliance": {
        "assertions_module": "tests.lib.compliance_assertions",
        "fixtures_module": "tests.lib.compliance_fixtures",
        "persona_categories": ("compliance",),
        "threshold_doc": "docs/COMPLIANCE_FALLBACK_POLICY.md",
    },
    "auto-coding": {
        "assertions_module": "tests.lib.coding_assertions",
        "fixtures_module": "tests.lib.coding_fixtures",
        "persona_categories": ("coding", "software", "development", "systems"),
        "threshold_doc": "docs/CODING_FALLBACK_POLICY.md",
    },
    # Shootout-only registry entry — same assertions and fixtures as auto-coding,
    # but filters by the benchmark persona category so bench-* personas (each
    # pinned to a single model) participate. The Creative Coder system prompt
    # is identical across all bench personas — only the model varies, which is
    # the controlled-experiment shape the shootout requires.
    #
    # models_explicit overrides the production workspace_routing chain. This
    # entry is NOT registered in backends.yaml's workspace_routing table — the
    # shootout is a test harness, not a production routing target. See
    # TASK_CODING_SHOOTOUT_V1.md §A2 and §T3.
    "auto-coding-bench": {
        "assertions_module": "tests.lib.coding_assertions",
        "fixtures_module": "tests.lib.coding_fixtures",
        # persona_categories is retained as a fallback if persona_slugs_explicit is
        # cleared, but V2 routes through the slug list. See A2/A7.
        "persona_categories": ("benchmark",),
        "threshold_doc": "TASK_CODING_SHOOTOUT_V2.md",
        # V2 enumerates the production personas the workspace actually serves,
        # pruned per A3. Categories-based filtering can't express this set
        # because it spans multiple persona categories AND requires exclusions
        # within those categories. See TASK_CODING_SHOOTOUT_V2.md §A2-A4.
        "persona_slugs_explicit": (
            # REPL shape (UAT 0/3 — Laguna's catastrophic miss; javascriptconsole
            # is regression guard, the only REPL persona that PASSed)
            "sqlterminal",
            "linuxterminal",
            "pythoninterpreter",
            "javascriptconsole",
            # Audit shape (UAT 0/2 FAIL on strict contracts; PASS on relaxed)
            "codereviewer",
            "softwarequalityassurancetester",
            "bugdiscoverycodeassistant",
            "codereviewassistant",
            # Composite shape (UAT 0/3 — multi-element output)
            "e2etestauthor",
            "e2edebugger",
            "fullstacksoftwaredeveloper",
            # Ship-It shape (UAT mostly PASS — regression guard)
            "creativecoder",
            "pythoncodegeneratorcleanoptimizedproduction-ready",
            "devopsautomator",
            "githubexpert",
        ),
        # Persona-shape mapping for the analyzer. The matrix's columns are
        # derived from this dict. Keys must match persona_slugs_explicit exactly.
        "persona_shapes": {
            "sqlterminal": "REPL",
            "linuxterminal": "REPL",
            "pythoninterpreter": "REPL",
            "javascriptconsole": "REPL",
            "codereviewer": "Audit",
            "softwarequalityassurancetester": "Audit",
            "bugdiscoverycodeassistant": "Audit",
            "codereviewassistant": "Audit",
            "e2etestauthor": "Composite",
            "e2edebugger": "Composite",
            "fullstacksoftwaredeveloper": "Composite",
            "creativecoder": "Ship-It",
            "pythoncodegeneratorcleanoptimizedproduction-ready": "Ship-It",
            "devopsautomator": "Ship-It",
            "githubexpert": "Ship-It",
        },
        "models_explicit": (
            # V2 incumbents retained for continuity — per-shape delta directly comparable
            "laguna-xs.2:Q4_K_M",
            "glm-4.7-flash:Q4_K_M",
            "qwen3-coder:30b-a3b-q4_K_M",
            "devstral-small-2",
            # V9 candidates (TASK_V9_EVAL_EXTENDED)
            "hf.co/yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M",
            "hf.co/Jackrong/Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf",
            # V4 fast-lane / reasoning probes (TASK_CODING_CAPABILITY_PROBE_V2)
            "lfm2.5:8b",
            "granite4.1:8b",
            "granite4.1:30b",
            "hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL",
            "hf.co/mradermacher/Josiefied-DeepSeek-R1-0528-Qwen3-8B-abliterated-v1-GGUF:Q4_K_M",
            "hf.co/ijohn07/harness-1-Q4_K_M-GGUF:Q4_K_M",
            # Reference columns — 80B/3B MoE (~46 GB), different weight class.
            # NOT auto-coding repin candidates. Comparison points for the upper tier.
            "qwen3-coder-next",  # auto-agentic production pin
            "hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M",  # auto-spl production pin (V8)
        ),
        # Models that should be flagged in the matrix as "reference" rather than
        # "candidate" — the analyzer excludes these from the overall-column
        # ranking so a reference column dominating doesn't get misread as a
        # repin signal. See A5.
        "models_reference_only": (
            "qwen3-coder-next",
            "hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M",
            "granite4.1:30b",  # different weight class — observation only
        ),
    },
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

