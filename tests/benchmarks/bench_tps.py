#!/usr/bin/env python3
"""Portal 5 — Comprehensive TPS Benchmark.

Measures tokens/sec across every model, every workspace, and every persona.

Three test paths:
  1. Direct backends  — Ollama (:11434), every model
  2. Pipeline routing  — portal-pipeline (:9099) per workspace
  3. Persona routing    — portal-pipeline (:9099) per persona workspace_model

Model discovery is config-driven (backends.yaml + persona YAMLs), not
runtime-only. Undownloaded Ollama models are tested and reported as unavailable.

Usage:
    python3 tests/benchmarks/bench_tps.py                                    # everything, 5 runs
    python3 tests/benchmarks/bench_tps.py --runs 1                           # single run (faster)
    python3 tests/benchmarks/bench_tps.py --mode direct                      # Ollama direct only
    python3 tests/benchmarks/bench_tps.py --mode pipeline                    # workspaces only
    python3 tests/benchmarks/bench_tps.py --mode personas                    # personas only
    python3 tests/benchmarks/bench_tps.py --mode all --order size --runs 5 --cooldown 10  # standard baseline
    python3 tests/benchmarks/bench_tps.py --model dolphin-llama3             # filter by model substring
    python3 tests/benchmarks/bench_tps.py --workspace auto-coding            # single workspace
    python3 tests/benchmarks/bench_tps.py --persona cybersecurity            # filter personas
    python3 tests/benchmarks/bench_tps.py --output results.json              # custom output
    python3 tests/benchmarks/bench_tps.py --dry-run                          # show plan

Memory management:
    Each model follows a warmup → bench → unload via /api/ps keep_alive:0:
      1. Warmup: Ollama loads the model into memory
      2. Test: N inference runs with the category-appropriate prompt
      3. Unload: keep_alive=0 forces model eviction from unified memory
      4. Cooldown: sleep --cooldown seconds to let Metal fully settle before next load

    This mirrors actual user behavior — no user loads back-to-back models without waiting.
    Prevents Metal page accumulation that causes OOM crashes under sequential large model loads.

    --order size (default): smallest models first so failures on large models don't waste time.
    --order config: preserves backends.yaml ordering.
    --cooldown N: seconds to wait after memory reclaim before loading next model (default: 10).
    --runs N: inference runs per model/workspace (default: 5).

Output: JSON file with raw TPS data for every model/workspace/persona.
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

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
# Legacy aliases — remove once all call sites are migrated.
BIG_MODEL_TIMEOUT = INFERENCE_TIMEOUT  # model already loaded after warmup
WORKSPACE_TIMEOUT = PIPELINE_INACTIVITY_TIMEOUT  # pipeline may buffer think

# Reasoning models (Laguna, Phi-4-reasoning, Magistral, Qwopus, DeepSeek-R1)
# emit <think> blocks that consume tokens before generating output. Two adjustments:
#   1. REASONING_MAX_TOKENS: larger budget so output isn't truncated mid-response.
#   2. Reasoning output is included in the token count; the larger budget keeps
#      TPS comparable across reasoning and non-reasoning models.
REASONING_MAX_TOKENS = 512
REASONING_WORKSPACES: frozenset[str] = frozenset(
    {
        "bench-laguna",
        "bench-phi4-reasoning",
        "bench-phi4-mini-reasoning",  # phi4-mini-reasoning — 3.8B thinking model
        "bench-foundation-sec",  # Foundation-Sec-8B-Reasoning — security CoT; 0 tokens without enable_thinking=False
        "bench-r1-0528-qwen3-8b",  # DeepSeek-R1-0528-Qwen3-8B — chain-of-thought
        "bench-r1-0528-abliterated",  # R1-0528 abliterated — same architecture
        "auto-mistral",
        "auto-reasoning",
        "auto-math",  # phi4-mini-reasoning production workspace
        "auto-security",  # AEON Qwen3.6-27B is a thinking model
        "auto-redteam",  # same — needs 512-token budget to avoid empty responses
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


RESULTS_DIR = Path(__file__).parent / "results"
# Default output: timestamped UTC file under tests/benchmarks/results/
# Override with --output. Operator commits selected baselines manually.
RESULTS_FILE = str(
    RESULTS_DIR / f"bench_tps_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
)

# ── Prompt library ────────────────────────────────────────────────────────────
# Category-mapped prompts designed to produce ~150-250 tokens of structured
# output. Each prompt targets a specific capability so TPS comparisons are
# apples-to-apples within a category. The "general" prompt is used as fallback.

PROMPTS: dict[str, str] = {
    "general": (
        "You are a helpful assistant. Answer concisely.\n\n"
        "List the 7 OSI model layers from bottom to top. For each layer, provide: "
        "1) the layer number, 2) the standard name, 3) one example protocol or technology. "
        "Format as a numbered list with one line per layer."
    ),
    "coding": (
        "You are a code assistant. Write clean, production-quality code.\n\n"
        "Write a Python function called `merge_intervals` that takes a list of "
        "tuples (each tuple is a pair of integers representing a start and end value) "
        "and returns a new list with overlapping intervals merged. "
        "Example: [(1,3),(2,6),(8,10),(15,18)] → [(1,6),(8,10),(15,18)]. "
        "Include type hints, a docstring with the algorithm explanation, and "
        "handle edge cases (empty list, single interval, fully overlapping). "
        "Return only the function, no explanation outside the docstring."
    ),
    "security": (
        "You are a cybersecurity analyst. Be precise and cite frameworks.\n\n"
        "Analyze the following scenario and provide a structured response:\n"
        "A company's SIEM detected repeated SSH brute-force attempts from 47 "
        "unique IPs over 2 hours targeting port 22 on 3 servers in the DMZ. "
        "Two IPs are on the CrowdSec community blocklist.\n\n"
        "For each item below, provide 2-3 sentences:\n"
        "1. Classification (MITRE ATT&CK tactic + technique ID)\n"
        "2. Immediate containment actions (first 30 minutes)\n"
        "3. Detection rule to write (field names + logic)\n"
        "4. Root cause question to investigate"
    ),
    "reasoning": (
        "You are a structured reasoner. Think step-by-step before concluding.\n\n"
        "A hospital emergency room has 30 patients arriving per hour during peak "
        "hours. The ER has 8 beds, 3 doctors, and 12 nurses. Average treatment "
        "time is 45 minutes per patient. Current wait time is 3.5 hours.\n\n"
        "Identify: 1) the primary bottleneck (beds, doctors, or nurses — show "
        "the math), 2) the minimum number of additional resources of each type "
        "needed to reduce wait time to under 1 hour, 3) one process change that "
        "could help without adding resources. Show your calculations."
    ),
    "creative": (
        "You are a creative writer with strong narrative voice.\n\n"
        "Write the opening scene (exactly 8-10 sentences) of a noir detective "
        "story set in a city where memories can be extracted and traded as "
        "currency. The detective has just been hired to find a stolen memory — "
        "but it belongs to the detective themselves. End the scene on a hook. "
        "Use vivid sensory details and short, punchy sentences."
    ),
    "vision": (
        "You are a multimodal vision analyst. Describe what you see precisely.\n\n"
        "For any image provided, respond with this exact structure:\n"
        "1. OBJECTS: List every distinct object visible (name + color + position)\n"
        "2. TEXT: Transcribe any visible text exactly as written\n"
        "3. SCENE: Describe the setting in 2-3 sentences\n"
        "4. ANOMALIES: Note anything unusual, damaged, or out of place\n"
        "5. CONFIDENCE: Rate your analysis certainty (high/medium/low) per category\n\n"
        "Since no image is provided for this text-only test, describe this prompt "
        "template itself — what it expects, what each section does, and suggest "
        "one improvement to the analysis framework."
    ),
    "math": (
        "You are a precise mathematical reasoner. Show all steps.\n\n"
        "Solve the following three problems. For each, show your work step by step "
        "and state your final answer clearly.\n\n"
        "1. ALGEBRA: Two trains travel toward each other. Train A leaves Station X "
        "at 8:00 AM at 60 km/h. Train B leaves Station Y (300 km away) at 8:00 AM "
        "at 40 km/h. At what time do they meet, and how far from Station X?\n\n"
        "2. COMBINATORICS: A team of 3 is chosen from 4 men and 5 women such that "
        "at least 2 women are on the team. How many distinct teams are possible? "
        "Show the case breakdown.\n\n"
        "3. NUMBER THEORY: Find all integers n such that n² + 3n − 18 = 0. "
        "Factor the expression and verify each solution by substitution."
    ),
}

# Map workspace IDs → prompt category
WORKSPACE_PROMPT_MAP: dict[str, str] = {
    "auto": "general",
    "auto-coding": "coding",
    "auto-agentic": "coding",
    "auto-spl": "coding",
    "auto-security": "security",
    "auto-redteam": "security",
    "auto-blueteam": "security",
    "auto-creative": "creative",
    "auto-reasoning": "reasoning",
    "auto-documents": "coding",
    "auto-video": "creative",
    "auto-music": "creative",
    "auto-research": "reasoning",
    "auto-vision": "vision",
    "auto-data": "reasoning",
    "auto-compliance": "reasoning",
    "auto-mistral": "reasoning",
    "auto-math": "reasoning",
    # Benchmark workspaces — prompt matches the model's primary capability
    "bench-qwen3-coder-next": "coding",
    "bench-qwen3-coder-30b": "coding",
    "bench-llama33-70b": "coding",
    "bench-phi4": "reasoning",
    "bench-phi4-reasoning": "reasoning",
    "bench-dolphin8b": "creative",
    "bench-glm": "coding",
    "bench-laguna": "reasoning",
    "bench-gptoss": "reasoning",
    # Granite 4.1 — IBM dense, no-think, tool-calling-first.
    # CC-01 is a creative-coding bench, but to keep cross-bench numbers
    # comparable Granite gets the same coding category as the other coders.
    # Granite's *strength* is tool calling/IFEval, not creative coding —
    # interpret a low CC-01 score against Laguna/GLM as expected, not a defect.
    "bench-granite41-8b": "coding",
    "bench-granite41-30b": "coding",
    "bench-qwen35-abliterated": "general",  # huihui_ai/qwen3.5-abliterated:9b — uncensored, AUTO primary baseline
    # ── V6 bench workspaces (TASK_MODEL_REFRESH_V6) — ascending size, family-grouped ──
    # 9B tier
    "bench-omnicoder2": "coding",  # omnicoder2:9b — Qwen3.5-9B SFT on agentic traces
    "bench-negentropy": "reasoning",  # Jackrong Negentropy 9B — trace-inversion CoT
    # Qwen3.6 family — 27B dense then 35B-A3B MoE (family-grouped, ascending)
    "bench-qwen36-27b": "coding",  # Qwen3.6-27B Q8 — dense 27B + vision, SWE-bench 77.2%
    "bench-qwen36-27b-mtp": "coding",  # Qwen3.6-27B MTP — speculative decoding bench
    "bench-qwen36-35b-a3b": "coding",  # Qwen3.6-35B-A3B — MoE 3B active, agentic-coding
    # 32B standalone
    "bench-olmo3-32b": "reasoning",  # OLMo-3-32B — Allen AI dense 32B, non-Qwen lineage
    # V7 bench workspaces — OCR, MoE creative, security reasoning, tools
    "bench-olmocr2": "vision",  # Allen AI olmOCR-2-7B — OCR/document understanding
    "bench-nanonets-ocr2": "vision",  # Nanonets OCR2-3B — OCR specialist
    "bench-lfm2-moe": "creative",  # LFM2-8B-A1B MoE — creative generation
    "bench-foundation-sec": "reasoning",  # Foundation-Sec-8B-Reasoning — security CoT
    "bench-toolace25": "coding",  # ToolACE-2.5 — tool-calling; "coding" is closest proxy
    # Auto workspaces added after TC-6 audit — fall back to "general" without these
    "auto-daily": "general",  # gemma4:26b-a4b-it-qat daily driver
    "auto-audio": "general",  # gemma4:12b-it-qat audio analyst
    # ── V7-final catalog refresh (TASK_MODEL_REFRESH_V7) ─────────────────
    # Apriel-Nemotron — ServiceNow+NVIDIA dense 15B reasoning, new lineage
    "bench-apriel-nemotron": "reasoning",
    # Unsloth Dynamic 2.0 Qwen3.6 pair — quant-method probe vs stock 4-bit
    "bench-qwen36-27b-ud": "coding",
    "bench-qwen36-35b-a3b-ud": "coding",
    # TASK_QUANT_TRUEUP_V1 — optimized-quant + uncensored-refresh A/B candidates
    "bench-qwen36-27b-optiq": "coding",  # OptiQ vs plain 4-bit dense (Finding A)
    "bench-gemma4-26b-optiq": "general",  # OptiQ vs plain gemma-4 (Finding A; fp16 KV only)
    "bench-huihui-qwen36-27b": "general",  # Qwen3.6 abliterated dense (Finding B)
    "bench-huihui-qwen36-35b-a3b": "general",  # Qwen3.6 abliterated MoE (Finding B, speed play)
    # ── V8 bench workspaces (TASK_MODEL_REFRESH_V8) ─────────────────────
    # Gemma 4 family — encoder-free multimodal, ascending size
    "bench-gemma4-e2b": "vision",  # Gemma 4 E2B — 2B efficient multimodal
    "bench-gemma4-e4b": "vision",  # Gemma 4 E4B — 4B efficient multimodal
    "bench-gemma4-e4b-qat": "vision",  # Gemma 4 E4B QAT — near-BF16 quant
    "bench-gemma4-12b": "general",  # Gemma 4 12B — mid-size multimodal
    "bench-gemma4-26b-qat": "general",  # Gemma 4 26B QAT — auto-daily production model
    "bench-gemma4-31b-qat": "general",  # Gemma 4 31B QAT — upper-tier candidate
    # Phi-4 mini family
    "bench-phi4-mini": "reasoning",  # Phi-4-mini — dense 3.8B reasoning
    "bench-phi4-mini-reasoning": "reasoning",  # Phi-4-mini-reasoning — AIME/MATH-500 specialist (auto-math primary)
    # LFM2.5 creative/music lane
    "bench-lfm25-8b": "creative",  # LFM2.5-8B — liquid foundation model, creative/music
    "bench-lfm25-8b-uncensored": "creative",  # LFM2.5-8B uncensored — abliterated creative variant
    # Coding lane additions
    "bench-starcoder2": "coding",  # StarCoder2 — code completion
    "bench-devstral-small-2": "coding",  # Devstral-Small-2 — Mistral coding specialist
    "bench-qwen3-coder-next-abliterated": "coding",  # Qwen3-Coder-Next abliterated (auto-spl primary)
    # Reasoning/security additions
    "bench-mistral-small32": "reasoning",  # Mistral-Small-3.2-24B
    "bench-r1-0528-qwen3-8b": "reasoning",  # DeepSeek-R1-0528-Qwen3-8B (auto-reasoning primary)
    "bench-r1-0528-abliterated": "reasoning",  # R1-0528 abliterated — CoT without refusals
    # General additions
    "bench-nex-n2-mini": "coding",  # Nex-N2-Mini — compact agentic coding
    "bench-harness1": "general",  # Harness-1 eval model
    "bench-qwen36-hauhaucs": "creative",  # Qwen3.6-35B-A3B HauhauCS uncensored (auto-creative primary)
    # Speech models — NOT in WORKSPACE_PROMPT_MAP by design:
    # - bench-voxtral-realtime (streaming ASR — text harness cannot exercise)
    # - bench-voxtral-tts (TTS — text harness cannot exercise)
    # - bench-granite-speech (ASR with keyword biasing — text harness cannot exercise)
    # These get probed by TASK_SPEECH_SHOOTOUT_V1 (deferred).
    # ── Drift backfill (pre-existing gap) ───────────────────────────────
    "tools-specialist": "coding",  # ToolACE-2.5 tool-calling specialist
}

# Map Ollama backend group → prompt category
GROUP_PROMPT_MAP: dict[str, str] = {
    "general": "general",
    "coding": "coding",
    "security": "security",
    "reasoning": "reasoning",
    "vision": "vision",
    "creative": "creative",
    "math": "math",
}

# Map persona category (from YAML) → prompt category
PERSONA_CATEGORY_PROMPT_MAP: dict[str, str] = {
    "security": "security",
    "redteam": "security",
    "blueteam": "security",
    "pentesting": "security",
    "coding": "coding",
    "software": "coding",
    "development": "coding",
    "systems": "coding",  # linuxterminal, sqlterminal
    "architecture": "reasoning",  # itarchitect — system design = reasoning
    "reasoning": "reasoning",
    "research": "reasoning",
    "analysis": "reasoning",
    "creative": "creative",
    "writing": "creative",
    "vision": "vision",
    "multimodal": "vision",
    "data": "reasoning",
    "compliance": "reasoning",
    "general": "general",  # itexpert, techreviewer
    "benchmark": "coding",  # benchmark personas test coding capability
}


def _get_prompt_for_model(model: str, group: str = "") -> str:
    """Get the right prompt for a model based on its group."""
    if group and group in GROUP_PROMPT_MAP:
        return PROMPTS[GROUP_PROMPT_MAP[group]]
    return PROMPTS["general"]


def _prompt_category_for_model(model: str, group: str = "") -> str:
    """Return the prompt category name for a model."""
    if group and group in GROUP_PROMPT_MAP:
        return GROUP_PROMPT_MAP[group]
    return "general"


def _get_prompt_for_workspace(workspace_id: str) -> str:
    category = WORKSPACE_PROMPT_MAP.get(workspace_id, "general")
    return PROMPTS[category]


def _get_prompt_for_persona_category(category: str) -> str:
    cat_lower = category.lower() if category else ""
    for key, prompt_cat in PERSONA_CATEGORY_PROMPT_MAP.items():
        if key in cat_lower:
            return PROMPTS[prompt_cat]
    return PROMPTS["general"]


def _prompt_category_for_persona(category: str) -> str:
    """Return the prompt category name for a persona category string."""
    cat_lower = category.lower() if category else ""
    for key, prompt_cat in PERSONA_CATEGORY_PROMPT_MAP.items():
        if key in cat_lower:
            return prompt_cat
    return "general"


PROJECT_ROOT = Path(__file__).parent.parent.parent


# ── Helpers ───────────────────────────────────────────────────────────────────


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


def _check_backend(url: str, path: str) -> bool:
    headers: dict[str, str] = {}
    if url == PIPELINE_URL and PIPELINE_API_KEY:
        headers["Authorization"] = f"Bearer {PIPELINE_API_KEY}"
    try:
        r = httpx.get(f"{url}{path}", timeout=3.0, headers=headers)
        return r.status_code == 200
    except Exception:
        pass
    return False


def _get_hardware_info() -> dict:
    info: dict = {"platform": platform.system(), "machine": platform.machine()}
    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
            info["unified_memory_gb"] = round(int(out.strip()) / 1024**3, 1)
        except Exception:
            pass
        try:
            out = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True)
            info["cpu"] = out.strip()
        except Exception:
            pass
    return info


def _load_backends_config() -> dict:
    cfg_path = PROJECT_ROOT / "config" / "backends.yaml"
    if not cfg_path.exists():
        return {}
    return yaml.safe_load(cfg_path.read_text()) or {}


def _unload_ollama_model(model: str) -> None:
    """Send keep_alive=0 to an Ollama model to force memory reclamation.

    Uses keep_alive=0 with an empty prompt to force immediate unload.
    """
    try:
        with httpx.Client(timeout=10.0) as client:
            client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": model, "keep_alive": 0, "prompt": ""},
            )
    except Exception:
        pass


def _unload_all_running_ollama_models() -> None:
    """Evict every model currently loaded in Ollama via keep_alive=0.

    Uses /api/ps (running models
    only) rather than /api/tags (all installed) to avoid briefly loading models
    that happen to be installed but idle.
    """
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{OLLAMA_URL}/api/ps")
            if r.status_code != 200:
                return
            models = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return
    for name in models:
        try:
            with httpx.Client(timeout=15.0) as client:
                client.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={"model": name, "keep_alive": 0, "prompt": ""},
                )
        except Exception:
            pass


def _warmup_ollama_model(model: str) -> bool:
    """Send a minimal warm-up request to force Ollama to load the model.

    Ollama lazily loads models into unified memory on first request. Without
    warm-up, run 1 of every benchmarked model includes load time, inflating
    elapsed and depressing TPS.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "max_tokens": 1,
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{OLLAMA_URL}/v1/chat/completions", json=payload)
            return resp.status_code == 200
    except Exception:
        return False


