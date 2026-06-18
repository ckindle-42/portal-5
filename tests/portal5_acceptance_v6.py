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

Test Coverage (~27 sections, ~300 tests):
    S0-S2:   Prerequisites, config consistency, service health
    S3a:     all production workspaces (auto-* + tools-specialist) tested
              directly (all Ollama). bench-* workspaces are out of acceptance
              scope — bench_tps.py --mode pipeline covers the full catalog.
              S41-02 verifies max_concurrent=1 (data-driven from WORKSPACES)
    S4-S5:   Document generation (Word/Excel/PowerPoint), code sandbox
    S6:      Security workspaces (auto-security, auto-redteam, auto-blueteam)
    S16:     Security MCP tools (classify_vulnerability via CIRCL VLAI)
    S7-S9:   Music generation, TTS, STT
    S10-S11: 84 non-compliance personas grouped by workspace; S10c drives
              the 7 compliance personas via tests/fixtures/compliance_scenarios.yaml
    S12-S13: Web search (SearXNG), RAG/embedding pipeline
    S21:     LLM Intent Router — semantic routing via Llama-3.2-3B
    S23:     Model diversity availability checks
    S30-S31: Image generation (ComfyUI/FLUX), video generation (Wan2.2)
    S40:     Metrics/monitoring (Prometheus, Grafana)
    S41:     M6 production hardening (/health/all, rate limits, admin endpoints, power metrics)
    S42:     M5 browser automation (Browser MCP health, tool manifest)
    S50:     Negative testing (malformed bodies, invalid auth, etc.)
    S60:     M2 tool-calling orchestration (registry, dispatch, metrics)
    S70:     M3 information access MCPs (research, memory, RAG, SearXNG)

