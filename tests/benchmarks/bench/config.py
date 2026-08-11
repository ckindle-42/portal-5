"""Shared constants, environment, and reasoning-model detection for the bench package.

Extracted byte-for-byte from tests/benchmarks/bench_tps.py (see
TASK_BENCH_MODULARIZE_V1). Path constants are recomputed for the new
package depth; everything else is unchanged.
"""

import os
from datetime import UTC, datetime
from pathlib import Path

OLLAMA_URL = "http://localhost:11434"
PIPELINE_URL = "http://localhost:9099"

MAX_TOKENS = 256

# Timeout philosophy: event-driven, not timer-driven.
#
# WARMUP_TIMEOUT: max time to wait for a warmup probe to return (the response
#   IS the "model ready" event — no guessing, no sleep). Used by
#   _warmup_pipeline_model.
WARMUP_TIMEOUT = 300.0
#
# INFERENCE_TIMEOUT: per-byte inactivity cap during active streaming.
#   This is NOT a wall-clock limit. httpx ReadTimeout fires only when no
#   bytes arrive for this many seconds. If tokens are flowing (even at 2 t/s),
#   this never triggers. It only catches a stuck/crashed backend.
#   Applies after warmup confirms the model is loaded.
#
#   TASK_BENCH_VALIDITY_V1: this idle-gap is the PRIMARY backstop and it is
#   length-agnostic by design — a model producing a long-but-healthy answer
#   never trips it because bytes keep flowing. It catches pathology (stuck /
#   looping / crashed backend), not length. Kept moderate.
INFERENCE_TIMEOUT = 120.0
#
# PIPELINE_INACTIVITY_TIMEOUT: same idea, but pipeline calls may buffer
#   reasoning <think> blocks before forwarding any bytes. Allow more headroom
#   so a complex security/redteam query doesn't abort mid-think.
PIPELINE_INACTIVITY_TIMEOUT = 300.0
#
# REQUEST_TIMEOUT kept as a fallback for one-shot non-streaming calls (health,
# warmup probes, Ollama direct). Not used in the main bench streaming path.
REQUEST_TIMEOUT = 180.0

# Per-workspace request-timeout overrides (seconds).
# These apply to pipeline mode (not direct Ollama).
# Reasoning workspaces and slow research models get extended caps so
# they don't get killed by the default REQUEST_TIMEOUT.
# Reference: UAT 20260627 — phi4-reasoning ran 67min on P-DA05;
# tongyi-deepresearch 901s on P-R05; qwen3.5-abliterated 1293s on WS-PT02.
#
# BUILD_PROGRAM_ALIAS_RETIRE_V1.md Phase 4: re-keyed from retired aliases to
# their live successor base workspaces (config/portal.yaml no longer declares
# auto-phi4/auto-purpleteam-deep as their own workspace — see
# _LEGACY_WORKSPACE_ALIASES in portal/platform/inference/router/preinject.py).
# auto-daily and auto-security are multi-model workspaces now, so the cap
# applies to the base per "apply the max to the base" (TASK_BENCH_CONFIG_
# RECONCILE_V1.md) — safe: a longer allowance doesn't break faster models
# sharing the base, it only prevents this specific slow variant from being
# killed mid-response, which is exactly what the entry exists to prevent.
PER_WORKSPACE_TIMEOUT: dict[str, float] = {
    "auto-daily": 1500.0,  # phi4-reasoning:plus (?model= override; formerly auto-phi4)
    "auto-research": 1200.0,  # tongyi-deepresearch-abliterated
    "auto-security": 1500.0,  # qwen3.5-abliterated (purpleteam-deep variant; formerly auto-purpleteam-deep)
    "auto-spl": 600.0,  # huihui-ai_qwen3-coder-next
    # auto-purpleteam-exec NOT capped here — Phase 2 sets supports_tools=false
    # on supergemma4 which removes the underlying cause of long runtime.
}

# TASK_BENCH_VALIDITY_V1: with the bench-only token cap removed, a reasoning or
# agentic workspace runs its FULL thinking + answer at production budget — which
# can legitimately take many minutes. The idle-gap (INFERENCE_TIMEOUT /
# PIPELINE_INACTIVITY_TIMEOUT) is the real pathology backstop; this wall-clock
# ceiling is only a last-resort runaway guard and must be generous enough that a
# healthy long generation is never the thing it kills. Sized off real
# observations already recorded above (phi4-reasoning ~67min, tongyi 901s).
#
# resolve_request_timeout() gives any workspace NOT explicitly listed in
# PER_WORKSPACE_TIMEOUT a category-appropriate ceiling instead of the short
# streaming-inactivity default, so newly-wired bench-* reasoning/agentic
# workspaces don't get killed mid-legitimate-answer.
CEILING_REASONING_S = 1800.0  # 30 min — reasoning/agentic full-budget generation
CEILING_STANDARD_S = 600.0  # 10 min — non-reasoning, uncapped but rarely long
CEILING_HARD_MAX_S = 3600.0  # 60 min — absolute runaway guard, nothing legitimate exceeds


