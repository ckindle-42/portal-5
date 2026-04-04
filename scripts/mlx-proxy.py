#!/usr/bin/env python3
"""MLX Model-Aware Proxy — single port :8081, auto-switches mlx_lm ↔ mlx_vlm.

Usage: python3 mlx-proxy.py

Starts the correct MLX server based on the requested model:
  - mlx_lm.server  (port 18081) → text-only models (Qwen3-Coder-Next, DeepSeek-R1, etc.)
  - mlx_vlm.server (port 18082) → VLM models (Qwen3.5 family with vision tower)

Only one server runs at a time due to unified memory constraints on Apple Silicon.
Switching takes ~30s for the new server to load.

Concurrency protection: bounded thread pool prevents kernel panic under load.
  - MAX_WORKERS: max concurrent requests (default 4)
  - MAX_QUEUE: max queued requests before 503 (default 8)
  - REQUEST_TIMEOUT: max seconds per request (default 300s)
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

VLM_MODELS = {
    "MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit",
    "MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-8bit",
    "Qwen3-VL-32B-Instruct-8bit",
    "gemma-4-26b-a4b-4bit",  # Google Gemma 4 MoE — uses mlx_vlm (vision tower)
}

ALL_MODELS = [
    # Text-only models (served by mlx_lm on port 18081)
    "mlx-community/Qwen3-Coder-Next-4bit",
    "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",
    "mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit",
    "mlx-community/Devstral-Small-2505-8bit",
    "mlx-community/Dolphin3.0-Llama3.1-8B-8bit",
    "mlx-community/Llama-3.2-3B-Instruct-8bit",
    # Model diversity additions
    "mlx-community/gemma-4-26b-a4b-4bit",
    "lmstudio-community/Magistral-Small-2509-MLX-8bit",
    "mlx-community/Llama-3.3-70B-Instruct-4bit",
    # Claude 4.6 Opus Reasoning Distilled
    "Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-8bit",
    "Jackrong/MLX-Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-8bit",
    "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit",
    "mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit",
    # VLM models (served by mlx_vlm on port 18082)
    "mlx-community/Qwen3-VL-32B-Instruct-8bit",
    "mlx-community/llava-1.5-7b-8bit",
]

lock = threading.Lock()
_request_semaphore = threading.Semaphore(MAX_WORKERS + MAX_QUEUE)


def needs_vlm(model: str) -> bool:
    return model.split("/")[-1] in VLM_MODELS


def detect_server() -> str | None:
    """Return 'lm', 'vlm', or None based on which server is responding."""
    for port, stype in [(LM_PORT, "lm"), (VLM_PORT, "vlm")]:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=3)
            if r.status_code == 200:
                d = r.json()
                if stype == "vlm" and "loaded_model" in d:
                    return "vlm"
                if stype == "lm" and "loaded_model" not in d:
                    return "lm"
        except Exception:
            pass
    return None


def stop_all():
    """Kill any running MLX server on LM_PORT or VLM_PORT."""
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
                        subprocess.run(["kill", "-9", pid], capture_output=True)
        except Exception:
            pass
    time.sleep(2)


def start_server(stype: str) -> int:
    """Start mlx_lm.server or mlx_vlm.server and wait for it to be healthy."""
    port = LM_PORT if stype == "lm" else VLM_PORT
    cmd = ["python3", "-m", f"mlx_{stype}.server", "--port", str(port), "--host", "127.0.0.1"]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # 100 retries × 2s = 200s max startup time — cold-loading large models
    # (Qwen3-Coder-Next-4bit at 46GB, Llama-3.3-70B at 40GB) can take 2-3 min.
    for _ in range(100):
        time.sleep(2)
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=3).status_code == 200:
                return port
        except Exception:
            pass
    raise TimeoutError(f"mlx_{stype} failed to start on port {port}")


def ensure_server(model: str) -> int:
    """Ensure the correct server is running for the given model. Returns the backend port."""
    target = "vlm" if needs_vlm(model) else "lm"
    if detect_server() == target:
        return VLM_PORT if target == "vlm" else LM_PORT
    with lock:
        if detect_server() == target:
            return VLM_PORT if target == "vlm" else LM_PORT
        print(f"[proxy] {detect_server()} -> {target} for {model}", flush=True)
        stop_all()
        port = start_server(target)
        print(f"[proxy] mlx_{target} ready on :{port}", flush=True)
        return port


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
            self._send_json(200, {"status": "ok", "active_server": detect_server() or "none"})
            return
        if self.path == "/v1/models":
            data = {
                "object": "list",
                "data": [{"id": m, "object": "model", "created": 0} for m in ALL_MODELS],
            }
            self._send_json(200, data)
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

    def process_request(self, request, client_address):
        self.executor.submit(self.process_request_thread, request, client_address)

    def shutdown(self):
        self.executor.shutdown(wait=False)
        super().shutdown()


if __name__ == "__main__":
    print(
        f"[mlx-proxy] Listening on :{PROXY_PORT} (workers={MAX_WORKERS}, queue={MAX_QUEUE})",
        flush=True,
    )
    server = BoundedThreadingHTTPServer(("0.0.0.0", PROXY_PORT), Handler, max_workers=MAX_WORKERS)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[mlx-proxy] Shutting down...", flush=True)
        server.shutdown()
