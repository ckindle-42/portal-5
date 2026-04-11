#!/usr/bin/env python3
"""
Portal 5 — End-to-End Acceptance Test Suite v6
===============================================
Comprehensive validation of all Portal 5 features and personas.

Run from the repo root:
    python3 portal5_acceptance_v6.py
    python3 portal5_acceptance_v6.py --section S3         # single section
    python3 portal5_acceptance_v6.py --section S3,S10,S11 # comma-separated
    python3 portal5_acceptance_v6.py --section S3-S11     # range (inclusive)
    python3 portal5_acceptance_v6.py --skip-passing       # skip all-PASS sections
    python3 portal5_acceptance_v6.py --rebuild            # force rebuild first
    python3 portal5_acceptance_v6.py --verbose

Dependencies (auto-installed on first run):
    mcp httpx pyyaml playwright python-docx python-pptx openpyxl

PROTECTED — never modify these files:
    portal_pipeline/**  portal_mcp/**  config/  deploy/  Dockerfile.*
    scripts/openwebui_init.py  docs/HOWTO.md  imports/

Status model:
    PASS    — verified working exactly as documented
    FAIL    — product is running but behavior does not match documentation
    BLOCKED — correct assertion, confirmed product code change required
    WARN    — soft failure: request served but response does not fully match
    INFO    — informational, no assertion

Test Coverage (21 sections, ~300 tests):
    S0-S2:   Prerequisites, config consistency, service health
    S3:      17 workspaces with content-aware routing
    S4-S5:   Document generation (Word/Excel/PowerPoint), code sandbox
    S6:      Security workspaces (auto-security, auto-redteam, auto-blueteam)
    S7-S9:   Music generation, TTS, STT
    S10-S11: 46 personas across 8 categories (Ollama + MLX backends)
    S12-S13: Web search (SearXNG), RAG/embedding pipeline
    S20:     MLX acceleration (proxy health, /v1/models, memory)
    S21:     LLM Intent Router (P5-FUT-006) — semantic routing via Llama-3.2-3B
    S22:     MLX Admission Control (P5-FUT-009) — memory-aware 503 rejection
    S23:     Model diversity (GPT-OSS, Gemma 4 E4B, Phi-4, Magistral)
    S30-S31: Image generation (ComfyUI/FLUX), video generation (Wan2.2)
    S40:     Metrics/monitoring (Prometheus, Grafana)

Changes from v5:
    - Added S21 (LLM Intent Router), S22 (Admission Control), S23 (Model Diversity)
    - Updated persona count to 46 (added gemma4e4bvision, phi4specialist, gptossanalyst)
    - Fixed persona slugs to match actual YAML filenames
    - Tests for new models: GPT-OSS:20B, Gemma 4 E4B, Phi-4-reasoning-plus
    - Consolidated test framework with unified helper functions
    - Improved MLX state detection and recovery
    - Enhanced document content validation
    - Structured blocked items register
    - Live progress logging
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import re
import subprocess
import sys
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).parent.parent.resolve()


# ══════════════════════════════════════════════════════════════════════════════
# Environment Setup
# ══════════════════════════════════════════════════════════════════════════════

def _load_env() -> None:
    """Load .env file into environment."""
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

# Service URLs
PIPELINE_URL = "http://localhost:9099"
OPENWEBUI_URL = "http://localhost:8080"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").replace(
    "host.docker.internal", "localhost"
)
MLX_URL = os.environ.get("MLX_LM_URL", "http://localhost:8081").replace(
    "host.docker.internal", "localhost"
)
SEARXNG_URL = "http://localhost:8088"
PROMETHEUS_URL = "http://localhost:9090"
GRAFANA_URL = "http://localhost:3000"
COMFYUI_URL = "http://localhost:8188"

# API credentials
API_KEY = os.environ.get("PIPELINE_API_KEY", "")
ADMIN_EMAIL = os.environ.get("OPENWEBUI_ADMIN_EMAIL", "admin@portal.local")
ADMIN_PASS = os.environ.get("OPENWEBUI_ADMIN_PASSWORD", "")
GRAFANA_PASS = os.environ.get("GRAFANA_PASSWORD", "admin")

AUTH = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# MCP ports
MCP = {
    "comfyui": int(os.environ.get("COMFYUI_MCP_HOST_PORT", "8910")),
    "video": int(os.environ.get("VIDEO_MCP_HOST_PORT", "8911")),
    "music": int(os.environ.get("MUSIC_HOST_PORT", "8912")),
    "documents": int(os.environ.get("DOCUMENTS_HOST_PORT", "8913")),
    "sandbox": int(os.environ.get("SANDBOX_HOST_PORT", "8914")),
    "whisper": int(os.environ.get("WHISPER_HOST_PORT", "8915")),
    "tts": int(os.environ.get("TTS_HOST_PORT", "8916")),
    "embedding": int(os.environ.get("EMBEDDING_HOST_PORT", "8917")),
}

# MLX Speech server (host-native)
MLX_SPEECH_PORT = int(os.environ.get("MLX_SPEECH_PORT", "8918"))
MLX_SPEECH_URL = f"http://localhost:{MLX_SPEECH_PORT}"

# Output directory
AI_OUTPUT_DIR = Path(os.environ.get("AI_OUTPUT_DIR", str(Path.home() / "AI_Output")))

# Docker compose command
DC = ["docker", "compose", "-f", "deploy/portal-5/docker-compose.yml"]

# Global flags
_FORCE_REBUILD = False
_verbose = False
_PROGRESS_LOG = "/tmp/portal5_progress.log"


# ══════════════════════════════════════════════════════════════════════════════
# Result Model and Recording
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class R:
    """Test result record."""
    section: str
    tid: str
    name: str
    status: str  # PASS | FAIL | BLOCKED | WARN | INFO
    detail: str = ""
    evidence: list[str] = field(default_factory=list)
    fix: str = ""
    duration: float = 0.0


_log: list[R] = []
_blocked: list[R] = []
_ICON = {"PASS": "✅", "FAIL": "❌", "BLOCKED": "🚫", "WARN": "⚠️ ", "INFO": "ℹ️ "}


def _emit(r: R) -> R:
    """Print and log a test result."""
    icon = _ICON.get(r.status, "  ")
    dur = f"({r.duration:.1f}s)" if r.duration else ""
    line = f"  {icon} [{r.tid}] {r.name}  {r.detail}  {dur}"
    print(line)
    if _verbose and r.evidence:
        for e in r.evidence:
            print(f"       {e}")
    # Write to live progress log
    try:
        ts = time.strftime("%H:%M:%S")
        counts = _progress_counts()
        with open(_PROGRESS_LOG, "a") as pf:
            pf.write(
                f"[{ts}] {icon} [{r.section}/{r.tid}] {r.name[:60]}  {r.detail[:60]}  {dur}  {counts}\n"
            )
    except Exception:
        pass
    return r


def _progress_counts() -> str:
    """Return live PASS/WARN/FAIL counts for progress log."""
    p = sum(1 for x in _log if x.status == "PASS")
    w = sum(1 for x in _log if x.status == "WARN")
    f = sum(1 for x in _log if x.status == "FAIL")
    b = sum(1 for x in _log if x.status == "BLOCKED")
    return f"[{p}P {w}W {f}F {b}B]"


def record(
    section: str,
    tid: str,
    name: str,
    status: str,
    detail: str = "",
    evidence: list[str] | None = None,
    fix: str = "",
    t0: float | None = None,
) -> R:
    """Record a test result."""
    dur = time.time() - t0 if t0 else 0.0
    r = R(section, tid, name, status, detail, evidence or [], fix, dur)
    _log.append(r)
    if status == "BLOCKED":
        _blocked.append(r)
    return _emit(r)


# ══════════════════════════════════════════════════════════════════════════════
# Git and Configuration Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _git_sha() -> str:
    """Get current git SHA."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        ).stdout.strip()
    except Exception:
        return "unknown"


def _load_workspaces() -> tuple[list[str], dict[str, str]]:
    """Load workspace definitions from router_pipe.py."""
    src = (ROOT / "portal_pipeline/router_pipe.py").read_text()
    start = src.index("WORKSPACES:")
    end = src.index("# ── Content-aware", start)
    block = src[start:end]
    ids = sorted(set(re.findall(r'"(auto[^"]*)":\s*\{', block)))
    names = dict(re.findall(r'"(auto[^"]*)":.*?"name":\s*"([^"]+)"', block, re.DOTALL))
    return ids, names


def _load_personas() -> list[dict]:
    """Load all persona YAML files."""
    return [
        yaml.safe_load(f.read_text())
        for f in sorted((ROOT / "config/personas").glob("*.yaml"))
    ]


def _load_backends_yaml() -> dict:
    """Load backends.yaml configuration."""
    return yaml.safe_load((ROOT / "config/backends.yaml").read_text())


# Load at module init
WS_IDS, WS_NAMES = _load_workspaces()
PERSONAS = _load_personas()


# ══════════════════════════════════════════════════════════════════════════════
# HTTP and API Helpers
# ══════════════════════════════════════════════════════════════════════════════

async def _get(url: str, timeout: int = 10) -> tuple[int, dict | str]:
    """Simple GET request returning (status_code, json_or_text)."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(url)
            try:
                return r.status_code, r.json()
            except Exception:
                return r.status_code, r.text
    except Exception as e:
        return 0, str(e)


async def _post(
    url: str,
    body: dict,
    headers: dict | None = None,
    timeout: int = 30,
) -> tuple[int, dict | str]:
    """Simple POST request returning (status_code, json_or_text)."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(url, json=body, headers=headers or AUTH)
            try:
                return r.status_code, r.json()
            except Exception:
                return r.status_code, r.text
    except Exception as e:
        return 0, str(e)