def _wait_ollama_idle(timeout_s: float = 60.0) -> bool:
    """Poll /api/ps until no models are running (memory fully reclaimed).

    Returns True if Ollama becomes idle within timeout_s, False otherwise.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = httpx.get(f"{OLLAMA_URL}/api/ps", timeout=5.0)
            if r.status_code == 200 and not r.json().get("models"):
                return True
        except Exception:
            pass
        time.sleep(2.0)
    return False


def _check_memory_pressure(threshold_pct: float = 85.0) -> tuple[bool, float]:
    """Check if system memory pressure is too high via vm_stat.

    Returns (safe, used_pct). If used_pct > threshold_pct, safe=False.
    """
    try:
        out = subprocess.check_output(["vm_stat"], text=True, timeout=5)
        free = active = inactive = speculative = wired = 0
        for line in out.splitlines():
            if "Pages free:" in line:
                free = int(line.split(":")[1].strip().rstrip("."))
            elif "Pages active:" in line:
                active = int(line.split(":")[1].strip().rstrip("."))
            elif "Pages inactive:" in line:
                inactive = int(line.split(":")[1].strip().rstrip("."))
            elif "Pages speculative:" in line:
                speculative = int(line.split(":")[1].strip().rstrip("."))
            elif "Pages wired down:" in line:
                wired = int(line.split(":")[1].strip().rstrip("."))
        total = free + active + inactive + speculative + wired
        if total > 0:
            used_pct = round((active + wired + speculative) / total * 100, 1)
            return used_pct < threshold_pct, used_pct
    except Exception:
        pass
    return False, 99.0


def _purge_memory() -> None:
    """Run macOS `purge` to force inactive-page compaction and unblock Metal buffers."""
    try:
        subprocess.run(["purge"], timeout=15, check=False, capture_output=True)
        print("  [metal] purge completed", flush=True)
    except Exception as e:
        print(f"  [metal] purge failed (non-fatal): {e}", flush=True)


def _restart_ollama_server() -> bool:
    """Restart Ollama to clear stuck Metal GPU contexts. Returns True if healthy after restart."""
    print("  [metal] Restarting Ollama to clear stuck Metal contexts ...", flush=True)
    try:
        subprocess.run(["brew", "services", "restart", "ollama"],
                       timeout=30, check=False, capture_output=True)
    except Exception:
        try:
            subprocess.run(["pkill", "-f", "ollama serve"],
                           timeout=5, check=False, capture_output=True)
            time.sleep(3)
            subprocess.Popen(["ollama", "serve"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"  [metal] Ollama restart failed: {e}", flush=True)
            return False
    deadline = time.time() + 30.0
    while time.time() < deadline:
        try:
            r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3)
            if r.status_code == 200:
                print("  [metal] Ollama back healthy after restart", flush=True)
                return True
        except Exception:
            pass
        time.sleep(2.0)
    return False


def _wait_metal_drain(threshold_pct: float = 80.0, timeout_s: float = 30.0,
                      retries: int = 2) -> bool:
    """Poll vm_stat until wired memory drops below threshold_pct.

    Escalating recovery on timeout:
      Round 1 timeout → run purge (memory compaction, no process kills)
      Round 2 timeout → restart Ollama (clears all Metal contexts)
      Round 3+ timeout → return False (caller should skip next model)

    Returns True if drain succeeded, False if all retries exhausted.
    """
    for attempt in range(retries + 1):
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            safe, used_pct = _check_memory_pressure(threshold_pct)
            if safe:
                print(f"  [metal] Clear at {used_pct:.0f}% — safe to load next model", flush=True)
                return True
            remaining = int(deadline - time.time())
            print(f"  [metal] {used_pct:.0f}% (attempt {attempt + 1}/{retries + 1}, {remaining}s left)",
                  flush=True)
            time.sleep(5.0)
        if attempt == 0:
            print(f"  [metal] Timeout — running purge to unblock Metal", flush=True)
            _purge_memory()
        elif attempt == 1:
            print(f"  [metal] Timeout — restarting Ollama to clear Metal contexts", flush=True)
            _restart_ollama_server()
    _, used_pct = _check_memory_pressure(threshold_pct)
    print(f"  [metal] DRAIN FAILED — {used_pct:.0f}% after all retries — skipping next model",
          flush=True)
    return False


def _cleanup_all_backends() -> None:
    """Full cleanup: unload all Ollama models to free memory.

    Called at the end of the benchmark to prevent OOM after testing completes.
    """
    print("\n  Cleaning up: unloading all models from memory ...", end=" ", flush=True)
    _unload_all_running_ollama_models()
    _wait_ollama_idle(timeout_s=30.0)
    print("ok")


def _parse_ollama_sizes_from_config() -> dict[str, float]:
    """Parse model→GB size estimates from backends.yaml inline comments.

    Priority:
    1. Inline comments like '# ~46GB' (Ollama models).
    2. Parameter count inferred from model name (e.g., ':70b' → ~40GB for Q4).
    3. Fallback: 20.0 GB (conservative).
    """
    import re

    sizes: dict[str, float] = {}
    cfg_path = PROJECT_ROOT / "config" / "backends.yaml"
    if cfg_path.exists():
        model_re = re.compile(r"^\s+-\s+(\S+)")
        size_re = re.compile(r"~(\d+(?:\.\d+)?)\s*GB")
        for line in cfg_path.read_text().splitlines():
            m = model_re.match(line)
            if m:
                name = m.group(1)
                s = size_re.search(line)
                if s:
                    sizes[name] = float(s.group(1))
    return sizes


def _infer_ollama_model_size(model_name: str) -> float:
    """Estimate Ollama model memory from name patterns.

    GGUF models: Q4 ≈ 0.6 bytes/param, Q5 ≈ 0.7, Q6 ≈ 0.8, Q8 ≈ 1.0.
    MoE models: size based on active parameters, not total.
    """
    import re

    name = model_name.lower()

    # MoE models: extract active param count (e.g., "30b-a3b" → 3B active)
    moe_match = re.search(r"(\d+)b-(\d+)b", name)
    if moe_match:
        active_b = int(moe_match.group(2))
        return _gb_per_param(active_b, name)

    # Standard models: extract param count from :Nb or -Nb pattern
    param_match = re.search(r"[:/-](\d+(?:\.\d+)?)b", name)
    if param_match:
        params_b = float(param_match.group(1))
        return _gb_per_param(params_b, name)

    return 20.0


def _gb_per_param(params_b: float, name: str) -> float:
    """Estimate GB from parameter count and quant level in name."""
    if "q8" in name or "8bit" in name:
        return round(params_b * 1.0, 1)
    if "q6" in name:
        return round(params_b * 0.8, 1)
    if "q5" in name:
        return round(params_b * 0.7, 1)
    if "q4" in name or "4bit" in name:
        return round(params_b * 0.6, 1)
    # Unknown quant: assume Q4 (most common GGUF default)
    return round(params_b * 0.6, 1)


_CONFIG_SIZES = _parse_ollama_sizes_from_config()


def _parse_model_size_gb(model_name: str) -> float:
    """Estimate model memory footprint in GB.

    Uses inline '# ~XXGB' comments from backends.yaml when available,
    then falls back to name-pattern inference, then 20GB.
    """
    if model_name in _CONFIG_SIZES:
        return _CONFIG_SIZES[model_name]
    return _infer_ollama_model_size(model_name)


# ── Model discovery: config-driven (canonical source of truth) ───────────────


def _config_ollama_models_by_group() -> dict[str, list[str]]:
    """Ollama models grouped by backend group from backends.yaml.

    Handles both legacy flat-string entries and the current dict form
    (`{id, supports_tools, notes, …}`) introduced in commit 1af5b3c.
    """
    cfg = _load_backends_config()
    groups: dict[str, list[str]] = {}
    for be in cfg.get("backends", []):
        if be.get("type") == "ollama":
            group = be.get("group", be.get("id", "unknown"))
            entries = be.get("models", []) or []
            ids: list[str] = []
            for m in entries:
                if isinstance(m, dict):
                    mid = m.get("id")
                    if mid:
                        ids.append(mid)
                elif isinstance(m, str):
                    ids.append(m)
            groups[group] = ids
    return groups


def _config_ollama_models_unique() -> list[str]:
    """All unique Ollama models from backends.yaml, deduplicated."""
    seen: set[str] = set()
    unique: list[str] = []
    for models in _config_ollama_models_by_group().values():
        for m in models:
            if m not in seen:
                seen.add(m)
                unique.append(m)
    return unique


def _runtime_ollama_models() -> set[str]:
    """Models actually installed in Ollama (from /api/tags).

    Adds lowercase + :latest-stripped variants so backends.yaml entries
    (e.g. 'deepseek-coder-v2-lite:q4_k_m') match Ollama's actual name
    ('deepseek-coder-v2-lite:Q4_K_M:latest').
    """
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
        if r.status_code == 200:
            names: set[str] = set()
            for m in r.json().get("models", []):
                name = m["name"]
                names.add(name)
                # lowercase variant (handles Q4_K_M vs q4_k_m)
                names.add(name.lower())
                # strip :latest suffix variants
                for variant in (name, name.lower()):
                    if variant.endswith(":latest"):
                        names.add(variant[: -len(":latest")])
            return names
    except Exception:
        pass
    return set()


def _config_workspaces() -> list[str]:
    """All workspace IDs from backends.yaml, sorted by primary backend group.

    Sorting by the first group in each workspace's routing list keeps the same
    backend active across consecutive tests, minimising model swaps.

    Workspaces listed in the top-level ``pipeline_bench_skip:`` list are
    excluded — see backends.yaml for rationale. The exclusion does NOT
    apply when bench_pipeline() is called with an explicit workspace
    filter (operator-driven probe overrides config-level skip).
    """
    cfg = _load_backends_config()
    routing: dict[str, list[str]] = cfg.get("workspace_routing", {})
    skip = set(cfg.get("pipeline_bench_skip", []))
    return sorted(
        (ws for ws in routing if ws not in skip),
        key=lambda ws: (routing[ws][0] if routing[ws] else "", ws),
    )


def _discover_personas() -> list[dict]:
    """Read all persona YAMLs, return [{slug, name, workspace_model, category}]."""
    personas_dir = PROJECT_ROOT / "config" / "personas"
    if not personas_dir.exists():
        return []
    personas = []
    for f in sorted(personas_dir.glob("*.yaml")):
        try:
            p = yaml.safe_load(f.read_text())
        except Exception:
            continue
        personas.append(
            {
                "slug": p.get("slug", f.stem),
                "name": p.get("name", f.stem),
                "workspace_model": p.get("workspace_model", "dolphin-llama3:8b"),
                "category": p.get("category", "general"),
            }
        )
    return personas


# ── Incremental result persistence ────────────────────────────────────────────


def _init_output(
    output_path: str, args, hw: dict, ollama_cfg, workspaces_cfg, personas_cfg
) -> dict:
    """Initialize or load the output file. Returns the output dict."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if os.path.exists(output_path):
        try:
            with open(output_path) as f:
                existing = json.load(f)
            if existing.get("results"):
                print(
                    f"  Resuming from {len(existing['results'])} existing results in {output_path}"
                )
                return existing
        except Exception:
            pass
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "order": args.order,
        "cooldown_s": args.cooldown,
        "runs_per_model": args.runs,
        "spec_decoding": args.spec_decoding_tag or "unspecified",
        "kv_quant_tag": args.kv_quant_tag or "unspecified",
        "total_wall_time_s": 0,
        "hardware": hw,
        "config_summary": {
            "ollama_models_configured": len(ollama_cfg),
            "workspaces_configured": len(workspaces_cfg),
            "personas_configured": len(personas_cfg),
        },
        "backends": {
            "ollama": {"url": OLLAMA_URL},
            "pipeline": {"url": PIPELINE_URL},
        },
        "results": [],
    }
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    return output


