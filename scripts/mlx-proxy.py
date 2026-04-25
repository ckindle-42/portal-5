#!/usr/bin/env python3
"""MLX Model-Aware Proxy — single port :8081, auto-switches mlx_lm ↔ mlx_vlm.

Usage: python3 mlx-proxy.py

Starts the correct MLX server based on the requested model:
  - mlx_lm.server  (port 18081) → text-only models (Qwen3-Coder-Next, DeepSeek-R1, etc.)
  - mlx_vlm.server (port 18082) → VLM models (Gemma 4, Qwen3-VL, LLaVA with vision tower)

Only one server runs at a time due to unified memory constraints on Apple Silicon.
Switching takes ~30s for the new server to load.

Concurrency protection: bounded thread pool prevents kernel panic under load.
  - MAX_WORKERS: max concurrent requests (default 4)
  - MAX_QUEUE: max queued requests before 503 (default 8)
  - REQUEST_TIMEOUT: max seconds per request (default 300s)

Monitoring: background watchdog detects crashes, /health reports true state.
  - WATCHDOG_INTERVAL: seconds between health polls (default 15)
  - States: ready | switching | degraded | down | none
"""

import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn

import httpx
import yaml

LM_PORT = 18081
VLM_PORT = 18082
PROXY_PORT = 8081

MAX_WORKERS = int(os.environ.get("MLX_PROXY_MAX_WORKERS", "4"))
MAX_QUEUE = int(os.environ.get("MLX_PROXY_MAX_QUEUE", "8"))
REQUEST_TIMEOUT = int(os.environ.get("MLX_PROXY_REQUEST_TIMEOUT", "300"))
WATCHDOG_INTERVAL = int(os.environ.get("MLX_WATCHDOG_INTERVAL", "15"))

# ── mlx_vlm performance tuning ──────────────────────────────────────────────
# KV cache quantization (TurboQuant) reduces memory pressure during long
# vision contexts. Fractional kv-bits (e.g. 4.5) auto-enables TurboQuant.
# prefill-step-size controls prompt-processing chunk size; lower values
# reduce peak memory but may slow prefill. Tune if you hit GPU OOM on
# multi-image or long-document vision workloads.
MLX_VLM_KV_BITS = os.environ.get("MLX_VLM_KV_BITS", "")
MLX_VLM_KV_QUANT_SCHEME = os.environ.get("MLX_VLM_KV_QUANT_SCHEME", "turboquant")
MLX_VLM_PREFILL_STEP_SIZE = os.environ.get("MLX_VLM_PREFILL_STEP_SIZE", "")

VLM_MODELS = {
    "Qwen3-VL-32B-Instruct-8bit",
    "gemma-4-31b-it-4bit",
    "gemma-4-e4b-it-4bit",  # Gemma 4 E4B — replaces LLaVA; text+vision+audio, 128K ctx, ~5GB
    "supergemma4-26b-abliterated-multimodal-mlx-4bit",  # Gemma 4 26B A4B MoE abliterated — vision, 256K ctx, uncensored ~15GB
    "GLM-OCR-bf16",  # OCR specialist — requires mlx_vlm (model_type=glm_ocr)
    "Llama-3.2-11B-Vision-Instruct-abliterated-4-bit",  # Uncensored VLM for Karakeep
    "Gemma-4-31B-JANG_4M-CRACK",  # Abliterated Gemma 4 31B, JANG v2 quant (~23GB) — uncensored VLM
}

ALL_MODELS = [
    # ── Text-only (mlx_lm) ────────────────────────────────────────────────
    # Coding
    "mlx-community/Qwen3-Coder-Next-4bit",  # 80B MoE 4bit (~46GB, BIG_MODEL)
    "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",  # 30B MoE 8bit (~22GB)
    "mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit",  # DS-Coder-V2 8bit (~12GB)
    "lmstudio-community/Devstral-Small-2507-MLX-4bit",  # Devstral v1.1 4bit (~15GB, 53.6% SWE-bench)
    "huihui-ai/Huihui-GLM-4.7-Flash-abliterated-mlx-4bit",  # GLM-4.7-Flash 30B-A3B MoE 4bit (~18GB), 59.2% SWE-bench, abliterated
    # Creative / general
    "mlx-community/Dolphin3.0-Llama3.1-8B-8bit",  # Dolphin 8B (~9GB, uncensored)
    "mlx-community/Llama-3.2-3B-Instruct-8bit",  # Ultra-fast routing (~3GB)
    # Model diversity — non-Qwen families
    "mlx-community/phi-4-8bit",  # Microsoft Phi-4 14B (~14GB, synthetic data, MIT)
    "lmstudio-community/Magistral-Small-2509-MLX-8bit",  # Mistral reasoning (~24GB, [THINK] mode)
    # Heavy (PULL_HEAVY only)
    "mlx-community/Llama-3.3-70B-Instruct-4bit",  # Llama 70B 4bit (~40GB, BIG_MODEL)
    # GLM-5.1 removed: exceeds 64GB safe headroom (both variants) — tested and confirmed OOM
    # Jackrong Qwopus3.5-v3 (primary reasoning) + Claude-4.6-Opus distills
    "Jackrong/MLX-Qwopus3.5-27B-v3-8bit",  # Reasoning primary 27B v3 8bit (~22GB, auto-reasoning)
    "Jackrong/MLX-Qwopus3.5-9B-v3-8bit",  # Available 9B v3 8bit (~9GB)
    "Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit",  # Reasoning alt 27B v2 4bit (~14GB, Claude-4.6-Opus)
    "Jackrong/MLX-Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-8bit",  # Available 9B Claude-4.6 8bit (~9GB)
    "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit",  # 35B-A3B 8bit (~28GB, compliance)
    # Reasoning/analysis
    "mlx-community/DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit",  # FIX: was missing from ALL_MODELS — R1 Distill 32B 8bit (~34GB, auto-data)
    "mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit",  # R1 Distill 32B 4bit uncensored (~18GB, auto-research)
    # Math/STEM specialist
    "mlx-community/Qwen2.5-Math-7B-Instruct-4bit",  # Qwen2.5-Math 7B 4bit (~5GB, auto-math)
    # ── Draft models for speculative decoding (M4 Track 1) ──────────────────
    "mlx-community/Qwen2.5-0.5B-Instruct-4bit",  # ~0.5GB, Qwen tokenizer (draft for Qwen family)
    "mlx-community/Llama-3.2-1B-Instruct-4bit",  # ~1GB, Llama-3 tokenizer (draft for Llama family)
    # ── VLM (mlx_vlm — auto-switched) ────────────────────────────────────────
    "mlx-community/gemma-4-31b-it-4bit",  # Gemma 4 dense 31B 4bit (~18GB, primary VLM)
    "mlx-community/Qwen3-VL-32B-Instruct-8bit",  # Qwen3-VL 32B 8bit (~36GB, VLM fallback)
    "mlx-community/gemma-4-e4b-it-4bit",  # Gemma 4 E4B — replaces LLaVA; vision+audio, 128K ctx (~5GB)
    "Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit",  # Gemma 4 26B A4B MoE abliterated — vision, 256K ctx, uncensored (~15GB)
    "lmstudio-community/Phi-4-reasoning-plus-MLX-4bit",  # Phi-4-reasoning-plus — STEM/math, RL-trained, ~7GB (Microsoft)
    "mlx-community/Llama-3.2-11B-Vision-Instruct-abliterated-4-bit",  # Uncensored VLM 11B 4bit (~7GB, Karakeep)
    "dealignai/Gemma-4-31B-JANG_4M-CRACK",  # Abliterated Gemma 4 31B JANG v2 5.1-bit (~23GB) — uncensored vision
]