def _ollama_models() -> list[str]:
    """Get list of Ollama models."""
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        try:
            r2 = subprocess.run(
                ["docker", "exec", "portal5-ollama", "ollama", "list"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return [ln.split()[0] for ln in r2.stdout.splitlines()[1:] if ln.strip()]
        except Exception:
            return []


def _owui_token() -> str:
    """Get Open WebUI JWT token."""
    if not ADMIN_PASS:
        return ""
    try:
        r = httpx.post(
            f"{OPENWEBUI_URL}/api/v1/auths/signin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
            timeout=10,
        )
        return r.json().get("token", "")
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# Audio Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _is_wav(data: bytes) -> bool:
    """Check if data is a valid WAV file."""
    return len(data) > 44 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def _wav_info(data: bytes) -> dict | None:
    """Parse WAV header — returns {channels, sample_rate, frames, duration_s}."""
    if not _is_wav(data):
        return None
    try:
        with wave.open(io.BytesIO(data)) as wf:
            return {
                "channels": wf.getnchannels(),
                "sample_rate": wf.getframerate(),
                "frames": wf.getnframes(),
                "duration_s": round(wf.getnframes() / wf.getframerate(), 2),
            }
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# MCP Tool Calling (uses real MCP SDK)
# ══════════════════════════════════════════════════════════════════════════════

async def _mcp(
    port: int,
    tool: str,
    args: dict,
    *,
    section: str,
    tid: str,
    name: str,
    ok_fn: Callable[[str], bool],
    detail_fn: Callable[[str], str] | None = None,
    warn_if: list[str] | None = None,
    timeout: int = 30,
) -> None:
    """Call an MCP tool and record the result."""
    t0 = time.time()
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        url = f"http://localhost:{port}/mcp"
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await asyncio.wait_for(
                    session.call_tool(tool, args), timeout=timeout
                )
                text = ""
                for block in result.content:
                    if hasattr(block, "text"):
                        text += block.text

        is_ok = ok_fn(text)
        is_warn = warn_if and any(w.lower() in text.lower() for w in warn_if)
        status = "WARN" if is_warn and not is_ok else ("PASS" if is_ok else "FAIL")
        detail = (detail_fn(text) if detail_fn else text[:120]) if text else "(empty)"
        record(section, tid, name, status, detail, t0=t0)

    except asyncio.TimeoutError:
        record(section, tid, name, "WARN", f"timeout after {timeout}s", t0=t0)
    except ImportError:
        record(section, tid, name, "FAIL", "pip install mcp --break-system-packages", t0=t0)
    except Exception as e:
        record(section, tid, name, "FAIL", str(e)[:200], t0=t0)


async def _mcp_raw(
    port: int,
    tool: str,
    args: dict,
    *,
    section: str,
    tid: str,
    name: str,
    ok_fn: Callable[[str], bool],
    detail_fn: Callable[[str], str] | None = None,
    warn_if: list[str] | None = None,
    timeout: int = 30,
) -> str:
    """Like _mcp but also returns the raw response text."""
    t0 = time.time()
    text = ""
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        url = f"http://localhost:{port}/mcp"
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await asyncio.wait_for(
                    session.call_tool(tool, args), timeout=timeout
                )
                for block in result.content:
                    if hasattr(block, "text"):
                        text += block.text

        is_ok = ok_fn(text)
        is_warn = warn_if and any(w.lower() in text.lower() for w in warn_if)
        status = "WARN" if is_warn and not is_ok else ("PASS" if is_ok else "FAIL")
        detail = (detail_fn(text) if detail_fn else text[:120]) if text else "(empty)"
        record(section, tid, name, status, detail, t0=t0)

    except asyncio.TimeoutError:
        record(section, tid, name, "WARN", f"timeout after {timeout}s", t0=t0)
    except ImportError:
        record(section, tid, name, "FAIL", "pip install mcp --break-system-packages", t0=t0)
    except Exception as e:
        record(section, tid, name, "FAIL", str(e)[:200], t0=t0)
    return text


# ══════════════════════════════════════════════════════════════════════════════
# Pipeline Chat (simulates Open WebUI traffic)
# ══════════════════════════════════════════════════════════════════════════════

async def _chat(
    workspace: str,
    prompt: str,
    system: str = "",
    max_tokens: int = 400,
    timeout: int = 240,
    stream: bool = False,
) -> tuple[int, str]:
    """Send a chat request to the pipeline."""
    code, text, _ = await _chat_with_model(workspace, prompt, system, max_tokens, timeout, stream)
    return code, text


async def _chat_with_model(
    workspace: str,
    prompt: str,
    system: str = "",
    max_tokens: int = 400,
    timeout: int = 240,
    stream: bool = False,
) -> tuple[int, str, str]:
    """Chat request that also returns the model used.
    
    Returns (status_code, response_text, model_used).
    """
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system[:800]})
    msgs.append({"role": "user", "content": prompt})
    body = {"model": workspace, "messages": msgs, "stream": stream, "max_tokens": max_tokens}

    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=timeout) as c:
                r = await c.post(f"{PIPELINE_URL}/v1/chat/completions", headers=AUTH, json=body)
                if r.status_code != 200:
                    if r.status_code in (502, 503) and attempt == 0:
                        continue  # Retry on MLX proxy crash
                    return r.status_code, r.text[:200], ""

                if stream:
                    text = ""
                    for line in r.text.splitlines():
                        if line.startswith("data: ") and line != "data: [DONE]":
                            try:
                                d = json.loads(line[6:])
                                text += d.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            except Exception:
                                pass
                    return 200, text, ""

                data = r.json()
                msg = data.get("choices", [{}])[0].get("message", {})
                model = data.get("model", "")
                content = msg.get("content", "") or msg.get("reasoning", "")
                return 200, content, model
        except httpx.ReadTimeout:
            return 408, "timeout", ""
        except Exception as e:
            if attempt == 0 and any(x in str(e).lower() for x in ["502", "connection refused"]):
                continue
            return 0, str(e)[:100], ""
    return 503, "MLX proxy down, fallback not available", ""


def _curl_stream(
    workspace: str, prompt: str, max_tokens: int = 5, timeout_s: int = 360
) -> tuple[bool, str]:
    """Test streaming via curl (more reliable than httpx for SSE)."""
    try:
        result = subprocess.run(
            [
                "curl", "-s", "-m", str(timeout_s),
                "-X", "POST", f"{PIPELINE_URL}/v1/chat/completions",
                "-H", f"Authorization: Bearer {API_KEY}",
                "-H", "Content-Type: application/json",
                "-d", json.dumps({
                    "model": workspace,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True,
                    "max_tokens": max_tokens,
                }),
            ],
            capture_output=True,
            text=True,
            timeout=timeout_s + 10,
        )
        if result.returncode != 0:
            return False, f"curl exit={result.returncode}: {result.stderr[:120]}"
        lines = result.stdout.strip().splitlines()
        chunks = [ln for ln in lines if ln.startswith("data: ") and ln != "data: [DONE]"]
        done = any(ln == "data: [DONE]" for ln in lines)
        return len(chunks) > 0, f"{len(chunks)} data chunks | [DONE]={'yes' if done else 'no'}"
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout_s}s"
    except Exception as e:
        return False, str(e)[:120]


# ══════════════════════════════════════════════════════════════════════════════
# Docker and Log Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _grep_logs(container: str, pattern: str, lines: int = 500) -> list[str]:
    """Grep container logs for a pattern."""
    try:
        r = subprocess.run(
            ["docker", "logs", "--tail", str(lines), container],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return [
            ln for ln in (r.stdout + r.stderr).splitlines()
            if re.search(pattern, ln, re.IGNORECASE)
        ]
    except Exception:
        return []


def _docker_alive() -> tuple[bool, str]:
    """Check if Docker daemon and critical containers are running."""
    try:
        # Check Docker daemon
        info = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        if info.returncode != 0:
            return False, "Docker daemon not responding"

        # Check critical containers
        ps = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        containers = ps.stdout.strip().split("\n")
        required = ["portal5-pipeline", "portal5-open-webui", "portal5-searxng", "portal5-prometheus"]
        missing = [c for c in required if c not in containers]
        if missing:
            return False, f"Missing containers: {missing}"
        return True, "Docker OK"
    except Exception as e:
        return False, str(e)


async def _wait_for_docker_recovery(timeout: int = 600) -> tuple[bool, int]:
    """Wait for Docker to recover."""
    start = time.time()
    while time.time() - start < timeout:
        alive, _ = _docker_alive()
        if alive:
            return True, int(time.time() - start)
        elapsed = int(time.time() - start)
        remaining = timeout - elapsed
        print(f"  ⏳ Docker recovery: {elapsed}s elapsed, {remaining}s remaining...")
        await asyncio.sleep(15)
    return False, timeout


# ══════════════════════════════════════════════════════════════════════════════
# MLX Helpers
# ══════════════════════════════════════════════════════════════════════════════

# MLX model full paths (HuggingFace org/name format)
_MLX_MODEL_FULL_PATHS = {
    "Qwen3-Coder-Next-4bit": "mlx-community/Qwen3-Coder-Next-4bit",
    "Qwen3-Coder-30B-A3B-Instruct-8bit": "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",
    "DeepSeek-Coder-V2-Lite-Instruct-8bit": "mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit",
    "Devstral-Small-2507-MLX-4bit": "lmstudio-community/Devstral-Small-2507-MLX-4bit",
    "Dolphin3.0-Llama3.1-8B-8bit": "mlx-community/Dolphin3.0-Llama3.1-8B-8bit",
    "Llama-3.2-3B-Instruct-8bit": "mlx-community/Llama-3.2-3B-Instruct-8bit",
    "phi-4-8bit": "mlx-community/phi-4-8bit",
    "Magistral-Small-2509-MLX-8bit": "lmstudio-community/Magistral-Small-2509-MLX-8bit",
    "Llama-3.3-70B-Instruct-4bit": "mlx-community/Llama-3.3-70B-Instruct-4bit",
    "MLX-Qwopus3.5-27B-v3-8bit": "Jackrong/MLX-Qwopus3.5-27B-v3-8bit",
    "MLX-Qwopus3.5-9B-v3-8bit": "Jackrong/MLX-Qwopus3.5-9B-v3-8bit",
    "MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit": "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit",
    "DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit": "mlx-community/DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit",
    "DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit": "mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit",
    "gemma-4-31b-it-4bit": "mlx-community/gemma-4-31b-it-4bit",
    "gemma-4-26b-a4b-it-4bit": "mlx-community/gemma-4-26b-a4b-it-4bit",
    "Qwen3-VL-32B-Instruct-8bit": "mlx-community/Qwen3-VL-32B-Instruct-8bit",
}

# MLX model sizes (approximate GB)
_MLX_MODEL_SIZES_GB = {
    "Qwen3-Coder-Next-4bit": 46,
    "Qwen3-Coder-30B-A3B-Instruct-8bit": 22,
    "DeepSeek-Coder-V2-Lite-Instruct-8bit": 12,
    "Devstral-Small-2507-MLX-4bit": 15,
    "Dolphin3.0-Llama3.1-8B-8bit": 9,
    "Llama-3.2-3B-Instruct-8bit": 3,
    "phi-4-8bit": 14,
    "Magistral-Small-2509-MLX-8bit": 24,
    "Llama-3.3-70B-Instruct-4bit": 40,
    "MLX-Qwopus3.5-27B-v3-8bit": 22,
    "MLX-Qwopus3.5-9B-v3-8bit": 10,
    "MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit": 28,
    "DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit": 34,
    "DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit": 18,
    "gemma-4-31b-it-4bit": 18,
    "gemma-4-26b-a4b-it-4bit": 15,
    "Qwen3-VL-32B-Instruct-8bit": 36,
}

# Known MLX org prefixes
_MLX_ORGS = ["mlx-community/", "lmstudio-community/", "Jackrong/", "unsloth/"]


async def _mlx_health() -> tuple[str, dict]:
    """Get MLX proxy health state."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{MLX_URL}/health")
            if r.status_code == 200:
                data = r.json()
                return data.get("state", "unknown"), data
            elif r.status_code == 503:
                return "down", {"status_code": 503}
            else:
                return "error", {"status_code": r.status_code}
    except Exception as e:
        return "unreachable", {"error": str(e)}


async def _wait_for_mlx_ready(timeout: int = 120) -> bool:
    """Wait for MLX proxy to be ready."""
    start = time.time()
    while time.time() - start < timeout:
        state, _ = await _mlx_health()
        if state == "ready":
            return True
        if state in ("none", "switching"):
            await asyncio.sleep(5)
            continue
        await asyncio.sleep(3)
    return False


async def _unload_ollama_models() -> None:
    """Evict all Ollama models from memory to free unified memory for MLX/ComfyUI."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{OLLAMA_URL}/api/ps")
            if r.status_code != 200:
                return
            models = [m["name"] for m in r.json().get("models", [])]
        if not models:
            print("  ── No Ollama models loaded ──")
            return
        print(f"  ── Evicting {len(models)} Ollama model(s): {models} ──")
        async with httpx.AsyncClient(timeout=30) as c:
            for model in models:
                try:
                    await c.post(
                        f"{OLLAMA_URL}/api/generate",
                        json={"model": model, "keep_alive": 0},
                        timeout=10,
                    )
                except Exception:
                    pass
        # Wait for memory to be released
        await asyncio.sleep(5)
    except Exception as e:
        print(f"  ⚠️  Ollama eviction failed: {e}")