def _append_result(output_path: str, result: dict) -> None:
    """Append a single result to the output JSON file (crash-safe)."""
    try:
        with open(output_path) as f:
            data = json.load(f)
        data["results"].append(result)
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"    ⚠️  Failed to save result: {e}")


def _result_already_done(output_path: str, match_key: str, match_value: str) -> bool:
    """Check if a result for this model/workspace/persona already exists."""
    try:
        with open(output_path) as f:
            data = json.load(f)
        return any(
            r.get(match_key) == match_value and r.get("runs_success", 0) > 0
            for r in data.get("results", [])
        )
    except Exception:
        return False


# ──Core benchmark ───────────────────────────────────────────────────────────


# P7-PERF: Module-level reusable httpx client for benchmarks
_bench_client: httpx.Client | None = None


def _get_bench_client() -> httpx.Client:
    """Get or create the shared benchmark httpx client."""
    global _bench_client
    if _bench_client is None:
        _bench_client = httpx.Client(
            timeout=REQUEST_TIMEOUT,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _bench_client


def _warmup_pipeline_model(
    model_id: str,
    timeout_s: float = WARMUP_TIMEOUT,
) -> bool:
    """Fire a 1-token request through the pipeline and block until it responds.

    The HTTP response IS the "model loaded" event — no timers, no sleep loops.
    Returns True when the pipeline replies (model is ready for timed runs).
    Returns False only if the pipeline never responds within timeout_s (failsafe).

    After this returns True, bench_tps should use INFERENCE_TIMEOUT (or
    PIPELINE_INACTIVITY_TIMEOUT for reasoning workspaces), not WARMUP_TIMEOUT,
    because the model is already loaded.
    """
    headers: dict[str, str] = {}
    if PIPELINE_API_KEY:
        headers["Authorization"] = f"Bearer {PIPELINE_API_KEY}"
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "max_tokens": 1,
    }
    deadline = time.time() + timeout_s
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        try:
            with httpx.Client(timeout=min(remaining, 30.0)) as c:
                r = c.post(
                    f"{PIPELINE_URL}/v1/chat/completions",
                    json=payload,
                    headers=headers,
                )
                if r.status_code == 200:
                    return True
                if r.status_code in (503, 502) and attempt < 5:
                    time.sleep(3)
                    continue
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError):
            if time.time() < deadline:
                time.sleep(3)
            continue
        except Exception:
            break
    return False


