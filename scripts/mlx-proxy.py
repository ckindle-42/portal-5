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

# Context ceiling for big-model requests — suppresses KV cache spike.
# 256K default context + KV cache can push memory over the edge.
# At 32K the KV cache is ~2 GB instead of ~16 GB.
# Override via env: MLX_BIG_MODEL_CTX (e.g. "65536" if you want 64K).
BIG_MODEL_CTX: int = int(os.environ.get("MLX_BIG_MODEL_CTX", "32768"))

# Minimum strictly-free GB required after full-evict before allowing a big-model load.
# Protects against proceeding into a guaranteed OOM.
BIG_MODEL_MIN_FREE_GB: float = float(os.environ.get("MLX_BIG_MODEL_MIN_FREE_GB", "6.0"))

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


def _load_mlx_metadata() -> "tuple[dict[str, float], set[str], set[str], list[str]]":
    """Load MODEL_MEMORY, BIG_MODEL_SET, VLM_MODELS, ALL_MODELS from backends.yaml.

    Reads the mlx_models structured entries under the first backend with type=mlx.
    Falls back to empty collections if the key is absent (old backends.yaml format).
    """
    try:
        with open(_backends_yaml_path()) as f:
            cfg = yaml.safe_load(f.read())
        mlx_be = next((b for b in cfg.get("backends", []) if b.get("type") == "mlx"), None)
        if not mlx_be:
            return {}, set(), set(), []
        items = mlx_be.get("mlx_models", [])
        if not items:
            # Old format: plain models list — no per-model metadata available
            return {}, set(), set(), mlx_be.get("models", [])
        model_memory = {it["id"]: float(it.get("memory_gb", 20.0)) for it in items}
        big_models: set[str] = {it["id"] for it in items if it.get("big_model")}
        # VLM_MODELS stores full HF IDs; needs_vlm() compares directly (no bare-name split)
        vlm_models: set[str] = {it["id"] for it in items if it.get("is_vlm")}
        all_models = [it["id"] for it in items]
        return model_memory, big_models, vlm_models, all_models
    except Exception as exc:
        print(f"[proxy] WARNING: failed to load mlx_models from backends.yaml: {exc}", flush=True)
        return {}, set(), set(), []


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


# Load model registry from backends.yaml (single source of truth — CLAUDE.md Rule 8)
MODEL_MEMORY, BIG_MODEL_SET, VLM_MODELS, ALL_MODELS = _load_mlx_metadata()
print(
    f"[proxy] loaded {len(MODEL_MEMORY)} MLX models from backends.yaml "
    f"({len(BIG_MODEL_SET)} big, {len(VLM_MODELS)} VLM)",
    flush=True,
)

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
    # VLM_MODELS stores full HuggingFace IDs (loaded from backends.yaml is_vlm: true)
    return model in VLM_MODELS


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


def _wait_for_memory_reclaim(target_free_gb: float, timeout_s: float = 45.0) -> bool:
    """Poll free memory after eviction, waiting for Metal GPU pages to release.

    macOS can hold Metal allocations as "inactive" or "wired" pages for 5-30s
    after a process exits. Calling this after stop_all() prevents the OOM that
    results from loading a new model while the old one's pages are still held.

    Returns True if target_free_gb of available memory (free+inactive) was
    reached within timeout_s, False if the timeout expired.
    """
    deadline = time.time() + timeout_s
    interval = 3.0
    while time.time() < deadline:
        available = _get_available_memory_gb()
        if available >= target_free_gb:
            print(
                f"[proxy] memory reclaim OK: {available:.1f}GB available >= {target_free_gb:.0f}GB target",
                flush=True,
            )
            return True
        remaining = deadline - time.time()
        print(
            f"[proxy] waiting for reclaim: {available:.1f}GB available, need {target_free_gb:.0f}GB "
            f"({remaining:.0f}s remaining)",
            flush=True,
        )
        time.sleep(interval)
    return False


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


