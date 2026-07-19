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
INFERENCE_TIMEOUT = 90.0
#
# PIPELINE_INACTIVITY_TIMEOUT: same idea, but pipeline calls may buffer
#   reasoning <think> blocks before forwarding any bytes. Allow more headroom
#   so a complex security/redteam query doesn't abort mid-think.
PIPELINE_INACTIVITY_TIMEOUT = 270.0
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


def _load_env() -> None:
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
        return
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                k = k.strip()
                if k in _ENV_KEYS_SKIP_FROM_DOTENV:
                    continue
                os.environ.setdefault(k, v.strip())


_load_env()

PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "")