def bench_tps(
    base_url: str,
    model: str,
    prompt: str,
    runs: int = 3,
    label: str = "",
    prompt_category: str = "",
    request_timeout: float = REQUEST_TIMEOUT,
) -> dict:
    """Benchmark TPS for a single model/endpoint. Returns summary dict.

    Uses streaming to capture time-to-first-token (TTFT) alongside TPS.

    P7-PERF: Reuses a shared httpx client to avoid TCP connection overhead
    between runs. This gives a more accurate measurement of actual inference
    time vs connection setup time.
    """
    import json as _json

    _reasoning = _is_reasoning_model(model, label)
    _nothink = any(p in model for p in _NOTHINK_PATTERNS)
    content = "/nothink\n" + prompt if _nothink else prompt
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "stream": True,
        "max_tokens": REASONING_MAX_TOKENS if _reasoning else MAX_TOKENS,
    }

    headers: dict[str, str] = {}
    if base_url == PIPELINE_URL and PIPELINE_API_KEY:
        headers["Authorization"] = f"Bearer {PIPELINE_API_KEY}"

    client = _get_bench_client()
    run_results = []

    def _stream_one_run(run_num: int) -> dict:
        """Execute one streaming inference run and return its result dict."""
        t0 = time.perf_counter()
        t_first_token: float | None = None
        completion_tokens = 0
        prompt_tokens = 0
        response_text = ""
        reasoning_text = ""
        response_model = ""

        try:
            with client.stream(
                "POST",
                f"{base_url}/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=request_timeout,
            ) as resp:
                if resp.status_code != 200:
                    body = resp.read()[:200].decode(errors="replace")
                    return {
                        "run": run_num,
                        "error": f"HTTP {resp.status_code}: {body[:80]}",
                        "elapsed_s": round(time.perf_counter() - t0, 2),
                    }
                for raw_line in resp.iter_lines():
                    line = (
                        raw_line.strip()
                        if isinstance(raw_line, str)
                        else raw_line.decode(errors="replace").strip()
                    )
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        obj = _json.loads(data_str)
                    except Exception:
                        continue
                    delta = obj.get("choices", [{}])[0].get("delta", {})
                    chunk_text = delta.get("content") or ""
                    reasoning_chunk = delta.get("reasoning") or ""
                    if (chunk_text or reasoning_chunk) and t_first_token is None:
                        t_first_token = time.perf_counter()
                    response_text += chunk_text
                    reasoning_text += reasoning_chunk
                    if not response_model:
                        response_model = obj.get("model", "")
                    # Usage may appear in the final chunk
                    usage = obj.get("usage") or {}
                    if usage.get("completion_tokens"):
                        completion_tokens = usage["completion_tokens"]
                    if usage.get("prompt_tokens"):
                        prompt_tokens = usage["prompt_tokens"]

        except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
            return {
                "run": run_num,
                "error": str(e)[:100],
                "elapsed_s": round(time.perf_counter() - t0, 2),
            }
        except httpx.ReadTimeout:
            return {"run": run_num, "error": "timeout", "elapsed_s": request_timeout}
        except Exception as e:
            return {
                "run": run_num,
                "error": str(e)[:100],
                "elapsed_s": round(time.perf_counter() - t0, 2),
            }

        elapsed = time.perf_counter() - t0
        # Fallback token count: estimate from response + reasoning text if server didn't emit usage.
        # Reasoning tokens (delta.reasoning) count toward TPS — they represent real generation work.
        combined_text = response_text + (" " + reasoning_text if reasoning_text else "")
        if completion_tokens == 0 and combined_text.strip():
            completion_tokens = max(1, len(combined_text.split()))
        # Empty response: server returned HTTP 200 and a valid stream, but zero
        # content and zero reasoning tokens.  Treat as a failure so runs_success
        # accurately reflects whether the model produced usable output.
        if completion_tokens == 0:
            return {
                "run": run_num,
                "error": "empty response (0 tokens)",
                "elapsed_s": round(elapsed, 2),
            }
        tps = completion_tokens / elapsed if elapsed > 0 else 0.0
        ttft = round(t_first_token - t0, 3) if t_first_token is not None else None

        result: dict = {
            "run": run_num,
            "elapsed_s": round(elapsed, 2),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tps": round(tps, 1),
            "time_to_first_token_s": ttft,
            "response_model": response_model,
            "response_text": response_text,
        }
        if reasoning_text:
            result["reasoning_text"] = reasoning_text
        return result

    for run_num in range(1, runs + 1):
        result = _stream_one_run(run_num)
        run_results.append(result)

    successful = [r for r in run_results if "tps" in r]
    if successful:
        import statistics  # noqa: PLC0415

        tps_vals = [r["tps"] for r in successful]
        avg_tps = round(sum(tps_vals) / len(tps_vals), 1)
        min_tps = min(tps_vals)
        max_tps = max(tps_vals)
        # Sample stddev requires ≥2 runs. With one run, jitter is undefined.
        stddev_tps = round(statistics.stdev(tps_vals), 2) if len(tps_vals) > 1 else None
        # Coefficient of variation: stddev / mean. Dimensionless — comparable
        # across models with different absolute TPS. <0.05 tight, 0.05-0.15
        # normal, >0.15 unstable (warmup not done, memory pressure, etc.)
        cv = round(stddev_tps / avg_tps, 3) if (stddev_tps is not None and avg_tps > 0) else None
        avg_tokens = round(sum(r["completion_tokens"] for r in successful) / len(successful))
        avg_elapsed = round(sum(r["elapsed_s"] for r in successful) / len(successful), 2)
        ttft_vals = [
            r["time_to_first_token_s"]
            for r in successful
            if r.get("time_to_first_token_s") is not None
        ]
        avg_ttft = round(sum(ttft_vals) / len(ttft_vals), 3) if ttft_vals else None
    else:
        avg_tps = min_tps = max_tps = 0.0
        stddev_tps = None
        cv = None
        avg_tokens = 0
        avg_elapsed = 0.0
        avg_ttft = None

    # Capture the actual model returned by the API (pipeline routing may differ)
    routed_model = ""
    last_response_text = ""
    if successful:
        last_ok = successful[-1]
        routed_model = last_ok.get("response_model", "")
        last_response_text = last_ok.get("response_text", "") or last_ok.get("reasoning_text", "")

    # Quality scoring: measure signal coverage for this prompt category
    try:
        import os as _os
        import sys as _sys

        _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), ".."))
        from quality_signals import quality_score as _qs

        qs = round(_qs(prompt_category, last_response_text), 2) if last_response_text else 0.0
    except Exception:
        qs = 1.0  # Don't penalize if signals module unavailable

    tps_quality = round(avg_tps * qs, 1)

    expected_match: bool | None = None
    expected_detail = ""
    try:
        import sys as _sys
        from pathlib import Path as _Path

        _sys.path.insert(0, str(_Path(__file__).parent.parent))
        from expected_models import (
            expected_model_keys,
            model_matches_expected,
        )

        if routed_model:
            if base_url == PIPELINE_URL:
                keys, src = expected_model_keys(model)
                if keys:
                    expected_match = model_matches_expected(routed_model, keys)
                    expected_detail = src
            else:
                requested_basename = model.split("/")[-1].lower()
                expected_match = requested_basename in routed_model.lower()
                expected_detail = f"requested {requested_basename}"
    except Exception as e:
        expected_detail = f"expected-check error: {e}"

    return {
        "model": model,
        "label": label,
        "runs_total": runs,
        "runs_success": len(successful),
        "avg_tps": avg_tps,
        "min_tps": min_tps,
        "max_tps": max_tps,
        "stddev_tps": stddev_tps,  # None if <2 successful runs
        "cv": cv,  # coefficient of variation; None if avg_tps==0
        "avg_completion_tokens": avg_tokens,
        "avg_elapsed_s": avg_elapsed,
        "avg_ttft_s": avg_ttft,
        "routed_model": routed_model,
        "prompt_category": prompt_category,
        "quality_score": qs,
        "tps_quality": tps_quality,
        "reasoning_mode": _reasoning,
        "expected_model_match": expected_match,
        "expected_model_detail": expected_detail,
        "runs": run_results,
    }


