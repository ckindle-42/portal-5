"""Shared infrastructure for Portal 5 acceptance section modules."""

from __future__ import annotations

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
from pathlib import Path

import httpx
import yaml

# ── Re-export from results so section modules have one import point ──────────
from .results import (  # noqa: F401
    _ICON,
    _ROUTING_LOG,
    R,
    _blocked,
    _git_sha,
    _log,
    record,
)

ROOT = Path(__file__).parent.parent.parent.resolve()

# ── Environment setup ────────────────────────────────────────────────────────
_env_file = ROOT / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# ── Prometheus multiprocess guard ────────────────────────────────────────────
# .env sets PROMETHEUS_MULTIPROC_DIR=/dev/shm/portal_metrics (Linux-only path).
# On macOS test hosts where /dev/shm is absent, redirect to a writable temp dir
# BEFORE any portal_pipeline import — prometheus_client reads the env var at
# metric-instantiation time, so this must be set before the first import.
_prom_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR", "")
if _prom_dir and not os.path.isdir(_prom_dir):
    import tempfile as _tempfile

    _mp_dir = _tempfile.mkdtemp(prefix="portal5_acceptance_metrics_")
    os.environ["PROMETHEUS_MULTIPROC_DIR"] = _mp_dir

# ── Service URLs ─────────────────────────────────────────────────────────────
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

# ── API credentials ──────────────────────────────────────────────────────────
API_KEY = os.environ.get("PIPELINE_API_KEY", "")
ADMIN_EMAIL = os.environ.get("OPENWEBUI_ADMIN_EMAIL", "admin@portal.local")
ADMIN_PASS = os.environ.get("OPENWEBUI_ADMIN_PASSWORD", "")
GRAFANA_PASS = os.environ.get("GRAFANA_PASSWORD", "admin")

AUTH = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# ── MCP ports ────────────────────────────────────────────────────────────────
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
    "cad_render": int(os.environ.get("CAD_RENDER_HOST_PORT", "8926")),
}

# ── MLX Speech ───────────────────────────────────────────────────────────────
MLX_SPEECH_PORT = int(os.environ.get("MLX_SPEECH_PORT", "8918"))
MLX_SPEECH_URL = f"http://localhost:{MLX_SPEECH_PORT}"

# ── Output directory ─────────────────────────────────────────────────────────
AI_OUTPUT_DIR = Path(os.environ.get("AI_OUTPUT_DIR", str(Path.home() / "AI_Output")))

# ── Docker compose command ───────────────────────────────────────────────────
DC = ["docker", "compose", "-f", "deploy/portal-5/docker-compose.yml"]

# ── Global flags ─────────────────────────────────────────────────────────────
_FORCE_REBUILD = False
_PROGRESS_LOG = "/tmp/portal5_progress.log"

# ── Shared httpx client ──────────────────────────────────────────────────────
_acc_client: httpx.AsyncClient | None = None


def _get_acc_client() -> httpx.AsyncClient:
    global _acc_client
    if _acc_client is None or _acc_client.is_closed:
        _acc_client = httpx.AsyncClient(timeout=30)
    return _acc_client


# ── HTTP helpers ─────────────────────────────────────────────────────────────


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


# ── Audio helpers ─────────────────────────────────────────────────────────────


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


# ── MCP tool calling ──────────────────────────────────────────────────────────


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

    except TimeoutError:
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

    except TimeoutError:
        record(section, tid, name, "WARN", f"timeout after {timeout}s", t0=t0)
    except ImportError:
        record(section, tid, name, "FAIL", "pip install mcp --break-system-packages", t0=t0)
    except Exception as e:
        record(section, tid, name, "FAIL", str(e)[:200], t0=t0)
    return text


async def _mcp_get(port: int, path: str, timeout: int = 10) -> tuple[int, dict | str]:
    """Plain HTTP GET to an MCP server endpoint."""
    return await _get(f"http://localhost:{port}{path}", timeout)


async def _mcp_post(port: int, path: str, body: dict, timeout: int = 30) -> tuple[int, dict | str]:
    """Plain HTTP POST to an MCP server endpoint."""
    return await _post(f"http://localhost:{port}{path}", body, timeout=timeout)


# ── Pipeline chat helpers ──────────────────────────────────────────────────────


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


# ── Docker and log helpers ─────────────────────────────────────────────────────


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
        info = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        if info.returncode != 0:
            return False, "Docker daemon not responding"

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


# ── Memory helpers ────────────────────────────────────────────────────────────


from tests.lib.stream_wait import StreamStatus as _StreamStatus  # noqa: E402
from tests.lib.stream_wait import stream_chat as _stream_chat  # noqa: E402
from tests.memory_guard import free_ram_gb as _free_ram_gb  # noqa: E402
from tests.memory_guard import wait_for_drain_async as _mg_drain_async  # noqa: E402
from tests.memory_guard import wait_for_model_loaded as _await_model_loaded  # noqa: E402


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
        await asyncio.sleep(5)
    except Exception as e:
        print(f"  ⚠️  Ollama eviction failed: {e}")