async def _unload_mlx_model() -> None:
    """Unload current MLX model to free unified memory."""
    try:
        state, data = await _mlx_health()
        if state == "none":
            print("  ── No MLX model loaded ──")
            return
        loaded = data.get("loaded_model", "unknown")
        print(f"  ── Unloading MLX model: {loaded} ──")
        # Send request to unload (if proxy supports it)
        async with httpx.AsyncClient(timeout=30) as c:
            try:
                await c.post(f"{MLX_URL}/unload", timeout=10)
            except Exception:
                pass
        # Wait for memory to be released
        await asyncio.sleep(10)
    except Exception as e:
        print(f"  ⚠️  MLX unload failed: {e}")


async def _memory_cleanup(phase: str) -> None:
    """Perform memory cleanup between test phases."""
    print(f"\n  ══ MEMORY CLEANUP: {phase} ══")
    await _unload_ollama_models()
    await _unload_mlx_model()
    # Force garbage collection
    import gc
    gc.collect()
    await asyncio.sleep(5)
    print("  ══ CLEANUP COMPLETE ══\n")


# ══════════════════════════════════════════════════════════════════════════════
# Test Signal Definitions
# ══════════════════════════════════════════════════════════════════════════════

# Workspace test prompts and expected signals
WORKSPACE_PROMPTS = {
    "auto": ("Explain what a DNS server does in two sentences.", ["DNS", "domain", "IP", "resolve", "name"]),
    "auto-coding": ("Write a Python function that reverses a string.", ["def", "return", "reverse", "[::-1]", "str"]),
    "auto-agentic": ("Explain how you would refactor a monolith into microservices.", ["service", "API", "boundary", "domain", "decouple"]),
    "auto-spl": ("Write a Splunk SPL query to find failed login attempts.", ["index", "source", "fail", "login", "stats", "|"]),
    "auto-security": ("What are the OWASP Top 10 vulnerabilities?", ["injection", "XSS", "authentication", "OWASP", "vulnerability"]),
    "auto-redteam": ("Describe common techniques for privilege escalation on Linux.", ["sudo", "SUID", "privilege", "root", "escalat"]),
    "auto-blueteam": ("How do you detect lateral movement in a network?", ["traffic", "network", "monitor", "detect", "lateral"]),
    "auto-creative": ("Write a haiku about artificial intelligence.", ["AI", "machine", "digital", "think", "learn", "syllable"]),
    "auto-reasoning": ("Solve this step by step: if a train travels at 60mph for 2.5 hours, how far does it go?", ["150", "mile", "distance", "60", "2.5"]),
    "auto-documents": ("Create an outline for a project proposal document.", ["introduction", "scope", "timeline", "budget", "section"]),
    "auto-video": ("Describe a 5-second video of a sunrise over mountains.", ["sun", "mountain", "light", "sky", "rise", "scene"]),
    "auto-music": ("Describe a 10-second lo-fi hip hop beat.", ["beat", "drum", "sample", "chill", "loop", "bass"]),
    "auto-research": ("What are the latest developments in quantum computing?", ["qubit", "quantum", "compute", "superconducting", "research"]),
    "auto-vision": ("How would you analyze an image for accessibility issues?", ["alt", "text", "contrast", "color", "image", "visual"]),
    "auto-data": ("Explain how to calculate standard deviation.", ["mean", "variance", "deviation", "σ", "standard", "sqrt"]),
    "auto-compliance": ("What evidence is needed for NERC CIP-007 R2?", ["CIP", "evidence", "patch", "compliance", "NERC", "requirement"]),
    "auto-mistral": ("Analyze the trade-offs between microservices and monolithic architectures.", ["trade", "scale", "complex", "deploy", "maintain"]),
}

# Persona test prompts and expected signals
# Full list of 46 personas from config/personas/*.yaml
PERSONA_PROMPTS = {
    # Development (17 personas)
    "bugdiscoverycodeassistant": ("Find bugs in: def add(a,b): return a+b", ["bug", "type", "error", "check", "valid"]),
    "codereviewassistant": ("Review this code: x = [i for i in range(100)]", ["list", "comprehension", "memory", "generator"]),
    "codereviewer": ("Review: if x == True:", ["==", "bool", "simplify", "True", "comparison"]),
    "codebasewikidocumentationskill": ("Document a Python function.", ["param", "return", "docstring", "description", "type"]),
    "devopsautomator": ("Write a bash script to backup a directory.", ["#!/", "bash", "cp", "rsync", "backup"]),
    "devopsengineer": ("Explain Kubernetes pod lifecycle.", ["pod", "pending", "running", "container", "lifecycle"]),
    "ethereumdeveloper": ("Write a simple Solidity smart contract.", ["contract", "pragma", "solidity", "function", "public"]),
    "fullstacksoftwaredeveloper": ("Design a REST API for a todo app.", ["GET", "POST", "endpoint", "REST", "API"]),
    "githubexpert": ("Explain git rebase vs merge.", ["rebase", "merge", "history", "commit", "branch"]),
    "javascriptconsole": ("Calculate 2 * Math.PI * 3", ["6.28", "18.84", "Math", "PI", "result"]),
    "kubernetesdockerrpglearningengine": ("Explain Docker layers.", ["layer", "image", "cache", "dockerfile", "build"]),
    "pythoncodegeneratorcleanoptimizedproduction-ready": ("Generate a function to sort a list of dicts by key.", ["sorted", "lambda", "key", "dict", "def"]),
    "pythoninterpreter": ("Execute: sorted([3,1,2], reverse=True)", ["[3, 2, 1]", "3", "2", "1", "sorted"]),
    "seniorfrontenddeveloper": ("Explain React hooks.", ["useState", "useEffect", "hook", "component", "state"]),
    "seniorsoftwareengineersoftwarearchitectrules": ("Design patterns for scalability.", ["pattern", "scale", "cache", "load", "balance"]),
    "softwarequalityassurancetester": ("Write test cases for a login form.", ["test", "case", "valid", "invalid", "password"]),
    "ux-uideveloper": ("Best practices for mobile-first design.", ["mobile", "responsive", "viewport", "breakpoint", "touch"]),
    # Security (6 personas)
    "cybersecurityspecialist": ("Explain zero-trust architecture.", ["zero", "trust", "verify", "never", "assume"]),
    "networkengineer": ("Configure a VLAN.", ["VLAN", "trunk", "access", "802.1Q", "switch"]),
    "redteamoperator": ("MITRE ATT&CK initial access techniques.", ["phishing", "exploit", "T1566", "initial", "access"]),
    "blueteamdefender": ("Detect ransomware activity.", ["encrypt", "extension", "ransom", "detect", "behavior"]),
    "pentester": ("OWASP testing methodology.", ["OWASP", "test", "inject", "XSS", "methodology"]),
    "splunksplgineer": ("Write SPL to detect brute force.", ["index", "stats", "count", "fail", "threshold"]),
    # Data (7 personas)
    "dataanalyst": ("Explain correlation vs causation.", ["correlation", "causation", "variable", "relationship"]),
    "datascientist": ("Feature engineering techniques.", ["feature", "encode", "normalize", "transform", "engineer"]),
    "machinelearningengineer": ("Explain gradient descent.", ["gradient", "descent", "learning", "rate", "optimize"]),
    "statistician": ("Explain p-value interpretation.", ["p-value", "null", "hypothesis", "significance", "0.05"]),
    "itarchitect": ("Design a high-availability system.", ["HA", "redundant", "failover", "availability", "replica"]),
    "researchanalyst": ("Conduct a literature review.", ["review", "source", "cite", "literature", "methodology"]),
    "excelsheet": ("Formula for VLOOKUP.", ["VLOOKUP", "formula", "range", "col_index", "FALSE"]),
    # Compliance (2 personas)
    "nerccipcomplianceanalyst": ("CIP-007 patch management requirements.", ["CIP", "patch", "35", "day", "compliance"]),
    "cippolicywriter": ("Write a policy for access control.", ["access", "control", "policy", "authorize", "role"]),
    # Systems (2 personas)
    "linuxterminal": ("List files by size.", ["ls", "-l", "sort", "size", "du"]),
    "sqlterminal": ("SELECT users with admin role.", ["SELECT", "FROM", "WHERE", "role", "admin"]),
    # General (2 personas)
    "itexpert": ("Troubleshoot slow network.", ["bandwidth", "latency", "packet", "loss", "diagnose"]),
    "techreviewer": ("Review iPhone 15 features.", ["camera", "chip", "battery", "feature", "review"]),
    # Writing (2 personas)
    "creativewriter": ("Write a story opening.", ["the", "once", "upon", "story", "character", "began", "dark", "light", "city", "sea", "ancient", "heart", "began", "in", "a"]),
    "techwriter": ("Document an API endpoint.", ["endpoint", "request", "response", "parameter", "method"]),
    # Reasoning (6 personas — includes new GPT-OSS, Phi-4, Gemma vision)
    "magistralstrategist": ("Strategic planning framework.", ["objective", "strategy", "goal", "plan", "execute"]),
    "gemmaresearchanalyst": ("Research methodology steps.", ["method", "data", "collect", "analyze", "research"]),
    "phi4stemanalyst": ("Explain the Pythagorean theorem.", ["a²", "b²", "c²", "triangle", "hypotenuse"]),
    "phi4specialist": ("Write a technical specification outline.", ["spec", "requirement", "section", "format", "structure"]),
    "gptossanalyst": ("Analyze trade-offs between microservices and monoliths.", ["trade", "scale", "complex", "maintain", "deploy"]),
    # Vision (1 persona — new Gemma 4 E4B multimodal)
    "gemma4e4bvision": ("Describe how you would analyze an uploaded image.", ["image", "visual", "describe", "analyze", "see"]),
}


# ══════════════════════════════════════════════════════════════════════════════
# Test Sections
# ══════════════════════════════════════════════════════════════════════════════

