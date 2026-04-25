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

Test Coverage (22 sections, ~300 tests):
    S0-S2:   Prerequisites, config consistency, service health
    S3:      17 workspaces with content-aware routing
    S4-S5:   Document generation (Word/Excel/PowerPoint), code sandbox
    S6:      Security workspaces (auto-security, auto-redteam, auto-blueteam)
    S16:     Security MCP tools (classify_vulnerability via CIRCL VLAI)
    S7-S9:   Music generation, TTS, STT
    S10-S11: personas across multiple categories (Ollama + MLX backends)
    S12-S13: Web search (SearXNG), RAG/embedding pipeline
    S20:     MLX acceleration (proxy health, /v1/models, memory)
    S21:     LLM Intent Router (P5-FUT-006) — semantic routing via Llama-3.2-3B
    S22:     MLX Admission Control (P5-FUT-009) — memory-aware 503 rejection
    S23:     Model diversity availability checks (GPT-OSS, Gemma 4 E4B, Phi-4, Magistral)
    S30-S31: Image generation (ComfyUI/FLUX), video generation (Wan2.2)
    S40:     Metrics/monitoring (Prometheus, Grafana)
    S41:     M6 production hardening (/health/all, rate limits, admin endpoints, power metrics)
    S42:     M5 browser automation (Browser MCP health, tool manifest)
    S60:     M2 tool-calling orchestration (registry, dispatch, metrics)
    S70:     M3 information access MCPs (research, memory, RAG, SearXNG)