def _wait_for_model_loaded(
    stype: str,
    model: str = "",
    timeout: float = 600.0,
    proc: subprocess.Popen | None = None,
) -> bool:
    """Wait for the MLX server to actually be serving inference requests.

    Monitors the server's stderr log for "Starting httpd" which appears
    AFTER the model finishes loading into GPU memory. This is deterministic —
    no guessing with timers or HTTP probes.

    If ``proc`` is provided and the subprocess exits before the ready signal
    appears, returns False immediately (rather than waiting out the full
    timeout). Surfaces the tail of the server log to aid diagnosis.
    """
    log_file = os.path.join(_server_log_dir, f"mlx_{stype}.log")
    deadline = time.time() + timeout
    last_size = 0
    last_log = 0

    while time.time() < deadline:
        # Fast-fail: child process exited before printing the ready signal.
        if proc is not None and proc.poll() is not None:
            elapsed = time.time() - (deadline - timeout)
            print(
                f"[proxy] mlx_{stype} subprocess exited rc={proc.returncode} "
                f"after {elapsed:.0f}s — never reached ready signal",
                flush=True,
            )
            try:
                if os.path.exists(log_file):
                    with open(log_file) as _f:
                        tail = _f.read()[-2000:]
                    print(f"[proxy] mlx_{stype} log tail:\n{tail}", flush=True)
            except Exception:
                pass
            return False
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
    which means the HTTP server is ready to accept connections.

    NOTE (mlx 0.31.2+): mlx_lm/server.py is patched to defer model loading
    to the _generate() worker thread (avoids cross-thread GPU stream errors).
    "Starting httpd" now signals HTTP-ready, not model-loaded. The model loads
    lazily on the first inference request within the 300s REQUEST_TIMEOUT.
    See: mlx_lm/server.py ModelProvider.__init__ patch.
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
    # Subprocess hardening — required for mlx_lm.server / mlx_vlm.server to start
    # cleanly under the proxy. Without these flags the child inherits the proxy's
    # stdin and process group, which causes multiprocessing.resource_tracker to
    # leak semaphores and the server to exit before binding its HTTP port.
    # See tests/UAT_RESULTS.md (2026-04-26) Research Notes — MLX Infrastructure Issue.
    proc = subprocess.Popen(
        cmd,
        stdout=log_fh,
        stderr=log_fh,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    print(
        f"[proxy] started mlx_{stype} (PID {proc.pid}) model={model or '(default)'} log={log_file}",
        flush=True,
    )

    # Wait for model to load — monitor log for "Starting httpd"
    print("[proxy] waiting for model to load (monitoring server log)...", flush=True)
    if _wait_for_model_loaded(stype, model, proc=proc):
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
                # Invariant: if a model is loaded, active_server must be set and
                # must match the expected server type for that model. This catches
                # state corruption where loaded_model and active_server disagree,
                # which would cause the admission credit to be computed for the
                # wrong server's memory footprint.
                if __debug__ and current_loaded and mlx_state.active_server:
                    expected_server = "vlm" if needs_vlm(current_loaded) else "lm"
                    assert mlx_state.active_server == expected_server, (
                        f"State invariant violated: loaded_model={current_loaded!r} "
                        f"implies active_server={expected_server!r} but "
                        f"active_server={mlx_state.active_server!r}"
                    )
                freed_by_stop_gb = MODEL_MEMORY.get(current_loaded, 0.0) if current_loaded else 0.0
                ok, rejection_msg = _check_memory_for_model(
                    model, freed_by_stop_gb=freed_by_stop_gb
                )
                if not ok:
                    print(f"[proxy] admission control: {rejection_msg} — resetting to idle", flush=True)
                    mlx_state.set_down(rejection_msg)  # record the error for /health
                    # Reset to idle immediately so the proxy can serve other models
                    mlx_state._state = "none"
                    mlx_state._state_since = time.time()
                    raise RuntimeError(rejection_msg)

                stop_all()

            # Wait for Metal GPU pages to release after process exit.
            # Admission control credits freed_by_stop_gb, but macOS holds
            # Metal allocations for 5-30s after process exit — loading
            # immediately causes OOM. Wait up to 45s for reclaim before load.
            estimated_gb = MODEL_MEMORY.get(model, MEMORY_UNKNOWN_DEFAULT_GB)
            _wait_for_memory_reclaim(target_free_gb=estimated_gb, timeout_s=45.0)

            # Post-reclaim check — abort if still insufficient after waiting.
            free_post = _get_free_memory_gb()
            available_post = _get_available_memory_gb()
            if free_post < MEMORY_HEADROOM_GB:
                print(
                    f"[proxy] WARNING: only {free_post:.1f}GB strictly free after reclaim — "
                    f"model load may be tight",
                    flush=True,
                )
            if available_post < estimated_gb:
                msg = (
                    f"Post-eviction memory still insufficient for {model!r}: "
                    f"{available_post:.1f}GB available (free+inactive), need ~{estimated_gb:.0f}GB. "
                    f"Metal GPU buffers still held — wait and retry, or close other GPU workloads."
                )
                print(f"[proxy] ABORT post-reclaim: {msg} — resetting to idle", flush=True)
                mlx_state.set_down(msg)  # record the error for /health
                # Reset to idle immediately so the proxy can serve other models
                mlx_state._state = "none"
                mlx_state._state_since = time.time()
                raise RuntimeError(msg)

            port = start_server(target, model)
            mlx_state.set_ready(target, model)
            print(f"[proxy] mlx_{target} ready on :{port} model={model}", flush=True)
            return port
        except Exception as e:
            mlx_state.set_down(str(e))
            # Admission control / memory rejections: proxy is healthy, just can't load this model.
            # Reset to idle so future requests can try other models (pipeline falls back to Ollama).
            if "Insufficient memory to load" in str(e) or "Post-eviction memory still insufficient" in str(e):
                mlx_state._state = "none"
                mlx_state._state_since = time.time()
            raise


def _watchdog_loop():
    """Background thread: probe both MLX servers and sample memory.

    Responsibility: keep mlx_state accurate for the /health endpoint.
    Recovery: if state is "down" but a server responds, clear the down state.

    Zombie cleanup and process restart are owned by the external mlx-watchdog.py
    daemon (under launchd), which has full OS-level visibility. This loop does
    NOT kill processes — doing so from two places produced redundant SIGTERM
    races and split the recovery logic across files.
    """
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
                    mlx_state.set_ready("lm", lm_model)
                # Failure: external watchdog owns zombie cleanup + restart
            elif active == "vlm":
                if vlm_healthy:
                    mlx_state.set_ready("vlm", vlm_model)
            else:
                # No active server tracked — detect if a server started running
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

            # Recovery: if proxy state is "down" but a server is now healthy, clear it
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
        # Stream the mlx_lm response back to the pipeline as chunks arrive.
        # Previous design (buffered c.post()) caused 300s pipeline timeout for
        # large models (70B @ 17min) because the pipeline saw no bytes until
        # the entire generation finished. With streaming, the first SSE chunk
        # arrives at the pipeline as soon as the first token is generated.
        with httpx.Client(timeout=REQUEST_TIMEOUT) as c:
            with c.stream("POST", url, content=body, headers=hdrs) as resp:
                self.send_response(resp.status_code)
                for k, v in resp.headers.items():
                    if k.lower() not in ("transfer-encoding", "content-encoding", "content-length"):
                        self.send_header(k, v)
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                for chunk in resp.iter_bytes(chunk_size=None):
                    if chunk:
                        # HTTP/1.1 chunked encoding: <hex-size>\r\n<data>\r\n
                        self.wfile.write(f"{len(chunk):x}\r\n".encode())
                        self.wfile.write(chunk)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()
                # Chunked terminator
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()

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