# ── Direct backend tests ─────────────────────────────────────────────────────


def bench_direct(
    ollama_available: bool,
    models_filter: str | None,
    runs: int,
    dry_run: bool,
    cooldown: float = 10.0,
    order: str = "size",
    output_path: str = "",
) -> list[dict]:
    results = []

    if ollama_available and not os.environ.get("BENCH_SKIP_OLLAMA"):
        ollama_groups = _config_ollama_models_by_group()
        ollama_unique = _config_ollama_models_unique()
        if models_filter:
            ollama_unique = [m for m in ollama_unique if models_filter in m]
        if order in ("size", "largest"):
            ollama_unique = sorted(
                ollama_unique,
                key=lambda m: _parse_model_size_gb(m),
                reverse=(order == "largest"),
            )
        runtime = _runtime_ollama_models()
        print(
            f"\n  Ollama models configured: {len(ollama_unique)} (across {len(ollama_groups)} groups, order={order})"
        )
        if runtime:
            installed = [m for m in ollama_unique if m in runtime]
            missing = [m for m in ollama_unique if m not in runtime]
            print(f"  Ollama installed: {len(installed)}/{len(ollama_unique)}")
            if missing:
                print(f"  Ollama not installed: {', '.join(missing)}")
        for i, model in enumerate(ollama_unique, 1):
            # Resume: skip already-completed models
            if output_path and _result_already_done(output_path, "model", model):
                print(f"    [{i}/{len(ollama_unique)}] {model} SKIP (already done)")
                continue
            available = model in runtime if runtime else True
            size_gb = _parse_model_size_gb(model)
            marker = "" if available else " [not installed]"
            print(
                f"    [{i}/{len(ollama_unique)}] {model} ({size_gb:.0f}GB){marker} ...",
                end=" ",
                flush=True,
            )
            if dry_run:
                print("(dry run)")
                continue
            if not available:
                print("SKIP")
                r = {
                    "model": model,
                    "label": "ollama-direct",
                    "backend": "ollama",
                    "path": "direct",
                    "available": False,
                    "error": "not installed in Ollama",
                    "est_memory_gb": size_gb,
                    "groups": [g for g, ms in ollama_groups.items() if model in ms],
                    "runs_total": runs,
                    "runs_success": 0,
                    "avg_tps": 0,
                    "min_tps": 0,
                    "max_tps": 0,
                    "stddev_tps": None,
                    "cv": None,
                    "avg_completion_tokens": 0,
                    "avg_elapsed_s": 0,
                    "runs": [],
                }
                results.append(r)
                if output_path:
                    _append_result(output_path, r)
                continue
            model_groups = [g for g, ms in ollama_groups.items() if model in ms]
            group = model_groups[0] if model_groups else ""
            prompt = _get_prompt_for_model(model, group=group)
            # Warm-up: force Ollama to load model before timed runs so run 1
            # doesn't include model-load latency.
            print("(warm-up) ", end="", flush=True)
            _warmup_ollama_model(model)
            prompt_cat = _prompt_category_for_model(model, group=group)
            r = bench_tps(
                OLLAMA_URL,
                model,
                prompt=prompt,
                runs=runs,
                label="ollama-direct",
                prompt_category=prompt_cat,
            )
            r["backend"] = "ollama"
            r["path"] = "direct"
            r["available"] = True
            r["est_memory_gb"] = size_gb
            r["groups"] = model_groups
            r["prompt_category"] = prompt_cat
            results.append(r)
            if output_path:
                _append_result(output_path, r)
            if r["avg_tps"] > 0:
                print(f"{r['avg_tps']} t/s  ({r['runs_success']}/{r['runs_total']} ok)")
            else:
                errors = [run.get("error", "?") for run in r["runs"] if "error" in run]
                print(f"FAIL ({', '.join(set(errors))})")
            if r.get("expected_model_match") is False:
                print(
                    f"  ⚠ ROUTING: got {r['routed_model']}, expected {r['expected_model_detail']}",
                    flush=True,
                )
            cv_val = r.get("cv")
            if cv_val is not None and cv_val > 0.15:
                print(
                    f"  ⚠ HIGH JITTER: cv={cv_val:.2f} "
                    f"(stddev={r.get('stddev_tps')} avg={r.get('avg_tps')})",
                    flush=True,
                )
            # Extra math pass — math-specialist models run the math prompt in addition
            # to their primary category prompt so both QS scores are in the results.
            is_math_specialist = any(
                p.lower() in model.lower() for p in _MATH_SPECIALIST_PATTERNS
            )
            if is_math_specialist and r.get("available", True) and not dry_run:
                math_model_label = f"{model}:math"
                if output_path and _result_already_done(output_path, "model", math_model_label):
                    print(f"      {model}:math SKIP (already done)")
                else:
                    print(f"      {model}:math ...", end=" ", flush=True)
                    rm = bench_tps(
                        OLLAMA_URL,
                        model,
                        prompt=PROMPTS["math"],
                        runs=runs,
                        label="ollama-direct",
                        prompt_category="math",
                    )
                    rm["backend"] = "ollama"
                    rm["path"] = "direct"
                    rm["available"] = True
                    rm["est_memory_gb"] = size_gb
                    rm["groups"] = model_groups
                    rm["prompt_category"] = "math"
                    rm["model"] = math_model_label
                    results.append(rm)
                    if output_path:
                        _append_result(output_path, rm)
                    if rm["avg_tps"] > 0:
                        print(f"{rm['avg_tps']} t/s  ({rm['runs_success']}/{rm['runs_total']} ok) [math]")
                    else:
                        errors = [run.get("error", "?") for run in rm["runs"] if "error" in run]
                        print(f"FAIL [math] ({', '.join(set(errors))})")
            # Force Ollama to release this model from unified memory before next test.
            if i < len(ollama_unique):
                _unload_all_running_ollama_models()
                idle = _wait_ollama_idle(timeout_s=max(cooldown * 10, 60.0))
                if not idle:
                    if cooldown > 0:
                        print(
                            f"    cooldown {cooldown:.0f}s (idle timeout) ...", end=" ", flush=True
                        )
                        time.sleep(cooldown)
                        print("ok")
                else:
                    print("    ollama idle (memory clear)", end="", flush=True)
                    if cooldown > 0:
                        print(f" + {cooldown:.0f}s cooldown ...", end=" ", flush=True)
                        time.sleep(cooldown)
                    print("ok")
                # Poll until Metal GPU buffers drain before loading the next model.
                # Escalates from purge → Ollama restart if polling times out.
                # Returns False if drain fails after all retries — skip next model
                # rather than loading into a known-bad memory state.
                if not _wait_metal_drain(threshold_pct=80.0, timeout_s=30.0, retries=2):
                    print(f"    [{i}/{len(ollama_unique)}] SKIP next — Metal drain failed, "
                          "continuing to avoid OOM cascade", flush=True)

    return results