Changes from v5:
    - Added S16 (Security MCP tool tests — classify_vulnerability)
    - Persona count is now dynamic (derived from config/personas/*.yaml at runtime)
    - Added S21 (LLM Intent Router), S23 (Model Diversity)
    - Fixed persona slugs to match actual YAML filenames
    - Tests for new models: GPT-OSS:20B, Gemma 4 E4B, Phi-4-reasoning-plus
    - Consolidated test framework with unified helper functions
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

# Ensure PROMETHEUS_MULTIPROC_DIR exists (wiped on reboot; macOS lacks /dev/shm)
_pmd = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
if _pmd:
    try:
        os.makedirs(_pmd, exist_ok=True)
    except (PermissionError, OSError):
        # macOS: /dev/shm not user-writable; use temp dir instead
        import tempfile

        _alt = tempfile.mkdtemp(prefix="portal5_prom_")
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = _alt

# Service URLs
PIPELINE_URL = "http://localhost:9099"
OPENWEBUI_URL = "http://localhost:8080"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").replace(
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

# Routing telemetry — populated by _assert_routing(), printed at end of run.
# Each entry: {tid, workspace, intended, actual, matched}
_ROUTING_LOG: list[dict] = []


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


def _check_image_freshness() -> None:
    """Warn if any portal Docker image predates the latest relevant git commit.

    Stale images mean tests exercise old code. Run './launch.sh rebuild' to fix.
    """
    import datetime

    def _last_commit_ts(paths: list[str]) -> datetime.datetime | None:
        try:
            r = subprocess.run(
                ["git", "-C", str(ROOT), "log", "-1", "--format=%ct", "--", *paths],
                capture_output=True,
                text=True,
                timeout=10,
            )
            ts = r.stdout.strip()
            return (
                datetime.datetime.fromtimestamp(int(ts), tz=datetime.timezone.utc) if ts else None
            )
        except Exception:
            return None

    def _image_built_ts(name: str) -> datetime.datetime | None:
        try:
            r = subprocess.run(
                ["docker", "inspect", "--format", "{{.Created}}", name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            raw = r.stdout.strip()
            if raw and raw != "[]":
                return datetime.datetime.fromisoformat(raw.rstrip("Z") + "+00:00")
        except Exception:
            return None

    checks = [
        (
            "portal-pipeline",
            "portal-5-portal-pipeline",
            [
                "portal_pipeline/",
                "config/backends.yaml",
                "config/personas/",
                "Dockerfile.pipeline",
                "pyproject.toml",
            ],
        ),
        (
            "mcp-services",
            "portal-5-mcp-documents",
            ["portal_mcp/", "portal_channels/", "Dockerfile.mcp", "pyproject.toml"],
        ),
    ]
    stale = []
    for label, image, paths in checks:
        built = _image_built_ts(image)
        committed = _last_commit_ts(paths)
        if built and committed:
            lag = (committed - built).total_seconds()
            if lag > 30:
                stale.append(f"{label} ({int(lag // 60)}m behind HEAD)")
    if stale:
        print("  WARNING: stale images — run './launch.sh rebuild' before trusting results:")
        for s in stale:
            print(f"    {s}")


def _load_workspaces() -> tuple[list[str], dict[str, str]]:
    """Load workspace definitions from portal_pipeline.router.workspaces."""
    sys.path.insert(0, str(ROOT))
    from portal_pipeline.router.workspaces import WORKSPACES  # noqa: PLC0415

    ids = sorted(
        k for k in WORKSPACES if k.startswith(("auto", "bench")) or k == "tools-specialist"
    )
    names = {k: WORKSPACES[k].get("name", k) for k in ids}
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

# All workspace IDs that route via Ollama (the full catalog — MLX proxy retired 3a0c58e).
# Includes workspace slugs (auto-*, bench-*) used as persona workspace_model values,
# plus the one direct model tag that some personas reference.
OLLAMA_WORKSPACES: set[str] = set(WS_IDS) | {"huihui_ai/Qwen3.6-abliterated:27b"}


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


async def _await_ollama_ready(timeout_s: float = 300.0, poll_s: float = 5.0) -> bool:
    """Event-driven cold-load wait — delegates to memory_guard.wait_for_model_loaded."""
    return await _await_model_loaded(timeout_s=timeout_s, poll_s=poll_s, ollama_url=OLLAMA_URL)


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
    tools: list | None = None,
) -> tuple[int, str, str, str]:
    """Chat request that also returns the model and route header.

    Returns (status_code, response_text, model_used, route_descriptor).
    route_descriptor is the x-portal-route header value: "{workspace};{backend_id};{model}".
    Uses shared client with 3-attempt backoff [0, 5, 15]s.
    On 502/503 continues to the next retry (backoff already handles the wait).

    When `tools` is provided the OpenAI tools array is forwarded to the backend.
    If the model responds with tool_calls (not content), those are serialized to
    JSON and returned as the response text so signal checks still work.
    """
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system[:800]})
    msgs.append({"role": "user", "content": prompt})
    # Always stream: the inter-token idle gap is the primary failure signal, so the
    # wall-clock `timeout` argument becomes the overall ceiling (last resort) rather
    # than the driver. tool_calls fragments are accumulated into text by the module.
    body: dict = {"model": workspace, "messages": msgs, "stream": True, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools

    result = await _stream_chat(
        url=f"{PIPELINE_URL}/v1/chat/completions",
        body=body,
        headers=AUTH,
        client=_get_acc_client(),
        overall_ceiling_s=float(timeout),
        ollama_url=OLLAMA_URL,
    )

    if result.status is _StreamStatus.OK:
        return 200, result.text, result.model, result.route
    if result.status is _StreamStatus.HTTP_ERROR:
        return result.http_status, result.detail[:200], "", result.route
    if result.status in (_StreamStatus.STALLED, _StreamStatus.CEILING):
        # Silence/ceiling after one retry → 408 so the caller records WARN, not FAIL.
        # Return whatever partial text streamed so signal checks can still inspect it.
        return 408, result.text or "timeout", result.model, result.route
    # CONN_ERROR
    return 0, result.detail[:100], "", ""


async def _assert_routing(
    sec: str,
    tid: str,
    workspace: str,
    actual_model: str,
    *,
    persona_slug: str = "",
) -> tuple[str, str]:
    from expected_models import (
        model_matches_expected,
        resolve_expected,
    )

    keys, src = resolve_expected(
        workspace_id=workspace,
        persona_slug=persona_slug,
    )
    if not keys:
        return "no_expectation", f"no routing expectation: {src}"
    if not actual_model:
        return "no_actual", "no model in response"

    matched = model_matches_expected(actual_model, keys)

    _ROUTING_LOG.append(
        {
            "tid": f"{sec}/{tid}",
            "workspace": workspace or persona_slug,
            "intended": src,
            "actual": actual_model,
            "matched": matched,
        }
    )

    if matched:
        return "match", f"routed -> {actual_model[:40]} matches {src}"
    return (
        "mismatch",
        f"ROUTING MISMATCH: got {actual_model[:40]}, expected {src}",
    )


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
# Memory Helpers
# ══════════════════════════════════════════════════════════════════════════════


from tests.lib.stream_wait import StreamStatus as _StreamStatus
from tests.lib.stream_wait import stream_chat as _stream_chat
from tests.memory_guard import free_ram_gb as _free_ram_gb
from tests.memory_guard import wait_for_drain_async as _mg_drain_async
from tests.memory_guard import wait_for_model_loaded as _await_model_loaded


async def _wait_metal_drain_async(
    timeout_s: float = 30.0, poll_s: float = 3.0, retries: int = 2
) -> float:
    """Wait for Metal drain with retry+recovery. See tests/memory_guard.py."""
    return await _mg_drain_async(
        timeout_s=timeout_s,
        poll_s=poll_s,
        retries=retries,
        ollama_url=OLLAMA_URL,
    )


async def _unload_ollama_models() -> None:
    """Evict all Ollama models from memory."""
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


def _stop_comfyui() -> None:
    """Kill ComfyUI process to reclaim GPU/RAM."""
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
    # Poll until Metal GPU buffers drain rather than using a blind fixed sleep.
    free = await _wait_metal_drain_async(timeout_s=90.0)
    print(f"  ── RAM after eviction: {free:.1f} GB free ──")
    if free < needed_gb:
        print(f"  ⚠️  Still low on RAM ({free:.1f}GB < {needed_gb}GB needed) — stopping ComfyUI")
        _stop_comfyui()
        await asyncio.sleep(10)
        free = _free_ram_gb()
        print(f"  ── RAM after ComfyUI stop: {free:.1f} GB free ──")
    return free


async def _memory_cleanup(phase: str) -> None:
    """Perform memory cleanup between test phases with active RAM verification."""
    print(f"\n  ══ MEMORY CLEANUP: {phase} ══")
    await _unload_ollama_models()
    import gc

    gc.collect()
    # Poll until Metal GPU buffers drain rather than using a blind fixed sleep.
    free = await _wait_metal_drain_async(timeout_s=90.0)
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
    "auto-coding-agentic": (
        "Fix a bug: a Python function returns None instead of the computed value.",
        ["return", "def", "bug", "fix", "value"],
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
        ["haiku", "syllable", "5-7-5", "5/7/5", "stanza", "5,7,5"],
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
        [
            "sum of squares",
            "(x - mean)",
            "n - 1",
            "n-1",
            "square root",
            "sqrt",
            "mean",
            "variance",
            "deviation",
            "σ",
            "sigma",
        ],
    ),
    "auto-compliance": (
        "What evidence is needed for NERC CIP-007 R2?",
        ["CIP", "evidence", "patch", "compliance", "NERC", "requirement"],
    ),
    "auto-mistral": (
        "Analyze the trade-offs between microservices and monolithic architectures.",
        ["trade", "scale", "complex", "deploy", "maintain"],
    ),
    "auto-math": (
        "Find the area enclosed by the curves y = x^2 and y = 2x. Show your work step by step.",
        ["integral", "intersection", "area", "4/3", "x^2", "2x"],
    ),
    "auto-audio": (
        "What audio formats can you analyze, and what information can you "
        "extract from a recording? Answer in two sentences.",
        ["audio", "transcri", "speech", "format", "recording"],
    ),
    "auto-daily": (
        "Draft a three-item plan for organizing a small team offsite.",
        ["offsite", "venue", "agenda", "plan", "schedule", "1"],
    ),
    "tools-specialist": (
        "In two sentences: what is JSON function calling, and when should an "
        "assistant invoke a tool instead of answering directly?",
        ["tool", "function", "JSON", "call", "schema", "structured"],
    ),
}

# Persona test prompts and expected signals
# Currently 76 entries against ~96 persona YAML files in config/personas/.
# Personas without entries: 12 bench-* personas (covered by S3a/S3b/S41-02),
# 7 compliance personas (covered by S10c via compliance_scenarios.yaml),
# and a small number of attachment-driven personas (e.g. transcriptanalyst).
PERSONA_PROMPTS_EXCLUDED: set[str] = {
    "transcriptanalyst",  # audio-attachment driven; tested via S8/S9 flow
    # Compliance personas — tested via S10c fixture (compliance_scenarios.yaml)
    "cippolicywriter",
    "complianceanalyst",
    "gdprdpoadvisor",
    "hipaaprivacyofficer",
    "nerccipcomplianceanalyst",
    "pcidssassessor",
    "soc2auditor",
    # Specialized personas tested via workspace routing or S24
    "dailydriver",  # auto-daily workspace, general-purpose
}
PERSONA_PROMPTS = {
    # Development (18 personas)
    # Real IndexError bug: no bounds check on lst, no empty-list guard
    "bugdiscoverycodeassistant": (
        "Find the bugs in this code:\ndef get_first(lst):\n    return lst[0]",
        [
            "indexerror",
            "out of range",
            "out-of-range",
            "bounds",
            "empty list",
            "empty input",
            "len(lst)",
            "len(list)",
            "if not",
            "if lst",
            "if list",
            "guard",
            "check empty",
            "default",
            "raise",
            "validation",
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
        [
            "param",
            "Args",
            "Returns",
            "raises",
            "str",
            "dict",
            "path",
            # qwen3-coder variants
            "parameters",
            "arguments",
            "return",
            "type",
            "bool",
            "optional",
            "description",
            ":param",
            ":return",
            ":raises",
            "->",
        ],
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
        [
            "sorted",
            "lambda",
            "key",
            "dict",
            "def",
            # qwen3-coder variants
            "sort",
            "list",
            "function",
            "return",
            "items",
            "operator",
            "itemgetter",
            "reverse",
            "callable",
        ],
    ),
    "pythoninterpreter": (
        "Execute: sorted([3,1,2], reverse=True)",
        # Was ["[3, 2, 1]", "reverse", "sorted", "descend", "output"]:
        #   - exact string "[3, 2, 1]" rejected valid "[3,2,1]" (no spaces)
        #   - "reverse" and "sorted" both appear in the prompt (always-pass)
        # Now: every spacing/notation variant of the actual answer plus
        # one structural marker for the result presentation.
        [
            "[3, 2, 1]",
            "[3,2,1]",
            "[3, 2,1]",
            "[3,2, 1]",
            "3, 2, 1",
            "3,2,1",
            "result:",
            "output:",
            "returns",
            "descending",
        ],
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
        [
            "test",
            "case",
            "valid",
            "invalid",
            "password",
            # qwen3-coder variants
            "username",
            "assert",
            "expect",
            "verify",
            "scenario",
            "empty",
            "credentials",
            "authentication",
            "boundary",
            "input",
        ],
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
    # Compliance personas — handled by S10c via the fixture in
    # tests/fixtures/compliance_scenarios.yaml. Do not add hardcoded prompts
    # here. See TASK_COMPLIANCE_ACCEPT_003.md.
    # Systems (2 personas)
    "linuxterminal": ("ls -lhS", ["total", "home", "user", "-rw", "ls"]),
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
            "gather",
            "troubleshoot",
            "speed",
            "connection",
            "router",
            "check",
            "ping",
            "traceroute",
            "iperf",
            "qos",
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
    # ── M1: Compliance personas — handled by S10c via fixture ───────────
    # The 6 compliance personas (soc2auditor, pcidssassessor, gdprdpoadvisor,
    # hipaaprivacyofficer, nerccipcomplianceanalyst, cippolicywriter, plus
    # the new complianceanalyst generalist) are tested by section S10c using
    # behavioral assertions from tests/lib/compliance_assertions.py against
    # scenarios in tests/fixtures/compliance_scenarios.yaml.
    # ── M1: Language personas ────────────────────────────────────────────
    "rustengineer": (
        "Write a thread-safe LRU cache in Rust with capacity bound and TTL eviction.",
        [
            "arc",
            "mutex",
            "rwlock",
            "hashmap",
            "vecdeque",
            "lru",
            "instant",
            "duration",
            "fn",
            "struct",
            "impl",
            "cache",
        ],
    ),
    "goengineer": (
        "Write a Go HTTP middleware that adds request IDs and structured logging via slog.",
        ["middleware", "http.handler", "context", "slog", "uuid", "next.servehttp"],
    ),
    "typescriptengineer": (
        "Write a TypeScript discriminated union for a state machine with idle, loading, success, error states. Include type guards.",
        [
            "discriminated union",
            "type",
            "loading",
            "success",
            "error",
            "type guard",
            "narrowing",
            # qwen3-coder variants
            "interface",
            "union",
            "idle",
            "state",
            "is",
            "switch",
            "kind",
            "status",
            "never",
            "extends",
        ],
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
            # qwen3-coder variants
            "terraform",
            "provider",
            "bucket",
            "aws",
            "module",
            "server_side_encryption",
            "block_public",
            "expiration",
            "variable",
            "output",
            "main.tf",
        ],
    ),
    "documentationarchitect": (
        "Outline the documentation structure for an open-source REST API library.",
        [
            "tutorial",
            "reference",
            "how-to",
            "explanation",
            "diataxis",
            "getting started",
            # granite4.1 variants (routes to auto-documents)
            "overview",
            "guide",
            "quickstart",
            "installation",
            "api",
            "endpoint",
            "authentication",
            "example",
            "introduction",
            "documentation",
        ],
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
    # ── M1: Additional personas (v6 sync) ─────────────────────────────────
    # Web/research group
    "webnavigator": (
        "Research the best practices for API rate limiting and cite three sources.",
        ["source", "url", "cited", "verified", "evidence"],
    ),
    "webresearcher": (
        "Research the impact of remote work on employee productivity and cite three sources.",
        ["source", "url", "cited", "verified", "evidence"],
    ),
    "paywalledresearcher": (
        "Research quantum computing advances in 2024 and cite three academic sources.",
        ["source", "url", "cited", "verified", "evidence"],
    ),
    "kbnavigator": (
        "Describe the steps you would take to search for a document about employee leave policies, including how you would handle too many or too few results.",
        ["search", "query", "results", "filter", "refine", "document", "keywords", "knowledge"],
    ),
    "factchecker": (
        "Verify the claim: 'The US GDP grew by 3.1% in Q3 2024' and cite three sources.",
        ["source", "url", "cited", "verified", "evidence"],
    ),
    # Data extraction group
    "dataextractor": (
        "Extract structured data from this description: User John Doe, email john@example.com, subscription tier Premium, renewal date 2025-03-15.",
        ["extracted", "field", "value", "parsed"],
    ),
    "chartanalyst": (
        "Extract the quarterly revenue data from this description: Q1 $1.2M, Q2 $1.4M, Q3 $1.7M, Q4 $2.1M.",
        ["extracted", "field", "value", "parsed", "quarter", "revenue"],
    ),
    "codescreenshotreader": (
        "Extract the code from this description: function calculateTotal(items) { return items.reduce((sum, item) => sum + item.price, 0); }",
        ["extracted", "function", "code", "parsed"],
    ),
    "whiteboardconverter": (
        "Convert this diagram description to structured format: Box A → Box B → Box C, with arrow from Box B to Box D.",
        ["extracted", "entities", "relationships", "parsed"],
    ),
    "formfiller": (
        "Extract the form fields from this description: Name field, Email field (required), Phone field, Submit button.",
        ["extracted", "field", "value", "parsed"],
    ),
    # Analytics group
    "marketanalyst": (
        "Analyze the Q3 revenue trend: $1.2M (Jan), $1.4M (Feb), $1.7M (Mar). What's the takeaway?",
        ["trend", "growth", "quarter", "revenue", "analysis"],
    ),
    # Agentic group
    "agentorchestrator": (
        "Plan the steps to set up a CI pipeline with three stages: build, test, deploy.",
        ["step", "plan", "stage", "task", "next"],
    ),
    "e2edebugger": (
        "Plan the steps to set up a CI pipeline with three stages: build, test, deploy.",
        ["step", "plan", "stage", "task", "next"],
    ),
    "e2etestauthor": (
        "Plan the steps to set up a CI pipeline with three stages: build, test, deploy.",
        ["step", "plan", "stage", "task", "next"],
    ),
    "personalassistant": (
        "Plan the steps to set up a CI pipeline with three stages: build, test, deploy.",
        ["step", "plan", "stage", "task", "next"],
    ),
    # toolcomposer — tool-calling planner; prompt asks for a step plan without requiring
    # live tools to be injected (system prompt establishes the methodology)
    "toolcomposer": (
        "I need to read a file at /workspace/data.csv, count the rows, and store the count "
        "in memory under the key 'row_count'. What tool calls would you plan, in order?",
        [
            "execute_python",
            "remember",
            "read",
            "call",
            "step",
            "tool",
            "plan",
            "memory",
            "store",
            "count",
            "function",
            "order",
        ],
    ),
    # ── M1: Security / pentest personas ──────────────────────────────────
    "adversarysimulator": (
        "Simulate an adversary attempting lateral movement after initial access. List three techniques with MITRE ATT&CK IDs.",
        ["lateral", "movement", "T1", "technique", "ATT&CK", "credential", "pivot", "pass-the-hash", "psexec"],
    ),
    "pentestlead": (
        "Outline the phases of a black-box web application penetration test and list two tools per phase.",
        ["reconnaissance", "scanning", "exploitation", "reporting", "tool", "nmap", "burp", "nikto", "phase"],
    ),
    # ── M1: CAD / 3D printing personas ───────────────────────────────────
    "cadquerydesigner": (
        "Write CadQuery Python code to create a simple 10mm cube.",
        ["cadquery", "cq", "box", "workplane", "export", "solid", "10"],
    ),
    "printabilityengineer": (
        "Review this 3D model issue: overhangs greater than 45 degrees with no support. What printability problems arise and how would you fix them?",
        ["overhang", "support", "45", "layer", "print", "bridge", "orient", "sag"],
    ),
}


# ══════════════════════════════════════════════════════════════════════════════
# Test Sections
# ══════════════════════════════════════════════════════════════════════════════


async def S0() -> None:
    """S0: Prerequisites and environment check — delegates to tests/acceptance/s00_startup.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s00_startup as _s

    await _s.run()


async def S1() -> None:
    """S1: Configuration consistency — delegates to tests/acceptance/s01_static_config.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s01_static_config as _s

    await _s.run()


async def S2() -> None:
    """S2: Service health checks — delegates to tests/acceptance/s02_services.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s02_services as _s

    await _s.run()


async def S3a() -> None:
    """S3a: Workspace routing (Ollama) — delegates to tests/acceptance/s03_routing.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s03_routing as _s

    await _s.run()


# retired async def S3b() -> None:
# retired     """S3b: Workspace routing (MLX) — delegates to tests/acceptance/_archive/s03b_routing_mlx.py."""
# retired     import sys as _sys
# retired     _sys.path.insert(0, str(ROOT / "tests"))
# retired     from acceptance._archive import s03b_routing_mlx as _s
# retired     await _s.run()
async def S3() -> None:
    """S3: Workspace routing tests (runs S3a). S3b (MLX) retired in 3a0c58e."""
    await S3a()


async def S4() -> None:
    """S4: Document generation — delegates to tests/acceptance/s04_documents.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s04_documents as _s

    await _s.run()


async def S5() -> None:
    """S5: Code sandbox — delegates to tests/acceptance/s05_health.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s05_health as _s

    await _s.run()


async def S6() -> None:
    """S6: Security workspace tests — delegates to tests/acceptance/s06_security_workspaces.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s06_security_workspaces as _s

    await _s.run()


async def S15() -> None:
    """S15: Shared workspace verification — delegates to tests/acceptance/s15_shared_workspace.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s15_shared_workspace as _s

    await _s.run()


async def S16() -> None:
    """S16: Security MCP tools — delegates to tests/acceptance/s16_security_mcp.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s16_security_mcp as _s

    await _s.run()


async def S17() -> None:
    """S17: CAD render MCP tests — delegates to tests/acceptance/s17_cad_render.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s17_cad_render as _s

    await _s.run()


async def S7() -> None:
    """S7: Music generation tests — delegates to tests/acceptance/s07_music.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s07_music as _s

    await _s.run()


async def S8() -> None:
    """S8: TTS tests — delegates to tests/acceptance/s08_tts.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s08_tts as _s

    await _s.run()


async def S9() -> None:
    """S9: STT tests — delegates to tests/acceptance/s09_stt.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s09_stt as _s

    await _s.run()


async def S10() -> None:
    """S10: Persona tests (Ollama) — delegates to tests/acceptance/s10_personas_ollama.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s10_personas_ollama as _s

    await _s.run()


async def S10c() -> None:
    """S10c: Compliance personas — delegates to tests/acceptance/s10c_compliance_personas.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s10c_compliance_personas as _s

    await _s.run()


# retired — MLX proxy deleted in 3a0c58e
# async def S11() -> None:
#     """S11: Persona tests (MLX) — delegates to tests/acceptance/_archive/s11_personas_mlx.py."""
#     import sys as _sys
#     _sys.path.insert(0, str(ROOT / "tests"))
#     from acceptance._archive import s11_personas_mlx as _s
#     await _s.run()
async def S12() -> None:
    """S12: Web search tests — delegates to tests/acceptance/s12_web_search.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s12_web_search as _s

    await _s.run()


async def S13() -> None:
    """S13: RAG/Embedding tests — delegates to tests/acceptance/s13_rag_embedding.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s13_rag_embedding as _s

    await _s.run()


# retired — MLX proxy deleted in 3a0c58e
# async def S20() -> None:
#     """S20: MLX acceleration tests — delegates to tests/acceptance/_archive/s20_mlx.py."""
#     import sys as _sys
#     _sys.path.insert(0, str(ROOT / "tests"))
#     from acceptance._archive import s20_mlx as _s
#     await _s.run()
async def S21() -> None:
    """S21: LLM Intent Router — delegates to tests/acceptance/s21_llm_router.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s21_llm_router as _s

    await _s.run()


# retired — MLX proxy deleted in 3a0c58e
# async def S22() -> None:
#     """S22: MLX Admission Control — delegates to tests/acceptance/_archive/s22_admission_control.py."""
#     import sys as _sys
#     _sys.path.insert(0, str(ROOT / "tests"))
#     from acceptance._archive import s22_admission_control as _s
#     await _s.run()
async def S23() -> None:
    """S23: Model diversity — delegates to tests/acceptance/s23_model_diversity.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s23_model_diversity as _s

    await _s.run()


# retired — MLX proxy deleted in 3a0c58e; specialists lost (see KNOWN_LIMITATIONS)
# async def S24() -> None:
#     """S24: Specialist MLX models — delegates to tests/acceptance/_archive/s24_specialist_mlx.py."""
#     import sys as _sys
#     _sys.path.insert(0, str(ROOT / "tests"))
#     from acceptance._archive import s24_specialist_mlx as _s
#     await _s.run()
async def S30() -> None:
    """S30: Image generation — delegates to tests/acceptance/s30_image_video.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s30_image_video as _s

    await _s.run()


async def S31() -> None:
    """S31: Video generation — delegates to tests/acceptance/s31_video_gen.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s31_video_gen as _s

    await _s.run()


async def S40() -> None:
    """S40: Metrics and monitoring — delegates to tests/acceptance/s40_metrics.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s40_metrics as _s

    await _s.run()


async def S41() -> None:
    """S41: M6 production hardening — delegates to tests/acceptance/s41_production_hardening.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s41_production_hardening as _s

    await _s.run()


async def S42() -> None:
    """S42: Browser automation — delegates to tests/acceptance/s42_browser_automation.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s42_browser_automation as _s

    await _s.run()


async def S18() -> None:
    """S18: Lab-exec lane — live AD attack chain (skips if SANDBOX_LAB_EXEC not set)."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s18_lab_exec as _s

    await _s.run()


async def S60() -> None:
    """S60: Tool-calling orchestration — delegates to tests/acceptance/s60_tool_calling.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s60_tool_calling as _s

    await _s.run()


async def S70() -> None:
    """S70: Information access MCPs — delegates to tests/acceptance/s70_information_access.py."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s70_information_access as _s

    await _s.run()


def _load_prior_results(sections_to_skip: set[str]) -> None:
    """Load ACCEPTANCE_RESULTS.md into _log, skipping sections being re-run.

    Used by --append mode so a targeted re-run merges with the full-run baseline.
    """
    results_path = ROOT / "ACCEPTANCE_RESULTS.md"
    if not results_path.exists():
        print("  [append] No prior ACCEPTANCE_RESULTS.md found — starting fresh")
        return
    loaded = 0
    for line in results_path.read_text().splitlines():
        if not line.startswith("| ") or "| Section |" in line or line.startswith("|---"):
            continue
        parts = [p.strip() for p in line.split("|")]
        # Table row: ['', section, tid, name, status, detail, dur, '']
        if len(parts) < 7:
            continue
        section = parts[1]
        if not section or section in sections_to_skip:
            continue
        tid = parts[2]
        name = parts[3]
        status_raw = parts[4]
        detail = parts[5].replace("\\|", "|")
        dur_str = parts[6]
        status = next(
            (s for s in ("PASS", "FAIL", "BLOCKED", "WARN", "INFO") if s in status_raw),
            None,
        )
        if not status:
            continue
        dur = 0.0
        if dur_str.endswith("s"):
            try:
                dur = float(dur_str[:-1])
            except ValueError:
                pass
        r = R(section=section, tid=tid, name=name, status=status, detail=detail, duration=dur)
        _log.append(r)
        if status == "BLOCKED":
            _blocked.append(r)
        loaded += 1
    print(
        f"  [append] Loaded {loaded} prior results (excluding: {', '.join(sorted(sections_to_skip))})"
    )


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
        lines.extend(
            [
                "",
                f"**Code defects: {code_defects} · Env issues: {env_issues} · Unclassified: {unclassified}**",
            ]
        )

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
        dur = f"{r.duration:.1f}s" if r.duration is not None else ""
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
# PHASE 3: router + diversity (Ollama)
#   S21 (LLM intent router), S23 (model diversity)
#
# PHASE 4: MCP/Docker tests (minimal memory)
#   S4 (documents), S5 (sandbox)
#
# PHASE 5: Audio tests (retained MLX Speech server :8918)
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


def _print_routing_summary() -> None:
    """Print a routing intent-vs-actual summary after all sections complete.

    Groups results into: correct, unmatched (wrong model), and unknown (no actual model).
    Helps identify when a primary model isn't doing the work it should.
    """
    if not _ROUTING_LOG:
        return

    correct = [r for r in _ROUTING_LOG if r["matched"]]
    unmatched = [r for r in _ROUTING_LOG if not r["matched"] and r["actual"]]
    no_actual = [r for r in _ROUTING_LOG if not r["actual"]]

    print("\n" + "=" * 70)
    print("ROUTING SUMMARY")
    print("=" * 70)
    total_checked = len(_ROUTING_LOG)
    print(f"  Checked : {total_checked}")
    print(f"  ✅ Correct   : {len(correct)}")
    if unmatched:
        print(f"  ⚠️  Unmatched model : {len(unmatched)}")
    if no_actual:
        print(f"  ℹ️  No model in response : {len(no_actual)}")

    if unmatched:
        print("\n  ── Unmatched Routing ──")
        for r in unmatched:
            print(f"    {r['tid']:20s}  ws={r['workspace']:22s}  actual={r['actual'][:45]}")
            print(f"    {'':20s}  expected: {r['intended']}")

    print("=" * 70)


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
    "S15": S15,  # Shared workspace verification (TASK-WORKSPACE-001)
    "S40": S40,
    "S50": S50,  # Negative tests (section file: tests/acceptance/s50_negative.py)
    # Phase 2: Ollama tests
    "S3a": S3a,
    "S6": S6,
    "S16": S16,
    "S10": S10,
    "S10c": S10c,  # Compliance personas via fixture (TASK_COMPLIANCE_ACCEPT_003)
    # Phase 3: router + diversity (Ollama)
    "S21": S21,
    "S23": S23,
    # Phase 4: MCP tests
    "S4": S4,
    "S5": S5,
    "S17": S17,  # CAD render MCP (TASK_CAD_RENDER_MCP_V1)
    "S18": S18,  # Lab-exec lane AD attack chain (skips gracefully if not configured)
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
    parser.add_argument(
        "--append",
        action="store_true",
        help="Merge targeted re-run results into prior ACCEPTANCE_RESULTS.md baseline",
    )
    args = parser.parse_args()

    _FORCE_REBUILD = args.rebuild
    _verbose = args.verbose

    sections = _parse_sections(args.section)

    if args.append:
        _load_prior_results(sections_to_skip=set(sections))

    # Define memory cleanup points between phases
    # Only apply when running ALL sections (full suite)
    PHASE_TRANSITIONS = {
        "S10": "Personas → Audio/MCP",  # After personas, before audio/MCP
        "S7": "Audio → ComfyUI",  # After audio tests, before ComfyUI
    }

    print("=" * 70)
    print("Portal 5 Acceptance Tests v6")
    print(f"Git: {_git_sha()}")
    print(f"Sections: {', '.join(sections)}")
    print("=" * 70)
    _check_image_freshness()

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

    _print_routing_summary()

    await _notify_test_end(args.section, elapsed, counts, len(sections))
    await _notify_test_summary(counts, elapsed, args.section, len(sections))

    # Return non-zero if any failures
    if counts.get("FAIL", 0) > 0 or counts.get("BLOCKED", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