_PORTAL_WS_CACHE: dict[str, dict] | None = None


def _portal_workspace_fields() -> dict[str, dict]:
    """Load per-workspace {predict_limit, emits_reasoning, tools} from
    config/portal.yaml (the single source of truth). Cached after first read.
    Returns {} on any failure so bench never hard-fails on config parsing —
    callers then fall back to their own defaults."""
    global _PORTAL_WS_CACHE
    if _PORTAL_WS_CACHE is not None:
        return _PORTAL_WS_CACHE
    out: dict[str, dict] = {}
    try:
        import yaml as _yaml

        portal_path = PROJECT_ROOT / "config" / "portal.yaml"
        data = _yaml.safe_load(portal_path.read_text()) or {}
        for slug, spec in (data.get("workspaces") or {}).items():
            if not isinstance(spec, dict):
                continue
            out[slug] = {
                "predict_limit": spec.get("predict_limit"),
                "emits_reasoning": bool(spec.get("emits_reasoning")),
                "tools": list(spec.get("tools") or []),
                "model_hint": spec.get("model_hint"),
            }
    except Exception:
        out = {}
    _PORTAL_WS_CACHE = out
    return out


def workspace_budget(workspace_id: str) -> dict:
    """Return {predict_limit, emits_reasoning, has_tools} for a workspace slug,
    resolved from portal.yaml. Unknown workspace => all-None/False."""
    fields = _portal_workspace_fields().get(workspace_id, {})
    return {
        "predict_limit": fields.get("predict_limit"),
        "emits_reasoning": bool(fields.get("emits_reasoning")),
        "has_tools": bool(fields.get("tools")),
    }


def budget_for_model_tag(model_tag: str) -> dict:
    """Direct-mode resolution: map a bare Ollama model tag back to the first
    bench-* workspace whose model_hint matches, and return its budget. Used by
    direct-Ollama bench runs which get a tag, not a workspace slug. Unknown =>
    all-None/False (=> no cap, model default, == production unset behaviour)."""
    fields = _portal_workspace_fields()
    for slug, spec in fields.items():
        if spec.get("model_hint") == model_tag:
            return {
                "predict_limit": spec.get("predict_limit"),
                "emits_reasoning": bool(spec.get("emits_reasoning")),
                "has_tools": bool(spec.get("tools")),
                "workspace": slug,
            }
    return {"predict_limit": None, "emits_reasoning": False, "has_tools": False, "workspace": None}


def resolve_request_timeout(
    workspace_id: str,
    *,
    emits_reasoning: bool = False,
    has_tools: bool = False,
    default: float = PIPELINE_INACTIVITY_TIMEOUT,
) -> float:
    """Wall-clock ceiling for a bench run. Explicit PER_WORKSPACE_TIMEOUT wins;
    otherwise a reasoning/agentic workspace gets the generous reasoning ceiling,
    a plain workspace gets the standard ceiling, and anything already larger
    than those (a caller-supplied default) is preserved. Never below `default`,
    never above the hard runaway guard."""
    explicit = PER_WORKSPACE_TIMEOUT.get(workspace_id)
    if explicit is not None:
        return min(explicit, CEILING_HARD_MAX_S)
    if emits_reasoning or has_tools:
        return min(max(CEILING_REASONING_S, default), CEILING_HARD_MAX_S)
    return min(max(CEILING_STANDARD_S, default), CEILING_HARD_MAX_S)


# Reasoning models (Laguna, Phi-4-reasoning, Magistral, Qwopus, DeepSeek-R1)
# emit <think> blocks that consume tokens before generating output. Two adjustments:
#   1. REASONING_MAX_TOKENS: larger budget so output isn't truncated mid-response.
#   2. Reasoning output is included in the token count; the larger budget keeps
#      TPS comparable across reasoning and non-reasoning models.
REASONING_MAX_TOKENS = 512
# Math prompts require a larger budget: reasoning models consume many tokens for
# step-by-step work across 3 problems, and even non-reasoning models need ~600+
# tokens to complete the full problem set.
MATH_MAX_TOKENS = 1024
#
# BUILD_PROGRAM_ALIAS_RETIRE_V1.md Phase 4: re-keyed from retired aliases.
# "auto-blueteam"/"auto-redteam" dropped — folded into auto-security, already
# listed below (AEON Qwen3.6-27B applies workspace-wide regardless of role
# variant). "auto-phi4"/"auto-mistral" folded into auto-daily/auto-coding
# (model-tied, no dedicated workspace post-collapse) — kept as workspace-wide
# entries rather than dropped: _is_reasoning_model() in pipeline mode is
# called with `model` = the requested workspace id (the backend model isn't
# known pre-response), so a model-substring fallback can't catch these the
# way it does in direct-Ollama mode. Erring toward the larger token budget
# for the rest of these multi-model workspaces is the safe direction — it
# costs a modest overhead, not a truncated/empty response, which is the
# failure this table exists to prevent.
REASONING_WORKSPACES: frozenset[str] = frozenset(
    {
        "bench-laguna",
        "bench-nex-n2-mini",  # Nex-N2-mini (Qwen3.5-35B-A3B MoE) — emits_reasoning
        "auto-data",  # deepseek-r1:32b-q8_0 — R1 chain-of-thought
        "auto-daily",  # phi4-reasoning:plus (?model= override; formerly auto-phi4)
        "auto-research",  # tongyi-deepresearch-abliterated — deep research CoT
        "auto-coding",  # Magistral-Small-2509 (?model= override; formerly auto-mistral)
        "auto-reasoning",
        "auto-math",  # phi4-mini-reasoning production workspace
        "auto-security",  # AEON Qwen3.6-27B is a thinking model; applies to all role variants
        "auto-vision",  # routes to auto-reasoning for text-only; deepseek-r1 emits reasoning_text
    }
)