# ── Pipeline workspace tests ─────────────────────────────────────────────────


def bench_pipeline(
    pipeline_available: bool,
    workspace_filter: str | None,
    runs: int,
    dry_run: bool,
    output_path: str = "",
) -> list[dict]:
    if not pipeline_available:
        return []

    if workspace_filter:
        # Explicit operator filter overrides pipeline_bench_skip — operator
        # wants to probe this specific workspace intentionally.
        cfg = _load_backends_config()
        routing: dict[str, list[str]] = cfg.get("workspace_routing", {})
        workspaces = [workspace_filter] if workspace_filter in routing else []
    else:
        workspaces = _config_workspaces()

    results = []
    print(f"\n  Pipeline workspaces to test: {len(workspaces)}")
    for i, ws in enumerate(workspaces, 1):
        # Resume: skip already-completed workspaces
        if output_path and _result_already_done(output_path, "workspace", ws):
            print(f"    [{i}/{len(workspaces)}] {ws} SKIP (already done)")
            continue
        print(f"    [{i}/{len(workspaces)}] {ws} ...", end=" ", flush=True)
        if dry_run:
            print("(dry run)")
            continue
        prompt = _get_prompt_for_workspace(ws)
        prompt_cat = WORKSPACE_PROMPT_MAP.get(ws, "general")
        print("(warm-up) ", end="", flush=True)
        _warmup_pipeline_model(ws)
        _ws_timeout = (
            PIPELINE_INACTIVITY_TIMEOUT
            if _is_reasoning_model("", ws)
            else PIPELINE_INACTIVITY_TIMEOUT
        )
        r = bench_tps(
            PIPELINE_URL,
            ws,
            prompt=prompt,
            runs=runs,
            label="pipeline",
            prompt_category=prompt_cat,
            request_timeout=_ws_timeout,
        )
        r["backend"] = "pipeline"
        r["path"] = "pipeline"
        r["workspace"] = ws
        r["prompt_category"] = prompt_cat
        results.append(r)
        if output_path:
            _append_result(output_path, r)
        if r["avg_tps"] > 0:
            print(f"{r['avg_tps']} t/s  ({r['runs_success']}/{r['runs_total']} ok)")
        else:
            errors = [run.get("error", "?") for run in r["runs"] if "error" in run]
            print(f"FAIL ({', '.join(set(errors))})")
        if r.get("expected_model_match") is False:
            print(
                f"  ⚠ ROUTING: got {r['routed_model']}, expected {r['expected_model_detail']}",
                flush=True,
            )

        # Extra math pass — run math-specialist workspaces with the math prompt
        # in addition to their primary category prompt.
        if ws in MATH_SPECIALIST_WORKSPACES and not dry_run:
            math_label = f"{ws}:math"
            if output_path and _result_already_done(output_path, "workspace", math_label):
                print(f"    [{i}/{len(workspaces)}] {ws}:math SKIP (already done)")
            else:
                print(f"    [{i}/{len(workspaces)}] {ws}:math ...", end=" ", flush=True)
                rm = bench_tps(
                    PIPELINE_URL,
                    ws,
                    prompt=PROMPTS["math"],
                    runs=runs,
                    label="pipeline",
                    prompt_category="math",
                    request_timeout=PIPELINE_INACTIVITY_TIMEOUT,
                )
                rm["backend"] = "pipeline"
                rm["path"] = "pipeline"
                rm["workspace"] = math_label
                rm["prompt_category"] = "math"
                results.append(rm)
                if output_path:
                    _append_result(output_path, rm)
                if rm["avg_tps"] > 0:
                    print(f"{rm['avg_tps']} t/s  ({rm['runs_success']}/{rm['runs_total']} ok) [math]")
                else:
                    errors = [run.get("error", "?") for run in rm["runs"] if "error" in run]
                    print(f"FAIL [math] ({', '.join(set(errors))})")

    return results


# ── Persona tests ────────────────────────────────────────────────────────────


def bench_personas(
    pipeline_available: bool,
    persona_filter: str | None,
    runs: int,
    dry_run: bool,
    output_path: str = "",
) -> list[dict]:
    """Test TPS for each persona's workspace_model through the pipeline."""
    if not pipeline_available:
        return []

    personas = _discover_personas()
    if persona_filter:
        personas = [
            p
            for p in personas
            if persona_filter in p["slug"] or persona_filter in p["name"].lower()
        ]
    # Sort by workspace_model so personas that share a model run consecutively,
    # minimising Ollama model swaps.
    personas = sorted(personas, key=lambda p: (p["workspace_model"], p["slug"]))

    results = []
    print(f"\n  Personas to test: {len(personas)}")
    for i, p in enumerate(personas, 1):
        slug = p["slug"]
        wm = p["workspace_model"]
        cat = p["category"]
        # Resume: skip already-completed personas
        if output_path and _result_already_done(output_path, "persona_slug", slug):
            print(f"    [{i}/{len(personas)}] {slug} ({cat}) SKIP (already done)")
            continue
        print(f"    [{i}/{len(personas)}] {slug} ({cat}) → {wm} ...", end=" ", flush=True)
        if dry_run:
            print("(dry run)")
            continue
        prompt = _get_prompt_for_persona_category(cat)
        prompt_cat = _prompt_category_for_persona(cat)
        _warmup_pipeline_model(wm)
        _p_timeout = (
            PIPELINE_INACTIVITY_TIMEOUT
            if _is_reasoning_model("", wm)
            else PIPELINE_INACTIVITY_TIMEOUT
        )
        r = bench_tps(
            PIPELINE_URL,
            wm,
            prompt=prompt,
            runs=runs,
            label="persona",
            prompt_category=prompt_cat,
            request_timeout=_p_timeout,
        )
        r["backend"] = "pipeline"
        r["path"] = "persona"
        r["persona_slug"] = slug
        r["persona_name"] = p["name"]
        r["persona_category"] = cat
        r["workspace_model"] = wm
        r["prompt_category"] = prompt_cat
        results.append(r)
        if output_path:
            _append_result(output_path, r)
        if r["avg_tps"] > 0:
            print(f"{r['avg_tps']} t/s  ({r['runs_success']}/{r['runs_total']} ok)")
        else:
            errors = [run.get("error", "?") for run in r["runs"] if "error" in run]
            print(f"FAIL ({', '.join(set(errors))})")
        if r.get("expected_model_match") is False:
            print(
                f"  ⚠ ROUTING: got {r['routed_model']}, expected {r['expected_model_detail']}",
                flush=True,
            )

    return results


