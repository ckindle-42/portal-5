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

from portal.platform.data_loader import load_data

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
# Hermetic-test guard — same class of bug as bench/config.py's _load_env:
# this ran unconditionally at import time, leaking every real .env key into
# whichever test session transitively imported this module.
if os.environ.get("UNIT_TEST_MODE") != "1":
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
# BEFORE any portal.platform.inference import — prometheus_client reads the env var at
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
EMBEDDING_URL = os.environ.get("EMBEDDING_URL", "http://localhost:8917")

# ── API credentials ──────────────────────────────────────────────────────────
API_KEY = os.environ.get("PIPELINE_API_KEY", "")
ADMIN_EMAIL = os.environ.get("OPENWEBUI_ADMIN_EMAIL", "admin@portal.local")
ADMIN_PASS = os.environ.get("OPENWEBUI_ADMIN_PASSWORD", "")
GRAFANA_PASS = os.environ.get("GRAFANA_PASSWORD", "admin")

AUTH = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# ── MCP ports ────────────────────────────────────────────────────────────────
MCP = {
    "mflux": int(os.environ.get("MFLUX_MCP_PORT", "8933")),
    "video_mlx": int(os.environ.get("VIDEO_MLX_MCP_PORT", "8935")),
    "music_minimax": int(os.environ.get("MUSIC_MINIMAX_PORT", "8912")),
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
        from mcp.client.streamable_http import streamable_http_client

        url = f"http://localhost:{port}/mcp"
        async with streamable_http_client(url) as (read, write):
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
        from mcp.client.streamable_http import streamable_http_client

        url = f"http://localhost:{port}/mcp"
        async with streamable_http_client(url) as (read, write):
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
    route_params: dict[str, str] | None = None,
    idle_gap_s: float | None = None,
) -> tuple[int, str, str, str]:
    """Chat request that also returns the model and route header.

    Returns (status_code, response_text, model_used, route_descriptor).
    route_descriptor is the x-portal-route header value: "{workspace};{backend_id};{model}".
    Uses shared client with 3-attempt backoff [0, 5, 15]s.
    On 502/503 continues to the next retry (backoff already handles the wait).

    When `tools` is provided the OpenAI tools array is forwarded to the backend.
    If the model responds with tool_calls (not content), those are serialized to
    JSON and returned as the response text so signal checks still work.

    `route_params` (optional): forwarded as URL query params — e.g.
    ``{"variant": "redteam"}`` or ``{"model": "phi4-reasoning:plus"}``.
    Acceptance tests call the pipeline directly (unlike the UAT driver, which
    is OWUI-mediated and can't carry these — see tests/uat/skips.py's
    _run_via_dispatcher docstring), so this is a plain query-string append.
    See portal.platform.inference.router.handlers — the pipeline reads
    request.query_params.get("variant"/"model") off its own incoming request.
    """
    msgs: list[dict] = []
    if system:
        # Callers deliberately select the applicable persona contract (S10c
        # caps it at 8 KiB). Truncating that contract here silently discarded
        # the compliance HARD CONSTRAINTS and made the acceptance request
        # materially different from the production persona request.
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    body: dict = {"model": workspace, "messages": msgs, "stream": True, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools

    url = f"{PIPELINE_URL}/v1/chat/completions"
    if route_params:
        from urllib.parse import urlencode

        url = f"{url}?{urlencode(route_params)}"

    stream_options = {
        "url": url,
        "body": body,
        "headers": AUTH,
        "client": _get_acc_client(),
        "overall_ceiling_s": float(timeout),
        "ollama_url": OLLAMA_URL,
    }
    if idle_gap_s is not None:
        stream_options["idle_gap_s"] = idle_gap_s

    result = await _stream_chat(
        **stream_options,
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
        print(f"  ⚠️  Still low on RAM ({free:.1f}GB < {needed_gb}GB needed)")
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
    """Load workspace definitions from portal.platform.inference.router.workspaces."""
    sys.path.insert(0, str(ROOT))
    from portal.platform.inference.router.workspaces import WORKSPACES  # noqa: PLC0415

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
                "portal/platform/inference/",
                "config/backends.yaml",
                "config/personas/",
                "Dockerfile.pipeline",
                "pyproject.toml",
            ],
        ),
        (
            "mcp-services",
            "portal-5-mcp-documents",
            [
                "portal/modules/",
                "portal/platform/mcp_host/",
                "portal/platform/memory/",
                "portal_mcp/",
                "portal_channels/",
                "Dockerfile.mcp",
                "pyproject.toml",
            ],
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


# Workspace test prompts and expected signals. Value is (prompt, signals) or,
# for a canonicalized former-alias entry (BUILD_PROGRAM_ALIAS_RETIRE_V1.md
# Phase 3), (prompt, signals, route_params) where route_params is forwarded
# by _chat_with_model as a ?variant=/?model= query param. Dict keys here are
# descriptive labels — s03_routing.py's PRODUCTION_WORKSPACES pairs each
# label with the real (base) workspace id used for the pipeline call.


WORKSPACE_PROMPTS = {
    k: tuple(v) for k, v in load_data("tests/data", "acceptance_common_workspace_prompts").items()
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
    # Specialized personas tested via workspace routing or S24 (general-purpose
    # workspace personas: dailydriver/auto-daily, nemotronlightning/auto-nemotron)
    "dailydriver",
    "nemotronlightning",
}
PERSONA_PROMPTS = {
    k: tuple(v) for k, v in load_data("tests/data", "acceptance_common_persona_prompts").items()
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