# ── Big-Model Mode (P5-BIG-001) ───────────────────────────────────────────────
# Models that require a full-evict load sequence:
#   1. Stop current MLX server + wait for Metal reclaim
#   2. Kill all Ollama loaded models (ollama stop --all)
#   3. Load the big model with a reduced context cap
#   4. On next non-big-model request, restore normal warm model
#
# Trigger: any model whose HF path is in this set is treated as big-model.
# The `auto-agentic` workspace is the intended entry point.
BIG_MODEL_SET: set[str] = {
    "mlx-community/Qwen3-Coder-Next-4bit",  # ~46GB — auto-agentic
    "mlx-community/Qwen3-VL-32B-Instruct-8bit",  # ~36GB — heavy VLM
    "mlx-community/Llama-3.3-70B-Instruct-4bit",  # ~40GB — heavy coding + reasoning
    # GLM-5.1 removed: too large for 64GB stack (MXFP4-Q8 = 49GB, both variants exceed safe headroom)
}

# Context ceiling for big-model requests — suppresses KV cache spike.
# 256K default context + KV cache can push memory over the edge.
# At 32K the KV cache is ~2 GB instead of ~16 GB.
# Override via env: MLX_BIG_MODEL_CTX (e.g. "65536" if you want 64K).
BIG_MODEL_CTX: int = int(os.environ.get("MLX_BIG_MODEL_CTX", "32768"))

# Minimum strictly-free GB required after full-evict before allowing a big-model load.
# Protects against proceeding into a guaranteed OOM.
BIG_MODEL_MIN_FREE_GB: float = float(os.environ.get("MLX_BIG_MODEL_MIN_FREE_GB", "6.0"))

# ── Model-Size-Aware Admission Control (P5-FUT-009) ──────────────────────────
# Maps each MLX model HuggingFace path → estimated peak memory in GB.
# Sourced from CLAUDE.md model catalog and mlx-community model cards.
# Values are conservative estimates including KV cache at default context.
#
# Rule: MODEL_MEMORY[model] + MEMORY_HEADROOM_GB <= _get_available_memory_gb()
# If the check fails, ensure_server() returns HTTP 503 instead of loading
# a model that would OOM — making CLAUDE.md coexistence rules self-enforcing.
MODEL_MEMORY: dict[str, float] = {
    # ── Text-only (mlx_lm) ────────────────────────────────────────────────
    "mlx-community/Qwen3-Coder-Next-4bit": 46.0,  # 80B MoE, 4bit (~46GB)
    "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit": 22.0,  # 30B MoE, 3B active (~22GB)
    "mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit": 12.0,  # Lite 8bit (~12GB)
    "lmstudio-community/Devstral-Small-2507-MLX-4bit": 15.0,  # Devstral Small 2507 MLX 4bit (~15GB, 53.6% SWE-bench)
    "mlx-community/Dolphin3.0-Llama3.1-8B-8bit": 9.0,  # Dolphin 8B 8bit (~9GB)
    "mlx-community/Llama-3.2-3B-Instruct-8bit": 3.0,  # Ultra-fast routing (~3GB)
    "lmstudio-community/Magistral-Small-2509-MLX-8bit": 24.0,  # Magistral 24B 8bit (~24GB)
    "mlx-community/Llama-3.3-70B-Instruct-4bit": 40.0,  # Llama 70B 4bit (~40GB)
    "Jackrong/MLX-Qwopus3.5-27B-v3-8bit": 22.0,  # Qwopus 27B v3 8bit (~22GB, primary auto-reasoning)
    "Jackrong/MLX-Qwopus3.5-9B-v3-8bit": 9.0,  # Qwopus 9B v3 8bit (~9GB)
    "Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit": 14.0,  # 27B v2 4bit (~14GB, Claude-4.6-Opus)
    "Jackrong/MLX-Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-8bit": 9.0,  # 9B Claude-4.6 8bit (~9GB)
    "mlx-community/phi-4-8bit": 14.0,  # Microsoft Phi-4 14B 8bit (~14GB)
    "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit": 28.0,  # 35B MoE 8bit (~28GB)
    "mlx-community/DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit": 34.0,  # R1 Distill 32B 8bit (~34GB)
    "mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit": 18.0,  # R1 Distill 32B 4bit (~18GB)
    "lmstudio-community/Phi-4-reasoning-plus-MLX-4bit": 8.0,  # Phi-4-reasoning-plus 14B 4bit (~7-8GB)
    "huihui-ai/Huihui-GLM-4.7-Flash-abliterated-mlx-4bit": 18.0,  # GLM-4.7-Flash 30B-A3B MoE 4bit (~18GB)
    "mlx-community/Qwen2.5-Math-7B-Instruct-4bit": 5.0,  # Qwen2.5-Math 7B 4bit (~5GB)
    # ── Draft models for speculative decoding (M4 Track 1) ──────────────────
    "mlx-community/Qwen2.5-0.5B-Instruct-4bit": 0.5,  # Qwen draft, additive with target
    "mlx-community/Llama-3.2-1B-Instruct-4bit": 1.0,  # Llama draft, additive with target
    # ── VLM (mlx_vlm) ─────────────────────────────────────────────────────
    "mlx-community/gemma-4-31b-it-4bit": 18.0,  # Gemma 4 dense 31B 4bit (~18GB)
    "mlx-community/Qwen3-VL-32B-Instruct-8bit": 36.0,  # Qwen3-VL 32B 8bit (~36GB)
    "mlx-community/gemma-4-e4b-it-4bit": 5.0,  # Gemma 4 E4B mlx-community 4bit (~5GB) — vision+audio
    "Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit": 15.0,  # Gemma 4 26B A4B MoE abliterated 4bit (~15GB)
    "mlx-community/Llama-3.2-11B-Vision-Instruct-abliterated-4-bit": 7.0,  # Uncensored VLM 11B 4bit (~7GB)
    "dealignai/Gemma-4-31B-JANG_4M-CRACK": 23.0,  # Abliterated Gemma 4 31B JANG v2 5.1-bit (~22.7GB)
}

# Safety headroom reserved for OS, Ollama sidecar, and KV cache spikes.
# Operator may override via env var.
MEMORY_HEADROOM_GB: float = float(os.environ.get("MLX_MEMORY_HEADROOM_GB", "10.0"))