# ── Output ────────────────────────────────────────────────────────────────────


def _print_availability_report(
    ollama_available: bool,
    pipeline_available: bool,
    results: list[dict],
) -> None:
    """Print configured vs available vs tested vs failed counts."""
    print("\n" + "=" * 70)
    print("AVAILABILITY REPORT")
    print("=" * 70)

    ollama = [r for r in results if r.get("backend") == "ollama"]
    if ollama:
        configured = len(ollama)
        available = sum(1 for r in ollama if r.get("available", True))
        tested = sum(1 for r in ollama if r["runs_success"] > 0)
        failed = available - tested
        missing = configured - available
        print(
            f"  Ollama:  {configured} configured | {available} installed | {tested} passed | {failed} failed | {missing} not installed"
        )

    pipeline = [r for r in results if r.get("path") == "pipeline"]
    if pipeline:
        configured = len(pipeline)
        tested = sum(1 for r in pipeline if r["runs_success"] > 0)
        failed = configured - tested
        print(
            f"  Pipeline (workspaces): {configured} configured | {tested} passed | {failed} failed"
        )

    personas = [r for r in results if r.get("path") == "persona"]
    if personas:
        configured = len(personas)
        tested = sum(1 for r in personas if r["runs_success"] > 0)
        failed = configured - tested
        print(
            f"  Pipeline (personas):   {configured} configured | {tested} passed | {failed} failed"
        )

    print("=" * 70)


def _print_direct_table(results: list[dict]) -> None:
    direct = [r for r in results if r["path"] == "direct"]
    if not direct:
        return

    print("\n" + "=" * 130)
    print(
        f"{'Model':<50} {'Backend':<10} {'Size':<8} {'Status':<10} {'Avg TPS':<10} {'Q-Score':<9} {'TPS×Q':<8} {'Tokens':<8}"
    )
    print("=" * 130)
    # Sort: successful first by tps_quality desc, then unavailable
    for r in sorted(
        direct,
        key=lambda x: (x["runs_success"] > 0, x.get("tps_quality", x["avg_tps"])),
        reverse=True,
    ):
        model_short = r["model"].split("/")[-1]
        size_gb = r.get("est_memory_gb", 0)
        size_str = f"{size_gb:.0f}GB" if size_gb else "-"
        if r["runs_success"] > 0:
            qs = r.get("quality_score", 1.0)
            tq = r.get("tps_quality", r["avg_tps"])
            print(
                f"{model_short:<50} {r['backend']:<10} {size_str:<8} {'OK':<10} {r['avg_tps']:<10.1f} "
                f"{qs:<9.2f} {tq:<8.1f} {r['avg_completion_tokens']:<8}"
            )
        elif not r.get("available", True):
            print(
                f"{model_short:<50} {r['backend']:<10} {size_str:<8} {'MISSING':<10} {'-':<10} {'-':<9} {'-':<8} {'-':<8}"
            )
        else:
            errors = {run.get("error", "?") for run in r.get("runs", []) if "error" in run}
            err_short = ", ".join(errors)[:20] if errors else "error"
            print(
                f"{model_short:<50} {r['backend']:<10} {size_str:<8} {err_short:<10} {'-':<10} {'-':<9} {'-':<8} {'-':<8}"
            )
    print("=" * 130)


def _print_pipeline_table(results: list[dict]) -> None:
    pipeline = [r for r in results if r["path"] == "pipeline"]
    if not pipeline:
        return

    print("\n" + "=" * 105)
    print(
        f"{'Workspace':<30} {'Avg TPS':<10} {'Q-Score':<9} {'TPS×Q':<8} {'Tokens':<8} {'Runs':<8}"
    )
    print("=" * 105)
    for r in sorted(pipeline, key=lambda x: x.get("tps_quality", x["avg_tps"]), reverse=True):
        ws = r.get("workspace", "?")
        if r["runs_success"] > 0:
            qs = r.get("quality_score", 1.0)
            tq = r.get("tps_quality", r["avg_tps"])
            print(
                f"{ws:<30} {r['avg_tps']:<10.1f} {qs:<9.2f} {tq:<8.1f} "
                f"{r['avg_completion_tokens']:<8} {r['runs_success']}/{r['runs_total']}"
            )
        else:
            print(
                f"{ws:<30} {'FAIL':<10} {'-':<9} {'-':<8} {'-':<8} {r['runs_success']}/{r['runs_total']}"
            )
    print("=" * 105)


def _print_persona_table(results: list[dict]) -> None:
    personas = [r for r in results if r["path"] == "persona"]
    if not personas:
        return

    print("\n" + "=" * 125)
    print(
        f"{'Persona':<30} {'Category':<12} {'Workspace Model':<40} {'Avg TPS':<10} {'Q-Score':<9} {'Runs':<8}"
    )
    print("=" * 125)
    for r in sorted(personas, key=lambda x: x.get("tps_quality", x["avg_tps"]), reverse=True):
        slug = r.get("persona_slug", "?")
        cat = r.get("persona_category", "?")
        wm = r.get("workspace_model", "?")
        wm_short = wm.split("/")[-1] if "/" in wm else wm
        if r["runs_success"] > 0:
            qs = r.get("quality_score", 1.0)
            print(
                f"{slug:<30} {cat:<12} {wm_short:<40} {r['avg_tps']:<10.1f} {qs:<9.2f} {r['runs_success']}/{r['runs_total']}"
            )
        else:
            print(
                f"{slug:<30} {cat:<12} {wm_short:<40} {'FAIL':<10} {'-':<9} {r['runs_success']}/{r['runs_total']}"
            )
    print("=" * 125)


# ── Notifications ─────────────────────────────────────────────────────────────


def _load_dotenv_for_notifications() -> None:
    """Pull notification env vars from .env without overwriting existing values."""
    env_file = Path(__file__).parent.parent.parent / ".env"
    if not env_file.exists():
        return
    needed = {
        "PUSHOVER_API_TOKEN",
        "PUSHOVER_USER_KEY",
        "TELEGRAM_ALERT_BOT_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALERT_CHANNEL_ID",
        "TELEGRAM_USER_IDS",
        "SLACK_ALERT_WEBHOOK_URL",
    }
    try:
        for raw in env_file.read_text().splitlines():
            line = raw.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k in needed and k not in os.environ:
                os.environ[k] = v.strip().strip('"').strip("'")
    except Exception:
        pass