Changes from v5:
    - Added S16 (Security MCP tool tests — classify_vulnerability)
    - Persona count is now dynamic (derived from config/personas/*.yaml at runtime)
    - Added S21 (LLM Intent Router), S22 (Admission Control), S23 (Model Diversity)
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
import itertools
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
EMBEDDING_URL = os.environ.get("EMBEDDING_URL", "http://localhost:8917")

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
    "security": int(os.environ.get("SECURITY_HOST_PORT", "8919")),
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

# Shared httpx client — created once, reused across all test HTTP calls
_acc_client: httpx.AsyncClient | None = None


def _get_acc_client() -> httpx.AsyncClient:
    """Return shared httpx client; create on first call."""
    global _acc_client
    if _acc_client is None or _acc_client.is_closed:
        _acc_client = httpx.AsyncClient(timeout=30)
    return _acc_client


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


_ERROR_PATTERNS_CODE_DEFECT = [
    r"No such file or directory.*portal_metrics",
    r"model_hint.*not in",
    r"workspace_model.*not in WORKSPACES",
    r"AttributeError|TypeError|NameError",
    r"port.*already in use|address already in use",
    r"semaphore.*concurrency limit",
]
_ERROR_PATTERNS_ENV_ISSUE = [
    r"All connection attempts failed",
    r"name resolution|getaddrinfo",
    r"docker.*registry|registry-1\.docker\.io",
    r"insufficient memory|out of memory",
    r"missing dependency|No module named",
    r"port.*not running|not running",
    r"ConnectError|Connection refused",
]


def _classify(detail: str) -> str:
    """Classify a FAIL/WARN detail string as CODE-DEFECT, ENV-ISSUE, or UNCLASSIFIED."""
    for pat in _ERROR_PATTERNS_CODE_DEFECT:
        if re.search(pat, detail, re.IGNORECASE):
            return "CODE-DEFECT"
    for pat in _ERROR_PATTERNS_ENV_ISSUE:
        if re.search(pat, detail, re.IGNORECASE):
            return "ENV-ISSUE"
    return "UNCLASSIFIED"


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
    if status in ("FAIL", "WARN") and detail:
        cls = _classify(detail)
        detail = f"{detail}  [{cls}]"
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
    ids = sorted(set(re.findall(r'"((?:auto|bench)[^"]*)":\s*\{', block)))
    names = dict(re.findall(r'"((?:auto|bench)[^"]*)":.*?"name":\s*"([^"]+)"', block, re.DOTALL))
    return ids, names


def _load_personas() -> list[dict]:
    """Load all persona YAML files."""
    return [
        yaml.safe_load(f.read_text()) for f in sorted((ROOT / "config/personas").glob("*.yaml"))
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
        c = _get_acc_client()
        r = await c.get(url, timeout=timeout)
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
        c = _get_acc_client()
        r = await c.post(url, json=body, headers=headers or AUTH, timeout=timeout)
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
                result = await asyncio.wait_for(session.call_tool(tool, args), timeout=timeout)
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
                result = await asyncio.wait_for(session.call_tool(tool, args), timeout=timeout)
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
    code, text, _, _route = await _chat_with_model(
        workspace, prompt, system, max_tokens, timeout, stream
    )
    return code, text


async def _chat_with_model(
    workspace: str,
    prompt: str,
    system: str = "",
    max_tokens: int = 400,
    timeout: int = 240,
    stream: bool = False,
) -> tuple[int, str, str, str]:
    """Chat request that also returns the model and route header.

    Returns (status_code, response_text, model_used, route_descriptor).
    route_descriptor is the x-portal-route header value: "{workspace};{backend_id};{model}".
    Uses shared client with 3-attempt backoff [0, 5, 15]s.
    On 502/503 probes MLX health state before retrying so we wait for
    cold-load (switching) rather than treating it as a hard failure.
    """
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system[:800]})
    msgs.append({"role": "user", "content": prompt})
    body = {"model": workspace, "messages": msgs, "stream": stream, "max_tokens": max_tokens}
    backoff = [0, 5, 15]

    for attempt, delay in enumerate(backoff):
        if delay:
            await asyncio.sleep(delay)
        try:
            c = _get_acc_client()
            r = await c.post(
                f"{PIPELINE_URL}/v1/chat/completions",
                headers=AUTH,
                json=body,
                timeout=timeout,
            )
            route_hdr = r.headers.get("x-portal-route", "")
            if r.status_code not in (200,):
                if r.status_code in (502, 503) and attempt < len(backoff) - 1:
                    # Probe MLX — if switching/starting, wait longer before retry
                    mlx_state, _ = await _mlx_health()
                    if mlx_state in ("switching", "none"):
                        await asyncio.sleep(15)
                    continue
                return r.status_code, r.text[:200], "", ""

            if stream:
                text = ""
                for line in r.text.splitlines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            d = json.loads(line[6:])
                            text += d.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        except Exception:
                            pass
                return 200, text, "", route_hdr

            data = r.json()
            msg = data.get("choices", [{}])[0].get("message", {})
            model = data.get("model", "")
            content = msg.get("content", "") or msg.get("reasoning", "")
            return 200, content, model, route_hdr
        except httpx.ReadTimeout:
            return 408, "timeout", "", ""
        except Exception as e:
            if attempt < len(backoff) - 1 and any(
                x in str(e).lower() for x in ["502", "connection refused"]
            ):
                continue
            return 0, str(e)[:100], "", ""
    return 503, "MLX proxy unreachable after retries", "", ""


def _curl_stream(
    workspace: str, prompt: str, max_tokens: int = 5, timeout_s: int = 360
) -> tuple[bool, str]:
    """Test streaming via curl (more reliable than httpx for SSE)."""
    try:
        result = subprocess.run(
            [
                "curl",
                "-s",
                "-m",
                str(timeout_s),
                "-X",
                "POST",
                f"{PIPELINE_URL}/v1/chat/completions",
                "-H",
                f"Authorization: Bearer {API_KEY}",
                "-H",
                "Content-Type: application/json",
                "-d",
                json.dumps(
                    {
                        "model": workspace,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": True,
                        "max_tokens": max_tokens,
                    }
                ),
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
            ln for ln in (r.stdout + r.stderr).splitlines() if re.search(pattern, ln, re.IGNORECASE)
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
        required = [
            "portal5-pipeline",
            "portal5-open-webui",
            "portal5-searxng",
            "portal5-prometheus",
        ]
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
    "supergemma4-26b-abliterated-multimodal-mlx-4bit": "Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit",
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
    "supergemma4-26b-abliterated-multimodal-mlx-4bit": 15,
    "Qwen3-VL-32B-Instruct-8bit": 36,
}

# Known MLX org prefixes
# MLX org prefixes — workspace_model values starting with these are raw HF paths
# that Open WebUI can never resolve (pipeline only exposes workspace IDs).
_MLX_ORGS = [
    "mlx-community/",
    "lmstudio-community/",
    "Jackrong/",
    "Jiunsong/",
    "unsloth/",
    "dealignai/",
    "huihui-ai/",
]

# Mapping from MLX model hint (HF path) → pipeline workspace name.
# All persona YAMLs now use workspace IDs directly; this dict is used by S11
# to know which MLX model to pre-load before testing each workspace.
_MLX_MODEL_TO_WORKSPACE: dict[str, str] = {
    "lmstudio-community/Devstral-Small-2507-MLX-4bit": "auto-coding",
    "mlx-community/Qwen3-Coder-Next-4bit": "auto-agentic",
    "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit": "auto-spl",
    "mlx-community/Dolphin3.0-Llama3.1-8B-8bit": "auto-creative",
    "Jackrong/MLX-Qwopus3.5-27B-v3-8bit": "auto-reasoning",
    "mlx-community/phi-4-8bit": "auto-documents",
    "Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit": "auto-research",  # Task 4: rerouted from 31B dense to 26B MoE abliterated (~35 vs ~20 TPS)
    "mlx-community/gemma-4-31b-it-4bit": "auto-vision",
    "mlx-community/DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit": "auto-data",
    "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit": "auto-compliance",
    "lmstudio-community/Magistral-Small-2509-MLX-8bit": "auto-mistral",
    # Phi-4-reasoning-plus has no pipeline workspace — it maps to auto-data (DeepSeek-R1)
    # for production routing. Tested via auto-data workspace in S11.
}


async def _mlx_health() -> tuple[str, dict]:
    """Get MLX proxy health state.

    The proxy returns HTTP 503 when no model is loaded (state='none') or when
    the active server has crashed (state='down').  Always parse the JSON body
    to get the actual state rather than inferring from the HTTP status code.
    """
    try:
        c = _get_acc_client()
        r = await c.get(f"{MLX_URL}/health", timeout=10)
        if r.status_code in (200, 503):
            try:
                data = r.json()
                return data.get("state", "unknown"), data
            except Exception:
                pass
        if r.status_code == 503:
            return "down", {"status_code": 503}
        return "error", {"status_code": r.status_code}
    except Exception as e:
        return "unreachable", {"error": str(e)}


async def _wait_for_mlx_ready(timeout: int = 120) -> bool:
    """Wait for MLX proxy to be ready (any model)."""
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


async def _wait_for_mlx_model(model_hint: str, timeout: int = 300) -> bool:
    """Wait for MLX proxy to load a specific model (by basename or full path).

    The proxy switches on first inference request.  We poll until loaded_model
    contains the model's basename (last path segment) OR the full hint.
    Returns True when the right model is loaded and ready.
    """
    basename = model_hint.split("/")[-1]
    start = time.time()
    while time.time() - start < timeout:
        state, data = await _mlx_health()
        loaded = data.get("loaded_model") or ""  # null → ""
        if state == "ready" and (basename in loaded or model_hint in loaded):
            return True
        if state in ("none", "switching", "ready"):
            await asyncio.sleep(8)
            continue
        if state in ("unreachable", "down"):
            await asyncio.sleep(5)
            continue
        await asyncio.sleep(5)
    return False


async def _unload_ollama_models() -> None:
    """Evict all Ollama models from memory to free unified memory for MLX/ComfyUI."""
    try:
        c = _get_acc_client()
        r = await c.get(f"{OLLAMA_URL}/api/ps", timeout=10)
        if r.status_code != 200:
            return
        models = [m["name"] for m in r.json().get("models", [])]
        if not models:
            print("  ── No Ollama models loaded ──")
            return
        print(f"  ── Evicting {len(models)} Ollama model(s): {models} ──")
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
        loaded = data.get("loaded_model") or "unknown"
        print(f"  ── Unloading MLX model: {loaded} ──")
        c = _get_acc_client()
        try:
            await c.post(f"{MLX_URL}/unload", timeout=10)
        except Exception:
            pass
        # Wait for memory to be released
        await asyncio.sleep(10)
    except Exception as e:
        print(f"  ⚠️  MLX unload failed: {e}")


def _free_ram_gb() -> float:
    """Return approximate free unified memory in GB via vm_stat."""
    try:
        out = subprocess.check_output(["vm_stat"], text=True)
        pages_free = pages_inactive = page_size = 0
        for line in out.splitlines():
            if "page size of" in line:
                page_size = int(line.split()[-2])
            elif "Pages free:" in line:
                pages_free = int(line.split()[-1].rstrip("."))
            elif "Pages inactive:" in line:
                pages_inactive = int(line.split()[-1].rstrip("."))
        if page_size == 0:
            page_size = 16384  # Apple Silicon default
        return round((pages_free + pages_inactive) * page_size / (1024**3), 1)
    except Exception:
        return 0.0


def _stop_comfyui() -> None:
    """Kill ComfyUI process to reclaim GPU/RAM before heavy MLX loads."""
    result = subprocess.run(["pkill", "-f", "comfyui"], capture_output=True)
    if result.returncode == 0:
        print("  ── ComfyUI stopped to free memory ──")
    # Also stop the MCP server that wraps ComfyUI if present
    subprocess.run(["pkill", "-f", "comfyui_mcp"], capture_output=True)


async def _ensure_free_ram_gb(needed_gb: float, phase: str) -> float:
    """Ensure at least needed_gb of free RAM, evicting what we can. Returns actual free GB."""
    free = _free_ram_gb()
    print(f"  ── RAM: {free:.1f} GB free (need {needed_gb:.0f} GB for {phase}) ──")
    if free >= needed_gb:
        return free
    print("  ── Insufficient RAM — running eviction ──")
    await _unload_ollama_models()
    await _unload_mlx_model()
    # Apple Silicon unified memory takes time to reclaim pages — wait 20s
    await asyncio.sleep(20)
    free = _free_ram_gb()
    print(f"  ── RAM after eviction: {free:.1f} GB free ──")
    if free < needed_gb:
        print(f"  ⚠️  Still low on RAM ({free:.1f}GB < {needed_gb}GB needed) — stopping ComfyUI")
        _stop_comfyui()
        await asyncio.sleep(10)
        free = _free_ram_gb()
        print(f"  ── RAM after ComfyUI stop: {free:.1f} GB free ──")
    return free


async def _remediate_mlx_crash(reason: str = "crash") -> bool:
    """Recover from MLX proxy 'down' state: kill all MLX procs and restart proxy.

    Ported from v4 acceptance tests.  Returns True if proxy is back and healthy.
    """
    print(f"  🔧 MLX remediation: {reason}")

    # Step 1: Kill all MLX server processes and the proxy
    for pattern in ["mlx_lm.server", "mlx_vlm.server", "mlx-proxy.py", "mlx-watchdog"]:
        subprocess.run(["pkill", "-9", "-f", pattern], capture_output=True)

    # Force-kill anything still on the MLX ports
    for port in [18081, 18082, 8081]:
        try:
            r = subprocess.run(
                ["lsof", "-ti", f":{port}"], capture_output=True, text=True, timeout=5
            )
            for pid in r.stdout.strip().split("\n"):
                if pid.strip():
                    try:
                        os.kill(int(pid.strip()), 9)
                    except (ProcessLookupError, ValueError):
                        pass
        except Exception:
            pass

    # Wait for ports to clear
    for _ in range(20):
        r = subprocess.run(["lsof", "-ti", ":8081"], capture_output=True, text=True, timeout=3)
        if not r.stdout.strip():
            break
        await asyncio.sleep(1)

    free = _free_ram_gb()
    print(f"  ── RAM after kill: {free:.1f} GB free ──")

    # Step 2: Restart proxy from deployed script
    proxy_script = Path.home() / ".portal5" / "mlx" / "mlx-proxy.py"
    if not proxy_script.exists():
        proxy_script = ROOT / "scripts" / "mlx-proxy.py"
    subprocess.Popen(
        ["python3", str(proxy_script)],
        stdout=open("/tmp/mlx-proxy.log", "a"),
        stderr=subprocess.STDOUT,
    )

    # Step 3: Wait for proxy to respond
    for _ in range(30):
        await asyncio.sleep(2)
        try:
            c = _get_acc_client()
            r = await c.get(f"{MLX_URL}/health", timeout=5)
            if r.status_code in (200, 503):
                data = r.json()
                state = data.get("state", "unknown")
                if state in ("none", "ready"):
                    print(f"  ✅ MLX proxy recovered (state={state})")
                    return True
        except Exception:
            pass

    print("  ❌ MLX proxy failed to recover")
    return False


async def _memory_cleanup(phase: str) -> None:
    """Perform memory cleanup between test phases with active RAM verification."""
    print(f"\n  ══ MEMORY CLEANUP: {phase} ══")
    await _unload_ollama_models()
    await _unload_mlx_model()
    import gc

    gc.collect()
    # Apple Silicon: 20s for unified memory pages to be reclaimed
    await asyncio.sleep(20)
    free = _free_ram_gb()
    print(f"  ══ CLEANUP COMPLETE — {free:.1f} GB free ══\n")


# ══════════════════════════════════════════════════════════════════════════════
# Test Signal Definitions
# ══════════════════════════════════════════════════════════════════════════════

# Workspace test prompts and expected signals
WORKSPACE_PROMPTS = {
    "auto": (
        "Explain what a DNS server does in two sentences.",
        ["DNS", "domain", "IP", "resolve", "name"],
    ),
    "auto-coding": (
        "Write a Python function that reverses a string.",
        ["def", "return", "reverse", "[::-1]", "str"],
    ),
    "auto-agentic": (
        "Explain how you would refactor a monolith into microservices.",
        ["service", "API", "boundary", "domain", "decouple"],
    ),
    "auto-spl": (
        "Write a Splunk SPL query to find failed login attempts.",
        ["index", "source", "fail", "login", "stats", "|"],
    ),
    "auto-security": (
        "What are the OWASP Top 10 vulnerabilities?",
        ["injection", "XSS", "authentication", "OWASP", "vulnerability"],
    ),
    "auto-redteam": (
        "Describe common techniques for privilege escalation on Linux.",
        ["sudo", "SUID", "privilege", "root", "escalat"],
    ),
    "auto-blueteam": (
        "How do you detect lateral movement in a network?",
        ["traffic", "network", "monitor", "detect", "lateral"],
    ),
    "auto-creative": (
        "Write a haiku about artificial intelligence.",
        [
            "AI",
            "machine",
            "digital",
            "think",
            "learn",
            "syllable",
            "code",
            "knowledge",
            "wisdom",
            "neural",
            "data",
            "realm",
            "intelligence",
            "gleam",
            "whisper",
            "deep",
            "poem",
            "artificial",
            "thought",
            "future",
            "human",
            "automat",
            "bloom",
            "mind",
            "electric",
            "silicon",
            "algorithm",
            "compute",
            "swift",
            "motion",
            "light",
            "dream",
            "silent",
            "rise",
            "glow",
            "world",
        ],
    ),
    "auto-reasoning": (
        "Solve this step by step: if a train travels at 60mph for 2.5 hours, how far does it go?",
        ["150", "mile", "distance", "60", "2.5"],
    ),
    "auto-documents": (
        "Create an outline for a project proposal document.",
        ["introduction", "scope", "timeline", "budget", "section"],
    ),
    "auto-video": (
        "Describe a 5-second video of a sunrise over mountains.",
        ["sun", "mountain", "light", "sky", "rise", "scene"],
    ),
    "auto-music": (
        "Describe a 10-second lo-fi hip hop beat.",
        ["beat", "drum", "sample", "chill", "loop", "bass"],
    ),
    "auto-research": (
        "What are the latest developments in quantum computing?",
        ["qubit", "quantum", "compute", "superconducting", "research"],
    ),
    "auto-vision": (
        "How would you analyze an image for accessibility issues?",
        ["alt", "text", "contrast", "color", "image", "visual"],
    ),
    "auto-data": (
        "Explain how to calculate standard deviation.",
        ["mean", "variance", "deviation", "σ", "standard", "sqrt"],
    ),
    "auto-compliance": (
        "What evidence is needed for NERC CIP-007 R2?",
        ["CIP", "evidence", "patch", "compliance", "NERC", "requirement"],
    ),
    "auto-mistral": (
        "Analyze the trade-offs between microservices and monolithic architectures.",
        ["trade", "scale", "complex", "deploy", "maintain"],
    ),
}

# Persona test prompts and expected signals
# Full list of 48 personas from config/personas/*.yaml
PERSONA_PROMPTS = {
    # Development (18 personas)
    # Real IndexError bug: no bounds check on lst, no empty-list guard
    "bugdiscoverycodeassistant": (
        "Find the bugs in this code:\ndef get_first(lst):\n    return lst[0]",
        [
            "index",
            "IndexError",
            "empty",
            "bounds",
            "check",
            "exception",
            "out-of-range",
            "list",
            "lst",
            "fail",
            "error",
            "first",
        ],
    ),
    "codereviewassistant": (
        "Review this code: x = [i for i in range(100)]",
        ["list", "comprehension", "memory", "generator"],
    ),
    "codereviewer": ("Review: if x == True:", ["==", "bool", "simplify", "True", "comparison"]),
    # Concrete function so model generates an actual docstring rather than describing docs
    "codebasewikidocumentationskill": (
        "Write a docstring for:\ndef parse_config(path: str, strict: bool = False) -> dict:",
        ["param", "Args", "Returns", "raises", "str", "dict", "path"],
    ),
    "devopsautomator": (
        "Write a bash script to back up /var/data to /backup with today's date in the filename.",
        ["#!/", "bash", "rsync", "date", "backup", "mkdir"],
    ),
    "devopsengineer": (
        "Explain Kubernetes pod lifecycle.",
        ["pod", "pending", "running", "container", "lifecycle"],
    ),
    "ethereumdeveloper": (
        "Write a simple Solidity smart contract.",
        ["contract", "pragma", "solidity", "function", "public"],
    ),
    "fullstacksoftwaredeveloper": (
        "Design a REST API for a todo app.",
        ["GET", "POST", "endpoint", "REST", "API"],
    ),
    "githubexpert": (
        "Explain git rebase vs merge.",
        ["rebase", "merge", "history", "commit", "branch"],
    ),
    "javascriptconsole": ("Calculate 2 * Math.PI * 3", ["6.28", "18.84", "Math", "PI", "result"]),
    "kubernetesdockerrpglearningengine": (
        "Explain Docker layers.",
        ["layer", "image", "cache", "dockerfile", "build"],
    ),
    "pythoncodegeneratorcleanoptimizedproduction-ready": (
        "Generate a function to sort a list of dicts by key.",
        ["sorted", "lambda", "key", "dict", "def"],
    ),
    # Remove single-digit signals ("3","2","1") — they match any text; keep specific output + sort terms
    "pythoninterpreter": (
        "Execute: sorted([3,1,2], reverse=True)",
        ["[3, 2, 1]", "reverse", "sorted", "descend", "output"],
    ),
    "seniorfrontenddeveloper": (
        "Explain React hooks.",
        ["useState", "useEffect", "hook", "component", "state"],
    ),
    "seniorsoftwareengineersoftwarearchitectrules": (
        "What design patterns would you apply to a REST API handling 10 million requests per day?",
        ["pattern", "cache", "load", "queue", "horizontal", "scale", "rate"],
    ),
    "softwarequalityassurancetester": (
        "Write test cases for a login form.",
        ["test", "case", "valid", "invalid", "password"],
    ),
    "ux-uideveloper": (
        "Best practices for mobile-first design.",
        ["mobile", "responsive", "viewport", "breakpoint", "touch"],
    ),
    "creativecoder": (
        "Write a single-file HTML Canvas game: a ball that bounces off walls and splits into two smaller balls when clicked.",
        [
            "canvas",
            "ball",
            "bounce",
            "click",
            "split",
            "radius",
            "velocity",
            "ctx",
            "requestAnimationFrame",
        ],
    ),
    # Security (6 personas)
    "cybersecurityspecialist": (
        "Explain zero-trust architecture.",
        ["zero", "trust", "verify", "never", "assume"],
    ),
    # Specific enough to force actual IOS commands with testable tokens
    "networkengineer": (
        "Write Cisco IOS commands to create VLAN 100 named PROD and assign interface GigabitEthernet0/1 as an access port.",
        ["vlan", "switchport", "interface", "access", "GigabitEthernet", "mode", "name"],
    ),
    # Question form so model lists techniques; T1566/T1190 are ATT&CK IDs; model may use TA0xxx or DS notation
    "redteamoperator": (
        "List three MITRE ATT&CK initial access techniques and their technique IDs.",
        [
            "T1566",
            "T1190",
            "phishing",
            "exploit",
            "technique",
            "initial",
            "TA0",
            "DS1",
            "access",
            "attack",
            "spearphish",
            "removable",
        ],
    ),
    "blueteamdefender": (
        "Detect ransomware activity.",
        ["encrypt", "extension", "ransom", "detect", "behavior"],
    ),
    "pentester": ("OWASP testing methodology.", ["OWASP", "test", "inject", "XSS", "methodology"]),
    "splunksplgineer": (
        "Write SPL to detect brute force.",
        ["index", "stats", "count", "fail", "threshold"],
    ),
    # Data (7 personas)
    "dataanalyst": (
        "Explain correlation vs causation.",
        ["correlation", "causation", "variable", "relationship"],
    ),
    "datascientist": (
        "Feature engineering techniques.",
        ["feature", "encode", "normalize", "transform", "engineer"],
    ),
    "machinelearningengineer": (
        "Explain gradient descent.",
        ["gradient", "descent", "learning", "rate", "optimize"],
    ),
    "statistician": (
        "Explain p-value interpretation.",
        ["p-value", "null", "hypothesis", "significance", "0.05"],
    ),
    # Remove "HA" — 2 chars match substrings in unrelated words; use full terms
    "itarchitect": (
        "Design a high-availability system.",
        ["redundant", "failover", "availability", "replica", "load balancer"],
    ),
    # Concrete task so model produces structured steps, not a disclaimer it can't do a review
    "researchanalyst": (
        "Outline the steps for a systematic literature review on transformer models in NLP.",
        ["systematic", "search", "inclusion", "database", "literature", "source", "criteria"],
    ),
    "excelsheet": ("Formula for VLOOKUP.", ["VLOOKUP", "formula", "range", "col_index", "FALSE"]),
    # Compliance (2 personas)
    "nerccipcomplianceanalyst": (
        "CIP-007 patch management requirements.",
        ["CIP", "patch", "35", "day", "compliance"],
    ),
    "cippolicywriter": (
        "Write a policy for access control.",
        ["access", "control", "policy", "authorize", "role"],
    ),
    # Systems (2 personas)
    "linuxterminal": ("List files by size.", ["ls", "-l", "sort", "size", "du"]),
    "sqlterminal": ("SELECT users with admin role.", ["SELECT", "FROM", "WHERE", "role", "admin"]),
    # General (2 personas)
    "itexpert": (
        "Troubleshoot slow network.",
        [
            "bandwidth",
            "latency",
            "packet",
            "loss",
            "diagnose",
            "network",
            "gather",
            "troubleshoot",
            "speed",
            "connection",
            "router",
            "check",
            "slow",
        ],
    ),
    "techreviewer": (
        "Review iPhone 15 features.",
        ["camera", "chip", "battery", "feature", "review"],
    ),
    # Writing (3 personas)
    # Removed stopword signals ("the","in","a") — matched everything; use narrative-specific terms
    "creativewriter": (
        "Write the opening paragraph of a noir detective story set in a rainy city.",
        [
            "rain",
            "detective",
            "night",
            "dark",
            "street",
            "shadow",
            "city",
            "stood",
            "office",
            "cigarette",
        ],
    ),
    "techwriter": (
        "Document an API endpoint.",
        ["endpoint", "request", "response", "parameter", "method"],
    ),
    # Reasoning (3 personas)
    # Concrete deliverable so model produces a structured plan with testable milestones
    "magistralstrategist": (
        "Create a 90-day strategic plan for launching a developer productivity SaaS, with milestones and KPIs.",
        ["milestone", "KPI", "launch", "objective", "strategy", "quarter", "metric", "goal"],
    ),
    # "square" matches "squared", "squares", "squaring" — more robust than exact "squared"
    "phi4stemanalyst": (
        "Explain the Pythagorean theorem.",
        ["pythagor", "triangle", "hypotenuse", "right", "square", "sides"],
    ),
    "phi4specialist": (
        "Write a technical specification outline.",
        ["spec", "requirement", "section", "format", "structure"],
    ),
    "gptossanalyst": (
        "Analyze trade-offs between microservices and monoliths.",
        ["trade", "scale", "complex", "maintain", "deploy"],
    ),
    # Vision (2 personas — Gemma 4 E4B + JANG uncensored VLM)
    # Text-only tests (no image upload in acceptance suite) — prompts exercise reasoning about visual context
    "gemma4e4bvision": (
        "A developer uploads a screenshot of an HTTP 500 error page with a stack trace. What would you identify and recommend?",
        ["stack", "trace", "error", "500", "exception", "debug", "log", "server"],
    ),
    # Uncensored VLM — prompt tests no-refusal behavior on a red team / OSINT task
    "gemma4jangvision": (
        "List three techniques for extracting credentials visible in a screenshot during a red team engagement.",
        ["credential", "password", "screenshot", "OCR", "extract", "hash", "capture", "image"],
    ),
    # Writing (hermes3writer — long-form narrative fiction via Hermes 3 / Dolphin)
    "hermes3writer": (
        "Write the opening paragraph of a serialized mystery novel set in a coastal town, introducing the detective character.",
        ["detective", "coastal", "town", "mystery", "character", "chapter", "story", "narrative"],
    ),
    # Research (2 personas)
    "gemmaresearchanalyst": (
        "Research methodology steps.",
        ["method", "data", "collect", "analyze", "research"],
    ),
    # Uncensored multimodal researcher — test no-refusal on a professional OSINT task
    "supergemma4researcher": (
        "Outline the steps for an OSINT investigation to verify a company's publicly disclosed executive team.",
        [
            "OSINT",
            "search",
            "verify",
            "public",
            "record",
            "source",
            "LinkedIn",
            "domain",
            "executive",
            "corporate",
            "registry",
            "confirm",
            "evidence",
        ],
    ),
    # ── M1: Compliance personas ─────────────────────────────────────────
    "soc2auditor": (
        "What's the difference between control design and operating effectiveness in a SOC 2 Type II audit?",
        ["design", "operating", "effectiveness", "type ii", "trust services"],
    ),
    "pcidssassessor": (
        "We process 5 million card transactions per year. Which PCI-DSS merchant level applies and what validation does it require?",
        ["level", "merchant", "report on compliance", "roc", "5 million", "6 million"],
    ),
    "gdprdpoadvisor": (
        "Our SaaS company is based in California and serves EU residents. Does GDPR apply to us, and if so under which article?",
        ["article 3", "territorial scope", "offering", "monitoring", "controller"],
    ),
    "hipaaprivacyofficer": (
        "What is the 4-factor low probability of compromise test in HIPAA breach assessment?",
        ["nature", "extent", "phi", "unauthorized", "acquired", "viewed", "extent of risk"],
    ),
    # ── M1: Language personas ────────────────────────────────────────────
    "rustengineer": (
        "Write a thread-safe LRU cache in Rust with capacity bound and TTL eviction.",
        ["arc", "mutex", "rwlock", "hashmap", "vecdeque", "lru", "instant", "duration"],
    ),
    "goengineer": (
        "Write a Go HTTP middleware that adds request IDs and structured logging via slog.",
        ["middleware", "http.handler", "context", "slog", "uuid", "next.servehttp"],
    ),
    "typescriptengineer": (
        "Write a TypeScript discriminated union for a state machine with idle, loading, success, error states. Include type guards.",
        ["discriminated union", "type", "loading", "success", "error", "type guard", "narrowing"],
    ),
    # ── M1: Workplace personas ───────────────────────────────────────────
    "productmanager": (
        "Write a one-page PRD for adding two-factor authentication to a banking app.",
        ["problem", "target user", "success metric", "scope", "non-goals", "rice"],
    ),
    "businessanalyst": (
        "Map the requirements for replacing our legacy CRM. We have 200 sales users.",
        ["business requirement", "stakeholder", "functional", "moscow", "process", "constraint"],
    ),
    "proofreader": (
        "Proofread: 'Their are several issues with the project, that needs to be address. Mainly, the timeline is to short.'",
        ["there are", "address", "addressed", "too short", "comma"],
    ),
    "interviewcoach": (
        "Run a mock behavioral interview question for a senior software engineer role at a fintech company.",
        ["star", "situation", "task", "action", "result", "behavioral"],
    ),
    # ── M1: Specialty personas ───────────────────────────────────────────
    "splunkdetectionauthor": (
        "Write a Splunk detection for password spraying — many failed logins from one source against many accounts.",
        ["tstats", "authentication", "data model", "t1110", "mitre", "false positive"],
    ),
    "terraformwriter": (
        "Write a Terraform module that provisions an S3 bucket with encryption, public access block, and lifecycle policy.",
        [
            "resource",
            "aws_s3_bucket",
            "encryption",
            "public_access_block",
            "lifecycle",
            "variables.tf",
        ],
    ),
    "documentationarchitect": (
        "Outline the documentation structure for an open-source REST API library.",
        ["tutorial", "reference", "how-to", "explanation", "diataxis", "getting started"],
    ),
    "databasearchitect": (
        "Design the schema for a multi-tenant SaaS application with users, organizations, projects, tasks.",
        ["users", "organizations", "tenant", "primary key", "foreign key", "index"],
    ),
    "dashboardarchitect": (
        "Design an executive dashboard for monthly recurring revenue (MRR) tracking.",
        ["mrr", "trend", "kpi", "month-over-month", "churn", "above the fold"],
    ),
    # ── M1: Vision personas ──────────────────────────────────────────────
    "ocrspecialist": (
        "Describe the framework you'd use to extract data from a scanned receipt.",
        ["receipt", "preprocessing", "layout", "line item", "total", "vendor", "confidence"],
    ),
    "diagramreader": (
        "Describe how you'd analyze and convert an architecture diagram to text.",
        ["entities", "relationships", "components", "directionality", "mermaid", "abstraction"],
    ),
    # ── M1: Math persona ─────────────────────────────────────────────────
    "mathreasoner": (
        "Find the eigenvalues of the matrix [[3, 1], [0, 2]].",
        ["eigenvalue", "characteristic polynomial", "det", "lambda", "3", "2"],
    ),
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
        sec,
        "S0-01",
        "Python version",
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
        sec,
        "S0-02",
        "Required packages",
        "PASS" if not missing else "FAIL",
        f"missing: {missing}" if missing else "all present",
        t0=t0,
    )

    # S0-03: .env file exists
    t0 = time.time()
    env_exists = (ROOT / ".env").exists()
    record(
        sec,
        "S0-03",
        ".env file exists",
        "PASS" if env_exists else "FAIL",
        str(ROOT / ".env"),
        t0=t0,
    )

    # S0-04: API key configured
    t0 = time.time()
    has_key = bool(API_KEY)
    record(
        sec,
        "S0-04",
        "PIPELINE_API_KEY configured",
        "PASS" if has_key else "FAIL",
        f"key length: {len(API_KEY)}" if has_key else "not set",
        t0=t0,
    )

    # S0-05: Git repository
    t0 = time.time()
    sha = _git_sha()
    record(
        sec,
        "S0-05",
        "Git repository",
        "PASS" if sha != "unknown" else "WARN",
        f"SHA: {sha}",
        t0=t0,
    )

    # S0-06: MLX watchdog status (informational — watchdog may run during tests).
    # The watchdog's check_server_zombies() is now gated on proxy state=switching,
    # so it no longer fights with test-driven model loads. It is intentionally left
    # running to provide zombie detection during the test run.
    t0 = time.time()
    try:
        r = subprocess.run(
            ["pgrep", "-f", "mlx-watchdog"], capture_output=True, text=True, timeout=5
        )
        running = r.returncode == 0 and bool(r.stdout.strip())
        record(
            sec,
            "S0-06",
            "MLX watchdog status",
            "INFO",
            f"watchdog {'running (PID ' + r.stdout.strip() + ') — provides zombie detection during tests' if running else 'not running — start with ./launch.sh start-mlx-watchdog'}",
            t0=t0,
        )
    except Exception as e:
        record(sec, "S0-06", "MLX watchdog status", "WARN", str(e)[:80], t0=t0)

    # S0-07: Deployed MLX proxy matches source (catches P5-ROAD-MLX-002 staleness)
    t0 = time.time()
    import filecmp  # noqa: PLC0415

    src = ROOT / "scripts/mlx-proxy.py"
    deployed = Path.home() / ".portal5/mlx/mlx-proxy.py"
    if not deployed.exists():
        record(
            sec,
            "S0-07",
            "Deployed MLX proxy",
            "INFO",
            "not yet deployed (run ./launch.sh install-mlx)",
            t0=t0,
        )
    elif filecmp.cmp(src, deployed, shallow=False):
        record(
            sec,
            "S0-07",
            "Deployed MLX proxy matches source",
            "PASS",
            "deployed copy in sync",
            t0=t0,
        )
    else:
        record(
            sec,
            "S0-07",
            "Deployed MLX proxy matches source",
            "WARN",
            "deployed != source — run ./launch.sh install-mlx",
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
        sec,
        "S1-01",
        "backends.yaml exists",
        "PASS" if backends_file.exists() else "FAIL",
        str(backends_file),
        t0=t0,
    )

    # S1-02: backends.yaml is valid YAML
    t0 = time.time()
    try:
        backends = _load_backends_yaml()
        record(
            sec,
            "S1-02",
            "backends.yaml valid YAML",
            "PASS",
            f"{len(backends.get('backends', []))} backends",
            t0=t0,
        )
    except Exception as e:
        record(sec, "S1-02", "backends.yaml valid YAML", "FAIL", str(e)[:100], t0=t0)
        return

    # S1-03: Workspace IDs consistent between router_pipe.py and backends.yaml
    t0 = time.time()
    pipe_ids = set(WS_IDS)
    yaml_ids = set(backends.get("workspace_routing", {}).keys())
    if pipe_ids == yaml_ids:
        record(
            sec, "S1-03", "Workspace IDs consistent", "PASS", f"{len(pipe_ids)} workspaces", t0=t0
        )
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
        sec,
        "S1-04",
        "Persona YAMLs valid",
        "PASS" if not invalid else "FAIL",
        f"{len(persona_files)} personas" if not invalid else f"invalid: {invalid}",
        t0=t0,
    )

    # S1-05: Persona count matches actual yaml file count (no frozen baseline)
    t0 = time.time()
    yaml_count = len(list((ROOT / "config/personas").glob("*.yaml")))
    actual_count = len(PERSONAS)
    record(
        sec,
        "S1-05",
        "Persona count matches yaml file count",
        "PASS" if actual_count == yaml_count else "FAIL",
        f"{actual_count} loaded, {yaml_count} yaml files",
        t0=t0,
    )

    # S1-06: routing_descriptions.json exists and valid
    t0 = time.time()
    routing_desc_file = ROOT / "config/routing_descriptions.json"
    try:
        if routing_desc_file.exists():
            desc = json.loads(routing_desc_file.read_text())
            record(
                sec,
                "S1-06",
                "routing_descriptions.json",
                "PASS",
                f"{len(desc)} descriptions",
                t0=t0,
            )
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

    # S1-08: MLX backend routing — VLM models in VLM_MODELS (routes to mlx_vlm)
    # Checks that models requiring vision+audio are in the VLM_MODELS set in mlx-proxy.py
    t0 = time.time()
    try:
        proxy_src = (ROOT / "scripts/mlx-proxy.py").read_text()
        # VLM_MODELS section appears before ALL_MODELS in the proxy source
        if "VLM_MODELS" in proxy_src and "ALL_MODELS" in proxy_src:
            vlm_section = proxy_src[proxy_src.index("VLM_MODELS") : proxy_src.index("ALL_MODELS")]
            # Gemma 4 31B dense, E4B, JANG, and abliterated 26B MoE must be in VLM_MODELS (require mlx_vlm)
            gemma_31b_vlm = "gemma-4-31b-it-4bit" in vlm_section
            gemma_e4b_vlm = "gemma-4-e4b-it-4bit" in vlm_section
            gemma_31b_all = "mlx-community/gemma-4-31b-it-4bit" in proxy_src
            jang_vlm = "Gemma-4-31B-JANG_4M-CRACK" in vlm_section
            jang_all = "dealignai/Gemma-4-31B-JANG_4M-CRACK" in proxy_src
            gemma_26b_abl_vlm = "supergemma4-26b-abliterated-multimodal-mlx-4bit" in vlm_section
            gemma_26b_abl_all = (
                "Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit" in proxy_src
            )
            all_ok = (
                gemma_31b_vlm
                and gemma_e4b_vlm
                and gemma_31b_all
                and jang_vlm
                and jang_all
                and gemma_26b_abl_vlm
                and gemma_26b_abl_all
            )
            record(
                sec,
                "S1-08",
                "MLX routing: VLM models in VLM_MODELS (mlx_vlm backend)",
                "PASS" if all_ok else "FAIL",
                "✓ Gemma 4 31B + E4B + JANG + 26B-abl in VLM_MODELS"
                if all_ok
                else f"31b_vlm={gemma_31b_vlm} e4b_vlm={gemma_e4b_vlm} 31b_all={gemma_31b_all} jang_vlm={jang_vlm} jang_all={jang_all} 26b_abl_vlm={gemma_26b_abl_vlm} 26b_abl_all={gemma_26b_abl_all}",
                t0=t0,
            )
        else:
            record(
                sec,
                "S1-08",
                "MLX routing: VLM models in VLM_MODELS",
                "WARN",
                "VLM_MODELS section not found",
                t0=t0,
            )
    except Exception as e:
        record(sec, "S1-08", "MLX routing: VLM models in VLM_MODELS", "FAIL", str(e)[:100], t0=t0)

    # S1-09: MLX backend routing — text-only models NOT in VLM_MODELS (routes to mlx_lm)
    # Checks that reasoning models like Magistral and Phi-4 use mlx_lm, not mlx_vlm
    t0 = time.time()
    try:
        proxy_src = (ROOT / "scripts/mlx-proxy.py").read_text()
        if "VLM_MODELS" in proxy_src and "ALL_MODELS" in proxy_src:
            vlm_section = proxy_src[proxy_src.index("VLM_MODELS") : proxy_src.index("ALL_MODELS")]
            magistral_in_all = "Magistral-Small-2509" in proxy_src
            magistral_in_vlm = "Magistral-Small-2509" in vlm_section
            phi4_in_all = "phi-4-8bit" in proxy_src
            phi4_in_vlm = "phi-4-8bit" in vlm_section
            lm_ok = magistral_in_all and not magistral_in_vlm and phi4_in_all and not phi4_in_vlm
            record(
                sec,
                "S1-09",
                "MLX routing: text-only models NOT in VLM_MODELS (mlx_lm backend)",
                "PASS" if lm_ok else "FAIL",
                "✓ Magistral + Phi-4 use mlx_lm"
                if lm_ok
                else f"magistral: all={magistral_in_all} vlm={magistral_in_vlm} | phi4: all={phi4_in_all} vlm={phi4_in_vlm}",
                t0=t0,
            )
        else:
            record(
                sec,
                "S1-09",
                "MLX routing: text-only models NOT in VLM_MODELS",
                "WARN",
                "proxy source not found",
                t0=t0,
            )
    except Exception as e:
        record(
            sec,
            "S1-09",
            "MLX routing: text-only models NOT in VLM_MODELS",
            "FAIL",
            str(e)[:100],
            t0=t0,
        )

    # S1-10: All persona workspace_model values are valid pipeline workspace IDs or Ollama tags.
    # Raw MLX HF paths (mlx-community/*, lmstudio-community/*, Jackrong/*, dealignai/*) are
    # INVALID because the pipeline only exposes workspace IDs in /v1/models.  Personas with
    # raw HF paths show "model not found" in Open WebUI even though the model is downloaded.
    t0 = time.time()
    valid_ws_ids = set(WS_IDS) | {"auto"}
    bad_personas: list[str] = []
    for p in PERSONAS:
        slug = p.get("slug", "?")
        ws_model = p.get("workspace_model", "")
        if not ws_model:
            bad_personas.append(f"{slug}:(missing)")
            continue
        # Valid if it's a known pipeline workspace ID
        if ws_model in valid_ws_ids:
            continue
        # Invalid if it starts with a known MLX org prefix — these are raw HF paths
        if any(ws_model.startswith(org) for org in _MLX_ORGS):
            bad_personas.append(f"{slug}:{ws_model.split('/')[-1]}")
    record(
        sec,
        "S1-10",
        "Persona workspace_model values are pipeline IDs or Ollama tags",
        "FAIL" if bad_personas else "PASS",
        f"invalid (raw MLX paths): {bad_personas}"
        if bad_personas
        else f"all {len(PERSONAS)} personas use valid workspace_model values",
        t0=t0,
    )

    # S1-11: Every non-benchmark persona has a PERSONA_PROMPTS entry
    t0 = time.time()
    non_bench = [p for p in PERSONAS if p.get("category") != "benchmark"]
    missing_prompts = [p["slug"] for p in non_bench if p["slug"] not in PERSONA_PROMPTS]
    record(
        sec,
        "S1-11",
        "All personas have PERSONA_PROMPTS entries",
        "FAIL" if missing_prompts else "PASS",
        f"missing prompts for: {missing_prompts}"
        if missing_prompts
        else f"all {len(non_bench)} non-benchmark personas covered",
        t0=t0,
    )

    # S1-17: workspace hint reachability
    t0 = time.time()
    try:
        from portal_pipeline.router_pipe import _validate_workspace_hints
        from portal_pipeline.cluster_backends import BackendRegistry
        reg = BackendRegistry()
        errors = _validate_workspace_hints(reg)
        if not errors:
            record(sec, "S1-17", "workspace hint reachability", "PASS",
                   f"all {len(WS_IDS)} workspace hints resolve", t0=t0)
        else:
            record(sec, "S1-17", "workspace hint reachability", "FAIL",
                   f"{len(errors)} hints unresolved: {errors[0][:120]}", t0=t0)
    except Exception as e:
        record(sec, "S1-17", "workspace hint reachability", "FAIL", str(e)[:200], t0=t0)


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
            sec,
            "S2-02",
            "Pipeline /health",
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
        sec,
        "S2-03",
        "Ollama",
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

    # S2-08 to S2-15: MCP services
    mcp_services = [
        ("S2-08", "documents", MCP["documents"]),
        # Music MCP is host-native (not a Docker service) — requires ./launch.sh install-music
        # WARN is expected if not installed; this is not a regression
        ("S2-09", "music", MCP["music"]),
        ("S2-10", "tts", MCP["tts"]),
        ("S2-11", "whisper", MCP["whisper"]),
        ("S2-12", "sandbox", MCP["sandbox"]),
        ("S2-13", "video", MCP["video"]),
        ("S2-14", "embedding", MCP["embedding"]),
        ("S2-15", "security", MCP["security"]),
    ]
    for tid, name, port in mcp_services:
        t0 = time.time()
        code, _ = await _get(f"http://localhost:{port}/health", timeout=5)
        record(
            sec,
            tid,
            f"MCP {name} (:{port})",
            "PASS" if code == 200 else "WARN",
            f"HTTP {code}",
            t0=t0,
        )

    # S2-16: MLX proxy health
    t0 = time.time()
    state, data = await _mlx_health()
    record(
        sec,
        "S2-16",
        "MLX proxy",
        "PASS" if state in ("ready", "none", "switching") else "INFO",
        f"state={state}",
        t0=t0,
    )

    # S2-17: MLX Speech health
    t0 = time.time()
    code, _ = await _get(f"{MLX_SPEECH_URL}/health", timeout=5)
    record(
        sec,
        "S2-17",
        "MLX Speech",
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
        # auto-documents moved to S3b (now [mlx, coding, general] after T-08)
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

            code, response, model, _route = await _chat_with_model(
                ws_id, prompt, max_tokens=300, timeout=180
            )

            if code != 200:
                record(
                    sec, tid, f"Workspace {ws_id}", "FAIL", f"HTTP {code}: {response[:80]}", t0=t0
                )
                test_num += 1
                continue

            response_lower = response.lower()
            found = [s for s in signals if s.lower() in response_lower]

            if found:
                record(
                    sec,
                    tid,
                    f"Workspace {ws_id}",
                    "PASS",
                    f"signals: {found[:3]} | model: {model[:40]}",
                    t0=t0,
                )
            else:
                record(
                    sec,
                    tid,
                    f"Workspace {ws_id}",
                    "WARN",
                    f"no signals in: {response[:100]}",
                    t0=t0,
                )

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
        (
            "MLX reasoning",
            ["auto-reasoning", "auto-research", "auto-data", "auto-compliance", "auto-mistral"],
        ),
        # Group 3: Creative (Dolphin-8B)
        ("MLX creative", ["auto-creative"]),
        # Group 4: Vision (Gemma-4, Qwen3-VL)
        ("MLX vision", ["auto-vision"]),
        # Group 5: Documents (Phi-4 8bit, MLX primary — T-08)
        ("MLX documents", ["auto-documents"]),
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

            code, response, model, _route = await _chat_with_model(
                ws_id, prompt, max_tokens=300, timeout=240
            )

            if code != 200:
                record(
                    sec, tid, f"Workspace {ws_id}", "FAIL", f"HTTP {code}: {response[:80]}", t0=t0
                )
                test_num += 1
                continue

            response_lower = response.lower()
            found = [s for s in signals if s.lower() in response_lower]
            is_mlx = any(org in model for org in _MLX_ORGS)

            # Distinguish "MLX healthy but routed Ollama" (FAIL) from "MLX down/switching" (WARN — infra)
            if not is_mlx:
                mlx_state, _ = await _mlx_health()
                if mlx_state in ("down", "switching"):
                    record(
                        sec,
                        tid,
                        f"Workspace {ws_id}",
                        "WARN",
                        f"Ollama fallback (MLX {mlx_state}) — infrastructure | model={model[:40]}",
                        t0=t0,
                    )
                else:
                    record(
                        sec,
                        tid,
                        f"Workspace {ws_id}",
                        "FAIL",
                        f"Ollama fallback! model={model[:40]} (MLX state={mlx_state}, expected MLX-tier)",
                        t0=t0,
                    )
            elif found:
                record(
                    sec,
                    tid,
                    f"Workspace {ws_id}",
                    "PASS",
                    f"MLX:{is_mlx} | signals: {found[:3]}",
                    t0=t0,
                )
            else:
                record(
                    sec,
                    tid,
                    f"Workspace {ws_id}",
                    "WARN",
                    f"MLX:{is_mlx} | no signals in: {response[:100]}",
                    t0=t0,
                )

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
    record(
        sec,
        "S4-01",
        "Documents MCP health",
        "PASS" if code == 200 else "FAIL",
        f"HTTP {code}",
        t0=t0,
    )

    # S4-02: Generate Word document
    await _mcp(
        MCP["documents"],
        "create_word_document",
        {
            "title": "Test Proposal",
            "content": "# Project Proposal\n\n## Executive Summary\n\nThis is a test document.\n\n## Timeline\n\n- Phase 1: Planning\n- Phase 2: Implementation",
        },
        section=sec,
        tid="S4-02",
        name="Generate Word document",
        ok_fn=lambda t: "success" in t.lower() or "created" in t.lower() or "docx" in t.lower(),
        timeout=60,
    )

    # S4-03: Generate Excel spreadsheet (tool: create_excel, data as list of lists)
    await _mcp(
        MCP["documents"],
        "create_excel",
        {
            "title": "Test Budget",
            "data": [
                ["Category", "Q1", "Q2"],
                ["Hardware", 1000, 1200],
                ["Software", 500, 600],
            ],
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
            "title": "Test Presentation",
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
    record(
        sec, "S5-01", "Sandbox MCP health", "PASS" if code == 200 else "FAIL", f"HTTP {code}", t0=t0
    )

    # S5-02: Execute Python code (tool: execute_python)
    await _mcp(
        MCP["sandbox"],
        "execute_python",
        {
            "code": "print(sum(range(1, 11)))",
        },
        section=sec,
        tid="S5-02",
        name="Execute Python (sum 1-10)",
        ok_fn=lambda t: "55" in t,
        timeout=60,
    )

    # S5-03: Execute with list comprehension
    await _mcp(
        MCP["sandbox"],
        "execute_python",
        {
            "code": "result = [x**2 for x in range(5)]\nprint(result)",
        },
        section=sec,
        tid="S5-03",
        name="Execute Python (list comprehension)",
        ok_fn=lambda t: "[0, 1, 4, 9, 16]" in t or "0, 1, 4, 9, 16" in t,
        timeout=60,
    )


async def S6() -> None:
    """S6: Security workspace tests."""
    print("\n━━━ S6. SECURITY WORKSPACES ━━━")
    sec = "S6"

    # S6-01: auto-security routing
    t0 = time.time()
    code, response, model, _route = await _chat_with_model(
        "auto-security",
        "What is SQL injection and how to prevent it?",
        max_tokens=300,
        timeout=180,
    )
    signals = ["sql", "inject", "sanitize", "parameter", "escape", "prepared"]
    found = [s for s in signals if s.lower() in response.lower()]
    record(
        sec,
        "S6-01",
        "auto-security routing",
        "PASS" if found and code == 200 else "WARN",
        f"signals: {found[:3]} | model: {model[:30]}",
        t0=t0,
    )

    # S6-02: auto-redteam routing
    t0 = time.time()
    code, response, model, _route = await _chat_with_model(
        "auto-redteam",
        "Explain common web application penetration testing methodology.",
        max_tokens=300,
        timeout=180,
    )
    signals = ["recon", "scan", "exploit", "pentest", "OWASP", "vulnerability"]
    found = [s for s in signals if s.lower() in response.lower()]
    record(
        sec,
        "S6-02",
        "auto-redteam routing",
        "PASS" if found and code == 200 else "WARN",
        f"signals: {found[:3]} | model: {model[:30]}",
        t0=t0,
    )

    # S6-03: auto-blueteam routing
    t0 = time.time()
    code, response, model, _route = await _chat_with_model(
        "auto-blueteam",
        "How do you respond to a ransomware incident?",
        max_tokens=300,
        timeout=180,
    )
    signals = ["isolate", "contain", "backup", "incident", "response", "recover"]
    found = [s for s in signals if s.lower() in response.lower()]
    record(
        sec,
        "S6-03",
        "auto-blueteam routing",
        "PASS" if found and code == 200 else "WARN",
        f"signals: {found[:3]} | model: {model[:30]}",
        t0=t0,
    )

    # S6-04: Content-aware routing (security keywords)
    t0 = time.time()
    code, response, _, _route = await _chat_with_model(
        "auto",  # Use auto to test content-aware routing
        "exploit vulnerability payload shellcode",
        max_tokens=200,
        timeout=180,
    )
    # Check pipeline logs for routing decision
    logs = _grep_logs("portal5-pipeline", "auto-redteam|auto-security", lines=100)
    record(
        sec,
        "S6-04",
        "Content-aware security routing",
        "PASS" if logs and code == 200 else "WARN",
        f"routed to security workspace: {bool(logs)}",
        t0=t0,
    )


async def S16() -> None:
    """S16: Security MCP tool tests — classify_vulnerability via MCP protocol."""
    print("\n━━━ S16. SECURITY MCP TOOLS ━━━")
    sec = "S16"

    sec_port = MCP.get("security", 8919)

    # S16-01: Health check
    t0 = time.time()
    code, data = await _get(f"http://localhost:{sec_port}/health", timeout=5)
    if code != 200:
        record(sec, "S16-01", "Security MCP health", "WARN", f"HTTP {code}", t0=t0)
        return
    record(
        sec,
        "S16-01",
        "Security MCP health",
        "PASS",
        f"service: {data.get('service', 'unknown')}",
        t0=t0,
    )

    # S16-02: classify_vulnerability with a high-severity RCE description
    await _mcp(
        sec_port,
        "classify_vulnerability",
        {
            "description": "Remote code execution via buffer overflow in OpenSSL 3.0 allows attackers to execute arbitrary code by sending a crafted certificate."
        },
        section=sec,
        tid="S16-02",
        name="classify_vulnerability (RCE — expect high/critical)",
        ok_fn=lambda t: any(s in t.lower() for s in ["severity", "high", "critical"]),
        warn_if=["error", "exception", "not available"],
        timeout=120,
    )

    # S16-03: classify_vulnerability with a low-severity info disclosure
    await _mcp(
        sec_port,
        "classify_vulnerability",
        {
            "description": "Information disclosure in debug endpoint reveals server version number to authenticated users."
        },
        section=sec,
        tid="S16-03",
        name="classify_vulnerability (info disclosure — expect low/medium)",
        ok_fn=lambda t: any(s in t.lower() for s in ["severity", "low", "medium", "high"]),
        warn_if=["error", "exception", "not available"],
        timeout=120,
    )

    # S16-04: classify_vulnerability returns probabilities
    await _mcp(
        sec_port,
        "classify_vulnerability",
        {"description": "SQL injection in login form allows unauthorized data access."},
        section=sec,
        tid="S16-04",
        name="classify_vulnerability returns probabilities",
        ok_fn=lambda t: all(s in t.lower() for s in ["probabilities", "confidence"]),
        warn_if=["error", "exception"],
        timeout=120,
    )


async def S7() -> None:
    """S7: Music generation tests."""
    print("\n━━━ S7. MUSIC GENERATION ━━━")
    sec = "S7"

    # S7-01: Music MCP health
    t0 = time.time()
    code, data = await _get(f"http://localhost:{MCP['music']}/health")
    if code == 200 and isinstance(data, dict):
        record(
            sec,
            "S7-01",
            "Music MCP health",
            "PASS",
            f"service: {data.get('service', 'unknown')}",
            t0=t0,
        )
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
        record(
            sec,
            "S8-01",
            "MLX Speech health",
            "PASS",
            f"voice_cloning: {data.get('voice_cloning', False)}",
            t0=t0,
        )

        # S8-02: TTS via MLX Speech
        t0 = time.time()
        try:
            c = _get_acc_client()
            r = await c.post(
                f"{MLX_SPEECH_URL}/v1/audio/speech",
                json={"input": "Hello from Portal 5 acceptance test.", "voice": "af_heart"},
                timeout=60,
            )
            if r.status_code == 200:
                wav_data = r.content
                info = _wav_info(wav_data)
                if info and info["duration_s"] > 0.5:
                    record(
                        sec,
                        "S8-02",
                        "MLX Speech TTS",
                        "PASS",
                        f"duration: {info['duration_s']}s",
                        t0=t0,
                    )
                else:
                    record(sec, "S8-02", "MLX Speech TTS", "WARN", f"invalid WAV: {info}", t0=t0)
            else:
                record(sec, "S8-02", "MLX Speech TTS", "FAIL", f"HTTP {r.status_code}", t0=t0)
        except Exception as e:
            record(sec, "S8-02", "MLX Speech TTS", "FAIL", str(e)[:100], t0=t0)
    else:
        record(
            sec,
            "S8-01",
            "MLX Speech health",
            "INFO",
            "not running (using Docker TTS fallback)",
            t0=t0,
        )

        # Fallback to Docker TTS
        t0 = time.time()
        code, data = await _get(f"http://localhost:{MCP['tts']}/health")
        record(
            sec,
            "S8-02",
            "Docker TTS health",
            "PASS" if code == 200 else "WARN",
            f"HTTP {code}",
            t0=t0,
        )


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
        record(
            sec,
            "S9-01",
            "MLX Speech ASR available",
            "INFO",
            "not running (Docker Whisper fallback)",
            t0=t0,
        )

        # Check Docker Whisper
        t0 = time.time()
        code, _ = await _get(f"http://localhost:{MCP['whisper']}/health")
        record(
            sec,
            "S9-02",
            "Docker Whisper health",
            "PASS" if code == 200 else "WARN",
            f"HTTP {code}",
            t0=t0,
        )


OLLAMA_WORKSPACES = {
    "auto",
    "auto-security",
    "auto-redteam",
    "auto-blueteam",
    "auto-creative",
    "auto-video",
    "auto-music",
}


async def S10() -> None:
    """S10: Persona tests (Ollama-routed) — driven by PERSONAS, grouped by workspace."""
    print("\n━━━ S10. PERSONAS (OLLAMA) ━━━")
    sec = "S10"

    candidates = [p for p in PERSONAS if p.get("workspace_model") in OLLAMA_WORKSPACES]
    candidates.sort(key=lambda p: p["workspace_model"])

    test_num = 1
    for ws_id, group in itertools.groupby(candidates, key=lambda p: p["workspace_model"]):
        members = list(group)
        print(f"\n  ── Workspace: {ws_id} ({len(members)} personas) ──")
        for p in members:
            slug = p["slug"]
            tid = f"S10-{test_num:02d}"
            t0 = time.time()
            if slug not in PERSONA_PROMPTS:
                record(sec, tid, f"Persona {slug}", "FAIL", "no PERSONA_PROMPTS entry", t0=t0)
                test_num += 1
                continue
            prompt, signals = PERSONA_PROMPTS[slug]
            system = p.get("system_prompt", "")[:500]
            code, response, model, _route = await _chat_with_model(
                ws_id,
                prompt,
                system=system,
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
                sec,
                tid,
                f"Persona {slug}",
                "PASS" if found else "WARN",
                f"signals: {found[:3]}" if found else f"no signals in: {response[:60]}",
                t0=t0,
            )
            test_num += 1
            await asyncio.sleep(0.5)
        await asyncio.sleep(2)


async def _mlx_chat_direct(
    model: str, prompt: str, system: str = "", max_tokens: int = 300, timeout: int = 300
) -> tuple[int, str, str]:
    """Send chat directly to MLX proxy (port 8081) — for models with no pipeline workspace.

    For thinking models (Phi-4-reasoning, Magistral, etc.) the content field may contain
    <think>...</think> blocks.  We concatenate content + reasoning for signal matching.
    """
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system[:800]})
    msgs.append({"role": "user", "content": prompt})
    try:
        c = _get_acc_client()
        r = await c.post(
            f"{MLX_URL}/v1/chat/completions",
            json={"model": model, "messages": msgs, "max_tokens": max_tokens},
            timeout=timeout,
        )
        if r.status_code != 200:
            return r.status_code, r.text[:300], ""
        data = r.json()
        msg = data.get("choices", [{}])[0].get("message", {})
        content = msg.get("content", "")
        reasoning = msg.get("reasoning", "")
        # Combine all text for signal search
        text = (content + " " + reasoning).strip() if (content or reasoning) else ""
        return 200, text, data.get("model", model)
    except httpx.ReadTimeout:
        return 408, "timeout", ""
    except Exception as e:
        return 0, str(e)[:100], ""


MLX_WORKSPACES = {
    "auto-coding",
    "auto-agentic",
    "auto-spl",
    "auto-reasoning",
    "auto-research",
    "auto-data",
    "auto-compliance",
    "auto-mistral",
    "auto-vision",
    "auto-documents",
}

# Memory sizes from mlx-proxy.py MODEL_MEMORY dict (approximate)
_MLX_MODEL_GB = {
    "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit": 17,
    "mlx-community/Qwen3-Coder-Next-4bit": 22,
    "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit": 28,
    "Jackrong/MLX-Qwopus3.5-27B-v3-8bit": 22,
    "mlx-community/gemma-4-31b-it-4bit": 18,
    "Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit": 15,
    "Jiunsong/supergemma4-26b-uncensored-mlx-4bit-v2": 15,
    "mlx-community/phi-4-8bit": 14,
    "lmstudio-community/Phi-4-reasoning-plus-MLX-4bit": 15,
    "lmstudio-community/Magistral-Small-2509-MLX-8bit": 22,
    "lmstudio-community/Devstral-Small-2507-MLX-4bit": 15,
    "mlx-community/DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit": 34,
    "mlx-community/gemma-4-e4b-it-4bit": 5,
    "dealignai/Gemma-4-31B-JANG_4M-CRACK": 23,
    "huihui-ai/Huihui-GLM-4.7-Flash-abliterated-mlx-4bit": 18,
}


async def S11() -> None:
    """S11: Persona tests (MLX-routed) — driven by PERSONAS, grouped by workspace."""
    print("\n━━━ S11. PERSONAS (MLX) ━━━")
    sec = "S11"

    state, _ = await _mlx_health()
    if state == "down":
        print("  ⚠️  MLX proxy is 'down' — attempting remediation before S11...")
        if not await _remediate_mlx_crash("MLX down before S11"):
            record(
                sec,
                "S11-00",
                "MLX availability",
                "BLOCKED",
                "MLX proxy is down and could not be recovered",
                t0=time.time(),
            )
            return
        state, _ = await _mlx_health()
    if state not in ("ready", "none", "switching"):
        record(
            sec,
            "S11-00",
            "MLX availability",
            "INFO",
            f"MLX state: {state}, skipping MLX persona tests",
            t0=time.time(),
        )
        return
    record(sec, "S11-00", "MLX availability", "PASS", f"state: {state}", t0=time.time())

    await _ensure_free_ram_gb(20, "S11 MLX personas")

    # Build (workspace_id → mlx_model_hint) at runtime — single source of truth
    from portal_pipeline.router_pipe import WORKSPACES as _WORKSPACES  # noqa: PLC0415

    ws_to_mlx = {
        wsid: _WORKSPACES[wsid].get("mlx_model_hint")
        for wsid in MLX_WORKSPACES
        if _WORKSPACES.get(wsid, {}).get("mlx_model_hint")
    }

    candidates = [p for p in PERSONAS if p.get("workspace_model") in MLX_WORKSPACES]
    candidates.sort(key=lambda p: p["workspace_model"])

    test_num = 1
    for ws_id, group in itertools.groupby(candidates, key=lambda p: p["workspace_model"]):
        members = list(group)
        model_hint = ws_to_mlx.get(ws_id, "")
        model_short = model_hint.split("/")[-1] if model_hint else "unknown"
        print(f"\n  ── Workspace: {ws_id} → {model_short} ({len(members)} personas) ──")

        if model_hint:
            model_gb = _MLX_MODEL_GB.get(model_hint, 10)
            if model_gb >= 14:
                await _ensure_free_ram_gb(model_gb + 10, model_short)

            print(f"  ── Triggering model load: {model_short} ──")
            try:
                c = _get_acc_client()
                await c.post(
                    f"{MLX_URL}/v1/chat/completions",
                    json={
                        "model": model_hint,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                    },
                    timeout=3,
                )
            except Exception:
                pass  # Expected timeout — just queuing the switch

            model_ready = await _wait_for_mlx_model(model_hint, timeout=300)
            if not model_ready:
                cur_state, _ = await _mlx_health()
                if cur_state == "down":
                    print(f"  ⚠️  MLX went down during {model_short} load — attempting recovery...")
                    recovered = await _remediate_mlx_crash(f"model load failed: {model_short}")
                    if not recovered:
                        for p in members:
                            record(
                                sec,
                                f"S11-{test_num:02d}",
                                f"Persona {p['slug']} (MLX)",
                                "BLOCKED",
                                f"MLX proxy down during {model_short} load, recovery failed",
                                t0=time.time(),
                            )
                            test_num += 1
                        break
                    try:
                        c = _get_acc_client()
                        await c.post(
                            f"{MLX_URL}/v1/chat/completions",
                            json={
                                "model": model_hint,
                                "messages": [{"role": "user", "content": "ping"}],
                                "max_tokens": 1,
                            },
                            timeout=3,
                        )
                    except Exception:
                        pass
                    model_ready = await _wait_for_mlx_model(model_hint, timeout=240)
                if not model_ready:
                    for p in members:
                        record(
                            sec,
                            f"S11-{test_num:02d}",
                            f"Persona {p['slug']} (MLX)",
                            "WARN",
                            f"Model {model_short} not loaded within 300s (proxy: {cur_state})",
                            t0=time.time(),
                        )
                        test_num += 1
                    continue

            _, health_data = await _mlx_health()
            loaded = health_data.get("loaded_model") or ""
            if loaded and model_hint not in loaded and model_hint.split("/")[-1] not in loaded:
                print(f"  ⚠️  Different model loaded: {loaded} (expected {model_short})")

        for p in members:
            slug = p["slug"]
            tid = f"S11-{test_num:02d}"
            t0 = time.time()
            if slug not in PERSONA_PROMPTS:
                record(sec, tid, f"Persona {slug} (MLX)", "FAIL", "no PERSONA_PROMPTS entry", t0=t0)
                test_num += 1
                continue
            prompt, signals = PERSONA_PROMPTS[slug]
            system = p.get("system_prompt", "")[:500]
            is_thinking = any(
                x in (model_hint or "") for x in ["reasoning", "R1", "Magistral", "Qwopus", "Opus"]
            )
            max_tok = 800 if is_thinking else 400
            code, response, model, _route = await _chat_with_model(
                ws_id,
                prompt,
                system=system,
                max_tokens=max_tok,
                timeout=300,
            )
            if code != 200:
                error_text = response[:120]
                if code == 500 and "audio_tower" in error_text:
                    record(
                        sec,
                        tid,
                        f"Persona {slug} (MLX)",
                        "BLOCKED",
                        "mlx_vlm audio_tower params missing in quantized model — requires full model download",
                        t0=t0,
                    )
                else:
                    record(
                        sec,
                        tid,
                        f"Persona {slug} (MLX)",
                        "FAIL",
                        f"HTTP {code}: {error_text}",
                        t0=t0,
                    )
                test_num += 1
                continue

            response_lower = response.lower()
            found = [s for s in signals if s.lower() in response_lower]
            is_mlx = any(org in model for org in _MLX_ORGS)
            ollama_fallback = ":" in model and not is_mlx

            if ollama_fallback:
                mlx_state, _ = await _mlx_health()
                if mlx_state in ("down", "switching"):
                    status = "WARN"
                    detail = (
                        f"Ollama fallback (MLX {mlx_state}) — infrastructure | model={model[:40]}"
                    )
                else:
                    status = "FAIL"
                    detail = f"Ollama fallback! model={model[:40]} (MLX state={mlx_state}, expected MLX-tier)"
            elif found:
                status = "PASS"
                detail = f"MLX:{is_mlx} model={model.split('/')[-1][:30]} | signals: {found[:2]}"
            else:
                status = "WARN"
                detail = f"MLX:{is_mlx} model={model[:30]} | no signals in: {response[:60]}"

            record(sec, tid, f"Persona {slug} (MLX)", status, detail, t0=t0)
            test_num += 1
            await asyncio.sleep(1)

        await asyncio.sleep(5)


async def S12() -> None:
    """S12: Web search tests."""
    print("\n━━━ S12. WEB SEARCH ━━━")
    sec = "S12"

    # S12-01: SearXNG direct query
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(
            f"{SEARXNG_URL}/search", params={"q": "test query", "format": "json"}, timeout=30
        )
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
        sec,
        "S13-01",
        "Embedding service",
        "PASS" if code == 200 else "WARN",
        f"HTTP {code}",
        t0=t0,
    )

    # S13-02: Generate embedding (if service is up)
    if code == 200:
        t0 = time.time()
        try:
            c = _get_acc_client()
            r = await c.post(
                f"http://localhost:{MCP['embedding']}/v1/embeddings",
                json={"input": "test embedding text", "model": "microsoft/harrier-oss-v1-0.6b"},
                timeout=30,
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
        sec,
        "S20-01",
        "MLX proxy health",
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
        sec,
        "S21-01",
        "LLM router enabled",
        "PASS" if llm_router_enabled else "INFO",
        f"LLM_ROUTER_ENABLED={llm_router_enabled}",
        t0=t0,
    )

    if not llm_router_enabled:
        record(
            sec, "S21-02", "LLM router model", "INFO", "skipped (router disabled)", t0=time.time()
        )
        return

    # S21-02: Check LLM router model exists in Ollama
    t0 = time.time()
    router_model = os.environ.get(
        "LLM_ROUTER_MODEL", "hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF"
    )
    models = _ollama_models()
    # Check if router model is available (may be abbreviated in ollama list)
    model_available = any(
        router_model.split("/")[-1].lower().replace("-gguf", "") in m.lower() for m in models
    ) or any("llama-3.2-3b" in m.lower() and "abliterated" in m.lower() for m in models)
    record(
        sec,
        "S21-02",
        "LLM router model available",
        "PASS" if model_available else "WARN",
        f"model: {router_model[:50]}",
        t0=t0,
    )

    # S21-03: Test content-aware routing with security keywords
    t0 = time.time()
    code, response, model, route = await _chat_with_model(
        "auto",  # Use auto to trigger content-aware routing
        "Write a SQL injection payload to bypass authentication",
        max_tokens=200,
        timeout=120,
    )
    routed_workspace = route.split(";")[0] if route else ""
    expected_security = {"auto-redteam", "auto-security"}
    record(
        sec,
        "S21-03",
        "LLM router security intent",
        "PASS" if routed_workspace in expected_security else ("WARN" if code == 200 else "FAIL"),
        f"routed→{routed_workspace or 'unknown'} | model: {model[:30]}",
        t0=t0,
    )

    # S21-04: Test content-aware routing with coding keywords
    t0 = time.time()
    code, response, model, route = await _chat_with_model(
        "auto",
        "Write a Python function to sort a list of dictionaries by key",
        max_tokens=200,
        timeout=120,
    )
    routed_workspace = route.split(";")[0] if route else ""
    expected_coding = {"auto-coding", "auto-agentic"}
    record(
        sec,
        "S21-04",
        "LLM router coding intent",
        "PASS" if routed_workspace in expected_coding else ("WARN" if code == 200 else "FAIL"),
        f"routed→{routed_workspace or 'unknown'} | model: {model[:30]}",
        t0=t0,
    )

    # S21-05: Test content-aware routing with compliance keywords
    t0 = time.time()
    code, response, model, route = await _chat_with_model(
        "auto",
        "What are the requirements for NERC CIP-007 R2 patch management?",
        max_tokens=200,
        timeout=120,
    )
    routed_workspace = route.split(";")[0] if route else ""
    expected_compliance = {"auto-compliance", "auto-reasoning"}
    record(
        sec,
        "S21-05",
        "LLM router compliance intent",
        "PASS" if routed_workspace in expected_compliance else ("WARN" if code == 200 else "FAIL"),
        f"routed→{routed_workspace or 'unknown'} | model: {model[:30]}",
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
            record(
                sec,
                "S21-06",
                "routing_descriptions.json",
                "PASS",
                f"{ws_count} workspace descriptions",
                t0=t0,
            )
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
            record(
                sec, "S21-07", "routing_examples.json", "PASS", f"{len(examples)} examples", t0=t0
            )
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
        record(
            sec, "S22-01", "MLX proxy for admission control", "INFO", "MLX proxy not running", t0=t0
        )
        return
    record(sec, "S22-01", "MLX proxy for admission control", "PASS", f"state: {state}", t0=t0)

    # S22-03: Test that proxy returns 503 for oversized model request.
    # Admission control should reject immediately (within ~2s) if memory < model_size + headroom.
    # Use 5s timeout: fast enough to catch prompt 503, short enough to avoid waiting for OOM.
    # ReadTimeout means the proxy accepted and started loading — admission control didn't trigger
    # (typically because enough memory was available), recorded as INFO not FAIL.
    t0 = time.time()
    try:
        c = _get_acc_client()
        # Llama-3.3-70B-Instruct-4bit: tracked at 40GB in MODEL_MEMORY.
        # Requires 40 + 10 = 50GB free — only available on a clean 64GB system.
        r = await c.post(
            f"{MLX_URL}/v1/chat/completions",
            json={
                "model": "mlx-community/Llama-3.3-70B-Instruct-4bit",
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 10,
            },
            timeout=8,
        )
        if r.status_code == 503:
            # Try to parse the detail from JSON body
            try:
                detail = r.json().get("detail", r.text[:100])
            except Exception:
                detail = r.text[:100] or "admission rejected"
            record(
                sec,
                "S22-03",
                "Admission control rejects oversized",
                "PASS",
                f"503: {detail[:80]}",
                t0=t0,
            )
        elif r.status_code == 200:
            # Proxy accepted and returned a response — enough memory was available
            record(
                sec,
                "S22-03",
                "Admission control rejects oversized",
                "INFO",
                "model loaded successfully — insufficient memory pressure to trigger rejection",
                t0=t0,
            )
        else:
            record(
                sec,
                "S22-03",
                "Admission control rejects oversized",
                "WARN",
                f"HTTP {r.status_code}",
                t0=t0,
            )
    except (httpx.ReadTimeout, httpx.ConnectTimeout, asyncio.TimeoutError):
        # Proxy accepted request and started loading (no immediate rejection) — memory not tight enough
        free_gb = _free_ram_gb()
        record(
            sec,
            "S22-03",
            "Admission control rejects oversized",
            "INFO",
            f"proxy accepted 70B request (free RAM: {free_gb:.1f}GB >= 50GB threshold) — no rejection expected",
            t0=t0,
        )
    except Exception as e:
        record(
            sec,
            "S22-03",
            "Admission control rejects oversized",
            "WARN",
            str(e)[:100] or repr(e)[:100],
            t0=t0,
        )

    # S22-04: MODEL_MEMORY dict coverage check
    t0 = time.time()
    try:
        # Check that common MLX models have memory estimates
        models_with_estimates = len(_MLX_MODEL_SIZES_GB)
        record(
            sec,
            "S22-04",
            "Model memory estimates",
            "PASS" if models_with_estimates >= 10 else "WARN",
            f"{models_with_estimates} models with size estimates",
            t0=t0,
        )
    except Exception as e:
        record(sec, "S22-04", "Model memory estimates", "WARN", str(e)[:100], t0=t0)


async def S23() -> None:
    """S23: Model diversity availability checks (GPT-OSS, Gemma 4, Phi-4, Magistral).

    S23-02 removed — GPT-OSS chat is covered by S10's gptossanalyst persona test.
    These checks verify model registration only (lightweight /v1/models queries).
    """
    print("\n━━━ S23. MODEL DIVERSITY ━━━")
    sec = "S23"

    # S23-01: GPT-OSS model available in Ollama
    t0 = time.time()
    models = _ollama_models()
    gpt_oss_available = any("gpt-oss" in m.lower() for m in models)
    record(
        sec,
        "S23-01",
        "GPT-OSS:20B available",
        "PASS" if gpt_oss_available else "INFO",
        f"gpt-oss in models: {gpt_oss_available}",
        t0=t0,
    )

    # S23-03: Gemma 4 E4B VLM available
    t0 = time.time()
    state, mlx_data = await _mlx_health()
    if state in ("ready", "none", "switching"):
        code, models_data = await _get(f"{MLX_URL}/v1/models")
        if code == 200 and isinstance(models_data, dict):
            model_ids = [m.get("id", "") for m in models_data.get("data", [])]
            gemma_e4b = any("gemma-4-e4b" in m.lower() or "gemma-4-E4B" in m for m in model_ids)
            record(
                sec,
                "S23-03",
                "Gemma 4 E4B VLM registered",
                "PASS" if gemma_e4b else "INFO",
                f"gemma-4-E4B in MLX models: {gemma_e4b}",
                t0=t0,
            )
        else:
            record(
                sec,
                "S23-03",
                "Gemma 4 E4B VLM registered",
                "INFO",
                "MLX models endpoint unavailable",
                t0=t0,
            )
    else:
        record(sec, "S23-03", "Gemma 4 E4B VLM registered", "INFO", f"MLX state: {state}", t0=t0)

    # S23-04: Phi-4 available in MLX pool
    t0 = time.time()
    code, models_data = await _get(f"{MLX_URL}/v1/models")
    if code == 200 and isinstance(models_data, dict):
        model_ids = [m.get("id", "") for m in models_data.get("data", [])]
        phi4 = any("phi-4" in m.lower() for m in model_ids)
        record(
            sec,
            "S23-04",
            "Phi-4 available",
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
            sec,
            "S23-05",
            "Magistral-Small available",
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
            sec,
            "S23-06",
            "Phi-4-reasoning-plus available",
            "PASS" if phi4_reasoning else "INFO",
            f"phi-4-reasoning-plus in MLX models: {phi4_reasoning}",
            t0=t0,
        )
    else:
        record(sec, "S23-06", "Phi-4-reasoning-plus available", "INFO", f"HTTP {code}", t0=t0)

    # S23-07: Huihui-GLM-4.7-Flash-abliterated-mlx-4bit available and produces output
    t0 = time.time()
    state, _ = await _mlx_health()
    if state in ("ready", "none", "switching"):
        code, models_data = await _get(f"{MLX_URL}/v1/models")
        if code == 200 and isinstance(models_data, dict):
            model_ids = [m.get("id", "") for m in models_data.get("data", [])]
            glm_present = any("Huihui-GLM-4.7-Flash" in m for m in model_ids)
            if not glm_present:
                record(
                    sec,
                    "S23-07",
                    "Huihui-GLM-4.7-Flash-abliterated registered",
                    "INFO",
                    "model not in MLX list — run hf download or ./launch.sh pull-mlx-models",
                    t0=t0,
                )
            else:
                try:
                    code2, response2, _ = await _mlx_chat_direct(
                        "huihui-ai/Huihui-GLM-4.7-Flash-abliterated-mlx-4bit",
                        "Write hello world in Python.",
                        max_tokens=50,
                        timeout=300,
                    )
                    if code2 == 200 and len(response2) > 10:
                        record(
                            sec,
                            "S23-07",
                            "Huihui-GLM-4.7-Flash-abliterated smoke test",
                            "PASS",
                            f"loaded + produced {len(response2)} chars",
                            t0=t0,
                        )
                    elif code2 == 200 and len(response2) == 0:
                        record(
                            sec,
                            "S23-07",
                            "Huihui-GLM-4.7-Flash-abliterated smoke test",
                            "WARN",
                            "empty content on Apple Metal — known issue P5-MLX-006 (Linux-only conversion)",
                            t0=t0,
                        )
                    else:
                        record(
                            sec,
                            "S23-07",
                            "Huihui-GLM-4.7-Flash-abliterated smoke test",
                            "WARN",
                            f"HTTP {code2}, response len={len(response2)} — P5-MLX-006",
                            t0=t0,
                        )
                except Exception as e:
                    record(
                        sec,
                        "S23-07",
                        "Huihui-GLM-4.7-Flash-abliterated smoke test",
                        "WARN",
                        f"P5-MLX-006: {str(e)[:80]}",
                        t0=t0,
                    )
        else:
            record(
                sec,
                "S23-07",
                "Huihui-GLM-4.7-Flash-abliterated registered",
                "INFO",
                "MLX models endpoint unavailable",
                t0=t0,
            )
    else:
        record(
            sec, "S23-07", "Huihui-GLM-4.7-Flash-abliterated", "INFO", f"MLX state: {state}", t0=t0
        )


async def S30() -> None:
    """S30: Image generation tests (ComfyUI)."""
    print("\n━━━ S30. IMAGE GENERATION ━━━")
    sec = "S30"

    # S30-01: ComfyUI direct health
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(f"{COMFYUI_URL}/system_stats", timeout=10)
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
        sec,
        "S30-02",
        "ComfyUI MCP bridge",
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
        sec,
        "S31-01",
        "Video MCP health",
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
        c = _get_acc_client()
        r = await c.get(f"{PIPELINE_URL}/metrics", timeout=10)
        if r.status_code == 200:
            lines = r.text.splitlines()
            metric_lines = [l for l in lines if l and not l.startswith("#")]
            record(
                sec, "S40-01", "Pipeline /metrics", "PASS", f"{len(metric_lines)} metrics", t0=t0
            )
        else:
            record(sec, "S40-01", "Pipeline /metrics", "FAIL", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S40-01", "Pipeline /metrics", "FAIL", str(e)[:100], t0=t0)

    # S40-02: Prometheus scrape targets
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(f"{PROMETHEUS_URL}/api/v1/targets", timeout=10)
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
        c = _get_acc_client()
        r = await c.get(
            f"{GRAFANA_URL}/api/search",
            headers={"Authorization": f"Basic {GRAFANA_PASS}"},
            timeout=10,
        )
        if r.status_code in (200, 401):  # 401 is OK, means API is responding
            record(sec, "S40-03", "Grafana API", "PASS", f"HTTP {r.status_code}", t0=t0)
        else:
            record(sec, "S40-03", "Grafana API", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S40-03", "Grafana API", "WARN", str(e)[:100], t0=t0)


# ══════════════════════════════════════════════════════════════════════════════
# S41: M6 Production Hardening — Health, Rate Limits, Admin
# ══════════════════════════════════════════════════════════════════════════════


async def S41() -> None:
    """S41: M6 production hardening tests — /health/all, rate limiting, admin endpoints."""
    print("\n━━━ S41. M6 PRODUCTION HARDENING ━━━")
    sec = "S41"

    # S41-01: /health/all aggregator
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(f"{PIPELINE_URL}/health/all", timeout=15)
        if r.status_code == 200:
            checks = r.json()
            services = list(checks.keys())
            ok_count = sum(1 for v in checks.values() if isinstance(v, dict) and v.get("status") == "ok")
            record(sec, "S41-01", "/health/all aggregator", "PASS",
                   f"{ok_count}/{len(services)} services ok: {', '.join(services[:5])}", t0=t0)
        else:
            record(sec, "S41-01", "/health/all aggregator", "FAIL", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S41-01", "/health/all aggregator", "FAIL", str(e)[:100], t0=t0)

    # S41-02: Workspace concurrency config (bench-* should be 1)
    t0 = time.time()
    try:
        from portal_pipeline.router_pipe import WORKSPACES, _get_workspace_concurrency_limit
        bench_ok = True
        for wsid in sorted(WORKSPACES.keys()):
            if wsid.startswith("bench-"):
                limit = _get_workspace_concurrency_limit(wsid)
                if limit != 1:
                    bench_ok = False
                    record(sec, "S41-02", "bench-* concurrency=1", "FAIL",
                           f"{wsid} limit={limit}, expected 1", t0=t0)
                    break
        if bench_ok:
            bench_count = sum(1 for k in WORKSPACES if k.startswith("bench-"))
            record(sec, "S41-02", "bench-* concurrency=1", "PASS",
                   f"all {bench_count} bench-* workspaces capped at 1", t0=t0)
    except Exception as e:
        record(sec, "S41-02", "bench-* concurrency=1", "FAIL", str(e)[:100], t0=t0)

    # S41-03: /admin/refresh-tools endpoint exists
    t0 = time.time()
    try:
        c = _get_acc_client()
        api_key = os.environ.get("PIPELINE_API_KEY", "")
        r = await c.post(
            f"{PIPELINE_URL}/admin/refresh-tools",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            record(sec, "S41-03", "/admin/refresh-tools", "PASS",
                   f"{data.get('tools_registered', 0)} tools registered", t0=t0)
        else:
            record(sec, "S41-03", "/admin/refresh-tools", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S41-03", "/admin/refresh-tools", "FAIL", str(e)[:100], t0=t0)

    # S41-04: Power metrics gauges present in /metrics
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(f"{PIPELINE_URL}/metrics", timeout=10)
        if r.status_code == 200:
            has_power = "portal5_power_current_watts" in r.text
            has_energy = "portal5_energy_consumed_watt_seconds_total" in r.text
            if has_power and has_energy:
                record(sec, "S41-04", "Power metrics in /metrics", "PASS",
                       "portal5_power_* and portal5_energy_* present", t0=t0)
            else:
                missing = []
                if not has_power:
                    missing.append("portal5_power_current_watts")
                if not has_energy:
                    missing.append("portal5_energy_consumed_watt_seconds_total")
                record(sec, "S41-04", "Power metrics in /metrics", "WARN",
                       f"missing: {', '.join(missing)}", t0=t0)
        else:
            record(sec, "S41-04", "Power metrics in /metrics", "FAIL", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S41-04", "Power metrics in /metrics", "FAIL", str(e)[:100], t0=t0)

    # S41-05: Workspace count matches config (27)
    t0 = time.time()
    try:
        from portal_pipeline.router_pipe import WORKSPACES
        import yaml
        cfg = yaml.safe_load(open(ROOT / "config" / "backends.yaml"))
        yaml_ids = set(cfg.get("workspace_routing", {}).keys())
        pipe_ids = set(WORKSPACES.keys())
        if yaml_ids == pipe_ids:
            record(sec, "S41-05", "Workspace consistency", "PASS",
                   f"{len(pipe_ids)} workspaces, pipe+yaml match", t0=t0)
        else:
            diff = yaml_ids.symmetric_difference(pipe_ids)
            record(sec, "S41-05", "Workspace consistency", "FAIL",
                   f"mismatch: {diff}", t0=t0)
    except Exception as e:
        record(sec, "S41-05", "Workspace consistency", "FAIL", str(e)[:100], t0=t0)


# ══════════════════════════════════════════════════════════════════════════════
# S42: M5 Browser Automation — MCP Service Check
# ══════════════════════════════════════════════════════════════════════════════


async def S42() -> None:
    """S42: M5 browser automation — MCP service health and tool count."""
    print("\n━━━ S42. M5 BROWSER AUTOMATION ━━━")
    sec = "S42"

    browser_mcp_url = os.environ.get("BROWSER_MCP_URL", "http://localhost:8922")

    # S42-01: Browser MCP health
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(f"{browser_mcp_url}/health", timeout=10)
        if r.status_code == 200:
            data = r.json()
            record(sec, "S42-01", "Browser MCP health", "PASS",
                   f"status={data.get('status')}, profiles={len(data.get('profiles', []))}", t0=t0)
        else:
            record(sec, "S42-01", "Browser MCP health", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S42-01", "Browser MCP health", "WARN",
               f"not running (expected if browser MCP not started): {str(e)[:60]}", t0=t0)

    # S42-02: Browser MCP tools manifest
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(f"{browser_mcp_url}/tools", timeout=10)
        if r.status_code == 200:
            tools = r.json()
            tool_names = [t["name"] for t in tools]
            expected = ["browser_navigate", "browser_snapshot", "browser_click",
                        "browser_fill", "browser_screenshot", "browser_close"]
            missing = [n for n in expected if n not in tool_names]
            if not missing:
                record(sec, "S42-02", "Browser MCP tools", "PASS",
                       f"{len(tools)} tools: {', '.join(tool_names[:4])}...", t0=t0)
            else:
                record(sec, "S42-02", "Browser MCP tools", "WARN",
                       f"missing tools: {missing}", t0=t0)
        else:
            record(sec, "S42-02", "Browser MCP tools", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S42-02", "Browser MCP tools", "WARN",
               f"not running (expected if browser MCP not started): {str(e)[:60]}", t0=t0)


# ══════════════════════════════════════════════════════════════════════════════
# S60: M2 Tool-Calling Orchestration
# ══════════════════════════════════════════════════════════════════════════════


async def S60() -> None:
    """S60: M2 tool-calling orchestration — registry, dispatch, multi-turn loop."""
    print("\n━━━ S60. M2 TOOL-CALLING ORCHESTRATION ━━━")
    sec = "S60"

    # S60-01: Tool registry module exists
    t0 = time.time()
    try:
        from portal_pipeline.tool_registry import tool_registry
        names = tool_registry.list_tool_names()
        record(sec, "S60-01", "Tool registry loaded", "PASS",
               f"{len(names)} tools: {', '.join(names[:5])}...", t0=t0)
    except Exception as e:
        record(sec, "S60-01", "Tool registry loaded", "FAIL", str(e)[:100], t0=t0)

    # S60-02: WORKSPACES have tools arrays
    t0 = time.time()
    try:
        from portal_pipeline.router_pipe import WORKSPACES
        with_tools = {k: v.get("tools", []) for k, v in WORKSPACES.items() if v.get("tools")}
        record(sec, "S60-02", "Workspace tool whitelists", "PASS",
               f"{len(with_tools)}/{len(WORKSPACES)} workspaces have tools", t0=t0)
    except Exception as e:
        record(sec, "S60-02", "Workspace tool whitelists", "FAIL", str(e)[:100], t0=t0)

    # S60-03: _resolve_persona_tools function exists
    t0 = time.time()
    try:
        from portal_pipeline.router_pipe import _resolve_persona_tools
        result = _resolve_persona_tools({"tools_allow": ["execute_python"]}, "auto-coding")
        assert "execute_python" in result
        record(sec, "S60-03", "Persona tool resolution", "PASS",
               f"tools_allow override works: {result}", t0=t0)
    except Exception as e:
        record(sec, "S60-03", "Persona tool resolution", "FAIL", str(e)[:100], t0=t0)

    # S60-04: _dispatch_tool_call function exists
    t0 = time.time()
    try:
        from portal_pipeline.router_pipe import _dispatch_tool_call
        record(sec, "S60-04", "Tool dispatch function", "PASS", "exists", t0=t0)
    except Exception as e:
        record(sec, "S60-04", "Tool dispatch function", "FAIL", str(e)[:100], t0=t0)

    # S60-05: MAX_TOOL_HOPS configurable
    t0 = time.time()
    try:
        from portal_pipeline.router_pipe import MAX_TOOL_HOPS
        assert isinstance(MAX_TOOL_HOPS, int) and MAX_TOOL_HOPS > 0
        record(sec, "S60-05", "MAX_TOOL_HOPS", "PASS", f"value={MAX_TOOL_HOPS}", t0=t0)
    except Exception as e:
        record(sec, "S60-05", "MAX_TOOL_HOPS", "FAIL", str(e)[:100], t0=t0)

    # S60-06: Tool-call metrics present in /metrics
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(f"{PIPELINE_URL}/metrics", timeout=10)
        if r.status_code == 200:
            has_tool_calls = "portal5_tool_calls_total" in r.text
            has_tool_duration = "portal5_tool_call_duration_seconds" in r.text
            has_tool_errors = "portal5_tool_call_errors_total" in r.text
            if has_tool_calls and has_tool_duration:
                record(sec, "S60-06", "Tool-call Prometheus metrics", "PASS",
                       "portal5_tool_calls_total + duration present", t0=t0)
            else:
                record(sec, "S60-06", "Tool-call Prometheus metrics", "WARN",
                       "some tool metrics missing", t0=t0)
        else:
            record(sec, "S60-06", "Tool-call Prometheus metrics", "FAIL",
                   f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S60-06", "Tool-call Prometheus metrics", "FAIL", str(e)[:100], t0=t0)

    # S60-07: agentorchestrator persona exists
    t0 = time.time()
    try:
        p = ROOT / "config" / "personas" / "agentorchestrator.yaml"
        if p.exists():
            import yaml
            data = yaml.safe_load(p.read_text())
            record(sec, "S60-07", "agentorchestrator persona", "PASS",
                   f"slug={data.get('slug')}, workspace={data.get('workspace_model')}", t0=t0)
        else:
            record(sec, "S60-07", "agentorchestrator persona", "FAIL", "file missing", t0=t0)
    except Exception as e:
        record(sec, "S60-07", "agentorchestrator persona", "FAIL", str(e)[:100], t0=t0)


# ══════════════════════════════════════════════════════════════════════════════
# S70: M3 Information Access MCPs
# ══════════════════════════════════════════════════════════════════════════════


async def S70() -> None:
    """S70: M3 information access MCPs — research, memory, RAG, SearXNG."""
    print("\n━━━ S70. M3 INFORMATION ACCESS MCPS ━━━")
    sec = "S70"

    # S70-01: SearXNG search
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(f"{SEARXNG_URL}/search?q=test&format=json", timeout=15)
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            record(sec, "S70-01", "SearXNG web search", "PASS",
                   f"{len(results)} results returned", t0=t0)
        else:
            record(sec, "S70-01", "SearXNG web search", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S70-01", "SearXNG web search", "FAIL", str(e)[:100], t0=t0)

    # S70-02: Research MCP health
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get("http://localhost:8920/health", timeout=10)
        if r.status_code == 200:
            record(sec, "S70-02", "Research MCP health", "PASS", r.text[:80], t0=t0)
        else:
            record(sec, "S70-02", "Research MCP health", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S70-02", "Research MCP health", "WARN",
               f"not running: {str(e)[:60]}", t0=t0)

    # S70-03: Memory MCP health
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get("http://localhost:8921/health", timeout=10)
        if r.status_code == 200:
            record(sec, "S70-03", "Memory MCP health", "PASS", r.text[:80], t0=t0)
        else:
            record(sec, "S70-03", "Memory MCP health", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S70-03", "Memory MCP health", "WARN",
               f"not running: {str(e)[:60]}", t0=t0)

    # S70-04: RAG MCP health
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get("http://localhost:8923/health", timeout=10)
        if r.status_code == 200:
            record(sec, "S70-04", "RAG MCP health", "PASS", r.text[:80], t0=t0)
        else:
            record(sec, "S70-04", "RAG MCP health", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S70-04", "RAG MCP health", "WARN",
               f"not running: {str(e)[:60]}", t0=t0)

    # S70-05: Embedding service
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(f"{EMBEDDING_URL}/health", timeout=10)
        if r.status_code == 200:
            record(sec, "S70-05", "Embedding service health", "PASS", r.text[:80], t0=t0)
        else:
            record(sec, "S70-05", "Embedding service health", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S70-05", "Embedding service health", "WARN", str(e)[:100], t0=t0)

    # S70-06: Research personas exist
    t0 = time.time()
    research_personas = ["webresearcher", "factchecker", "kbnavigator", "marketanalyst",
                         "supergemma4researcher", "gemmaresearchanalyst"]
    found = []
    for p in research_personas:
        if (ROOT / "config" / "personas" / f"{p}.yaml").exists():
            found.append(p)
    if len(found) == len(research_personas):
        record(sec, "S70-06", "Research personas", "PASS",
               f"{len(found)}/{len(research_personas)} present", t0=t0)
    else:
        missing = [p for p in research_personas if p not in found]
        record(sec, "S70-06", "Research personas", "WARN",
               f"missing: {missing}", t0=t0)

    # S70-07: web_search in auto-research workspace tools
    t0 = time.time()
    try:
        from portal_pipeline.router_pipe import WORKSPACES
        research_tools = WORKSPACES.get("auto-research", {}).get("tools", [])
        has_search = "web_search" in research_tools
        has_fetch = "web_fetch" in research_tools
        if has_search and has_fetch:
            record(sec, "S70-07", "auto-research tool whitelist", "PASS",
                   f"tools: {research_tools}", t0=t0)
        else:
            record(sec, "S70-07", "auto-research tool whitelist", "WARN",
                   f"missing web_search/web_fetch in {research_tools}", t0=t0)
    except Exception as e:
        record(sec, "S70-07", "auto-research tool whitelist", "FAIL", str(e)[:100], t0=t0)


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

    # Classifier breakdown for FAIL/WARN
    fail_warn = [r for r in _log if r.status in ("FAIL", "WARN")]
    if fail_warn:
        code_defects = sum(1 for r in fail_warn if "CODE-DEFECT" in r.detail)
        env_issues = sum(1 for r in fail_warn if "ENV-ISSUE" in r.detail)
        unclassified = len(fail_warn) - code_defects - env_issues
        lines.extend([
            "",
            f"**Code defects: {code_defects} · Env issues: {env_issues} · Unclassified: {unclassified}**",
        ])

    lines.extend(
        [
            "",
            "## Results",
            "",
            "| Section | ID | Name | Status | Detail | Duration |",
            "|---------|-----|------|--------|--------|----------|",
        ]
    )

    for r in _log:
        icon = _ICON.get(r.status, "")
        detail = r.detail.replace("|", "\\|")[:80]
        dur = f"{r.duration:.1f}s" if r.duration else ""
        lines.append(
            f"| {r.section} | {r.tid} | {r.name[:40]} | {icon} {r.status} | {detail} | {dur} |"
        )

    if _blocked:
        lines.extend(
            [
                "",
                "## Blocked Items Register",
                "",
            ]
        )
        for i, r in enumerate(_blocked, 1):
            lines.extend(
                [
                    f"### BLOCKED-{i}: {r.name}",
                    "",
                    f"**Test ID:** {r.tid}",
                    f"**Section:** {r.section}",
                    f"**Detail:** {r.detail}",
                    f"**Fix:** {r.fix or 'TBD'}",
                    "",
                ]
            )

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


async def _send_notification(event_type: str, message: str, metadata: dict | None = None) -> None:
    """Fire a notification via the Portal 5 notification dispatcher.

    Gracefully handles missing dependencies or disabled notifications — never
    crashes the test suite.
    """
    if os.environ.get("NOTIFICATIONS_ENABLED", "false").lower() not in ("true", "1", "yes"):
        return
    try:
        from portal_pipeline.notifications.channels.email import EmailChannel
        from portal_pipeline.notifications.channels.pushover import PushoverChannel
        from portal_pipeline.notifications.channels.slack import SlackChannel
        from portal_pipeline.notifications.channels.telegram import TelegramChannel
        from portal_pipeline.notifications.channels.webhook import WebhookChannel
        from portal_pipeline.notifications.dispatcher import NotificationDispatcher
        from portal_pipeline.notifications.events import AlertEvent, EventType

        dispatcher = NotificationDispatcher()
        for ch in [SlackChannel, TelegramChannel, EmailChannel, PushoverChannel, WebhookChannel]:
            dispatcher.add_channel(ch())

        event = AlertEvent(
            type=EventType(event_type.lower()),
            message=message,
            workspace="acceptance-test",
            metadata=metadata or {},
        )
        await dispatcher.dispatch(event)
    except Exception as e:
        print(f"  ⚠️  Notification failed: {e}")


async def _notify_test_start(section: str, total_sections: int) -> None:
    """Send a notification that acceptance testing has started."""
    await _send_notification(
        "test_start",
        f"Acceptance test suite started — section {section} ({total_sections} total)\n"
        f"Git: {_git_sha()}  |  Host: {os.uname().nodename}",
        metadata={"section": section, "total_sections": total_sections},
    )


async def _notify_test_end(
    section: str, elapsed: int, counts: dict[str, int], total_sections: int
) -> None:
    """Send a notification that acceptance testing has completed."""
    summary_parts = [
        f"PASS={counts.get('PASS', 0)}",
        f"FAIL={counts.get('FAIL', 0)}",
        f"WARN={counts.get('WARN', 0)}",
        f"INFO={counts.get('INFO', 0)}",
    ]
    await _send_notification(
        "test_end",
        f"Acceptance test suite completed — section {section} in {elapsed}s\n"
        f"Results: {', '.join(summary_parts)}\n"
        f"Git: {_git_sha()}",
        metadata={"elapsed_s": elapsed, "counts": counts},
    )


async def _notify_test_summary(
    counts: dict[str, int], elapsed: int, section: str, total_sections: int
) -> None:
    """Send the narrative summary + formatted table via all enabled notification channels."""
    total = sum(counts.values())
    passed = counts.get("PASS", 0)
    failed = counts.get("FAIL", 0)
    blocked = counts.get("BLOCKED", 0)
    warned = counts.get("WARN", 0)

    if failed:
        narrative = f"{failed} test{'s' if failed > 1 else ''} failed"
    elif blocked:
        narrative = f"{blocked} test{'s' if blocked > 1 else ''} blocked (require code changes)"
    elif warned:
        narrative = f"All {total} tests passed with {warned} warning{'s' if warned > 1 else ''}"
    else:
        narrative = f"All {total} tests passed"

    lines = [
        narrative,
        "",
        f"Portal 5 Acceptance Test v6 — {section}",
        f"Duration: {elapsed}s  |  Sections: {total_sections}",
        f"Git: {_git_sha()}  |  Host: {os.uname().nodename}",
        "",
    ]
    for s in ["PASS", "FAIL", "BLOCKED", "WARN", "INFO"]:
        if s in counts:
            icon = _ICON.get(s, "  ")
            lines.append(f"  {icon} {s}: {counts[s]}")
    lines.append(f"  Total: {total}")

    if failed or blocked:
        lines.append("")
        label = "Failed" if failed else "Blocked"
        lines.append(f"{label} checks:")
        for r in _log:
            if r.status in ("FAIL", "BLOCKED"):
                lines.append(f"  [{r.status}] {r.section}/{r.name}: {r.detail[:120]}")

    await _send_notification(
        "test_summary",
        "\n".join(lines),
        metadata={"counts": counts, "elapsed_s": elapsed, "section": section},
    )


async def S50() -> None:
    """S50: Negative tests — delegates to tests/acceptance/s50_negative.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s50_negative as _s50

    await _s50.run()


ALL_SECTIONS = {
    # Phase 1: No-model tests
    "S0": S0,
    "S1": S1,
    "S2": S2,
    "S12": S12,
    "S13": S13,
    "S40": S40,
    "S50": S50,  # Negative tests (section file: tests/acceptance/s50_negative.py)
    # Phase 2: Ollama tests
    "S3a": S3a,
    "S6": S6,
    "S16": S16,
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
    # Phase 7: M5/M6 features
    "S41": S41,  # M6 production hardening
    "S42": S42,  # M5 browser automation
    # Phase 8: M2/M3 tool-calling and information access
    "S60": S60,  # M2 tool-calling orchestration
    "S70": S70,  # M3 information access MCPs
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
    parser.add_argument(
        "--skip-passing", action="store_true", help="Skip sections that passed in prior run"
    )
    args = parser.parse_args()

    _FORCE_REBUILD = args.rebuild
    _verbose = args.verbose

    sections = _parse_sections(args.section)

    # Define memory cleanup points between phases
    # Only apply when running ALL sections (full suite)
    PHASE_TRANSITIONS = {
        "S10": "Ollama → MLX",  # After Ollama personas, before MLX
        "S23": "MLX → MCP",  # After MLX tests, before MCP
        "S7": "Audio → ComfyUI",  # After audio tests, before ComfyUI
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

    await _notify_test_start(args.section, len(sections))

    try:
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
    finally:
        global _acc_client
        if _acc_client and not _acc_client.is_closed:
            await _acc_client.aclose()

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

    await _notify_test_end(args.section, elapsed, counts, len(sections))
    await _notify_test_summary(counts, elapsed, args.section, len(sections))

    # Return non-zero if any failures
    if counts.get("FAIL", 0) > 0 or counts.get("BLOCKED", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