# Unknown models get this conservative default rather than being blocked
MEMORY_UNKNOWN_DEFAULT_GB: float = float(os.environ.get("MLX_MEMORY_UNKNOWN_DEFAULT_GB", "20.0"))

# ── Speculative Decoding (M4 Track 1) ────────────────────────────────────────
# Draft models are loaded alongside target models for 2-3× token acceptance.
# The mapping is defined in config/backends.yaml under speculative_decoding.draft_models.


def _backends_yaml_path() -> str:
    """Locate config/backends.yaml — try Docker mount then repo-relative."""
    candidates = [
        "/app/config/backends.yaml",
        os.path.join(os.path.dirname(__file__), "..", "config", "backends.yaml"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return candidates[-1]  # fallback (will fail later with clear error)


def _load_draft_model_map() -> dict[str, str]:
    """Read config/backends.yaml for speculative_decoding.draft_models map."""
    try:
        with open(_backends_yaml_path()) as f:
            cfg = yaml.safe_load(f.read())
        return cfg.get("speculative_decoding", {}).get("draft_models", {})
    except Exception:
        return {}


def _model_exists_locally(model_id: str) -> bool:
    """Check if model directory exists in the Portal 5 models mount or HF cache."""
    portal5_models = Path(os.environ.get("PORTAL5_MODELS_DIR", "/Volumes/data01/models"))
    p = portal5_models / model_id
    if p.is_dir():
        return True
    hf_home = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
    cache_dir = Path(hf_home) / "hub"
    safe_name = model_id.replace("/", "--")
    return any(cache_dir.glob(f"models--{safe_name}*"))


DRAFT_MODEL_MAP: dict[str, str] = _load_draft_model_map()
if DRAFT_MODEL_MAP:
    print(f"[proxy] speculative decoding map loaded: {len(DRAFT_MODEL_MAP)} pairs", flush=True)

lock = threading.Lock()
_request_semaphore = threading.Semaphore(MAX_WORKERS + MAX_QUEUE)


class MLXState:
    """Thread-safe state machine tracking MLX server health and lifecycle."""

    def __init__(self):
        self._lock = threading.Lock()
        self._active_server: str | None = None  # "lm" | "vlm" | None
        self._loaded_model: str | None = None
        self._state: str = "none"  # none | ready | switching | degraded | down
        self._state_since: float = time.time()
        self._last_health_check: float = 0.0
        self._consecutive_failures: int = 0
        self._switch_count: int = 0
        self._last_error: str | None = None

    @property
    def active_server(self) -> str | None:
        with self._lock:
            return self._active_server

    @property
    def loaded_model(self) -> str | None:
        with self._lock:
            return self._loaded_model

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def state_since(self) -> float:
        with self._lock:
            return self._state_since

    @property
    def consecutive_failures(self) -> int:
        with self._lock:
            return self._consecutive_failures

    @property
    def switch_count(self) -> int:
        with self._lock:
            return self._switch_count

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    def set_ready(self, server: str, model: str | None = None):
        with self._lock:
            old = self._active_server
            self._active_server = server
            # Preserve existing loaded_model if probe didn't return one (mlx_lm.server
            # health endpoint doesn't expose which model is loaded, so _probe_server
            # returns None for lm-type servers — don't clobber the known model).
            if model is not None:
                self._loaded_model = model
            self._state = "ready"
            self._consecutive_failures = 0
            self._last_error = None
            if old != server:
                self._switch_count += 1
            self._state_since = time.time()
            self._last_health_check = time.time()

    def set_switching(self, target: str):
        with self._lock:
            self._state = "switching"
            self._state_since = time.time()
            self._last_error = None
            print(f"[proxy] switching to mlx_{target}...", flush=True)

    def set_degraded(self, error: str):
        with self._lock:
            self._state = "degraded"
            self._consecutive_failures += 1
            self._last_error = error
            self._state_since = time.time()

    def set_down(self, error: str):
        with self._lock:
            self._state = "down"
            self._consecutive_failures += 1
            self._last_error = error
            self._state_since = time.time()

    def record_health_check(self, healthy: bool):
        with self._lock:
            self._last_health_check = time.time()
            if healthy:
                self._consecutive_failures = 0
                if self._state in ("degraded", "down"):
                    self._state = "ready"
                    self._state_since = time.time()
                    self._last_error = None
            else:
                self._consecutive_failures += 1

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "active_server": self._active_server,
                "loaded_model": self._loaded_model,
                "state": self._state,
                "state_since": self._state_since,
                "state_duration_sec": round(time.time() - self._state_since, 1),
                "last_health_check": self._last_health_check,
                "seconds_since_health": round(time.time() - self._last_health_check, 1),
                "consecutive_failures": self._consecutive_failures,
                "switch_count": self._switch_count,
                "last_error": self._last_error,
            }


mlx_state = MLXState()


class MemoryMonitor:
    """Track system memory usage over time. Samples every POLL_INTERVAL seconds.

    Exposes current stats and history for /health endpoint and logging.
    Detects memory pressure changes and logs warnings.
    """

    POLL_INTERVAL = 30  # seconds between samples
    MAX_HISTORY = 2880  # 24 hours at 30s intervals

    def __init__(self):
        self._lock = threading.Lock()
        self._current: dict = {}
        self._history: list[dict] = []
        self._last_pressure: str = ""
        self._peak_used_pct: float = 0.0

    def sample(self) -> dict:
        """Take a memory snapshot. Returns the sample dict."""
        sample = _get_memory_stats()
        sample["timestamp"] = time.time()
        with self._lock:
            self._current = sample
            self._history.append(sample)
            if len(self._history) > self.MAX_HISTORY:
                self._history = self._history[-self.MAX_HISTORY :]
            used = sample.get("used_pct", 0)
            if used > self._peak_used_pct:
                self._peak_used_pct = used
        # Log pressure changes
        pressure = sample.get("pressure", "unknown")
        if pressure != self._last_pressure:
            if self._last_pressure:  # skip first sample
                print(
                    f"[memory] pressure changed: {self._last_pressure} -> {pressure} "
                    f"({sample.get('free_gb', 0):.1f}GB free, {sample.get('used_pct', 0)}% used)",
                    flush=True,
                )
            self._last_pressure = pressure
        # Warn on high memory
        if used > 90:
            print(
                f"[memory] CRITICAL: {used}% used, only {sample.get('free_gb', 0):.1f}GB free",
                flush=True,
            )
        return sample

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "current": self._current,
                "peak_used_pct": round(self._peak_used_pct, 1),
                "samples": len(self._history),
                "history_minutes": round(len(self._history) * self.POLL_INTERVAL / 60, 1),
            }

    def get_recent(self, n: int = 20) -> list[dict]:
        with self._lock:
            return self._history[-n:]