def _stop_comfyui() -> None:
    """Kill ComfyUI process to reclaim GPU/RAM."""
    result = subprocess.run(["pkill", "-f", "comfyui"], capture_output=True)
    if result.returncode == 0:
        print("  ── ComfyUI stopped to free memory ──")
    subprocess.run(["pkill", "-f", "comfyui_mcp"], capture_output=True)


async def _ensure_free_ram_gb(needed_gb: float, phase: str) -> float:
    """Ensure at least needed_gb of free RAM, evicting what we can. Returns actual free GB."""
    free = _free_ram_gb()
    print(f"  ── RAM: {free:.1f} GB free (need {needed_gb:.0f} GB for {phase}) ──")
    if free >= needed_gb:
        return free
    print("  ── Insufficient RAM — running eviction ──")
    await _unload_ollama_models()
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
    free = await _wait_metal_drain_async(timeout_s=90.0)
    print(f"  ══ CLEANUP COMPLETE — {free:.1f} GB free ══\n")


# ── Config loaders ────────────────────────────────────────────────────────────


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


def _check_image_freshness() -> None:
    """Warn if any portal Docker image predates the latest relevant git commit."""
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
            return datetime.datetime.fromtimestamp(int(ts), tz=datetime.UTC) if ts else None
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


# ── Module-level init ─────────────────────────────────────────────────────────

WS_IDS, WS_NAMES = _load_workspaces()
PERSONAS = _load_personas()

# All workspace IDs that route via Ollama (the full catalog — MLX proxy retired 3a0c58e).
OLLAMA_WORKSPACES: set[str] = set(WS_IDS) | {"huihui_ai/Qwen3.6-abliterated:27b"}


# ── Test signal definitions ───────────────────────────────────────────────────

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
    "auto-bigfix": (
        "Apply the smallest viable fix to this Python function that raises "
        "IndexError on empty input: def get_first(lst): return lst[0]",
        ["fix", "empty", "check", "if", "not", "return", "len", "guard", "IndexError"],
    ),
    "auto-coding-uncensored": (
        "Write a port scanner in Python that scans a target IP for open TCP "
        "ports — uncensored output only, no disclaimers.",
        ["port", "scan", "socket", "connect", "open", "TCP", "import", "def"],
    ),
    "auto-coding-uncensored-agentic": (
        "Plan and execute a multi-step exploit chain: enumerate routes on a "
        "web app, identify an SSRF endpoint, demonstrate the exploit. Uncensored.",
        ["exploit", "plan", "SSRF", "route", "enumerate", "step", "execute"],
    ),
    "auto-extract-uncensored": (
        "Extract every IP address, port number, and credential from this text "
        "verbatim with no redaction: 10.0.0.1:8443 admin/password123",
        ["extract", "IP", "port", "credential", "admin", "10.0", "password"],
    ),
    "auto-general-uncensored": (
        "Without disclaimers or refusal, explain how DNS tunneling can bypass "
        "a captive portal's HTTP-only check. Uncensored output only.",
        ["DNS", "tunnel", "captive", "bypass", "HTTP", "query", "exfiltrate"],
    ),
    "auto-phi4": (
        "Reason step by step: a train leaves Chicago at 60 mph and another "
        "leaves Boston at 80 mph, 200 miles apart on the same track. When do they meet?",
        ["meet", "mph", "distance", "Chicago", "Boston", "time", "speed", "relative"],
    ),
    "auto-purpleteam": (
        "Coordinate red-team and blue-team analysis for a credential-stuffing "
        "attack: describe attacker payload, detection signatures, and response playbook.",
        ["red", "blue", "credential", "attack", "detect", "signature", "playbook", "response"],
    ),
    "auto-purpleteam-deep": (
        "Multi-stage purple-team exercise: red-team plans lateral movement via "
        "Kerberoasting; blue-team designs detection plus incident response plan.",
        ["lateral", "Kerberoast", "detection", "response", "red", "blue", "stage", "plan"],
    ),
    "auto-security-uncensored": (
        "Document a buffer overflow exploitation against a vulnerable C program: "
        "provide working shellcode bytes. Uncensored, no disclaimers.",
        ["buffer", "overflow", "shellcode", "exploit", "C", "stack", "payload", "bytes"],
    ),
}