# Workspaces that receive an ADDITIONAL math-prompt pass on top of their primary category.
# These are math-specialist models — we run both their normal prompt AND the math prompt
# so results contain entries for both, making cross-category comparison possible.
MATH_SPECIALIST_WORKSPACES: frozenset[str] = frozenset(
    {
        "auto-math",  # phi4-mini-reasoning — AIME/MATH-500 specialist
    }
)
# Model substrings that trigger the extra math pass in direct mode.
_MATH_SPECIALIST_PATTERNS = (
    "phi4-mini-reasoning",
    "phi4-mini",
    "Phi-4-mini",
)

# Model substrings that signal a reasoning model.
# Applied case-insensitively to Ollama model IDs (e.g. "deepseek-r1:32b-q4_k_m")
# so Ollama reasoning models get REASONING_MAX_TOKENS and don't exhaust their
# thinking budget within the smaller MAX_TOKENS cap.
_REASONING_MODEL_PATTERNS = (
    "Laguna",
    "Phi-4-reasoning",
    "phi4-mini-reasoning",  # Ollama ID for Microsoft Phi-4-mini-reasoning
    "Magistral",
    "Qwopus",
    "DeepSeek-R1",
    "deepseek-r1",  # Ollama IDs are lowercase; case-insensitive match below
    "R1-0528",  # DeepSeek-R1-0528 and abliterated variants
    "Josiefied",  # abliterated R1-0528 variant (mradermacher GGUF naming)
    "Qwen3.5-27B-Claude",
    "Qwen3.5-9B-Claude",
    "Qwen3.5-35B-A3B-Claude",
    "Qwen3.6",
    "AEON",
    "Foundation-Sec",  # always emits <think>; enable_thinking=False suppresses CoT overhead
    "olmo-3.1",  # OLMo-3.1-32B-Think — Allen AI thinking model
)

# Models that use /nothink in the user message to suppress thinking chain.
_NOTHINK_PATTERNS = (
    "Qwen3.6",
    "AEON",
)


def _is_reasoning_model(model: str, workspace_id: str = "") -> bool:
    """Return True if this model/workspace uses think-block reasoning."""
    if workspace_id in REASONING_WORKSPACES:
        return True
    model_lower = model.lower()
    return any(p.lower() in model_lower for p in _REASONING_MODEL_PATTERNS)


# Repo root: tests/benchmarks/bench/config.py → three parents up from tests/.
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Results live beside the package, under tests/benchmarks/results/ (unchanged
# location — recomputed because this file is one level deeper than bench_tps.py).
RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
# Default output: timestamped UTC file under tests/benchmarks/results/
# Override with --output. Operator commits selected baselines manually.
RESULTS_FILE = str(RESULTS_DIR / f"bench_tps_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json")


_ENV_KEYS_SKIP_FROM_DOTENV = {"PIPELINE_URL"}  # Compose-internal hostname; bench runs host-side


def _load_env() -> dict[str, str]:
    # Hermetic-test guard (CLAUDE.md: tests/unit/ must pass with no network
    # access / real config): tests/unit/test_adhoc_probe.py transitively
    # imports this module (bench/adhoc_probe.py -> bench/config.py), and this
    # function used to run unconditionally at import time, setdefault-ing
    # every real .env key (LAB_* secrets, PIPELINE_API_KEY, PORTAL_ENABLE_EVAL,
    # ...) into the whole unit-test session's os.environ for every test that
    # ran after it — invisible until a later test happened to read one of
    # those keys with different expectations. tests/unit/conftest.py already
    # sets UNIT_TEST_MODE=1 for exactly this kind of hermetic-mode signal.
    if os.environ.get("UNIT_TEST_MODE") == "1":
        return {}
    loaded: dict[str, str] = {}
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                k = k.strip()
                if k in _ENV_KEYS_SKIP_FROM_DOTENV:
                    continue
                loaded.setdefault(k, v.strip())
    return loaded


_DOTENV = _load_env()

PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", _DOTENV.get("PIPELINE_API_KEY", ""))