def _get_memory_stats() -> dict:
    """Get current memory statistics from vm_stat and memory_pressure."""
    stats: dict = {}
    page_size = 16384  # Apple Silicon
    try:
        result = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines():
            for key, label in [
                ("free", "Pages free:"),
                ("active", "Pages active:"),
                ("inactive", "Pages inactive:"),
                ("speculative", "Pages speculative:"),
                ("wired", "Pages wired down:"),
                ("purgeable", "Pages purgeable:"),
            ]:
                if label in line:
                    try:
                        stats[key] = int(line.split(":")[-1].strip().rstrip(".")) * page_size
                    except ValueError:
                        pass
    except Exception:
        pass

    free = stats.get("free", 0)
    active = stats.get("active", 0)
    inactive = stats.get("inactive", 0)
    speculative = stats.get("speculative", 0)
    wired = stats.get("wired", 0)
    total = free + active + inactive + speculative + wired
    used = active + wired + speculative

    free_gb = free / (1024**3)
    total_gb = total / (1024**3) if total > 0 else 64
    used_pct = round((used / total) * 100) if total > 0 else 0

    # Get pressure level
    pressure = "unknown"
    try:
        result = subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "free percentage" in line.lower():
                    pct_str = line.split(":")[-1].strip().replace("%", "")
                    try:
                        free_pct = int(pct_str)
                        if free_pct < 10:
                            pressure = "critical"
                        elif free_pct < 20:
                            pressure = "high"
                        elif free_pct < 30:
                            pressure = "moderate"
                        else:
                            pressure = "normal"
                    except ValueError:
                        pass
    except Exception:
        pass

    return {
        "free_gb": round(free_gb, 1),
        "total_gb": round(total_gb, 1),
        "used_pct": used_pct,
        "pressure": pressure,
        "wired_gb": round(wired / (1024**3), 1),
        "active_gb": round(active / (1024**3), 1),
        "inactive_gb": round(inactive / (1024**3), 1),
        "purgeable_gb": round(stats.get("purgeable", 0) / (1024**3), 2),
    }


memory_monitor = MemoryMonitor()


def needs_vlm(model: str) -> bool:
    return model.split("/")[-1] in VLM_MODELS


def _probe_server(stype: str) -> tuple[bool, str | None]:
    """Probe a specific MLX server. Returns (healthy, loaded_model)."""
    port = LM_PORT if stype == "lm" else VLM_PORT
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=3)
        if r.status_code == 200:
            d = r.json()
            model = d.get("loaded_model")
            if stype == "vlm" and model:
                return True, model
            if stype == "lm" and "loaded_model" not in d:
                return True, None
    except Exception:
        pass
    return False, None


def detect_server() -> str | None:
    """Return 'lm', 'vlm', or None based on which server is responding."""
    for stype in ["lm", "vlm"]:
        healthy, _ = _probe_server(stype)
        if healthy:
            return stype
    return None


def _graceful_kill(pid: int, timeout: float = 10.0) -> None:
    """Send SIGTERM first, wait for graceful exit, then SIGKILL if needed."""
    try:
        os.kill(pid, 15)  # SIGTERM — lets Metal release GPU memory
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                os.kill(pid, 0)  # check if still alive
                time.sleep(0.5)
            except ProcessLookupError:
                return  # process exited cleanly
        # Still alive after SIGTERM timeout — force kill
        subprocess.run(["kill", "-9", str(pid)], capture_output=True)
    except (ProcessLookupError, PermissionError):
        pass


# Track whether a zombie cleanup is already in progress so the watchdog
# doesn't start a second one before the first finishes.
_zombie_cleanup_active = threading.Event()


def _cleanup_zombie_servers() -> None:
    """Proactively kill any MLX server process that is alive in the OS but
    not responding to its /health endpoint.

    This runs as a daemon thread from _watchdog_loop the moment a crash is
    detected, rather than waiting for the next inference request to trigger
    stop_all(). That means GPU memory is reclaimed within ~10s of a crash,
    not indefinitely.

    Called from _watchdog_loop only — do not call from request handlers.
    """
    if _zombie_cleanup_active.is_set():
        return  # another cleanup already running

    _zombie_cleanup_active.set()
    try:
        killed_any = False
        for proc_pattern, port, label in [
            ("mlx_lm.server", LM_PORT, "mlx_lm"),
            ("mlx_vlm.server", VLM_PORT, "mlx_vlm"),
        ]:
            try:
                res = subprocess.run(["pgrep", "-f", proc_pattern], capture_output=True, text=True)
                pids = [int(p) for p in res.stdout.strip().split() if p.isdigit()]
                if not pids:
                    continue

                # Process exists — still answering?
                alive = False
                try:
                    r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=3)
                    alive = r.status_code == 200
                except Exception:
                    pass

                if alive:
                    continue

                # Zombie confirmed — SIGTERM then wait
                print(
                    f"[watchdog] zombie cleanup: {label} process {pids} alive but /health dead — sending SIGTERM",
                    flush=True,
                )
                for pid in pids:
                    _graceful_kill(pid)
                killed_any = True

            except Exception as e:
                print(f"[watchdog] zombie cleanup error for {label}: {e}", flush=True)

        if killed_any:
            print(
                "[watchdog] waiting for Metal GPU memory reclaim after zombie cleanup…", flush=True
            )
            _wait_for_gpu_memory_reclaim()
            # Reset the down state so the proxy attempts a clean restart on next request
            if mlx_state.state == "down":
                mlx_state._state = "none"
                mlx_state._active_server = None
                mlx_state._loaded_model = None
                print(
                    "[watchdog] state reset to 'none' — proxy will restart server on next request",
                    flush=True,
                )

    finally:
        _zombie_cleanup_active.clear()


def _get_available_memory_gb() -> float:
    """Get available memory in GB via vm_stat (macOS).

    On macOS/Apple Silicon, "available" = free + inactive + purgeable.
    Inactive pages are reclaimable but not yet freed — only counting
    "Pages free" underestimates available memory and can cause premature
    rejection of model loads. However, after a process exits, inactive
    pages must be reclaimed by Metal before a new model can use them.
    """
    try:
        result = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5)
        page_size = 16384
        pages = {}
        for line in result.stdout.splitlines():
            for key, label in [
                ("free", "Pages free:"),
                ("inactive", "Pages inactive:"),
                ("purgeable", "Pages purgeable:"),
            ]:
                if label in line:
                    try:
                        pages[key] = int(line.split(":")[-1].strip().rstrip("."))
                    except ValueError:
                        pass
                    break
        available = pages.get("free", 0) + pages.get("inactive", 0) + pages.get("purgeable", 0)
        return (available * page_size) / (1024**3)
    except Exception:
        return 0.0


def _get_free_memory_gb() -> float:
    """Get current free memory in GB via vm_stat (macOS).

    Returns ONLY strictly free pages — used for GPU memory reclamation
    detection (inactive pages may still hold Metal GPU allocations).
    """
    try:
        result = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5)
        page_size = 16384
        free_pages = 0
        for line in result.stdout.splitlines():
            if "Pages free:" in line:
                free_pages = int(line.split(":")[-1].strip().rstrip("."))
                break
        return (free_pages * page_size) / (1024**3)
    except Exception:
        return 0.0