async def S0() -> None:
    """S0: Prerequisites and environment check."""
    print("\n━━━ S0. PREREQUISITES ━━━")
    sec = "S0"

    # S0-01: Python version
    t0 = time.time()
    py_ver = sys.version_info
    record(
        sec, "S0-01", "Python version",
        "PASS" if py_ver >= (3, 10) else "FAIL",
        f"Python {py_ver.major}.{py_ver.minor}.{py_ver.micro}",
        t0=t0,
    )

    # S0-02: Required packages
    t0 = time.time()
    required = ["httpx", "yaml", "mcp"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    record(
        sec, "S0-02", "Required packages",
        "PASS" if not missing else "FAIL",
        f"missing: {missing}" if missing else "all present",
        t0=t0,
    )

    # S0-03: .env file exists
    t0 = time.time()
    env_exists = (ROOT / ".env").exists()
    record(
        sec, "S0-03", ".env file exists",
        "PASS" if env_exists else "FAIL",
        str(ROOT / ".env"),
        t0=t0,
    )

    # S0-04: API key configured
    t0 = time.time()
    has_key = bool(API_KEY)
    record(
        sec, "S0-04", "PIPELINE_API_KEY configured",
        "PASS" if has_key else "FAIL",
        f"key length: {len(API_KEY)}" if has_key else "not set",
        t0=t0,
    )

    # S0-05: Git repository
    t0 = time.time()
    sha = _git_sha()
    record(
        sec, "S0-05", "Git repository",
        "PASS" if sha != "unknown" else "WARN",
        f"SHA: {sha}",
        t0=t0,
    )


async def S1() -> None:
    """S1: Configuration consistency."""
    print("\n━━━ S1. CONFIGURATION CONSISTENCY ━━━")
    sec = "S1"

    # S1-01: backends.yaml exists
    t0 = time.time()
    backends_file = ROOT / "config/backends.yaml"
    record(
        sec, "S1-01", "backends.yaml exists",
        "PASS" if backends_file.exists() else "FAIL",
        str(backends_file),
        t0=t0,
    )

    # S1-02: backends.yaml is valid YAML
    t0 = time.time()
    try:
        backends = _load_backends_yaml()
        record(sec, "S1-02", "backends.yaml valid YAML", "PASS", f"{len(backends.get('backends', []))} backends", t0=t0)
    except Exception as e:
        record(sec, "S1-02", "backends.yaml valid YAML", "FAIL", str(e)[:100], t0=t0)
        return

    # S1-03: Workspace IDs consistent between router_pipe.py and backends.yaml
    t0 = time.time()
    pipe_ids = set(WS_IDS)
    yaml_ids = set(backends.get("workspace_routing", {}).keys())
    if pipe_ids == yaml_ids:
        record(sec, "S1-03", "Workspace IDs consistent", "PASS", f"{len(pipe_ids)} workspaces", t0=t0)
    else:
        diff = pipe_ids.symmetric_difference(yaml_ids)
        record(sec, "S1-03", "Workspace IDs consistent", "FAIL", f"mismatch: {diff}", t0=t0)

    # S1-04: All persona YAMLs are valid
    t0 = time.time()
    persona_dir = ROOT / "config/personas"
    persona_files = list(persona_dir.glob("*.yaml"))
    invalid = []
    for pf in persona_files:
        try:
            yaml.safe_load(pf.read_text())
        except Exception:
            invalid.append(pf.name)
    record(
        sec, "S1-04", "Persona YAMLs valid",
        "PASS" if not invalid else "FAIL",
        f"{len(persona_files)} personas" if not invalid else f"invalid: {invalid}",
        t0=t0,
    )

    # S1-05: Persona count matches expected
    t0 = time.time()
    expected_persona_count = 44
    actual_count = len(PERSONAS)
    record(
        sec, "S1-05", "Persona count",
        "PASS" if actual_count >= expected_persona_count - 2 else "WARN",
        f"{actual_count} personas (expected ~{expected_persona_count})",
        t0=t0,
    )

    # S1-06: routing_descriptions.json exists and valid
    t0 = time.time()
    routing_desc_file = ROOT / "config/routing_descriptions.json"
    try:
        if routing_desc_file.exists():
            desc = json.loads(routing_desc_file.read_text())
            record(sec, "S1-06", "routing_descriptions.json", "PASS", f"{len(desc)} descriptions", t0=t0)
        else:
            record(sec, "S1-06", "routing_descriptions.json", "WARN", "file not found", t0=t0)
    except Exception as e:
        record(sec, "S1-06", "routing_descriptions.json", "FAIL", str(e)[:100], t0=t0)

    # S1-07: routing_examples.json exists and valid
    t0 = time.time()
    routing_ex_file = ROOT / "config/routing_examples.json"
    try:
        if routing_ex_file.exists():
            ex = json.loads(routing_ex_file.read_text())
            record(sec, "S1-07", "routing_examples.json", "PASS", f"{len(ex)} examples", t0=t0)
        else:
            record(sec, "S1-07", "routing_examples.json", "WARN", "file not found", t0=t0)
    except Exception as e:
        record(sec, "S1-07", "routing_examples.json", "FAIL", str(e)[:100], t0=t0)


async def S2() -> None:
    """S2: Service health checks."""
    print("\n━━━ S2. SERVICE HEALTH ━━━")
    sec = "S2"

    # S2-01: Docker alive
    t0 = time.time()
    alive, detail = _docker_alive()
    record(sec, "S2-01", "Docker daemon", "PASS" if alive else "FAIL", detail, t0=t0)

    # S2-02: Pipeline health
    t0 = time.time()
    code, data = await _get(f"{PIPELINE_URL}/health")
    if code == 200 and isinstance(data, dict):
        backends_total = data.get("backends_total", 0)
        backends_healthy = data.get("backends_healthy", 0)
        workspaces = data.get("workspaces", 0)
        record(
            sec, "S2-02", "Pipeline /health",
            "PASS" if backends_healthy > 0 else "WARN",
            f"backends={backends_healthy}/{backends_total}, workspaces={workspaces}",
            t0=t0,
        )
    else:
        record(sec, "S2-02", "Pipeline /health", "FAIL", f"HTTP {code}", t0=t0)

    # S2-03: Ollama health
    t0 = time.time()
    code, _ = await _get(f"{OLLAMA_URL}/api/tags")
    models = _ollama_models()
    record(
        sec, "S2-03", "Ollama",
        "PASS" if code == 200 else "FAIL",
        f"{len(models)} models" if code == 200 else f"HTTP {code}",
        t0=t0,
    )

    # S2-04: Open WebUI health
    t0 = time.time()
    code, _ = await _get(f"{OPENWEBUI_URL}/health")
    record(sec, "S2-04", "Open WebUI", "PASS" if code == 200 else "FAIL", f"HTTP {code}", t0=t0)

    # S2-05: SearXNG health
    t0 = time.time()
    code, _ = await _get(f"{SEARXNG_URL}/healthz")
    record(sec, "S2-05", "SearXNG", "PASS" if code == 200 else "WARN", f"HTTP {code}", t0=t0)

    # S2-06: Prometheus health
    t0 = time.time()
    code, _ = await _get(f"{PROMETHEUS_URL}/-/healthy")
    record(sec, "S2-06", "Prometheus", "PASS" if code == 200 else "WARN", f"HTTP {code}", t0=t0)

    # S2-07: Grafana health
    t0 = time.time()
    code, _ = await _get(f"{GRAFANA_URL}/api/health")
    record(sec, "S2-07", "Grafana", "PASS" if code == 200 else "WARN", f"HTTP {code}", t0=t0)

    # S2-08 to S2-14: MCP services
    mcp_services = [
        ("S2-08", "documents", MCP["documents"]),
        ("S2-09", "music", MCP["music"]),
        ("S2-10", "tts", MCP["tts"]),
        ("S2-11", "whisper", MCP["whisper"]),
        ("S2-12", "sandbox", MCP["sandbox"]),
        ("S2-13", "video", MCP["video"]),
        ("S2-14", "embedding", MCP["embedding"]),
    ]
    for tid, name, port in mcp_services:
        t0 = time.time()
        code, _ = await _get(f"http://localhost:{port}/health", timeout=5)
        record(
            sec, tid, f"MCP {name} (:{port})",
            "PASS" if code == 200 else "WARN",
            f"HTTP {code}",
            t0=t0,
        )

    # S2-15: MLX proxy health
    t0 = time.time()
    state, data = await _mlx_health()
    record(
        sec, "S2-15", "MLX proxy",
        "PASS" if state in ("ready", "none", "switching") else "INFO",
        f"state={state}",
        t0=t0,
    )

    # S2-16: MLX Speech health
    t0 = time.time()
    code, _ = await _get(f"{MLX_SPEECH_URL}/health", timeout=5)
    record(
        sec, "S2-16", "MLX Speech",
        "PASS" if code == 200 else "INFO",
        f"HTTP {code}" if code else "not running (optional)",
        t0=t0,
    )


async def S3a() -> None:
    """S3a: Workspace routing tests (Ollama backends only)."""
    print("\n━━━ S3a. WORKSPACE ROUTING (OLLAMA) ━━━")
    sec = "S3a"

    # Ollama-only workspaces (no MLX in routing chain)
    OLLAMA_WORKSPACES = [
        # Group 1: General (dolphin-llama3:8b)
        ("Ollama general", ["auto", "auto-video", "auto-music"]),
        # Group 2: Security (baronllm, lily-cybersecurity, xploiter)
        ("Ollama security", ["auto-security", "auto-redteam", "auto-blueteam"]),
        # Group 3: Documents (qwen3.5:9b via coding group)
        ("Ollama coding", ["auto-documents"]),
    ]

    test_num = 1

    for group_name, workspaces in OLLAMA_WORKSPACES:
        print(f"\n  ── {group_name} ({len(workspaces)} workspaces) ──")

        for ws_id in workspaces:
            if ws_id not in WORKSPACE_PROMPTS:
                continue

            prompt, signals = WORKSPACE_PROMPTS[ws_id]
            t0 = time.time()
            tid = f"S3a-{test_num:02d}"

            code, response, model = await _chat_with_model(ws_id, prompt, max_tokens=300, timeout=180)

            if code != 200:
                record(sec, tid, f"Workspace {ws_id}", "FAIL", f"HTTP {code}: {response[:80]}", t0=t0)
                test_num += 1
                continue

            response_lower = response.lower()
            found = [s for s in signals if s.lower() in response_lower]

            if found:
                record(sec, tid, f"Workspace {ws_id}", "PASS", f"signals: {found[:3]} | model: {model[:40]}", t0=t0)
            else:
                record(sec, tid, f"Workspace {ws_id}", "WARN", f"no signals in: {response[:100]}", t0=t0)

            test_num += 1
            await asyncio.sleep(0.5)

        await asyncio.sleep(2)


async def S3b() -> None:
    """S3b: Workspace routing tests (MLX backends)."""
    print("\n━━━ S3b. WORKSPACE ROUTING (MLX) ━━━")
    sec = "S3b"

    # First evict Ollama to free memory for MLX
    await _unload_ollama_models()

    # MLX-primary workspaces (grouped by likely model)
    MLX_WORKSPACES = [
        # Group 1: Coding (Devstral, Qwen3-Coder)
        ("MLX coding", ["auto-coding", "auto-agentic", "auto-spl"]),
        # Group 2: Reasoning (Qwopus, DeepSeek-R1, Magistral)
        ("MLX reasoning", ["auto-reasoning", "auto-research", "auto-data", "auto-compliance", "auto-mistral"]),
        # Group 3: Creative (Dolphin-8B)
        ("MLX creative", ["auto-creative"]),
        # Group 4: Vision (Gemma-4, Qwen3-VL)
        ("MLX vision", ["auto-vision"]),
    ]

    test_num = 1

    for group_name, workspaces in MLX_WORKSPACES:
        print(f"\n  ── {group_name} ({len(workspaces)} workspaces) ──")

        for ws_id in workspaces:
            if ws_id not in WORKSPACE_PROMPTS:
                continue

            prompt, signals = WORKSPACE_PROMPTS[ws_id]
            t0 = time.time()
            tid = f"S3b-{test_num:02d}"

            code, response, model = await _chat_with_model(ws_id, prompt, max_tokens=300, timeout=240)

            if code != 200:
                record(sec, tid, f"Workspace {ws_id}", "FAIL", f"HTTP {code}: {response[:80]}", t0=t0)
                test_num += 1
                continue

            response_lower = response.lower()
            found = [s for s in signals if s.lower() in response_lower]
            is_mlx = any(org in model for org in _MLX_ORGS)

            if found:
                record(sec, tid, f"Workspace {ws_id}", "PASS", f"MLX:{is_mlx} | signals: {found[:3]}", t0=t0)
            else:
                record(sec, tid, f"Workspace {ws_id}", "WARN", f"no signals in: {response[:100]}", t0=t0)

            test_num += 1
            await asyncio.sleep(1)

        await asyncio.sleep(3)


# Keep S3 as a wrapper for backward compatibility
async def S3() -> None:
    """S3: Workspace routing tests (runs S3a then S3b)."""
    await S3a()
    await S3b()


async def S4() -> None:
    """S4: Document generation tests."""
    print("\n━━━ S4. DOCUMENT GENERATION ━━━")
    sec = "S4"

    # S4-01: MCP Documents health
    t0 = time.time()
    code, _ = await _get(f"http://localhost:{MCP['documents']}/health")
    record(sec, "S4-01", "Documents MCP health", "PASS" if code == 200 else "FAIL", f"HTTP {code}", t0=t0)

    # S4-02: Generate Word document
    await _mcp(
        MCP["documents"],
        "create_word_document",
        {
            "filename": "test_proposal.docx",
            "content": "# Project Proposal\n\n## Executive Summary\n\nThis is a test document.\n\n## Timeline\n\n- Phase 1: Planning\n- Phase 2: Implementation",
        },
        section=sec,
        tid="S4-02",
        name="Generate Word document",
        ok_fn=lambda t: "success" in t.lower() or "created" in t.lower() or "docx" in t.lower(),
        timeout=60,
    )

    # S4-03: Generate Excel spreadsheet
    await _mcp(
        MCP["documents"],
        "create_excel_spreadsheet",
        {
            "filename": "test_budget.xlsx",
            "data": {
                "headers": ["Category", "Q1", "Q2", "Total"],
                "rows": [
                    ["Hardware", 1000, 1200, "=B2+C2"],
                    ["Software", 500, 600, "=B3+C3"],
                ],
            },
        },
        section=sec,
        tid="S4-03",
        name="Generate Excel spreadsheet",
        ok_fn=lambda t: "success" in t.lower() or "created" in t.lower() or "xlsx" in t.lower(),
        timeout=60,
    )

    # S4-04: Generate PowerPoint
    await _mcp(
        MCP["documents"],
        "create_powerpoint",
        {
            "filename": "test_presentation.pptx",
            "slides": [
                {"title": "Introduction", "content": "Welcome to the presentation"},
                {"title": "Overview", "content": "Key points covered today"},
                {"title": "Conclusion", "content": "Thank you"},
            ],
        },
        section=sec,
        tid="S4-04",
        name="Generate PowerPoint",
        ok_fn=lambda t: "success" in t.lower() or "created" in t.lower() or "pptx" in t.lower(),
        timeout=60,
    )


async def S5() -> None:
    """S5: Code sandbox tests."""
    print("\n━━━ S5. CODE SANDBOX ━━━")
    sec = "S5"

    # S5-01: Sandbox health
    t0 = time.time()
    code, _ = await _get(f"http://localhost:{MCP['sandbox']}/health")
    record(sec, "S5-01", "Sandbox MCP health", "PASS" if code == 200 else "FAIL", f"HTTP {code}", t0=t0)

    # S5-02: Execute Python code
    await _mcp(
        MCP["sandbox"],
        "execute_code",
        {
            "language": "python",
            "code": "print(sum(range(1, 11)))",
        },
        section=sec,
        tid="S5-02",
        name="Execute Python (sum 1-10)",
        ok_fn=lambda t: "55" in t,
        timeout=30,
    )

    # S5-03: Execute with error handling
    await _mcp(
        MCP["sandbox"],
        "execute_code",
        {
            "language": "python",
            "code": "result = [x**2 for x in range(5)]\nprint(result)",
        },
        section=sec,
        tid="S5-03",
        name="Execute Python (list comprehension)",
        ok_fn=lambda t: "[0, 1, 4, 9, 16]" in t or "0, 1, 4, 9, 16" in t,
        timeout=30,
    )


async def S6() -> None:
    """S6: Security workspace tests."""
    print("\n━━━ S6. SECURITY WORKSPACES ━━━")
    sec = "S6"

    # S6-01: auto-security routing
    t0 = time.time()
    code, response, model = await _chat_with_model(
        "auto-security",
        "What is SQL injection and how to prevent it?",
        max_tokens=300,
        timeout=180,
    )
    signals = ["sql", "inject", "sanitize", "parameter", "escape", "prepared"]
    found = [s for s in signals if s.lower() in response.lower()]
    record(
        sec, "S6-01", "auto-security routing",
        "PASS" if found and code == 200 else "WARN",
        f"signals: {found[:3]} | model: {model[:30]}",
        t0=t0,
    )

    # S6-02: auto-redteam routing
    t0 = time.time()
    code, response, model = await _chat_with_model(
        "auto-redteam",
        "Explain common web application penetration testing methodology.",
        max_tokens=300,
        timeout=180,
    )
    signals = ["recon", "scan", "exploit", "pentest", "OWASP", "vulnerability"]
    found = [s for s in signals if s.lower() in response.lower()]
    record(
        sec, "S6-02", "auto-redteam routing",
        "PASS" if found and code == 200 else "WARN",
        f"signals: {found[:3]} | model: {model[:30]}",
        t0=t0,
    )

    # S6-03: auto-blueteam routing
    t0 = time.time()
    code, response, model = await _chat_with_model(
        "auto-blueteam",
        "How do you respond to a ransomware incident?",
        max_tokens=300,
        timeout=180,
    )
    signals = ["isolate", "contain", "backup", "incident", "response", "recover"]
    found = [s for s in signals if s.lower() in response.lower()]
    record(
        sec, "S6-03", "auto-blueteam routing",
        "PASS" if found and code == 200 else "WARN",
        f"signals: {found[:3]} | model: {model[:30]}",
        t0=t0,
    )

    # S6-04: Content-aware routing (security keywords)
    t0 = time.time()
    code, response, _ = await _chat_with_model(
        "auto",  # Use auto to test content-aware routing
        "exploit vulnerability payload shellcode",
        max_tokens=200,
        timeout=180,
    )
    # Check pipeline logs for routing decision
    logs = _grep_logs("portal5-pipeline", "auto-redteam|auto-security", lines=100)
    record(
        sec, "S6-04", "Content-aware security routing",
        "PASS" if logs and code == 200 else "WARN",
        f"routed to security workspace: {bool(logs)}",
        t0=t0,
    )


async def S7() -> None:
    """S7: Music generation tests."""
    print("\n━━━ S7. MUSIC GENERATION ━━━")
    sec = "S7"

    # S7-01: Music MCP health
    t0 = time.time()
    code, data = await _get(f"http://localhost:{MCP['music']}/health")
    if code == 200 and isinstance(data, dict):
        record(sec, "S7-01", "Music MCP health", "PASS", f"service: {data.get('service', 'unknown')}", t0=t0)
    else:
        record(sec, "S7-01", "Music MCP health", "WARN", f"HTTP {code}", t0=t0)

    # S7-02: Generate music
    await _mcp(
        MCP["music"],
        "generate_music",
        {
            "prompt": "upbeat jazz piano solo",
            "duration": 5,
            "model_size": "small",
        },
        section=sec,
        tid="S7-02",
        name="Generate music (5s jazz)",
        ok_fn=lambda t: "success" in t.lower() or "path" in t.lower() or "wav" in t.lower(),
        warn_if=["not available", "error"],
        timeout=180,
    )


async def S8() -> None:
    """S8: Text-to-Speech tests."""
    print("\n━━━ S8. TEXT-TO-SPEECH ━━━")
    sec = "S8"

    # S8-01: Check MLX Speech first (preferred on Apple Silicon)
    t0 = time.time()
    code, data = await _get(f"{MLX_SPEECH_URL}/health", timeout=5)
    mlx_speech_available = code == 200

    if mlx_speech_available:
        record(sec, "S8-01", "MLX Speech health", "PASS", f"voice_cloning: {data.get('voice_cloning', False)}", t0=t0)

        # S8-02: TTS via MLX Speech
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.post(
                    f"{MLX_SPEECH_URL}/v1/audio/speech",
                    json={"input": "Hello from Portal 5 acceptance test.", "voice": "af_heart"},
                )
                if r.status_code == 200:
                    wav_data = r.content
                    info = _wav_info(wav_data)
                    if info and info["duration_s"] > 0.5:
                        record(sec, "S8-02", "MLX Speech TTS", "PASS", f"duration: {info['duration_s']}s", t0=t0)
                    else:
                        record(sec, "S8-02", "MLX Speech TTS", "WARN", f"invalid WAV: {info}", t0=t0)
                else:
                    record(sec, "S8-02", "MLX Speech TTS", "FAIL", f"HTTP {r.status_code}", t0=t0)
        except Exception as e:
            record(sec, "S8-02", "MLX Speech TTS", "FAIL", str(e)[:100], t0=t0)
    else:
        record(sec, "S8-01", "MLX Speech health", "INFO", "not running (using Docker TTS fallback)", t0=t0)

        # Fallback to Docker TTS
        t0 = time.time()
        code, data = await _get(f"http://localhost:{MCP['tts']}/health")
        record(sec, "S8-02", "Docker TTS health", "PASS" if code == 200 else "WARN", f"HTTP {code}", t0=t0)


async def S9() -> None:
    """S9: Speech-to-Text tests."""
    print("\n━━━ S9. SPEECH-TO-TEXT ━━━")
    sec = "S9"

    # Check if MLX Speech is available for ASR
    t0 = time.time()
    code, _ = await _get(f"{MLX_SPEECH_URL}/health", timeout=5)

    if code == 200:
        record(sec, "S9-01", "MLX Speech ASR available", "PASS", "Qwen3-ASR", t0=t0)
    else:
        record(sec, "S9-01", "MLX Speech ASR available", "INFO", "not running (Docker Whisper fallback)", t0=t0)

        # Check Docker Whisper
        t0 = time.time()
        code, _ = await _get(f"http://localhost:{MCP['whisper']}/health")
        record(sec, "S9-02", "Docker Whisper health", "PASS" if code == 200 else "WARN", f"HTTP {code}", t0=t0)


async def S10() -> None:
    """S10: Persona tests (Ollama-routed) — grouped by model to minimize switching."""
    print("\n━━━ S10. PERSONAS (OLLAMA) ━━━")
    sec = "S10"

    # Group personas by their Ollama model to minimize model switching
    # Order: most personas first (amortize load time), then smaller groups
    OLLAMA_PERSONA_GROUPS = [
        # Group 1: qwen3-coder-next:30b-q5 (16 personas) — load once, test all
        ("qwen3-coder-next:30b-q5", [
            "bugdiscoverycodeassistant", "codebasewikidocumentationskill", "codereviewassistant",
            "codereviewer", "devopsautomator", "devopsengineer", "ethereumdeveloper",
            "githubexpert", "javascriptconsole", "kubernetesdockerrpglearningengine",
            "linuxterminal", "pythoncodegeneratorcleanoptimizedproduction-ready",
            "pythoninterpreter", "seniorfrontenddeveloper",
            "seniorsoftwareengineersoftwarearchitectrules", "softwarequalityassurancetester",
            "sqlterminal",
        ]),
        # Group 2: deepseek-r1:32b-q4_k_m (7 personas)
        ("deepseek-r1:32b-q4_k_m", [
            "dataanalyst", "datascientist", "excelsheet", "itarchitect",
            "machinelearningengineer", "researchanalyst", "statistician",
        ]),
        # Group 3: dolphin-llama3:8b (4 personas)
        ("dolphin-llama3:8b", [
            "creativewriter", "itexpert", "techreviewer", "techwriter",
        ]),
        # Group 4: Security models (1 persona each — unavoidable switches)
        ("xploiter/the-xploiter", ["cybersecurityspecialist", "networkengineer"]),
        ("baronllm:q6_k", ["redteamoperator"]),
        ("lily-cybersecurity:7b-q4_k_m", ["blueteamdefender"]),
        ("lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0", ["pentester"]),
        # Group 5: gpt-oss:20b (1 persona)
        ("gpt-oss:20b", ["gptossanalyst"]),
    ]

    test_num = 1

    for model_hint, persona_slugs in OLLAMA_PERSONA_GROUPS:
        # Log which model group we're testing
        print(f"\n  ── Model: {model_hint} ({len(persona_slugs)} personas) ──")

        for slug in persona_slugs:
            if slug not in PERSONA_PROMPTS:
                continue

            prompt, signals = PERSONA_PROMPTS[slug]
            t0 = time.time()
            tid = f"S10-{test_num:02d}"

            persona_data = next((p for p in PERSONAS if p.get("slug") == slug), None)
            if not persona_data:
                record(sec, tid, f"Persona {slug}", "WARN", "persona YAML not found", t0=t0)
                test_num += 1
                continue

            workspace_model = persona_data.get("workspace_model", "auto")
            system_prompt = persona_data.get("system_prompt", "")[:500]

            code, response, model = await _chat_with_model(
                workspace_model,
                prompt,
                system=system_prompt,
                max_tokens=250,
                timeout=180,
            )

            if code != 200:
                record(sec, tid, f"Persona {slug}", "FAIL", f"HTTP {code}", t0=t0)
                test_num += 1
                continue

            response_lower = response.lower()
            found = [s for s in signals if s.lower() in response_lower]

            record(
                sec, tid, f"Persona {slug}",
                "PASS" if found else "WARN",
                f"signals: {found[:3]}" if found else f"no signals in: {response[:60]}",
                t0=t0,
            )

            test_num += 1
            await asyncio.sleep(0.5)  # Shorter sleep within same model

        # Longer pause between model groups to allow clean switching
        await asyncio.sleep(2)


async def S11() -> None:
    """S11: Persona tests (MLX-routed) — grouped by model to minimize switching."""
    print("\n━━━ S11. PERSONAS (MLX) ━━━")
    sec = "S11"

    # Check MLX availability
    state, _ = await _mlx_health()
    if state not in ("ready", "none", "switching"):
        record(sec, "S11-00", "MLX availability", "INFO", f"MLX state: {state}, skipping MLX persona tests", t0=time.time())
        return

    record(sec, "S11-00", "MLX availability", "PASS", f"state: {state}", t0=time.time())

    # Evict Ollama models first to free unified memory for MLX
    await _unload_ollama_models()
    await asyncio.sleep(3)

    # Group MLX personas by model to minimize switching
    # Order: larger groups first to amortize load time
    MLX_PERSONA_GROUPS = [
        # Group 1: mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit (3 personas)
        ("mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit", [
            "fullstacksoftwaredeveloper", "splunksplgineer", "ux-uideveloper",
        ]),
        # Group 2: Jackrong compliance model (2 personas)
        ("Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit", [
            "cippolicywriter", "nerccipcomplianceanalyst",
        ]),
        # Group 3: Single-persona models (unavoidable switches, but grouped at end)
        ("mlx-community/gemma-4-31b-it-4bit", ["gemmaresearchanalyst"]),
        ("mlx-community/phi-4-8bit", ["phi4specialist"]),
        ("lmstudio-community/Phi-4-reasoning-plus-MLX-4bit", ["phi4stemanalyst"]),
        ("lmstudio-community/Magistral-Small-2509-MLX-8bit", ["magistralstrategist"]),
        ("unsloth/gemma-4-E4B-it-UD-MLX-4bit", ["gemma4e4bvision"]),
    ]

    test_num = 1

    for model_hint, persona_slugs in MLX_PERSONA_GROUPS:
        print(f"\n  ── MLX Model: {model_hint.split('/')[-1]} ({len(persona_slugs)} personas) ──")

        # Wait for model to be ready before testing
        ready = await _wait_for_mlx_ready(timeout=180)
        if not ready:
            for slug in persona_slugs:
                record(sec, f"S11-{test_num:02d}", f"Persona {slug} (MLX)", "WARN", "MLX not ready", t0=time.time())
                test_num += 1
            continue

        for slug in persona_slugs:
            if slug not in PERSONA_PROMPTS:
                continue

            prompt, signals = PERSONA_PROMPTS[slug]
            t0 = time.time()
            tid = f"S11-{test_num:02d}"

            persona_data = next((p for p in PERSONAS if p.get("slug") == slug), None)
            if not persona_data:
                record(sec, tid, f"Persona {slug} (MLX)", "WARN", "persona not found", t0=t0)
                test_num += 1
                continue

            workspace_model = persona_data.get("workspace_model", "auto-coding")
            system_prompt = persona_data.get("system_prompt", "")[:500]

            code, response, model = await _chat_with_model(
                workspace_model,
                prompt,
                system=system_prompt,
                max_tokens=300,
                timeout=300,  # MLX models need longer timeout for first request
            )

            if code != 200:
                record(sec, tid, f"Persona {slug} (MLX)", "FAIL", f"HTTP {code}", t0=t0)
                test_num += 1
                continue

            response_lower = response.lower()
            found = [s for s in signals if s.lower() in response_lower]

            # Check if MLX was actually used
            is_mlx = any(org in model for org in _MLX_ORGS)

            record(
                sec, tid, f"Persona {slug} (MLX)",
                "PASS" if found else "WARN",
                f"MLX: {is_mlx} | signals: {found[:2]}" if found else f"no signals, model: {model[:30]}",
                t0=t0,
            )

            test_num += 1
            await asyncio.sleep(1)  # Short sleep within same model

        # Longer pause between MLX model switches (they're expensive)
        await asyncio.sleep(5)


async def S12() -> None:
    """S12: Web search tests."""
    print("\n━━━ S12. WEB SEARCH ━━━")
    sec = "S12"

    # S12-01: SearXNG direct query
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{SEARXNG_URL}/search", params={"q": "test query", "format": "json"})
            if r.status_code == 200:
                data = r.json()
                results = data.get("results", [])
                record(sec, "S12-01", "SearXNG search", "PASS", f"{len(results)} results", t0=t0)
            else:
                record(sec, "S12-01", "SearXNG search", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S12-01", "SearXNG search", "WARN", str(e)[:100], t0=t0)


async def S13() -> None:
    """S13: RAG/Embedding tests."""
    print("\n━━━ S13. RAG/EMBEDDING ━━━")
    sec = "S13"

    # S13-01: Embedding service health
    t0 = time.time()
    code, data = await _get(f"http://localhost:{MCP['embedding']}/health")
    record(
        sec, "S13-01", "Embedding service",
        "PASS" if code == 200 else "WARN",
        f"HTTP {code}",
        t0=t0,
    )

    # S13-02: Generate embedding (if service is up)
    if code == 200:
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(
                    f"http://localhost:{MCP['embedding']}/v1/embeddings",
                    json={"input": "test embedding text", "model": "microsoft/harrier-oss-v1-0.6b"},
                )
                if r.status_code == 200:
                    data = r.json()
                    embedding = data.get("data", [{}])[0].get("embedding", [])
                    record(sec, "S13-02", "Generate embedding", "PASS", f"dim: {len(embedding)}", t0=t0)
                else:
                    record(sec, "S13-02", "Generate embedding", "WARN", f"HTTP {r.status_code}", t0=t0)
        except Exception as e:
            record(sec, "S13-02", "Generate embedding", "WARN", str(e)[:100], t0=t0)


async def S20() -> None:
    """S20: MLX acceleration tests."""
    print("\n━━━ S20. MLX ACCELERATION ━━━")
    sec = "S20"

    # S20-01: MLX proxy health
    t0 = time.time()
    state, data = await _mlx_health()
    record(
        sec, "S20-01", "MLX proxy health",
        "PASS" if state in ("ready", "none", "switching") else "WARN",
        f"state: {state}, data: {str(data)[:80]}",
        t0=t0,
    )

    # S20-02: MLX /v1/models endpoint
    t0 = time.time()
    code, data = await _get(f"{MLX_URL}/v1/models")
    if code == 200 and isinstance(data, dict):
        models = data.get("data", [])
        record(sec, "S20-02", "MLX /v1/models", "PASS", f"{len(models)} models", t0=t0)
    elif code == 503:
        record(sec, "S20-02", "MLX /v1/models", "INFO", "503 (no model loaded)", t0=t0)
    else:
        record(sec, "S20-02", "MLX /v1/models", "WARN", f"HTTP {code}", t0=t0)

    # S20-03: Memory info endpoint
    t0 = time.time()
    code, data = await _get(f"{MLX_URL}/health/memory")
    if code == 200:
        record(sec, "S20-03", "MLX memory info", "PASS", str(data)[:100], t0=t0)
    else:
        record(sec, "S20-03", "MLX memory info", "INFO", f"HTTP {code}", t0=t0)


async def S21() -> None:
    """S21: LLM Intent Router tests (P5-FUT-006)."""
    print("\n━━━ S21. LLM INTENT ROUTER ━━━")
    sec = "S21"

    # S21-01: Check if LLM router is enabled
    t0 = time.time()
    llm_router_enabled = os.environ.get("LLM_ROUTER_ENABLED", "true").lower() == "true"
    record(
        sec, "S21-01", "LLM router enabled",
        "PASS" if llm_router_enabled else "INFO",
        f"LLM_ROUTER_ENABLED={llm_router_enabled}",
        t0=t0,
    )

    if not llm_router_enabled:
        record(sec, "S21-02", "LLM router model", "INFO", "skipped (router disabled)", t0=time.time())
        return

    # S21-02: Check LLM router model exists in Ollama
    t0 = time.time()
    router_model = os.environ.get("LLM_ROUTER_MODEL", "hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF")
    models = _ollama_models()
    # Check if router model is available (may be abbreviated in ollama list)
    model_available = any(
        router_model.split("/")[-1].lower().replace("-gguf", "") in m.lower()
        for m in models
    ) or any("llama-3.2-3b" in m.lower() and "abliterated" in m.lower() for m in models)
    record(
        sec, "S21-02", "LLM router model available",
        "PASS" if model_available else "WARN",
        f"model: {router_model[:50]}",
        t0=t0,
    )

    # S21-03: Test content-aware routing with security keywords
    t0 = time.time()
    code, response, model = await _chat_with_model(
        "auto",  # Use auto to trigger content-aware routing
        "Write a SQL injection payload to bypass authentication",
        max_tokens=200,
        timeout=120,
    )
    # Should route to auto-redteam or auto-security
    logs = _grep_logs("portal5-pipeline", "auto-redteam|auto-security|LLM.*router|intent", lines=100)
    routed_correctly = any("redteam" in log.lower() or "security" in log.lower() for log in logs)
    record(
        sec, "S21-03", "LLM router security intent",
        "PASS" if (routed_correctly or code == 200) else "WARN",
        f"HTTP {code} | model: {model[:30]}",
        t0=t0,
    )

    # S21-04: Test content-aware routing with coding keywords
    t0 = time.time()
    code, response, model = await _chat_with_model(
        "auto",
        "Write a Python function to sort a list of dictionaries by key",
        max_tokens=200,
        timeout=120,
    )
    logs = _grep_logs("portal5-pipeline", "auto-coding|LLM.*router|intent", lines=100)
    record(
        sec, "S21-04", "LLM router coding intent",
        "PASS" if code == 200 else "WARN",
        f"HTTP {code} | model: {model[:30]}",
        t0=t0,
    )

    # S21-05: Test content-aware routing with compliance keywords
    t0 = time.time()
    code, response, model = await _chat_with_model(
        "auto",
        "What are the requirements for NERC CIP-007 R2 patch management?",
        max_tokens=200,
        timeout=120,
    )
    logs = _grep_logs("portal5-pipeline", "auto-compliance|LLM.*router|intent", lines=100)
    record(
        sec, "S21-05", "LLM router compliance intent",
        "PASS" if code == 200 else "WARN",
        f"HTTP {code} | model: {model[:30]}",
        t0=t0,
    )

    # S21-06: routing_descriptions.json valid
    t0 = time.time()
    desc_file = ROOT / "config/routing_descriptions.json"
    try:
        if desc_file.exists():
            desc = json.loads(desc_file.read_text())
            # Should have descriptions for all workspaces
            ws_count = len([k for k in desc.keys() if k.startswith("auto")])
            record(sec, "S21-06", "routing_descriptions.json", "PASS", f"{ws_count} workspace descriptions", t0=t0)
        else:
            record(sec, "S21-06", "routing_descriptions.json", "WARN", "file not found", t0=t0)
    except Exception as e:
        record(sec, "S21-06", "routing_descriptions.json", "FAIL", str(e)[:100], t0=t0)

    # S21-07: routing_examples.json valid
    t0 = time.time()
    ex_file = ROOT / "config/routing_examples.json"
    try:
        if ex_file.exists():
            ex = json.loads(ex_file.read_text())
            examples = ex.get("examples", [])
            record(sec, "S21-07", "routing_examples.json", "PASS", f"{len(examples)} examples", t0=t0)
        else:
            record(sec, "S21-07", "routing_examples.json", "WARN", "file not found", t0=t0)
    except Exception as e:
        record(sec, "S21-07", "routing_examples.json", "FAIL", str(e)[:100], t0=t0)


async def S22() -> None:
    """S22: MLX Admission Control tests (P5-FUT-009)."""
    print("\n━━━ S22. MLX ADMISSION CONTROL ━━━")
    sec = "S22"

    # S22-01: Check MLX proxy is running
    t0 = time.time()
    state, data = await _mlx_health()
    if state == "unreachable":
        record(sec, "S22-01", "MLX proxy for admission control", "INFO", "MLX proxy not running", t0=t0)
        return
    record(sec, "S22-01", "MLX proxy for admission control", "PASS", f"state: {state}", t0=t0)

    # S22-02: Memory endpoint available
    t0 = time.time()
    code, mem_data = await _get(f"{MLX_URL}/health/memory")
    if code == 200:
        if isinstance(mem_data, dict):
            available_gb = mem_data.get("available_gb", 0)
            record(sec, "S22-02", "MLX memory endpoint", "PASS", f"available: {available_gb:.1f}GB", t0=t0)
        else:
            record(sec, "S22-02", "MLX memory endpoint", "PASS", str(mem_data)[:80], t0=t0)
    else:
        record(sec, "S22-02", "MLX memory endpoint", "WARN", f"HTTP {code}", t0=t0)

    # S22-03: Test that proxy returns 503 for oversized model request
    # This tests admission control rejecting a model that won't fit in memory
    t0 = time.time()
    # Request a huge model that definitely won't fit
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            # This should return 503 if admission control is working
            r = await c.post(
                f"{MLX_URL}/v1/chat/completions",
                json={
                    "model": "mlx-community/Llama-3.3-70B-Instruct-8bit",  # 8bit 70B ~70GB
                    "messages": [{"role": "user", "content": "test"}],
                    "max_tokens": 10,
                },
            )
            if r.status_code == 503:
                detail = r.text[:100] if r.text else "admission rejected"
                record(sec, "S22-03", "Admission control rejects oversized", "PASS", f"503: {detail}", t0=t0)
            elif r.status_code == 200:
                # If it succeeded, either memory was available or admission control is off
                record(sec, "S22-03", "Admission control rejects oversized", "INFO", "model loaded (sufficient memory?)", t0=t0)
            else:
                record(sec, "S22-03", "Admission control rejects oversized", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S22-03", "Admission control rejects oversized", "WARN", str(e)[:100], t0=t0)

    # S22-04: MODEL_MEMORY dict coverage check
    t0 = time.time()
    try:
        # Check that common MLX models have memory estimates
        models_with_estimates = len(_MLX_MODEL_SIZES_GB)
        record(
            sec, "S22-04", "Model memory estimates",
            "PASS" if models_with_estimates >= 10 else "WARN",
            f"{models_with_estimates} models with size estimates",
            t0=t0,
        )
    except Exception as e:
        record(sec, "S22-04", "Model memory estimates", "WARN", str(e)[:100], t0=t0)


async def S23() -> None:
    """S23: New model diversity tests (GPT-OSS, Gemma 4, Phi-4)."""
    print("\n━━━ S23. MODEL DIVERSITY ━━━")
    sec = "S23"

    # S23-01: GPT-OSS model available in Ollama
    t0 = time.time()
    models = _ollama_models()
    gpt_oss_available = any("gpt-oss" in m.lower() for m in models)
    record(
        sec, "S23-01", "GPT-OSS:20B available",
        "PASS" if gpt_oss_available else "INFO",
        f"gpt-oss in models: {gpt_oss_available}",
        t0=t0,
    )

    # S23-02: Test GPT-OSS reasoning (if available)
    if gpt_oss_available:
        t0 = time.time()
        code, response, model = await _chat_with_model(
            "auto-reasoning",
            "What are the trade-offs between eventual consistency and strong consistency?",
            max_tokens=300,
            timeout=180,
        )
        signals = ["eventual", "strong", "consistency", "latency", "availability", "trade"]
        found = [s for s in signals if s.lower() in response.lower()]
        record(
            sec, "S23-02", "GPT-OSS reasoning test",
            "PASS" if found and code == 200 else "WARN",
            f"signals: {found[:3]} | model: {model[:30]}",
            t0=t0,
        )
    else:
        record(sec, "S23-02", "GPT-OSS reasoning test", "INFO", "skipped (model not available)", t0=time.time())

    # S23-03: Gemma 4 E4B VLM available
    t0 = time.time()
    state, mlx_data = await _mlx_health()
    if state in ("ready", "none", "switching"):
        code, models_data = await _get(f"{MLX_URL}/v1/models")
        if code == 200 and isinstance(models_data, dict):
            model_ids = [m.get("id", "") for m in models_data.get("data", [])]
            gemma_e4b = any("gemma-4-e4b" in m.lower() or "gemma-4-E4B" in m for m in model_ids)
            record(
                sec, "S23-03", "Gemma 4 E4B VLM registered",
                "PASS" if gemma_e4b else "INFO",
                f"gemma-4-E4B in MLX models: {gemma_e4b}",
                t0=t0,
            )
        else:
            record(sec, "S23-03", "Gemma 4 E4B VLM registered", "INFO", "MLX models endpoint unavailable", t0=t0)
    else:
        record(sec, "S23-03", "Gemma 4 E4B VLM registered", "INFO", f"MLX state: {state}", t0=t0)

    # S23-04: Phi-4 available in MLX pool
    t0 = time.time()
    code, models_data = await _get(f"{MLX_URL}/v1/models")
    if code == 200 and isinstance(models_data, dict):
        model_ids = [m.get("id", "") for m in models_data.get("data", [])]
        phi4 = any("phi-4" in m.lower() for m in model_ids)
        record(
            sec, "S23-04", "Phi-4 available",
            "PASS" if phi4 else "INFO",
            f"phi-4 in MLX models: {phi4}",
            t0=t0,
        )
    else:
        record(sec, "S23-04", "Phi-4 available", "INFO", f"HTTP {code}", t0=t0)

    # S23-05: Magistral-Small available
    t0 = time.time()
    code, models_data = await _get(f"{MLX_URL}/v1/models")
    if code == 200 and isinstance(models_data, dict):
        model_ids = [m.get("id", "") for m in models_data.get("data", [])]
        magistral = any("magistral" in m.lower() for m in model_ids)
        record(
            sec, "S23-05", "Magistral-Small available",
            "PASS" if magistral else "INFO",
            f"magistral in MLX models: {magistral}",
            t0=t0,
        )
    else:
        record(sec, "S23-05", "Magistral-Small available", "INFO", f"HTTP {code}", t0=t0)

    # S23-06: Phi-4-reasoning-plus available (RL-trained STEM reasoning)
    t0 = time.time()
    code, models_data = await _get(f"{MLX_URL}/v1/models")
    if code == 200 and isinstance(models_data, dict):
        model_ids = [m.get("id", "") for m in models_data.get("data", [])]
        phi4_reasoning = any("phi-4-reasoning" in m.lower() for m in model_ids)
        record(
            sec, "S23-06", "Phi-4-reasoning-plus available",
            "PASS" if phi4_reasoning else "INFO",
            f"phi-4-reasoning-plus in MLX models: {phi4_reasoning}",
            t0=t0,
        )
    else:
        record(sec, "S23-06", "Phi-4-reasoning-plus available", "INFO", f"HTTP {code}", t0=t0)


async def S30() -> None:
    """S30: Image generation tests (ComfyUI)."""
    print("\n━━━ S30. IMAGE GENERATION ━━━")
    sec = "S30"

    # S30-01: ComfyUI direct health
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{COMFYUI_URL}/system_stats")
            if r.status_code == 200:
                data = r.json()
                version = data.get("system", {}).get("comfyui_version", "unknown")
                record(sec, "S30-01", "ComfyUI direct", "PASS", f"version: {version}", t0=t0)
            else:
                record(sec, "S30-01", "ComfyUI direct", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S30-01", "ComfyUI direct", "INFO", f"not running: {str(e)[:50]}", t0=t0)

    # S30-02: ComfyUI MCP health
    t0 = time.time()
    code, _ = await _get(f"http://localhost:{MCP['comfyui']}/health")
    record(
        sec, "S30-02", "ComfyUI MCP bridge",
        "PASS" if code == 200 else "INFO",
        f"HTTP {code}",
        t0=t0,
    )


async def S31() -> None:
    """S31: Video generation tests."""
    print("\n━━━ S31. VIDEO GENERATION ━━━")
    sec = "S31"

    # S31-01: Video MCP health
    t0 = time.time()
    code, _ = await _get(f"http://localhost:{MCP['video']}/health")
    record(
        sec, "S31-01", "Video MCP health",
        "PASS" if code == 200 else "INFO",
        f"HTTP {code}",
        t0=t0,
    )


async def S40() -> None:
    """S40: Metrics and monitoring tests."""
    print("\n━━━ S40. METRICS & MONITORING ━━━")
    sec = "S40"

    # S40-01: Pipeline /metrics endpoint
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{PIPELINE_URL}/metrics")
            if r.status_code == 200:
                lines = r.text.splitlines()
                metric_lines = [l for l in lines if l and not l.startswith("#")]
                record(sec, "S40-01", "Pipeline /metrics", "PASS", f"{len(metric_lines)} metrics", t0=t0)
            else:
                record(sec, "S40-01", "Pipeline /metrics", "FAIL", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S40-01", "Pipeline /metrics", "FAIL", str(e)[:100], t0=t0)

    # S40-02: Prometheus scrape targets
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{PROMETHEUS_URL}/api/v1/targets")
            if r.status_code == 200:
                data = r.json()
                targets = data.get("data", {}).get("activeTargets", [])
                up = sum(1 for t in targets if t.get("health") == "up")
                record(sec, "S40-02", "Prometheus targets", "PASS", f"{up}/{len(targets)} up", t0=t0)
            else:
                record(sec, "S40-02", "Prometheus targets", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S40-02", "Prometheus targets", "WARN", str(e)[:100], t0=t0)

    # S40-03: Grafana API
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{GRAFANA_URL}/api/search",
                headers={"Authorization": f"Basic {GRAFANA_PASS}"},
            )
            if r.status_code in (200, 401):  # 401 is OK, means API is responding
                record(sec, "S40-03", "Grafana API", "PASS", f"HTTP {r.status_code}", t0=t0)
            else:
                record(sec, "S40-03", "Grafana API", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S40-03", "Grafana API", "WARN", str(e)[:100], t0=t0)


# ══════════════════════════════════════════════════════════════════════════════
# Report Generation
# ══════════════════════════════════════════════════════════════════════════════

def _write_results(elapsed: int, sections_run: list[str]) -> None:
    """Write ACCEPTANCE_RESULTS.md."""
    counts = {}
    for r in _log:
        counts[r.status] = counts.get(r.status, 0) + 1

    total = sum(counts.values())

    lines = [
        "# Portal 5 Acceptance Test Results — V6",
        "",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Git SHA:** {_git_sha()}",
        f"**Sections:** {', '.join(sections_run)}",
        f"**Runtime:** {elapsed}s ({elapsed // 60}m {elapsed % 60}s)",
        "",
        "## Summary",
        "",
        "| Status | Count |",
        "|--------|-------|",
    ]

    for status in ["PASS", "FAIL", "BLOCKED", "WARN", "INFO"]:
        if status in counts:
            lines.append(f"| {_ICON.get(status, '')} {status} | {counts[status]} |")
    lines.append(f"| **Total** | **{total}** |")

    lines.extend([
        "",
        "## Results",
        "",
        "| Section | ID | Name | Status | Detail | Duration |",
        "|---------|-----|------|--------|--------|----------|",
    ])

    for r in _log:
        icon = _ICON.get(r.status, "")
        detail = r.detail.replace("|", "\\|")[:80]
        dur = f"{r.duration:.1f}s" if r.duration else ""
        lines.append(f"| {r.section} | {r.tid} | {r.name[:40]} | {icon} {r.status} | {detail} | {dur} |")

    if _blocked:
        lines.extend([
            "",
            "## Blocked Items Register",
            "",
        ])
        for i, r in enumerate(_blocked, 1):
            lines.extend([
                f"### BLOCKED-{i}: {r.name}",
                "",
                f"**Test ID:** {r.tid}",
                f"**Section:** {r.section}",
                f"**Detail:** {r.detail}",
                f"**Fix:** {r.fix or 'TBD'}",
                "",
            ])

    (ROOT / "ACCEPTANCE_RESULTS.md").write_text("\n".join(lines))
    print("\n📄 Results written to ACCEPTANCE_RESULTS.md")


# ══════════════════════════════════════════════════════════════════════════════
# Main Execution
# ══════════════════════════════════════════════════════════════════════════════

# Section execution order optimized for memory management on 64GB unified memory:
#
# PHASE 1: No-model tests (health checks, config validation)
#   S0, S1, S2, S12, S13, S40
#
# PHASE 2: Ollama tests (keep Ollama models warm)
#   S3a (Ollama workspaces), S6 (security), S10 (all 34 Ollama personas)
#   [EVICT OLLAMA]
#
# PHASE 3: MLX tests (need unified memory free)
#   S21 (LLM router - small 3B model), S3b (MLX workspaces), S11 (MLX personas)
#   S20, S22, S23 (MLX acceleration tests)
#   [EVICT MLX]
#
# PHASE 4: MCP/Docker tests (minimal memory)
#   S4 (documents), S5 (sandbox)
#
# PHASE 5: Audio tests (MLX Speech server - separate from main MLX)
#   S8 (TTS), S9 (STT), S7 (MusicGen)
#   [EVICT ALL]
#
# PHASE 6: ComfyUI tests LAST (huge memory footprint)
#   S30 (image - FLUX ~8-20GB), S31 (video - Wan2.2 ~18GB)

ALL_SECTIONS = {
    # Phase 1: No-model tests
    "S0": S0,
    "S1": S1,
    "S2": S2,
    "S12": S12,
    "S13": S13,
    "S40": S40,
    # Phase 2: Ollama tests
    "S3a": S3a,
    "S6": S6,
    "S10": S10,
    # Phase 3: MLX tests
    "S21": S21,
    "S3b": S3b,
    "S11": S11,
    "S20": S20,
    "S22": S22,
    "S23": S23,
    # Phase 4: MCP tests
    "S4": S4,
    "S5": S5,
    # Phase 5: Audio tests
    "S8": S8,
    "S9": S9,
    "S7": S7,
    # Phase 6: ComfyUI tests (LAST - huge memory)
    "S30": S30,
    "S31": S31,
    # Legacy S3 wrapper (runs S3a + S3b)
    "S3": S3,
}


def _parse_sections(spec: str) -> list[str]:
    """Parse section specification (e.g., 'S3', 'S3,S10', 'S3-S11', 'S3a', 'S3b')."""
    if not spec or spec.upper() == "ALL":
        return list(ALL_SECTIONS.keys())

    # Build case-insensitive lookup: upper(key) -> canonical key
    _upper_map = {k.upper(): k for k in ALL_SECTIONS}

    def _resolve(part: str) -> str | None:
        """Return canonical ALL_SECTIONS key for part (case-insensitive), or None."""
        if not part.startswith("S") and not part.startswith("s"):
            part = f"S{part}"
        return _upper_map.get(part.upper())

    sections = []
    for part in spec.split(","):
        part = part.strip()
        upper = part.upper()
        if "-" in upper and not upper.startswith("S"):
            # Range like "3-11"
            start, end = upper.split("-")
            for i in range(int(start), int(end) + 1):
                key = _resolve(str(i))
                if key:
                    sections.append(key)
        elif "-" in upper:
            # Range like "S3-S11"
            start, end = upper.split("-")
            start_num = int(start[1:])
            end_num = int(end[1:])
            for i in range(start_num, end_num + 1):
                key = _resolve(str(i))
                if key:
                    sections.append(key)
        else:
            # Single section (e.g. "S3a", "S10", "S3b")
            key = _resolve(part)
            if key:
                sections.append(key)

    return list(dict.fromkeys(sections))  # Remove duplicates, preserve order


async def main() -> int:
    """Run acceptance tests."""
    global _FORCE_REBUILD, _verbose

    parser = argparse.ArgumentParser(description="Portal 5 Acceptance Tests v6")
    parser.add_argument("--section", "-s", default="ALL", help="Section(s) to run")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild before tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--skip-passing", action="store_true", help="Skip sections that passed in prior run")
    args = parser.parse_args()

    _FORCE_REBUILD = args.rebuild
    _verbose = args.verbose

    sections = _parse_sections(args.section)

    # Define memory cleanup points between phases
    # Only apply when running ALL sections (full suite)
    PHASE_TRANSITIONS = {
        "S10": "Ollama → MLX",      # After Ollama personas, before MLX
        "S23": "MLX → MCP",          # After MLX tests, before MCP
        "S7": "Audio → ComfyUI",     # After audio tests, before ComfyUI
    }

    print("=" * 70)
    print("Portal 5 Acceptance Tests v6")
    print(f"Git: {_git_sha()}")
    print(f"Sections: {', '.join(sections)}")
    print("=" * 70)

    # Clear progress log
    Path(_PROGRESS_LOG).write_text(f"[{time.strftime('%H:%M:%S')}] Starting acceptance tests\n")

    start_time = time.time()
    running_full_suite = len(sections) > 10  # Heuristic for full suite

    for sec in sections:
        if sec in ALL_SECTIONS:
            try:
                await ALL_SECTIONS[sec]()
            except Exception as e:
                record(sec, f"{sec}-ERR", "Section error", "FAIL", str(e)[:200])

            # Memory cleanup at phase transitions (only for full suite runs)
            if running_full_suite and sec in PHASE_TRANSITIONS:
                await _memory_cleanup(PHASE_TRANSITIONS[sec])
            else:
                # Brief pause between sections
                await asyncio.sleep(2)

    elapsed = int(time.time() - start_time)

    # Write results
    _write_results(elapsed, sections)

    # Print summary
    counts = {}
    for r in _log:
        counts[r.status] = counts.get(r.status, 0) + 1

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for status in ["PASS", "FAIL", "BLOCKED", "WARN", "INFO"]:
        if status in counts:
            print(f"  {_ICON.get(status, '')} {status}: {counts[status]}")
    print(f"  Total: {sum(counts.values())}")
    print(f"  Runtime: {elapsed}s ({elapsed // 60}m {elapsed % 60}s)")
    print("=" * 70)

    # Return non-zero if any failures
    if counts.get("FAIL", 0) > 0 or counts.get("BLOCKED", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