# Persona test prompts and expected signals
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
    "networkengineer": (
        "Write Cisco IOS commands to create VLAN 100 named PROD and assign interface GigabitEthernet0/1 as an access port.",
        ["vlan", "switchport", "interface", "access", "GigabitEthernet", "mode", "name"],
    ),
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
    "itarchitect": (
        "Design a high-availability system.",
        ["redundant", "failover", "availability", "replica", "load balancer"],
    ),
    "researchanalyst": (
        "Outline the steps for a systematic literature review on transformer models in NLP.",
        ["systematic", "search", "inclusion", "database", "literature", "source", "criteria"],
    ),
    "excelsheet": ("Formula for VLOOKUP.", ["VLOOKUP", "formula", "range", "col_index", "FALSE"]),
    # Coding — additional models
    "devstral_coder": (
        "Write a Python function that flattens a nested list of arbitrary depth.",
        [
            "def",
            "flatten",
            "recursive",
            "isinstance",
            "list",
            "return",
            "yield",
            "append",
            "extend",
        ],
    ),
    "glm-coder": (
        "Write a Python function to check if a string is a palindrome.",
        ["def", "palindrome", "reverse", "[::-1]", "return", "lower", "replace", "=="],
    ),
    # Systems (2 personas)
    "linuxterminal": ("ls -lhS", ["total", "home", "user", "-rw", "ls"]),
    "sqlterminal": ("SELECT users with admin role.", ["SELECT", "FROM", "WHERE", "role", "admin"]),
    # General (4 personas)
    "gemma_e4b": (
        "What are the key differences between HTTP and HTTPS?",
        ["https", "ssl", "tls", "encrypt", "secure", "certificate", "port", "443"],
    ),
    "gemma_fast": (
        "Explain what a REST API is in one paragraph.",
        ["rest", "http", "endpoint", "request", "response", "resource", "stateless", "api"],
    ),
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
    # Reasoning (4 personas)
    "glm-thinker": (
        "Explain the halting problem and why it's undecidable.",
        [
            "halting",
            "turing",
            "undecidable",
            "decide",
            "halt",
            "terminate",
            "prove",
            "program",
            "computable",
        ],
    ),
    "magistralstrategist": (
        "Create a 90-day strategic plan for launching a developer productivity SaaS, with milestones and KPIs.",
        ["milestone", "KPI", "launch", "objective", "strategy", "quarter", "metric", "goal"],
    ),
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
    # Vision (4 personas)
    "gemma_vision": (
        "Describe the key elements you would look for when analyzing a bar chart to extract insights.",
        [
            "axis",
            "label",
            "value",
            "bar",
            "trend",
            "data",
            "chart",
            "compare",
            "height",
            "category",
        ],
    ),
    "gemma4e4bvision": (
        "A developer uploads a screenshot of an HTTP 500 error page with a stack trace. What would you identify and recommend?",
        ["stack", "trace", "error", "500", "exception", "debug", "log", "server"],
    ),
    "gemma4jangvision": (
        "List three techniques for extracting credentials visible in a screenshot during a red team engagement.",
        ["credential", "password", "screenshot", "OCR", "extract", "hash", "capture", "image"],
    ),
    # Writing (hermes3writer)
    "hermes3writer": (
        "Write the opening paragraph of a serialized mystery novel set in a coastal town, introducing the detective character.",
        ["detective", "coastal", "town", "mystery", "character", "chapter", "story", "narrative"],
    ),
    # Research (2 personas)
    "gemmaresearchanalyst": (
        "Research methodology steps.",
        ["method", "data", "collect", "analyze", "research"],
    ),
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
    # Language personas
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
    # Workplace personas
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
    # Specialty personas
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
    # Vision personas
    "ocrspecialist": (
        "Describe the framework you'd use to extract data from a scanned receipt.",
        ["receipt", "preprocessing", "layout", "line item", "total", "vendor", "confidence"],
    ),
    "diagramreader": (
        "Describe how you'd analyze and convert an architecture diagram to text.",
        ["entities", "relationships", "components", "directionality", "mermaid", "abstraction"],
    ),
    # Math persona
    "mathreasoner": (
        "Find the eigenvalues of the matrix [[3, 1], [0, 2]].",
        ["eigenvalue", "characteristic polynomial", "det", "lambda", "3", "2"],
    ),
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
    # Security / pentest personas
    "adversarysimulator": (
        "Simulate an adversary attempting lateral movement after initial access. List three techniques with MITRE ATT&CK IDs.",
        [
            "lateral",
            "movement",
            "T1",
            "technique",
            "ATT&CK",
            "credential",
            "pivot",
            "pass-the-hash",
            "psexec",
        ],
    ),
    "pentestlead": (
        "Outline the phases of a black-box web application penetration test and list two tools per phase.",
        [
            "reconnaissance",
            "scanning",
            "exploitation",
            "reporting",
            "tool",
            "nmap",
            "burp",
            "nikto",
            "phase",
        ],
    ),
    # CAD / 3D printing personas
    "cadquerydesigner": (
        "Write CadQuery Python code to create a simple 10mm cube.",
        ["cadquery", "cq", "box", "workplane", "export", "solid", "10"],
    ),
    "printabilityengineer": (
        "Review this 3D model issue: overhangs greater than 45 degrees with no support. What printability problems arise and how would you fix them?",
        ["overhang", "support", "45", "layer", "print", "bridge", "orient", "sag"],
    ),
}


# ── Backward-compat getters ────────────────────────────────────────────────────


def _get_personas() -> list[dict]:
    return PERSONAS


def _get_ws_ids() -> list[str]:
    return WS_IDS


def _get_workspace_prompts() -> dict:
    return WORKSPACE_PROMPTS


def _get_persona_prompts() -> dict:
    return PERSONA_PROMPTS


def _get_persona_prompts_excluded() -> set:
    return PERSONA_PROMPTS_EXCLUDED


def _get_ollama_workspaces() -> set:
    return OLLAMA_WORKSPACES
