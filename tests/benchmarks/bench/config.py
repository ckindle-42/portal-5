"""Shared constants, environment, and reasoning-model detection for the bench package.

Extracted byte-for-byte from tests/benchmarks/bench_tps.py (see
TASK_BENCH_MODULARIZE_V1). Path constants are recomputed for the new
package depth; everything else is unchanged.
"""

import os
from datetime import datetime, timezone
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
PER_WORKSPACE_TIMEOUT: dict[str, float] = {
    "auto-phi4": 1500.0,             # phi4-reasoning:plus
    "auto-research": 1200.0,         # tongyi-deepresearch-abliterated
    "auto-purpleteam-deep": 1500.0,  # qwen3.5-abliterated
    "auto-spl": 600.0,               # huihui-ai_qwen3-coder-next
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
REASONING_WORKSPACES: frozenset[str] = frozenset(
    {
        "bench-laguna",
        "bench-phi4-reasoning",
        "bench-phi4",  # phi4 (non-reasoning variant) emits only reasoning_text via pipeline
        "bench-phi4-mini-reasoning",  # phi4-mini-reasoning — 3.8B thinking model
        "bench-foundation-sec",  # Foundation-Sec-8B-Reasoning — native <think> (Llama-3.1 base)
        "bench-r1-0528-qwen3-8b",  # DeepSeek-R1-0528-Qwen3-8B — chain-of-thought
        "bench-r1-0528-abliterated",  # R1-0528 abliterated — same architecture
        "bench-olmo3-32b",  # OLMo-3.1-32B-Think — emits <think> blocks
        "bench-negentropy",  # deepseek-r1:32b-q4_k_m — CoT reasoning
        "bench-nex-n2-mini",  # Nex-N2-mini (Qwen3.5-35B-A3B MoE) — emits_reasoning
        "auto-blueteam",  # Foundation-Sec-8B-Reasoning — same model as bench-foundation-sec
        "auto-data",  # deepseek-r1:32b-q8_0 — R1 chain-of-thought
        "auto-phi4",  # phi4-reasoning:plus — RL-trained 14B STEM reasoner
        "auto-research",  # tongyi-deepresearch-abliterated — deep research CoT
        "auto-mistral",
        "auto-reasoning",
        "auto-math",  # phi4-mini-reasoning production workspace
        "auto-security",  # AEON Qwen3.6-27B is a thinking model
        "auto-redteam",  # same — needs 512-token budget to avoid empty responses
        "auto-vision",  # routes to auto-reasoning for text-only; deepseek-r1 emits reasoning_text
    }
)

# Workspaces that receive an ADDITIONAL math-prompt pass on top of their primary category.
# These are math-specialist models — we run both their normal prompt AND the math prompt
# so results contain entries for both, making cross-category comparison possible.
MATH_SPECIALIST_WORKSPACES: frozenset[str] = frozenset(
    {
        "auto-math",  # phi4-mini-reasoning — AIME/MATH-500 specialist
        "bench-phi4-mini-reasoning",  # direct bench target for auto-math model
        "bench-phi4-mini",  # phi4-mini non-thinking baseline — compare vs reasoning variant
        "bench-phi4",  # phi4 — broader reasoning, include for full phi4 family picture
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
RESULTS_FILE = str(
    RESULTS_DIR / f"bench_tps_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
)


def _load_env() -> None:
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "")
