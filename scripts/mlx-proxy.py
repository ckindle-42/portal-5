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
from socketserver import ThreadingMixIn

import httpx

LM_PORT = 18081
VLM_PORT = 18082
PROXY_PORT = 8081

MAX_WORKERS = int(os.environ.get("MLX_PROXY_MAX_WORKERS", "4"))
MAX_QUEUE = int(os.environ.get("MLX_PROXY_MAX_QUEUE", "8"))
REQUEST_TIMEOUT = int(os.environ.get("MLX_PROXY_REQUEST_TIMEOUT", "300"))
WATCHDOG_INTERVAL = int(os.environ.get("MLX_WATCHDOG_INTERVAL", "15"))

VLM_MODELS = {
    "Qwen3-VL-32B-Instruct-8bit",
    "gemma-4-31b-it-4bit",
    "llava-1.5-7b-8bit",
}

ALL_MODELS = [
    "mlx-community/Qwen3-Coder-Next-4bit",
    "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",
    "mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit",
    "mlx-community/Devstral-Small-2505-8bit",
    "mlx-community/Dolphin3.0-Llama3.1-8B-8bit",
    "mlx-community/Llama-3.2-3B-Instruct-8bit",
    "mlx-community/gemma-4-31b-it-4bit",
    "lmstudio-community/Magistral-Small-2509-MLX-8bit",
    "mlx-community/Llama-3.3-70B-Instruct-4bit",
    "Jackrong/MLX-Qwopus3.5-27B-v3-8bit",
    "Jackrong/MLX-Qwopus3.5-9B-v3-8bit",
    "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit",
    "mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit",
    "mlx-community/Qwen3-VL-32B-Instruct-8bit",
    "mlx-community/llava-1.5-7b-8bit",
]

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


def _get_free_memory_gb() -> float:
    """Get current free memory in GB via vm_stat (macOS)."""
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


def _wait_for_gpu_memory_reclaim(min_wait: float = 5.0, max_wait: float = 20.0) -> None:
    """Wait for Metal GPU memory to be reclaimed after server shutdown.

    On Apple Silicon, Metal GPU memory is reclaimed asynchronously after a
    process exits. Starting a new model before the old memory is released
    causes command buffer errors (crash). We actively poll free memory
    and wait until it stabilizes, indicating reclamation is complete.
    """
    time.sleep(min_wait)  # Minimum wait for process teardown
    free_before = _get_free_memory_gb()
    stable_count = 0
    deadline = time.time() + max_wait
    while time.time() < deadline:
        time.sleep(2)
        free_now = _get_free_memory_gb()
        if free_now >= free_before - 0.5:  # memory stable or increasing
            stable_count += 1
            if stable_count >= 2:
                return  # Memory has been stable for 4+ seconds — reclamation done
        else:
            stable_count = 0
            free_before = free_now
    # Timed out but don't block forever — proceed with best effort
    print(f"[proxy] memory reclaim wait timed out ({max_wait}s) — proceeding", flush=True)


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

    # Graceful kill all — SIGTERM first, then wait
    for pid in pids_to_kill:
        _graceful_kill(pid)

    # Wait for Metal GPU memory reclamation
    _wait_for_gpu_memory_reclaim()


def start_server(stype: str, model: str = "") -> int:
    """Start mlx_lm.server or mlx_vlm.server and wait for it to be healthy."""
    port = LM_PORT if stype == "lm" else VLM_PORT
    cmd = ["python3", "-m", f"mlx_{stype}.server", "--port", str(port), "--host", "127.0.0.1"]
    if model:
        cmd.extend(["--model", model])
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        time.sleep(2)
        healthy, model_loaded = _probe_server(stype)
        if healthy:
            mlx_state.set_ready(stype, model_loaded)
            return port
    raise TimeoutError(f"mlx_{stype} failed to start on port {port}")


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
            stop_all()
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
            else:
                if lm_healthy:
                    mlx_state.set_ready("lm", lm_model)
                    print("[watchdog] detected mlx_lm running, updating state", flush=True)
                elif vlm_healthy:
                    mlx_state.set_ready("vlm", vlm_model)
                    print("[watchdog] detected mlx_vlm running, updating state", flush=True)

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
        except Exception as e:
            self._send_json(502, {"error": str(e)})
        finally:
            _request_semaphore.release()

    def do_GET(self):
        if self.path == "/health":
            state_info = mlx_state.to_dict()
            state_info["memory"] = memory_monitor.to_dict()
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