def _evict_ollama_models() -> None:
    """Send keep_alive=0 to all CURRENTLY LOADED Ollama models to free unified memory.

    Ollama holds loaded models in unified memory indefinitely when keep_alive=-1.
    For big-model mode we must evict them before loading a 46 GB MLX model.

    Strategy: GET /api/ps to find ONLY currently-loaded (running) models, then POST a
    generate request with keep_alive=0 and an empty prompt for each one.
    This is the documented Ollama mechanism for explicit unloading.

    NOTE: /api/ps returns only actively running models; /api/tags returns ALL installed
    models (which could be 25+). Using /api/tags would send keep_alive=0 to unloaded
    models, causing Ollama to briefly load each one before unloading — adding minutes
    of unnecessary latency to the big-model pre-load sequence.

    Errors are suppressed — if Ollama is unreachable the load may still succeed
    if memory happens to be sufficient.
    """
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    try:
        with httpx.Client(timeout=10) as c:
            resp = c.get(f"{ollama_url}/api/ps")
            if resp.status_code != 200:
                print(
                    "[big-model] could not list running Ollama models — skipping evict", flush=True
                )
                return
            models = [m["name"] for m in resp.json().get("models", [])]
    except Exception as e:
        print(f"[big-model] Ollama unreachable during evict ({e}) — skipping", flush=True)
        return

    if not models:
        print("[big-model] no Ollama models loaded — nothing to evict", flush=True)
        return

    print(f"[big-model] evicting {len(models)} running Ollama model(s): {models}", flush=True)
    with httpx.Client(timeout=30) as c:
        for model_name in models:
            try:
                c.post(
                    f"{ollama_url}/api/generate",
                    json={"model": model_name, "keep_alive": 0, "prompt": ""},
                    timeout=15,
                )
                print(f"[big-model] evicted Ollama model: {model_name}", flush=True)
            except Exception as e:
                print(f"[big-model] failed to evict {model_name!r}: {e}", flush=True)

    # Brief settle time for Ollama to release unified memory pages
    time.sleep(3)
    free_after = _get_free_memory_gb()
    print(f"[big-model] post-Ollama-evict free memory: {free_after:.1f} GB", flush=True)


def _wait_for_gpu_memory_reclaim(min_wait: float = 10.0, max_wait: float = 60.0) -> None:
    """Wait for Metal GPU memory to be reclaimed after server shutdown.

    On Apple Silicon, Metal GPU memory is reclaimed asynchronously after a
    process exits. Starting a new model before the old memory is released
    causes command buffer errors (crash). We actively poll free memory
    and wait until it stabilizes, indicating reclamation is complete.

    Uses STRICT free pages (not available) because inactive pages may still
    hold Metal GPU allocations that haven't been released yet.
    """
    time.sleep(min_wait)  # Minimum wait for process teardown + Metal reclaim
    free_before = _get_free_memory_gb()
    stable_count = 0
    deadline = time.time() + max_wait
    while time.time() < deadline:
        time.sleep(3)
        free_now = _get_free_memory_gb()
        if free_now >= free_before - 0.5:  # memory stable or increasing
            stable_count += 1
            if stable_count >= 2:
                print(
                    f"[proxy] GPU memory reclaimed: {free_now:.1f}GB free (stable)",
                    flush=True,
                )
                return
        else:
            stable_count = 0
            free_before = free_now
    print(
        f"[proxy] WARNING: memory reclaim wait timed out ({max_wait}s) — "
        f"free={_get_free_memory_gb():.1f}GB, proceeding anyway",
        flush=True,
    )


_server_log_dir = "/tmp/mlx-proxy-logs"


def _wait_for_model_loaded(stype: str, model: str = "", timeout: float = 600.0) -> bool:
    """Wait for the MLX server to actually be serving inference requests.

    Monitors the server's stderr log for "Starting httpd" which appears
    AFTER the model finishes loading into GPU memory. This is deterministic —
    no guessing with timers or HTTP probes.
    """
    log_file = os.path.join(_server_log_dir, f"mlx_{stype}.log")
    deadline = time.time() + timeout
    last_size = 0
    last_log = 0

    while time.time() < deadline:
        try:
            if os.path.exists(log_file):
                with open(log_file) as f:
                    content = f.read()
                # Readiness signals differ by server type:
                # - mlx_lm.server prints "Starting httpd" (OpenAI-compatible HTTP server)
                # - mlx_vlm.server (uvicorn/FastAPI) prints "Uvicorn running on" and
                #   "Application startup complete"
                _ready_signals = [
                    "Starting httpd",
                    "Uvicorn running on",
                    "Application startup complete",
                ]
                if any(sig in content for sig in _ready_signals):
                    elapsed = time.time() - (deadline - timeout)
                    matched = next(sig for sig in _ready_signals if sig in content)
                    print(
                        f"[proxy] model loaded (log confirmed: '{matched}', {elapsed:.0f}s)",
                        flush=True,
                    )
                    return True
                # Check for errors
                if "Error" in content or "Traceback" in content:
                    # Don't fail immediately — might be a warning, not fatal
                    if "Traceback" in content and time.time() - last_log > 15:
                        print("[proxy] server log has errors, continuing to wait...", flush=True)
                        last_log = time.time()
                # Log progress
                size = len(content)
                if size != last_size and time.time() - last_log > 15:
                    elapsed = time.time() - (deadline - timeout)
                    remaining = deadline - time.time()
                    print(
                        f"[proxy] model loading... ({elapsed:.0f}s elapsed, "
                        f"{remaining:.0f}s remaining, log active)",
                        flush=True,
                    )
                    last_size = size
                    last_log = time.time()
        except Exception:
            pass
        time.sleep(2)

    # Timeout — check one more time
    try:
        with open(log_file) as f:
            content = f.read()
            if any(
                sig in content
                for sig in ["Starting httpd", "Uvicorn running on", "Application startup complete"]
            ):
                return True
    except Exception:
        pass
    return False


def stop_all():
    """Gracefully stop any running MLX server on LM_PORT or VLM_PORT.

    Uses SIGTERM (not SIGKILL) to let Metal release GPU memory properly.
    Waits for process exit, then waits for GPU memory reclamation.
    """
    pids_to_kill = []
    for port in [LM_PORT, VLM_PORT]:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=3)
            if r.status_code == 200:
                res = subprocess.run(
                    ["lsof", "-ti", f":{port}", "-sTCP:LISTEN"],
                    capture_output=True,
                    text=True,
                )
                for pid in res.stdout.strip().split("\n"):
                    if pid:
                        pids_to_kill.append(int(pid))
        except Exception:
            pass

    # Also kill by process name (handles case where port is not responding)
    for pattern in ["mlx_lm.server", "mlx_vlm.server"]:
        try:
            res = subprocess.run(
                ["pgrep", "-f", pattern],
                capture_output=True,
                text=True,
            )
            for pid in res.stdout.strip().split("\n"):
                if pid and int(pid) not in pids_to_kill:
                    pids_to_kill.append(int(pid))
        except Exception:
            pass

    # Graceful kill all — SIGTERM first, then wait
    for pid in pids_to_kill:
        _graceful_kill(pid)

    # Wait for Metal GPU memory reclamation
    _wait_for_gpu_memory_reclaim()


