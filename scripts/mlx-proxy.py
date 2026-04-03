#!/usr/bin/env python3
"""MLX Model-Aware Proxy — single port :8081, auto-switches mlx_lm ↔ mlx_vlm.

Usage: python3 mlx-proxy.py

Starts the correct MLX server based on the requested model:
  - mlx_lm.server  (port 18081) → text-only models (Qwen3-Coder-Next, DeepSeek-R1, etc.)
  - mlx_vlm.server (port 18082) → VLM models (Qwen3.5 family with vision tower)

Only one server runs at a time due to unified memory constraints on Apple Silicon.
Switching takes ~30s for the new server to load.
"""

import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

LM_PORT = 18081
VLM_PORT = 18082
PROXY_PORT = 8081

VLM_MODELS = {
    "MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit",
    "MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-8bit",
    "Qwen3-VL-32B-Instruct-8bit",
    "gemma-4-26b-a4b-4bit",  # Google Gemma 4 MoE — uses mlx_vlm (vision tower)
}

ALL_MODELS = [
    # Text-only models (served by mlx_lm on port 18081)
    "mlx-community/Qwen3-Coder-Next-8bit",
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
    for _ in range(45):
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
    def do_POST(self):
        clen = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(clen)
        try:
            model = json.loads(body).get("model", "")
        except Exception:
            model = ""
        try:
            bp = ensure_server(model)
            url = f"http://127.0.0.1:{bp}{self.path}"
            hdrs = {
                k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length")
            }
            hdrs["Content-Type"] = "application/json"
            with httpx.Client(timeout=300) as c:
                resp = c.post(url, content=body, headers=hdrs)
            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                if k.lower() not in ("transfer-encoding", "content-encoding"):
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(resp.content)
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"status": "ok", "active_server": detect_server() or "none"}).encode()
            )
            return
        if self.path == "/v1/models":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "object": "list",
                "data": [{"id": m, "object": "model", "created": 0} for m in ALL_MODELS],
            }
            self.wfile.write(json.dumps(data).encode())
            return
        # Forward to active server
        active = detect_server()
        if active:
            port = VLM_PORT if active == "vlm" else LM_PORT
            try:
                with httpx.Client(timeout=30) as c:
                    resp = c.get(f"http://127.0.0.1:{port}{self.path}")
                self.send_response(resp.status_code)
                for k, v in resp.headers.items():
                    if k.lower() != "transfer-encoding":
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp.content)
                return
            except Exception:
                pass
        self.send_response(503)
        self.end_headers()
        self.wfile.write(b'{"error":"no server"}')

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"[mlx-proxy] Listening on :{PROXY_PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PROXY_PORT), Handler).serve_forever()