def _send_bench_notification(message: str, title: str = "Portal 5 Bench") -> None:
    """Fire-and-forget: send message to every configured notification channel."""
    import urllib.parse
    import urllib.request

    _load_dotenv_for_notifications()

    # Pushover
    token = os.environ.get("PUSHOVER_API_TOKEN", "")
    user = os.environ.get("PUSHOVER_USER_KEY", "")
    if token and user:
        try:
            data = urllib.parse.urlencode(
                {
                    "token": token,
                    "user": user,
                    "title": title,
                    "message": message[:512],
                }
            ).encode()
            urllib.request.urlopen(
                urllib.request.Request("https://api.pushover.net/1/messages.json", data=data),
                timeout=8,
            )
        except Exception:
            pass

    # Telegram
    bot_token = os.environ.get("TELEGRAM_ALERT_BOT_TOKEN") or os.environ.get(
        "TELEGRAM_BOT_TOKEN", ""
    )
    raw_ids = os.environ.get("TELEGRAM_ALERT_CHANNEL_ID") or os.environ.get("TELEGRAM_USER_IDS", "")
    chat_id = raw_ids.split(",")[0].strip() if raw_ids else ""
    if bot_token and chat_id:
        try:
            data = urllib.parse.urlencode(
                {
                    "chat_id": chat_id,
                    "text": f"*{title}*\n{message}",
                    "parse_mode": "Markdown",
                }
            ).encode()
            urllib.request.urlopen(
                urllib.request.Request(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage", data=data
                ),
                timeout=8,
            )
        except Exception:
            pass

    # Slack
    slack_url = os.environ.get("SLACK_ALERT_WEBHOOK_URL", "")
    if slack_url:
        try:
            data = json.dumps({"text": f"*{title}*\n{message}"}).encode()
            urllib.request.urlopen(
                urllib.request.Request(
                    slack_url, data=data, headers={"Content-Type": "application/json"}
                ),
                timeout=8,
            )
        except Exception:
            pass


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Portal 5 TPS Benchmark")
    parser.add_argument(
        "--mode",
        choices=["direct", "pipeline", "personas", "all"],
        default="all",
        help="Test direct backends, pipeline workspaces, persona routing, or all (default: all)",
    )
    parser.add_argument("--runs", type=int, default=5, help="Runs per model/workspace (default: 5)")
    parser.add_argument("--model", help="Filter: substring match on model name (direct only)")
    parser.add_argument("--workspace", help="Filter: exact workspace ID (pipeline only)")
    parser.add_argument("--persona", help="Filter: substring match on persona slug/name")
    parser.add_argument("--prompt", help="Override all prompts with this single prompt string")
    parser.add_argument("--output", default=RESULTS_FILE, help="Output JSON path")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help=(
            "Resume from the most recent results file, skipping successful entries "
            "and re-testing only failed ones. Pair with --mode to target a specific tier "
            "(e.g. --mode pipeline --retry-failed retests only failed workspaces)."
        ),
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=10.0,
        help="Seconds to wait after memory reclaim before loading next model (default: 10)",
    )
    parser.add_argument(
        "--order",
        choices=["size", "config", "largest"],
        default="size",
        help="Model test order: 'size' = smallest first (default), 'largest' = biggest first, 'config' = backends.yaml order",
    )
    parser.add_argument(
        "--spec-decoding-tag",
        type=str,
        default="",
        help="Label this run as 'spec_decoding=on/off' for later comparison (M4 Track 1)",
    )
    parser.add_argument(
        "--kv-quant-tag",
        default="",
        help="Label appended to output JSON tagging the KV-quant configuration "
        "active during the run (e.g. 'off', 'lm-kv4.5', 'vlm-kv4.5'). "
        "Used for before/after comparison across TASK_KV_PROMOTE_V1 runs.",
    )
    args = parser.parse_args()

    # --retry-failed: find the most recent results file and use it as --output so
    # successful entries are skipped and failures are re-run automatically.
    if args.retry_failed and args.output == RESULTS_FILE:
        candidates = sorted(
            RESULTS_DIR.glob("bench_tps_*.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        if candidates:
            args.output = str(candidates[0])
            print(f"--retry-failed: resuming from {candidates[0].name}")
        else:
            print("--retry-failed: no previous results file found in results/, starting fresh")

    original_prompts = dict(PROMPTS) if args.prompt else None
    if args.prompt:
        for key in PROMPTS:
            PROMPTS[key] = args.prompt

    try:
        _run_main(args)
    finally:
        if original_prompts is not None:
            PROMPTS.clear()
            PROMPTS.update(original_prompts)
        global _bench_client
        if _bench_client is not None:
            _bench_client.close()
            _bench_client = None


def _check_image_freshness() -> None:
    """Warn if any portal Docker image predates the latest relevant git commit."""

    def _ts(git_paths=None, image=None):
        try:
            if git_paths:
                r = subprocess.run(
                    ["git", "-C", str(PROJECT_ROOT), "log", "-1", "--format=%ct", "--", *git_paths],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                ts = r.stdout.strip()
                from datetime import datetime, timezone

                return datetime.fromtimestamp(int(ts), tz=timezone.utc) if ts else None
            if image:
                r = subprocess.run(
                    ["docker", "inspect", "--format", "{{.Created}}", image],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                raw = r.stdout.strip()
                if raw and raw != "[]":
                    from datetime import datetime

                    return datetime.fromisoformat(raw.rstrip("Z") + "+00:00")
        except Exception:
            return None

    checks = [
        (
            "portal-pipeline",
            "portal-5-portal-pipeline",
            ["portal_pipeline/", "config/backends.yaml", "Dockerfile.pipeline", "pyproject.toml"],
        ),
        (
            "mcp-services",
            "portal-5-mcp-documents",
            ["portal_mcp/", "Dockerfile.mcp", "pyproject.toml"],
        ),
    ]
    stale = []
    for label, image, paths in checks:
        built = _ts(image=image)
        committed = _ts(git_paths=paths)
        if built and committed:
            lag = (committed - built).total_seconds()
            if lag > 30:
                stale.append(f"{label} ({int(lag // 60)}m behind HEAD)")
    if stale:
        print("  WARNING: stale Docker images — run './launch.sh rebuild' before trusting results:")
        for s in stale:
            print(f"    {s}")


def _run_main(args) -> None:
    print("=" * 70)
    print("Portal 5 — Comprehensive TPS Benchmark")
    print("=" * 70)
    _check_image_freshness()

    hw = _get_hardware_info()
    print(f"Hardware: {json.dumps(hw)}")
    if args.prompt:
        print(f"Prompt override: {args.prompt[:60]}...")
    else:
        print(f"Prompts: {len(PROMPTS)} categories ({', '.join(PROMPTS.keys())})")
    print(f"Max tokens: {MAX_TOKENS}  |  Runs per model: {args.runs}")
    print(f"Mode: {args.mode}  |  Order: {args.order}  |  Cooldown: {args.cooldown:.0f}s")

    # Config summary
    ollama_cfg = _config_ollama_models_unique()
    workspaces_cfg = _config_workspaces()
    personas_cfg = _discover_personas()

    print("\nConfigured (from backends.yaml + persona YAMLs):")
    print(f"  Ollama models: {len(ollama_cfg)}")
    print(f"  Workspaces:    {len(workspaces_cfg)}")
    print(f"  Personas:      {len(personas_cfg)}")
    total_configured = len(ollama_cfg)
    if args.mode in ("pipeline", "all"):
        total_configured += len(workspaces_cfg)
    if args.mode in ("personas", "all"):
        total_configured += len(personas_cfg)
    print(f"  Total to test: ~{total_configured} (mode={args.mode})")

    ollama_available = _check_backend(OLLAMA_URL, "/api/tags")
    pipeline_available = _check_backend(PIPELINE_URL, "/v1/models")

    print("\nBackends:")
    print(f"  Ollama     ({OLLAMA_URL}):    {'available' if ollama_available else 'not running'}")
    print(f"  Pipeline   ({PIPELINE_URL}):  {'available' if pipeline_available else 'not running'}")

    if not any([ollama_available, pipeline_available]):
        print("\nNo backends running. Start at least one and retry.")
        return

    do_direct = args.mode in ("direct", "all")
    do_pipeline = args.mode in ("pipeline", "all")
    do_personas = args.mode in ("personas", "all")

    _ws_filter = f" ws={args.workspace}" if getattr(args, "workspace", None) else ""
    _model_filter = f" model={args.model}" if getattr(args, "model", None) else ""
    _send_bench_notification(
        f"mode={args.mode}{_ws_filter}{_model_filter}  runs={args.runs}\n"
        f"HW: {hw.get('cpu', '?')}  {hw.get('unified_memory_gb', '?')}GB\n"
        f"Ollama={'✓' if ollama_available else '✗'}  Pipeline={'✓' if pipeline_available else '✗'}",
        title="Portal 5 Bench — Started",
    )

    t0 = time.time()

    # Initialize output file (or load existing for resume)
    output = _init_output(args.output, args, hw, ollama_cfg, workspaces_cfg, personas_cfg)
    all_results = list(output.get("results", []))
    if all_results:
        print(f"\n  Resuming: {len(all_results)} results already saved")

    if do_direct:
        print("\n── Ollama Direct Tests ──")
        all_results.extend(
            bench_direct(
                ollama_available,
                args.model,
                args.runs,
                args.dry_run,
                cooldown=args.cooldown,
                order=args.order,
                output_path=args.output,
            )
        )

    if do_pipeline:
        print("\n── Pipeline Workspace Tests ──")
        all_results.extend(
            bench_pipeline(
                pipeline_available, args.workspace, args.runs, args.dry_run, output_path=args.output
            )
        )

    if do_personas:
        print("\n── Persona Routing Tests ──")
        all_results.extend(
            bench_personas(
                pipeline_available, args.persona, args.runs, args.dry_run, output_path=args.output
            )
        )

    total_time = time.time() - t0

    if not args.dry_run:
        _print_availability_report(ollama_available, pipeline_available, all_results)
        _print_direct_table(all_results)
        _print_pipeline_table(all_results)
        _print_persona_table(all_results)

    # Finalize output with wall time and metadata
    output["timestamp"] = datetime.now(timezone.utc).isoformat()
    output["total_wall_time_s"] = round(total_time, 1)
    output["backends"] = {
        "ollama": {"url": OLLAMA_URL, "available": ollama_available},
        "pipeline": {"url": PIPELINE_URL, "available": pipeline_available},
    }
    output["prompts"] = {
        "override": args.prompt if args.prompt else None,
        "library": {k: v[:80] + "..." if len(v) > 80 else v for k, v in PROMPTS.items()},
        "workspace_map": WORKSPACE_PROMPT_MAP,
        "group_map": GROUP_PROMPT_MAP,
        "persona_category_map": PERSONA_CATEGORY_PROMPT_MAP,
    }
    # Merge: keep all results from the file (including resumed ones)
    try:
        with open(args.output) as f:
            file_data = json.load(f)
        output["results"] = file_data.get("results", all_results)
    except Exception:
        output["results"] = all_results

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    tested = sum(1 for r in output["results"] if r.get("runs_success", 0) > 0)
    available_ct = sum(1 for r in output["results"] if r.get("available", True))
    failed_ct = available_ct - tested
    hours = total_time / 3600
    print(
        f"\nTotal: {tested}/{available_ct} passed ({len(output['results'])} total) in {total_time:.0f}s"
    )
    _top = sorted(
        [r for r in output["results"] if r.get("avg_tps", 0) > 0],
        key=lambda r: r.get("avg_tps", 0),
        reverse=True,
    )[:5]
    _top_lines = "\n".join(
        f"  {r.get('model', r.get('workspace', '?'))[:30]:30s} {r['avg_tps']:.1f} t/s"
        for r in _top
    )
    _send_bench_notification(
        f"{tested}/{available_ct} passed  {failed_ct} failed  {total_time:.0f}s\n"
        + (_top_lines + "\n" if _top_lines else "")
        + f"→ {Path(args.output).name}",
        title="Portal 5 Bench — Done",
    )
    # Final cleanup: unload all Ollama models to prevent OOM after testing
    if not args.dry_run and ollama_available:
        _cleanup_all_backends()

    print(f"Results: {args.output}")


if __name__ == "__main__":
    main()