def start_server(stype: str, model: str = "") -> int:
    """Start mlx_lm.server or mlx_vlm.server and wait for it to be serving.

    Captures server stderr to a log file and monitors for "Starting httpd"
    which means the model has finished loading. This is deterministic —
    the mlx_lm server loads the model synchronously before starting HTTP.
    """
    port = LM_PORT if stype == "lm" else VLM_PORT
    cmd = ["python3", "-m", f"mlx_{stype}.server", "--port", str(port), "--host", "127.0.0.1"]
    if model:
        cmd.extend(["--model", model])

    # ── mlx_vlm performance flags ───────────────────────────────────────────
    if stype == "vlm":
        if MLX_VLM_KV_BITS:
            cmd.extend(["--kv-bits", MLX_VLM_KV_BITS])
            cmd.extend(["--kv-quant-scheme", MLX_VLM_KV_QUANT_SCHEME])
        if MLX_VLM_PREFILL_STEP_SIZE:
            cmd.extend(["--prefill-step-size", MLX_VLM_PREFILL_STEP_SIZE])

    # KV cache quantization (int8) saves 2-4GB on 32B models but requires mlx_lm ≥ 0.22.
    # Check support at runtime to avoid crashing on older installs.
    if stype == "lm":
        import subprocess as _sp

        help_out = (
            _sp.run(
                ["python3", "-m", "mlx_lm.server", "--help"],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
            + _sp.run(
                ["python3", "-m", "mlx_lm.server", "--help"],
                capture_output=True,
                text=True,
                timeout=10,
            ).stderr
        )
        if "--kv-cache-quantization" in help_out:
            cmd.extend(["--kv-cache-quantization", "int8"])

    # ── Speculative decoding via --draft-model (M4 Track 1) ─────────────────
    if stype == "lm" and model and DRAFT_MODEL_MAP:
        draft_model = DRAFT_MODEL_MAP.get(model, "")
        if draft_model and _model_exists_locally(draft_model):
            cmd.extend(["--draft-model", draft_model])
            num_draft = os.environ.get("MLX_NUM_DRAFT_TOKENS", "4")
            cmd.extend(["--num-draft-tokens", num_draft])
            print(
                f"[proxy] speculative decoding enabled: target={model} "
                f"draft={draft_model} num_draft={num_draft}",
                flush=True,
            )
        elif draft_model:
            print(
                f"[proxy] draft model {draft_model!r} not found locally; "
                f"skipping spec-decoding for {model}",
                flush=True,
            )

    # Ensure log directory exists
    os.makedirs(_server_log_dir, exist_ok=True)
    log_file = os.path.join(_server_log_dir, f"mlx_{stype}.log")
    # Truncate old log
    with open(log_file, "w") as f:
        f.write("")

    log_fh = open(log_file, "a")
    proc = subprocess.Popen(cmd, stdout=log_fh, stderr=log_fh)
    print(
        f"[proxy] started mlx_{stype} (PID {proc.pid}) model={model or '(default)'} log={log_file}",
        flush=True,
    )

    # Wait for model to load — monitor log for "Starting httpd"
    print("[proxy] waiting for model to load (monitoring server log)...", flush=True)
    if _wait_for_model_loaded(stype, model):
        mlx_state.set_ready(stype, model or None)
        print(f"[proxy] mlx_{stype} ready on :{port} model={model or '(default)'}", flush=True)
        return port
    else:
        # Model didn't load in time — kill the server
        print(f"[proxy] model load timeout — killing server PID {proc.pid}", flush=True)
        try:
            _graceful_kill(proc.pid)
        except Exception:
            pass
        raise TimeoutError(f"mlx_{stype} model failed to load within timeout")


def _check_memory_for_model(model: str, freed_by_stop_gb: float = 0.0) -> tuple[bool, str]:
    """Pre-flight memory admission check for a model load request.

    Returns (ok: bool, message: str).
    - ok=True: sufficient memory available, proceed with load.
    - ok=False: insufficient memory; message is operator-actionable 503 detail.

    Uses MODEL_MEMORY dict for known models; falls back to MEMORY_UNKNOWN_DEFAULT_GB
    for unknown models (conservative, not blocking unless truly constrained).

    Args:
        freed_by_stop_gb: Memory (GB) that will be freed by unloading the current model
            before the new model loads. Caller should pass MODEL_MEMORY[current_model]
            when switching models so the admission check doesn't reject valid switches.
    """
    estimated_gb = MODEL_MEMORY.get(model, MEMORY_UNKNOWN_DEFAULT_GB)

    # Include draft model memory if speculative decoding is configured
    draft_model = DRAFT_MODEL_MAP.get(model, "")
    if draft_model:
        draft_gb = MODEL_MEMORY.get(draft_model, 0.5)
        estimated_gb += draft_gb

    available_gb = _get_available_memory_gb() + freed_by_stop_gb
    required_gb = estimated_gb + MEMORY_HEADROOM_GB

    if available_gb >= required_gb:
        print(
            f"[proxy] memory check OK: model={model!r} needs ~{estimated_gb:.0f}GB + "
            f"{MEMORY_HEADROOM_GB:.0f}GB headroom = {required_gb:.0f}GB, "
            f"available={available_gb:.1f}GB",
            flush=True,
        )
        return True, ""

    # Insufficient — build actionable message
    deficit = required_gb - available_gb
    is_known = model in MODEL_MEMORY

    model_label = model.split("/")[-1] if "/" in model else model
    draft_note = f" (incl {draft_model.split('/')[-1]} draft)" if draft_model else ""
    msg = (
        f"Insufficient memory to load {model_label!r}: "
        f"needs ~{estimated_gb:.0f}GB{draft_note}"
        + (" (estimated)" if not is_known else "")
        + f" + {MEMORY_HEADROOM_GB:.0f}GB headroom = {required_gb:.0f}GB, "
        f"only {available_gb:.1f}GB available ({deficit:.1f}GB short). "
        f"Free memory by stopping ComfyUI, unloading Ollama models "
        f"(`ollama stop <model>`), or closing other GPU workloads, then retry."
    )
    print(f"[proxy] ADMISSION REJECTED: {msg}", flush=True)
    return False, msg


def _big_model_pre_load(model: str) -> None:
    """Full-evict sequence before loading a big model.

    Order:
    1. Stop current MLX server (frees GPU allocation, waits for Metal reclaim)
    2. Evict all Ollama models from unified memory
    3. Assert minimum free memory — abort if below floor
    4. Log final headroom

    Called by ensure_server() when model is in BIG_MODEL_SET.
    """
    print(
        f"[big-model] PRE-LOAD sequence for {model!r} "
        f"(ctx_cap={BIG_MODEL_CTX}, min_free={BIG_MODEL_MIN_FREE_GB} GB)",
        flush=True,
    )
    # Step 1: stop any running MLX server
    stop_all()
    # Step 2: evict Ollama
    _evict_ollama_models()
    # Step 3: assert floor
    free_gb = _get_free_memory_gb()
    if free_gb < BIG_MODEL_MIN_FREE_GB:
        raise RuntimeError(
            f"Big-model pre-load aborted: only {free_gb:.1f} GB strictly free after full evict "
            f"(floor={BIG_MODEL_MIN_FREE_GB} GB). Close ComfyUI or other GPU workloads and retry."
        )
    # Step 4: log
    estimated = MODEL_MEMORY.get(model, MEMORY_UNKNOWN_DEFAULT_GB)
    print(
        f"[big-model] pre-load complete: {free_gb:.1f} GB free, "
        f"model needs ~{estimated:.0f} GB — proceeding",
        flush=True,
    )


_warm_model: str = os.environ.get("MLX_WARM_MODEL", "mlx-community/Llama-3.2-3B-Instruct-8bit")
_big_model_active: bool = False
_big_model_lock = threading.Lock()


def _big_model_post_restore() -> None:
    """Restore normal operation after a big-model session ends.

    Called by ensure_server() when a non-big-model request arrives and
    _big_model_active is True. Reloads the warm model so normal workspaces
    resume without cold-start penalty.

    Warm-model identity: MLX_WARM_MODEL env var (default: Llama-3.2-3B-Instruct-8bit).
    If the caller requests the warm model directly this is a no-op.
    """
    global _big_model_active
    with _big_model_lock:
        if not _big_model_active:
            return
        print(
            f"[big-model] POST-RESTORE: reloading warm model {_warm_model!r}",
            flush=True,
        )
        try:
            # stop big model first (it should still be loaded)
            stop_all()
            start_server("lm", _warm_model)
            _big_model_active = False
            print("[big-model] warm model restored — big-model mode deactivated", flush=True)
        except Exception as e:
            _big_model_active = False  # don't block future requests
            print(
                f"[big-model] post-restore failed ({e}) — proxy will cold-start on next request",
                flush=True,
            )


def ensure_server(model: str) -> int:
    """Ensure the correct server is running for the requested model.

    Tracks which model is loaded and restarts the server when the model changes.
    Returns the backend port.
    """
    target = "vlm" if needs_vlm(model) else "lm"
    current_model = mlx_state.loaded_model

    # Check if the right model is already loaded
    if current_model and model and current_model != model:
        # Model change requested — need to restart server
        print(f"[proxy] model switch: {current_model} -> {model}", flush=True)
    elif current_model and model and current_model == model:
        # Same model — check server is healthy
        healthy, _ = _probe_server(target)
        if healthy:
            mlx_state.set_ready(target, current_model)
            return VLM_PORT if target == "vlm" else LM_PORT
        # Server died — need to restart below
    else:
        # No current model tracked — check if server is running
        healthy, loaded = _probe_server(target)
        if healthy and not model:
            mlx_state.set_ready(target, loaded)
            return VLM_PORT if target == "vlm" else LM_PORT

    # Need to start or restart the server
    with lock:
        # Double-check under lock
        healthy, loaded = _probe_server(target)
        if healthy and current_model == model:
            mlx_state.set_ready(target, current_model or loaded)
            return VLM_PORT if target == "vlm" else LM_PORT

        mlx_state.set_switching(target)
        try:
            # ── Big-model mode (P5-BIG-001) ─────────────────────────────────
            # If this is a big model: full-evict (MLX + Ollama) before load.
            # Skip standard admission check — big_model_pre_load() handles it.
            global _big_model_active
            if model in BIG_MODEL_SET:
                _big_model_pre_load(model)
                with _big_model_lock:
                    _big_model_active = True
            else:
                # Non-big-model request — restore warm model if big-model was active
                if _big_model_active:
                    _big_model_post_restore()

                # ── Admission control (P5-FUT-009) ───────────────────────────
                # Check memory BEFORE stop_all() so we don't evict a healthy model
                # for a request that will be rejected anyway.
                # When switching models, credit the memory freed by unloading the
                # current model — it WILL be released by stop_all() below.
                current_loaded = mlx_state.loaded_model
                freed_by_stop_gb = MODEL_MEMORY.get(current_loaded, 0.0) if current_loaded else 0.0
                ok, rejection_msg = _check_memory_for_model(
                    model, freed_by_stop_gb=freed_by_stop_gb
                )
                if not ok:
                    mlx_state.set_down(rejection_msg)
                    raise RuntimeError(rejection_msg)

                stop_all()

            # Post-reclaim check — secondary safety net after eviction
            free_post = _get_free_memory_gb()
            if free_post < MEMORY_HEADROOM_GB:
                print(
                    f"[proxy] WARNING: only {free_post:.1f}GB free after reclaim — "
                    f"model load may fail on 64GB system",
                    flush=True,
                )

            port = start_server(target, model)
            mlx_state.set_ready(target, model)
            print(f"[proxy] mlx_{target} ready on :{port} model={model}", flush=True)
            return port
        except Exception as e:
            mlx_state.set_down(str(e))
            raise


def _watchdog_loop():
    """Background thread: probe both MLX servers and sample memory."""
    mem_sample_counter = 0
    while True:
        time.sleep(WATCHDOG_INTERVAL)
        try:
            # Don't interfere with active model switches
            if mlx_state.state == "switching":
                continue

            lm_healthy, lm_model = _probe_server("lm")
            vlm_healthy, vlm_model = _probe_server("vlm")
            active = mlx_state.active_server

            if active == "lm":
                if lm_healthy:
                    mlx_state.record_health_check(True)
                    mlx_state.set_ready("lm", lm_model)
                else:
                    mlx_state.record_health_check(False)
                    if mlx_state.consecutive_failures >= 2:
                        mlx_state.set_down("mlx_lm server not responding (crashed or OOM)")
                        print(
                            f"[watchdog] mlx_lm appears down after {mlx_state.consecutive_failures} failed checks",
                            flush=True,
                        )
                        # Proactively kill zombie — don't wait for next request
                        threading.Thread(target=_cleanup_zombie_servers, daemon=True).start()
            elif active == "vlm":
                if vlm_healthy:
                    mlx_state.record_health_check(True)
                    mlx_state.set_ready("vlm", vlm_model)
                else:
                    mlx_state.record_health_check(False)
                    if mlx_state.consecutive_failures >= 2:
                        mlx_state.set_down("mlx_vlm server not responding (crashed or OOM)")
                        print(
                            f"[watchdog] mlx_vlm appears down after {mlx_state.consecutive_failures} failed checks",
                            flush=True,
                        )
                        # Proactively kill zombie — don't wait for next request
                        threading.Thread(target=_cleanup_zombie_servers, daemon=True).start()
            else:
                # No active server tracked — only update if server is responding
                # AND has a known model. Don't set ready with unknown model —
                # let ensure_server() handle the model selection.
                if lm_healthy and lm_model:
                    mlx_state.set_ready("lm", lm_model)
                    print(
                        "[watchdog] detected mlx_lm running with model, updating state", flush=True
                    )
                elif vlm_healthy and vlm_model:
                    mlx_state.set_ready("vlm", vlm_model)
                    print(
                        "[watchdog] detected mlx_vlm running with model, updating state", flush=True
                    )

            # Recovery: if proxy is "down" but a server is healthy, recover
            if mlx_state.state == "down":
                if lm_healthy:
                    mlx_state.set_ready("lm", lm_model)
                    print("[watchdog] recovered: mlx_lm healthy, clearing down state", flush=True)
                elif vlm_healthy:
                    mlx_state.set_ready("vlm", vlm_model)
                    print("[watchdog] recovered: mlx_vlm healthy, clearing down state", flush=True)

            # Sample memory every ~60s (every 4th watchdog cycle at 15s interval)
            mem_sample_counter += 1
            if mem_sample_counter >= max(1, 60 // WATCHDOG_INTERVAL):
                memory_monitor.sample()
                mem_sample_counter = 0
        except Exception as e:
            print(f"[watchdog] error: {e}", flush=True)


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_post(self):
        clen = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(clen)
        try:
            model = json.loads(body).get("model", "")
        except Exception:
            model = ""
        bp = ensure_server(model)
        url = f"http://127.0.0.1:{bp}{self.path}"
        hdrs = {
            k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length")
        }
        hdrs["Content-Type"] = "application/json"
        with httpx.Client(timeout=REQUEST_TIMEOUT) as c:
            resp = c.post(url, content=body, headers=hdrs)
        self.send_response(resp.status_code)
        for k, v in resp.headers.items():
            if k.lower() not in ("transfer-encoding", "content-encoding"):
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(resp.content)

    def _handle_get_forward(self):
        active = detect_server()
        if active:
            port = VLM_PORT if active == "vlm" else LM_PORT
            with httpx.Client(timeout=30) as c:
                resp = c.get(f"http://127.0.0.1:{port}{self.path}")
            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                if k.lower() != "transfer-encoding":
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(resp.content)
            return True
        return False

    def do_POST(self):
        if not _request_semaphore.acquire(blocking=False):
            self._send_json(503, {"error": "MLX proxy overloaded — too many concurrent requests"})
            return
        try:
            self._handle_post()
        except RuntimeError as e:
            # Admission control rejection (P5-FUT-009) — 503 Service Unavailable
            self._send_json(
                503,
                {"error": {"message": str(e), "type": "capacity_error", "code": 503}},
            )
        except Exception as e:
            self._send_json(502, {"error": str(e)})
        finally:
            _request_semaphore.release()

    def do_GET(self):
        if self.path == "/health":
            state_info = mlx_state.to_dict()
            state_info["memory"] = memory_monitor.to_dict()
            state_info["big_model_active"] = _big_model_active
            state_info["big_model_ctx_cap"] = BIG_MODEL_CTX if _big_model_active else None
            state = state_info["state"]
            code = 200 if state in ("ready", "switching") else 503
            self._send_json(code, state_info)
            return
        if self.path == "/health/memory":
            self._send_json(
                200,
                {
                    "current": memory_monitor.to_dict(),
                    "recent": memory_monitor.get_recent(30),
                },
            )
            return
        if self.path == "/metrics":
            mem = memory_monitor.to_dict()
            cur = mem.get("current", {}) or {}
            state = mlx_state.to_dict()
            lines = [
                "# HELP mlx_memory_free_gb Free memory in GB",
                "# TYPE mlx_memory_free_gb gauge",
                f"mlx_memory_free_gb {cur.get('free_gb', 0)}",
                "# HELP mlx_memory_used_pct Memory usage percentage",
                "# TYPE mlx_memory_used_pct gauge",
                f"mlx_memory_used_pct {cur.get('used_pct', 0)}",
                "# HELP mlx_memory_wired_gb Wired memory in GB",
                "# TYPE mlx_memory_wired_gb gauge",
                f"mlx_memory_wired_gb {cur.get('wired_gb', 0)}",
                "# HELP mlx_memory_active_gb Active memory in GB",
                "# TYPE mlx_memory_active_gb gauge",
                f"mlx_memory_active_gb {cur.get('active_gb', 0)}",
                "# HELP mlx_memory_peak_used_pct Peak memory usage percentage",
                "# TYPE mlx_memory_peak_used_pct gauge",
                f"mlx_memory_peak_used_pct {mem.get('peak_used_pct', 0)}",
                "# HELP mlx_proxy_state Proxy state (1=ready, 0=other)",
                "# TYPE mlx_proxy_state gauge",
                f'mlx_proxy_state{{state="{state.get("state", "unknown")}"}} 1',
                "# HELP mlx_proxy_switch_count Model switch count",
                "# TYPE mlx_proxy_switch_count counter",
                f"mlx_proxy_switch_count {state.get('switch_count', 0)}",
                "# HELP mlx_proxy_consecutive_failures Consecutive health check failures",
                "# TYPE mlx_proxy_consecutive_failures gauge",
                f"mlx_proxy_consecutive_failures {state.get('consecutive_failures', 0)}",
                "# HELP mlx_memory_samples_total Total memory samples taken",
                "# TYPE mlx_memory_samples_total counter",
                f"mlx_memory_samples_total {mem.get('samples', 0)}",
            ]
            body = "\n".join(lines) + "\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body.encode())
            return
        if self.path == "/v1/models":
            if mlx_state.state in ("ready", "switching"):
                data = {
                    "object": "list",
                    "data": [{"id": m, "object": "model", "created": 0} for m in ALL_MODELS],
                }
                self._send_json(200, data)
            else:
                self._send_json(
                    503,
                    {
                        "error": f"MLX server {mlx_state.state} — {mlx_state.last_error or 'no server running'}"
                    },
                )
            return
        if not self._handle_get_forward():
            self._send_json(503, {"error": "no server"})

    def log_message(self, format, *args):
        pass


class BoundedThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """HTTP server that delegates request handling to a bounded thread pool."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, *args, max_workers=MAX_WORKERS, **kwargs):
        super().__init__(*args, **kwargs)
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="mlx-proxy",
        )
        self.watchdog_thread = threading.Thread(
            target=_watchdog_loop,
            daemon=True,
            name="mlx-watchdog",
        )
        self.watchdog_thread.start()

    def process_request(self, request, client_address):
        self.executor.submit(self.process_request_thread, request, client_address)

    def shutdown(self):
        self.executor.shutdown(wait=False)
        super().shutdown()


if __name__ == "__main__":
    os.makedirs(_server_log_dir, exist_ok=True)

    # Write PID file so external watchdog can track and recover us
    pid_file = Path("/tmp/mlx-proxy.pid")
    pid_file.write_text(str(os.getpid()))

    print(
        f"[mlx-proxy] Listening on :{PROXY_PORT} (workers={MAX_WORKERS}, queue={MAX_QUEUE}, watchdog={WATCHDOG_INTERVAL}s)",
        flush=True,
    )
    server = BoundedThreadingHTTPServer(("0.0.0.0", PROXY_PORT), Handler, max_workers=MAX_WORKERS)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[mlx-proxy] Shutting down...", flush=True)
        server.shutdown()
    finally:
        pid_file.unlink(missing_ok=True)
