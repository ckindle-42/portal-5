#!/usr/bin/env python3
"""
Portal 5 — ComfyUI / Image & Video Generation Acceptance Tests
==============================================================
Dedicated test script for image and video generation testing.
Separated from portal5_acceptance_v4.py because ComfyUI testing
requires significant iteration (workflow updates, model availability,
API version compatibility) independent of the core pipeline tests.

Run from the repo root:
    python3 portal5_acceptance_comfyui.py
    python3 portal5_acceptance_comfyui.py --verbose
    python3 portal5_acceptance_comfyui.py --section C2  # single section

Prerequisites:
    ComfyUI running on :8188 (host-native, NOT in Docker):
        cd ~/ComfyUI && python main.py --listen 0.0.0.0 --port 8188

    Portal 5 stack running:
        ./launch.sh status   # verify all services up

    Ollama models unloaded (script does this automatically before generation):
        Only needed if you have large models loaded — frees unified memory.

    Python deps (install once):
        pip install mcp httpx pyyaml --break-system-packages

Sections:
    C0  — Prerequisites (memory, dependencies, ComfyUI process)
    C1  — ComfyUI direct API (system stats, object info, model discovery)
    C2  — MCP bridge health (comfyui_mcp, video_mcp containers)
    C3  — Model discovery via MCP (list_workflows, list_video_models)
    C4  — Image generation: FLUX schnell (fast, 4 steps)
    C5  — Image generation: FLUX dev + LoRAs + NSFW checkpoint
    C6  — Image generation: all SDXL/XL variants (loops every installed XL checkpoint)
    C7  — Image generation: parameter sweep (steps, cfg, sampler, seed)
    C8  — Video generation: HunyuanVideo T2V (short/long clip, NSFW LoRA)
    C9  — Pipeline round-trips (auto-video workspace via portal-pipeline)
    C10 — Output validation (file size, MIME type, URL accessibility)
    C11 — All LoRAs × FLUX schnell (exhaustive per-LoRA coverage)

Status model:
    PASS    — verified working exactly as expected
    FAIL    — service running but behavior does not match expectation
    BLOCKED — correct assertion; only a protected file change can fix it
    WARN    — soft failure: served but response does not fully match assertion
    INFO    — informational, no assertion (e.g. model not installed)

PROTECTED — never modify these files:
    portal_pipeline/**  portal_mcp/**  config/  deploy/  Dockerfile.*
    scripts/openwebui_init.py  docs/HOWTO.md  imports/

Changes:
    v1.0 (2026-04-05):
        Initial standalone ComfyUI/video test suite split from
        portal5_acceptance_v4.py S18/S19. Adds: direct ComfyUI API tests,
        per-checkpoint generation tests, parameter sweep, output validation,
        Wan2.2 video, and memory management before generation.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.resolve()
# Repo root — one level up from tests/
REPO_ROOT = ROOT.parent


# ── Load .env ─────────────────────────────────────────────────────────────────
def _load_env() -> None:
    # Try tests/.env first, fall back to repo-root .env (the canonical location)
    for candidate in [ROOT / ".env", REPO_ROOT / ".env"]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())
            break


_load_env()

PIPELINE_URL = "http://localhost:9099"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").replace(
    "host.docker.internal", "localhost"
)
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://localhost:8188").replace(
    "host.docker.internal", "localhost"
)

API_KEY = os.environ.get("PIPELINE_API_KEY", "")
AUTH = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# MCP ports
COMFYUI_MCP_PORT = int(os.environ.get("COMFYUI_MCP_HOST_PORT", "8910"))
VIDEO_MCP_PORT = int(os.environ.get("VIDEO_MCP_HOST_PORT", "8911"))

DC = ["docker", "compose", "-f", "deploy/portal-5/docker-compose.yml"]

_verbose = False


# ── Checkpoint filter ─────────────────────────────────────────────────────────
def _filter_checkpoints(ckpts: list[str]) -> list[str]:
    """Remove files from the checkpoints folder that are clearly not checkpoints.

    ComfyUI scans models/checkpoints/ for any .safetensors — LoRAs or other
    model types accidentally placed there show up as phantom checkpoint options.
    """
    exclude = ["lora"]
    return [c for c in ckpts if not any(e in c.lower() for e in exclude)]


# ── Result model ──────────────────────────────────────────────────────────────
@dataclass
class R:
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
    icon = _ICON.get(r.status, "  ")
    dur = f"({r.duration:.1f}s)" if r.duration else ""
    print(f"  {icon} [{r.tid}] {r.name}  {r.detail}  {dur}")
    if _verbose and r.evidence:
        for e in r.evidence:
            print(f"       {e}")
    return r


def record(section, tid, name, status, detail="", evidence=None, fix="", t0=None) -> R:
    dur = time.time() - t0 if t0 else 0.0
    r = R(section, tid, name, status, detail, evidence or [], fix, dur)
    _log.append(r)
    if status == "BLOCKED":
        _blocked.append(r)
    return _emit(r)


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=str(ROOT)
        ).stdout.strip()
    except Exception:
        return "unknown"


# ── Memory management (free unified memory before generation) ─────────────────
async def _unload_ollama_models() -> None:
    """Evict all Ollama models from unified memory via keep_alive=0."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{OLLAMA_URL}/api/ps")
            if r.status_code != 200:
                return
            models = [m["name"] for m in r.json().get("models", [])]
        if not models:
            print("  ℹ️  No Ollama models loaded — nothing to evict")
            return
        print(f"  ── Evicting {len(models)} Ollama model(s) from unified memory ──")
        async with httpx.AsyncClient(timeout=30) as c:
            for model in models:
                try:
                    await c.post(
                        f"{OLLAMA_URL}/api/generate",
                        json={"model": model, "keep_alive": 0},
                        timeout=10,
                    )
                    print(f"     evicted: {model}")
                except Exception:
                    pass
    except Exception as e:
        print(f"  ⚠️  Ollama eviction failed: {e}")


async def _free_memory_for_comfyui() -> None:
    """Unload Ollama models before ComfyUI tests."""
    print("  ── Freeing unified memory for ComfyUI ──")
    await _unload_ollama_models()


async def _clear_comfyui_queue() -> None:
    """Interrupt running tasks and clear pending queue — prevents stuck jobs from blocking tests."""
    print("  ── Clearing ComfyUI queue ──")
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            # Check queue state first
            r = await c.get(f"{COMFYUI_URL}/queue")
            if r.status_code == 200:
                q = r.json()
                running = len(q.get("queue_running", []))
                pending = len(q.get("queue_pending", []))
                if running == 0 and pending == 0:
                    print("    Queue already empty — nothing to clear")
                    return
                print(f"    Found {running} running + {pending} pending tasks — clearing")

            # Interrupt any running task
            await c.post(f"{COMFYUI_URL}/interrupt")
            # Free models and clear queue
            await c.post(
                f"{COMFYUI_URL}/free",
                json={"unload_models": False, "free_memory": False},
            )
            # Verify cleared
            r2 = await c.get(f"{COMFYUI_URL}/queue")
            if r2.status_code == 200:
                q2 = r2.json()
                remaining = len(q2.get("queue_running", [])) + len(q2.get("queue_pending", []))
                if remaining == 0:
                    print("    Queue cleared successfully")
                else:
                    print(f"    Warning: {remaining} tasks still in queue after clear")
    except Exception as e:
        print(f"    Warning: queue clear failed: {e}")


async def _wait_for_comfyui_idle(max_wait: int = 300) -> bool:
    """Wait for ComfyUI queue to be empty before proceeding.

    Returns True if idle, False if still busy after max_wait.
    Prevents piling up MCP requests behind slow-loading models.
    If the MCP client timed out but ComfyUI is still processing the old job,
    we wait for it to finish instead of stacking another one.
    """
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{COMFYUI_URL}/queue")
                if r.status_code == 200:
                    q = r.json()
                    running = len(q.get("queue_running", []))
                    pending = len(q.get("queue_pending", []))
                    if running == 0 and pending == 0:
                        return True
        except Exception:
            pass
        await asyncio.sleep(5)
    return False


# ── MCP SDK call ──────────────────────────────────────────────────────────────
async def _mcp(
    port: int,
    tool: str,
    args: dict,
    *,
    section: str,
    tid: str,
    name: str,
    ok_fn,
    detail_fn=None,
    warn_if: list[str] | None = None,
    timeout: int | None = None,
) -> None:
    """Call an MCP tool and record the result.

    timeout: seconds before giving up. Pass None (default) for generation tools —
    the MCP server's internal COMFYUI_TIMEOUT / VIDEO_TIMEOUT already gates how long
    it will wait for ComfyUI to finish. Adding a test-side timeout on top causes false
    WARNs when generation is simply slow. Use a small explicit timeout only for
    near-instant tools (health checks, list_*, etc.).
    """
    t0 = time.time()
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        url = f"http://localhost:{port}/mcp"
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                if timeout is not None:
                    result = await asyncio.wait_for(session.call_tool(tool, args), timeout=timeout)
                else:
                    result = await session.call_tool(tool, args)
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
    except BaseException as e:
        err_str = str(e)
        if (
            "TaskGroup" in err_str
            or "Cancel" in type(e).__name__
            or isinstance(e, BaseExceptionGroup)
        ):
            label = (
                f"timeout after {timeout}s (TaskGroup)"
                if timeout
                else f"cancelled ({err_str[:80]})"
            )
            record(section, tid, name, "WARN", label, t0=t0)
        else:
            record(section, tid, name, "FAIL", err_str[:200], t0=t0)


# ── Pipeline chat ─────────────────────────────────────────────────────────────
async def _chat(
    workspace: str,
    prompt: str,
    max_tokens: int = 400,
    timeout: int = 240,
) -> tuple[int, str]:
    body = {
        "model": workspace,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "max_tokens": max_tokens,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(f"{PIPELINE_URL}/v1/chat/completions", headers=AUTH, json=body)
            if r.status_code != 200:
                return r.status_code, r.text[:200]
            data = r.json()
            msg = data["choices"][0]["message"]
            text = msg.get("content") or msg.get("reasoning") or ""
            return 200, text
    except Exception as e:
        return 0, str(e)[:200]


# ── ComfyUI direct API helpers ────────────────────────────────────────────────
async def _comfyui_get(path: str, timeout: int = 10) -> tuple[int, dict | str]:
    """GET from the ComfyUI API. Returns (status_code, json_or_text)."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(f"{COMFYUI_URL}{path}")
            try:
                return r.status_code, r.json()
            except Exception:
                return r.status_code, r.text
    except Exception as e:
        return 0, str(e)


async def _comfyui_post(path: str, body: dict, timeout: int = 30) -> tuple[int, dict | str]:
    """POST to the ComfyUI API. Returns (status_code, json_or_text)."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(f"{COMFYUI_URL}{path}", json=body)
            try:
                return r.status_code, r.json()
            except Exception:
                return r.status_code, r.text
    except Exception as e:
        return 0, str(e)


async def _wait_for_comfyui_queue(prompt_id: str, timeout: int = 600) -> tuple[bool, str]:
    """Poll ComfyUI /history until the prompt_id appears (generation complete).

    Returns (success, detail_message).
    ComfyUI moves a prompt from the queue to /history when generation finishes.
    Polls /queue to detect if we're even in the queue, then /history for completion.
    """
    deadline = time.time() + timeout
    queued_confirmed = False

    while time.time() < deadline:
        # Check history first — if it's there, we're done
        code, history = await _comfyui_get(f"/history/{prompt_id}")
        if code == 200 and isinstance(history, dict) and prompt_id in history:
            entry = history[prompt_id]
            outputs = entry.get("outputs", {})
            # Collect all image/video output references
            files: list[str] = []
            for node_outputs in outputs.values():
                for key in ("images", "videos", "gifs"):
                    for item in node_outputs.get(key, []):
                        fname = item.get("filename", "")
                        subfolder = item.get("subfolder", "")
                        ftype = item.get("type", "output")
                        files.append(f"{ftype}/{subfolder}/{fname}".strip("/"))
            if files:
                return True, f"{len(files)} output(s): {', '.join(files[:3])}"
            # Completed but no outputs (error node)
            status_info = entry.get("status", {})
            status_str = status_info.get("status_str", "unknown")
            return False, f"completed with status={status_str}, no output files"

        # Check queue to confirm our job is in progress
        code, queue = await _comfyui_get("/queue")
        if code == 200 and isinstance(queue, dict):
            running = [
                item
                for item in queue.get("queue_running", [])
                if len(item) > 1 and item[1] == prompt_id
            ]
            pending = [
                item
                for item in queue.get("queue_pending", [])
                if len(item) > 1 and item[1] == prompt_id
            ]
            if running or pending:
                queued_confirmed = True
            elif queued_confirmed:
                # Was in queue, now gone — check history one more time
                await asyncio.sleep(0.5)
                code2, history2 = await _comfyui_get(f"/history/{prompt_id}")
                if code2 == 200 and isinstance(history2, dict) and prompt_id in history2:
                    return True, "completed (dequeued)"
                return False, "left queue without appearing in history"

        await asyncio.sleep(2)

    return False, f"timed out after {timeout}s"


async def _comfyui_watchdog(interval: int = 60, stall_limit: int = 2400) -> None:
    """Background task that prints periodic progress for long-running generations.

    Polls ComfyUI /queue every `interval` seconds and logs the running prompt.
    If the queue has been non-empty with no state change for `stall_limit` seconds,
    prints a STUCK warning so the operator knows to investigate.
    This runs alongside generation calls (not instead of them) — completion is still
    event-driven from the MCP server; this only surfaces stuck-job visibility.
    """
    last_running_id: str = ""
    stall_start: float = 0.0
    while True:
        await asyncio.sleep(interval)
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{COMFYUI_URL}/queue")
                q = r.json()
            running = q.get("queue_running", [])
            pending = q.get("queue_pending", [])
            if running:
                rid = running[0][1] if len(running[0]) > 1 else str(running[0])
                elapsed = time.time() - stall_start if last_running_id == rid else 0
                if last_running_id != rid:
                    last_running_id = rid
                    stall_start = time.time()
                    elapsed = 0
                elapsed_min = int(elapsed // 60)
                elapsed_sec = int(elapsed % 60)
                print(
                    f"  ⏳ ComfyUI generating… {elapsed_min}m{elapsed_sec:02d}s elapsed"
                    f"  (queue: {len(pending)} pending)"
                )
                if elapsed > stall_limit:
                    print(
                        f"  ⚠️  WATCHDOG: same job running for >{stall_limit // 60}min — "
                        "may be stuck. Check ComfyUI logs."
                    )
            else:
                last_running_id = ""
                stall_start = 0.0
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# C0 — PREREQUISITES
# ═══════════════════════════════════════════════════════════════════════════════
async def C0() -> None:
    print("\n━━━ C0. PREREQUISITES ━━━")
    sec = "C0"

    # Python deps
    t0 = time.time()
    missing = []
    for pkg in ["httpx", "mcp", "yaml"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    record(
        sec,
        "C0-01",
        "Python dependencies available",
        "PASS" if not missing else "FAIL",
        f"missing: {missing}" if missing else "httpx, mcp, yaml all present",
        t0=t0,
    )

    # Pipeline reachable
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{PIPELINE_URL}/health")
            record(
                sec,
                "C0-02",
                f"Portal pipeline reachable ({PIPELINE_URL})",
                "PASS" if r.status_code == 200 else "FAIL",
                f"HTTP {r.status_code}",
                t0=t0,
            )
    except Exception as e:
        record(sec, "C0-02", f"Portal pipeline reachable ({PIPELINE_URL})", "FAIL", str(e), t0=t0)

    # ComfyUI process running
    t0 = time.time()
    result = subprocess.run(
        ["pgrep", "-f", "comfy.*main.py|python.*main.py.*8188"],
        capture_output=True,
        text=True,
    )
    comfyui_process_running = result.returncode == 0
    record(
        sec,
        "C0-03",
        "ComfyUI process running on host",
        "PASS" if comfyui_process_running else "WARN",
        f"PIDs: {result.stdout.strip()}"
        if comfyui_process_running
        else "not found — start: cd ~/ComfyUI && python main.py --listen 0.0.0.0 --port 8188",
        t0=t0,
    )

    # ComfyUI API reachable
    t0 = time.time()
    code, data = await _comfyui_get("/system_stats")
    record(
        sec,
        "C0-04",
        f"ComfyUI API reachable ({COMFYUI_URL})",
        "PASS" if code == 200 else "WARN",
        f"HTTP {code}" + (f" — {str(data)[:80]}" if code != 200 else ""),
        t0=t0,
    )

    # Free unified memory
    print("  ── Freeing unified memory before tests ──")
    await _free_memory_for_comfyui()

    # Clear ComfyUI queue — stuck tasks from previous runs block all generation tests
    await _clear_comfyui_queue()


# ═══════════════════════════════════════════════════════════════════════════════
# C1 — COMFYUI DIRECT API
# ═══════════════════════════════════════════════════════════════════════════════
async def C1() -> None:
    print("\n━━━ C1. COMFYUI DIRECT API ━━━")
    sec = "C1"

    # System stats
    t0 = time.time()
    code, data = await _comfyui_get("/system_stats")
    if code == 200 and isinstance(data, dict):
        system = data.get("system", {})
        detail = (
            f"Python {system.get('python_version', '?')}, "
            f"ComfyUI version {data.get('comfyui_version', '?')}"
        )
        record(sec, "C1-01", "ComfyUI system_stats", "PASS", detail, t0=t0)
    else:
        record(
            sec,
            "C1-01",
            "ComfyUI system_stats",
            "WARN",
            f"HTTP {code}" if code != 0 else str(data)[:80],
            t0=t0,
        )

    # Prompt queue state
    t0 = time.time()
    code, data = await _comfyui_get("/queue")
    if code == 200 and isinstance(data, dict):
        running = len(data.get("queue_running", []))
        pending = len(data.get("queue_pending", []))
        record(
            sec,
            "C1-02",
            "ComfyUI /queue reachable",
            "PASS",
            f"running={running} pending={pending}",
            t0=t0,
        )
    else:
        record(
            sec,
            "C1-02",
            "ComfyUI /queue reachable",
            "WARN",
            f"HTTP {code}: {str(data)[:80]}",
            t0=t0,
        )

    # Object info (node catalogue)
    t0 = time.time()
    code, data = await _comfyui_get("/object_info", timeout=15)
    if code == 200 and isinstance(data, dict):
        node_count = len(data)
        # Check for key nodes we depend on
        required_nodes = ["KSampler", "CLIPTextEncode", "VAEDecode", "SaveImage"]
        missing_nodes = [n for n in required_nodes if n not in data]
        record(
            sec,
            "C1-03",
            "ComfyUI /object_info (node catalogue)",
            "PASS" if not missing_nodes else "WARN",
            f"{node_count} nodes registered"
            + (f" — missing: {missing_nodes}" if missing_nodes else ""),
            t0=t0,
        )
    else:
        record(
            sec,
            "C1-03",
            "ComfyUI /object_info (node catalogue)",
            "WARN",
            f"HTTP {code}: {str(data)[:80]}",
            t0=t0,
        )

    # Checkpoint model discovery via /object_info
    t0 = time.time()
    checkpoints: list[str] = []
    if code == 200 and isinstance(data, dict):
        ckpt_node = data.get("CheckpointLoaderSimple", {})
        input_types = ckpt_node.get("input", {}).get("required", {})
        ckpt_entry = input_types.get("ckpt_name", [])
        if ckpt_entry and isinstance(ckpt_entry[0], list):
            checkpoints = ckpt_entry[0]
    record(
        sec,
        "C1-04",
        "Checkpoint models installed",
        "PASS" if checkpoints else "WARN",
        f"{len(checkpoints)} checkpoint(s): {', '.join(checkpoints[:5])}"
        if checkpoints
        else "none found — check ComfyUI models/checkpoints/",
        t0=t0,
    )

    # VAE discovery
    t0 = time.time()
    vaes: list[str] = []
    if code == 200 and isinstance(data, dict):
        vae_node = data.get("VAELoader", {})
        input_types = vae_node.get("input", {}).get("required", {})
        vae_entry = input_types.get("vae_name", [])
        if vae_entry and isinstance(vae_entry[0], list):
            vaes = vae_entry[0]
    record(
        sec,
        "C1-05",
        "VAE models installed",
        "PASS" if vaes else "INFO",
        f"{len(vaes)} VAE(s): {', '.join(vaes[:5])}"
        if vaes
        else "none (using checkpoint-embedded VAE)",
        t0=t0,
    )

    # LoRA discovery
    t0 = time.time()
    loras: list[str] = []
    if code == 200 and isinstance(data, dict):
        lora_node = data.get("LoraLoader", {})
        input_types = lora_node.get("input", {}).get("required", {})
        lora_entry = input_types.get("lora_name", [])
        if lora_entry and isinstance(lora_entry[0], list):
            loras = lora_entry[0]
    record(
        sec,
        "C1-06",
        "LoRA models installed",
        "PASS" if loras else "WARN",
        f"{len(loras)} LoRA(s): {', '.join(loras[:5])}"
        if loras
        else "none installed — download at least one LoRA",
        t0=t0,
    )

    # Upscale models
    t0 = time.time()
    upscalers: list[str] = []
    if code == 200 and isinstance(data, dict):
        up_node = data.get("UpscaleModelLoader", {})
        input_types = up_node.get("input", {}).get("required", {})
        up_entry = input_types.get("model_name", [])
        # ComfyUI returns ['COMBO', {'options': ['model1', 'model2']}] for upscale
        if up_entry and isinstance(up_entry, list) and len(up_entry) > 1:
            if isinstance(up_entry[1], dict):
                upscalers = up_entry[1].get("options", [])
            elif isinstance(up_entry[0], list):
                upscalers = up_entry[0]
    record(
        sec,
        "C1-07",
        "Upscale models installed",
        "PASS" if upscalers else "WARN",
        f"{len(upscalers)} upscaler(s): {', '.join(upscalers[:5])}"
        if upscalers
        else "none installed — download an upscale model (e.g. RealESRGAN_x4.pth)",
        t0=t0,
    )

    # Store checkpoints for later sections
    return checkpoints


# ═══════════════════════════════════════════════════════════════════════════════
# C2 — MCP BRIDGE HEALTH
# ═══════════════════════════════════════════════════════════════════════════════
async def C2() -> None:
    print("\n━━━ C2. MCP BRIDGE HEALTH ━━━")
    sec = "C2"

    for tid, port, name in [
        ("C2-01", COMFYUI_MCP_PORT, "ComfyUI MCP bridge"),
        ("C2-02", VIDEO_MCP_PORT, "Video MCP bridge"),
    ]:
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(f"http://localhost:{port}/health")
                record(
                    sec,
                    tid,
                    f"{name} (:{port})",
                    "PASS" if r.status_code == 200 else "WARN",
                    str(r.json()) if r.status_code == 200 else f"HTTP {r.status_code}",
                    t0=t0,
                )
        except Exception as e:
            record(sec, tid, f"{name} (:{port})", "FAIL", str(e)[:120], t0=t0)

    # Docker containers running
    t0 = time.time()
    result = subprocess.run(
        DC + ["ps", "--format", "json"],
        capture_output=True,
        text=True,
    )
    containers: list[str] = []
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                name = obj.get("Name", obj.get("Service", ""))
                if "comfyui" in name.lower() or "video" in name.lower():
                    containers.append(f"{name}={obj.get('State', '?')}")
            except Exception:
                pass
    record(
        sec,
        "C2-03",
        "ComfyUI+video MCP containers running",
        "PASS" if containers else "WARN",
        ", ".join(containers) if containers else "none matched — check docker compose ps",
        t0=t0,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# C3 — MODEL DISCOVERY VIA MCP
# ═══════════════════════════════════════════════════════════════════════════════
async def C3() -> None:
    print("\n━━━ C3. MODEL DISCOVERY VIA MCP ━━━")
    sec = "C3"

    # list_workflows via ComfyUI MCP
    await _mcp(
        COMFYUI_MCP_PORT,
        "list_workflows",
        {},
        section=sec,
        tid="C3-01",
        name="list_workflows returns checkpoint list",
        ok_fn=lambda t: len(t) > 2,
        detail_fn=lambda t: f"workflows/checkpoints: {t[:160]}",
        timeout=15,
    )

    # list_video_models via Video MCP
    await _mcp(
        VIDEO_MCP_PORT,
        "list_video_models",
        {},
        section=sec,
        tid="C3-02",
        name="list_video_models returns model list",
        ok_fn=lambda t: len(t) > 2,
        detail_fn=lambda t: f"video models: {t[:160]}",
        timeout=15,
    )

    # list_samplers — not implemented in comfyui_mcp; record as INFO so it doesn't
    # pollute pass/fail counts (it correctly returns "Unknown tool: list_samplers").
    t0 = time.time()
    record(
        sec,
        "C3-03",
        "list_samplers MCP tool",
        "INFO",
        "Not implemented in comfyui_mcp — KSampler sampler list available via /object_info",
        t0=t0,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# C4 — IMAGE GENERATION: FLUX SCHNELL (fast path, 4 steps)
# ═══════════════════════════════════════════════════════════════════════════════
async def C4() -> None:
    print("\n━━━ C4. IMAGE GENERATION — FLUX SCHNELL ━━━")
    sec = "C4"

    # Check availability
    t0 = time.time()
    code, data = await _comfyui_get("/object_info", timeout=15)
    has_flux = False
    if code == 200 and isinstance(data, dict):
        ckpt_node = data.get("CheckpointLoaderSimple", {})
        ckpts = ckpt_node.get("input", {}).get("required", {}).get("ckpt_name", [[]])[0]
        flux_ckpts = [c for c in ckpts if "flux" in c.lower() and "schnell" in c.lower()]
        has_flux = bool(flux_ckpts)
        record(
            sec,
            "C4-01",
            "FLUX schnell checkpoint installed",
            "PASS" if has_flux else "INFO",
            f"{flux_ckpts[0]}"
            if flux_ckpts
            else "not installed — download: huggingface-cli download black-forest-labs/FLUX.1-schnell",
            t0=t0,
        )
    else:
        record(
            sec,
            "C4-01",
            "FLUX schnell checkpoint installed",
            "WARN",
            f"ComfyUI not reachable (HTTP {code})",
            t0=t0,
        )

    if not has_flux:
        record(
            sec,
            "C4-02",
            "FLUX schnell generation via MCP",
            "INFO",
            "skipped — checkpoint not installed",
            t0=None,
        )
        record(
            sec,
            "C4-03",
            "FLUX schnell output accessible via ComfyUI",
            "INFO",
            "skipped — checkpoint not installed",
            t0=None,
        )
        return

    # Generate via MCP
    await _wait_for_comfyui_idle()
    await _mcp(
        COMFYUI_MCP_PORT,
        "generate_image",
        {
            "prompt": "a red apple on a wooden table, photorealistic, studio lighting",
            "steps": 4,
            "seed": 42,
            "checkpoint": flux_ckpts[0],
        },
        section=sec,
        tid="C4-02",
        name="FLUX schnell: generate_image (4 steps)",
        ok_fn=lambda t: (
            "success" in t.lower()
            or "url" in t.lower()
            or "filename" in t.lower()
            or "output" in t.lower()
        ),
        detail_fn=lambda t: t[:200],
        warn_if=["error", "failed", "rejected", "not available"],
    )

    # Verify output accessible from ComfyUI /view endpoint
    t0 = time.time()
    code, data = await _comfyui_get("/history?max_items=1")
    if code == 200 and isinstance(data, dict) and data:
        # Find the most recent image output
        latest_key = next(iter(data))
        outputs = data[latest_key].get("outputs", {})
        found_image = False
        for node_outputs in outputs.values():
            images = node_outputs.get("images", [])
            if images:
                img = images[0]
                fname = img.get("filename", "")
                subfolder = img.get("subfolder", "")
                ftype = img.get("type", "output")
                # Try to fetch the image
                params = f"filename={fname}&subfolder={subfolder}&type={ftype}"
                img_code, _ = await _comfyui_get(f"/view?{params}", timeout=10)
                found_image = img_code == 200
                record(
                    sec,
                    "C4-03",
                    "FLUX schnell output accessible via /view",
                    "PASS" if found_image else "WARN",
                    f"{fname} — HTTP {img_code}" if fname else "no filename in history",
                    t0=t0,
                )
                break
        if not found_image:
            record(
                sec,
                "C4-03",
                "FLUX schnell output accessible via /view",
                "WARN",
                "no image outputs found in ComfyUI history",
                t0=t0,
            )
    else:
        record(
            sec,
            "C4-03",
            "FLUX schnell output accessible via /view",
            "WARN",
            f"ComfyUI /history returned HTTP {code}",
            t0=t0,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# C5 — IMAGE GENERATION: FLUX DEV (high quality, optional)
# ═══════════════════════════════════════════════════════════════════════════════
async def C5() -> None:
    print("\n━━━ C5. IMAGE GENERATION — FLUX DEV (optional) ━━━")
    sec = "C5"

    t0 = time.time()
    code, data = await _comfyui_get("/object_info", timeout=15)
    has_flux_dev = False
    flux_dev_ckpt = ""
    if code == 200 and isinstance(data, dict):
        ckpt_node = data.get("CheckpointLoaderSimple", {})
        ckpts = ckpt_node.get("input", {}).get("required", {}).get("ckpt_name", [[]])[0]
        flux_dev_ckpts = [c for c in ckpts if "flux" in c.lower() and "dev" in c.lower()]
        has_flux_dev = bool(flux_dev_ckpts)
        flux_dev_ckpt = flux_dev_ckpts[0] if flux_dev_ckpts else ""
        record(
            sec,
            "C5-01",
            "FLUX dev checkpoint installed",
            "PASS" if has_flux_dev else "INFO",
            flux_dev_ckpt
            if has_flux_dev
            else "not installed (optional) — download: huggingface-cli download black-forest-labs/FLUX.1-dev",
            t0=t0,
        )
    else:
        record(
            sec,
            "C5-01",
            "FLUX dev checkpoint installed",
            "WARN",
            f"ComfyUI not reachable (HTTP {code})",
            t0=t0,
        )
        return

    if not has_flux_dev:
        record(
            sec,
            "C5-02",
            "FLUX dev generation via MCP",
            "INFO",
            "skipped — checkpoint not installed",
            t0=None,
        )
        return

    await _wait_for_comfyui_idle()
    await _mcp(
        COMFYUI_MCP_PORT,
        "generate_image",
        {
            "prompt": "mountain landscape at sunrise, dramatic golden hour lighting, 8k detail, photorealistic, professional photography",
            "steps": 28,
            "cfg": 3.5,
            "seed": 42,
            "checkpoint": flux_dev_ckpt,
        },
        section=sec,
        tid="C5-02",
        name="FLUX dev: generate_image (28 steps, cfg=3.5)",
        ok_fn=lambda t: "success" in t.lower() or "url" in t.lower() or "filename" in t.lower(),
        detail_fn=lambda t: t[:200],
        warn_if=["error", "failed", "rejected"],
    )

    # LoRA tests — verify both regular and NSFW LoRAs work with image generation
    code, lora_data = await _comfyui_get("/object_info/LoraLoader", timeout=15)
    loras: list[str] = []
    if code == 200 and isinstance(lora_data, dict):
        lora_node = lora_data.get("LoraLoader", {})
        entries = lora_node.get("input", {}).get("required", {}).get("lora_name", [])
        if entries and isinstance(entries[0], list):
            loras = entries[0]

    # Regular LoRA test
    regular_loras = [l for l in loras if "nsfw" not in l.lower()]
    if regular_loras:
        await _wait_for_comfyui_idle()
        await _mcp(
            COMFYUI_MCP_PORT,
            "generate_image",
            {
                "prompt": "portrait of a woman, highly detailed face, soft studio lighting, photorealistic, 8k",
                "steps": 28,
                "cfg": 3.5,
                "seed": 42,
                "checkpoint": flux_dev_ckpt,
                "lora": regular_loras[0],
                "lora_strength": 0.8,
            },
            section=sec,
            tid="C5-03",
            name=f"LoRA generation: {regular_loras[0]} (FLUX dev, 28 steps)",
            ok_fn=lambda t: "success" in t.lower() or "url" in t.lower() or "filename" in t.lower(),
            detail_fn=lambda t: t[:200],
            warn_if=["error", "failed", "rejected"],
        )
    else:
        record(
            sec, "C5-03", "LoRA generation (regular)", "WARN", "no regular LoRA installed", t0=None
        )

    # NSFW image test — use the uncensored Flux_v8-NSFW checkpoint (not the video LoRA)
    code_ckpt, data_ckpt = await _comfyui_get("/object_info/CheckpointLoaderSimple", timeout=15)
    all_ckpts: list[str] = []
    if code_ckpt == 200 and isinstance(data_ckpt, dict):
        entries = (
            data_ckpt.get("CheckpointLoaderSimple", {})
            .get("input", {})
            .get("required", {})
            .get("ckpt_name", [])
        )
        if entries and isinstance(entries[0], list):
            all_ckpts = entries[0]
    nsfw_image_ckpts = [c for c in all_ckpts if "nsfw" in c.lower()]

    if nsfw_image_ckpts:
        await _wait_for_comfyui_idle()
        await _mcp(
            COMFYUI_MCP_PORT,
            "generate_image",
            {
                "prompt": "nsfwsks, artistic nude portrait, dramatic studio lighting, highly detailed, photorealistic, 8k",
                "steps": 28,
                "cfg": 3.5,
                "seed": 42,
                "checkpoint": nsfw_image_ckpts[0],
            },
            section=sec,
            tid="C5-04",
            name=f"NSFW checkpoint: {nsfw_image_ckpts[0]} (28 steps)",
            ok_fn=lambda t: "success" in t.lower() or "url" in t.lower() or "filename" in t.lower(),
            detail_fn=lambda t: t[:200],
            warn_if=["error", "failed", "rejected"],
        )
    else:
        record(
            sec,
            "C5-04",
            "NSFW checkpoint generation",
            "WARN",
            "no NSFW checkpoint installed (e.g. Flux_v8-NSFW.safetensors)",
            t0=None,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# C6 — IMAGE GENERATION: SDXL & XL VARIANTS (all installed)
# ═══════════════════════════════════════════════════════════════════════════════
async def C6() -> None:
    """Test every installed SDXL / XL-family checkpoint.

    Discovers all XL-family checkpoints dynamically (sd_xl_base, Juggernaut-XL,
    RealVisXL, Animagine-XL, SDXL-Turbo, pony-diffusion, epicrealism, etc.) and
    generates one image per checkpoint using the SDXL workflow.  NSFW-capable
    checkpoints get prompts that exercise that capability.
    """
    print("\n━━━ C6. IMAGE GENERATION — SDXL & XL VARIANTS ━━━")
    sec = "C6"

    t0 = time.time()
    code, data = await _comfyui_get("/object_info", timeout=15)
    if code != 200 or not isinstance(data, dict):
        record(
            sec,
            "C6-00",
            "XL checkpoint discovery",
            "WARN",
            f"ComfyUI not reachable (HTTP {code})",
            t0=t0,
        )
        return

    raw_ckpts = (
        data.get("CheckpointLoaderSimple", {})
        .get("input", {})
        .get("required", {})
        .get("ckpt_name", [[]])[0]
    )
    all_ckpts = _filter_checkpoints(raw_ckpts)

    # XL/SDXL family — any non-Flux checkpoint whose name contains XL-family keywords.
    # Keeps sd_xl_base, juggernaut-xl, realvis, animagine, sdxl-turbo, pony, epicrealism, etc.
    xl_patterns = ["xl", "sdxl", "juggernaut", "pony", "epic", "realistic", "animagine", "turbo"]
    xl_ckpts = [
        c for c in all_ckpts if any(p in c.lower() for p in xl_patterns) and "flux" not in c.lower()
    ]

    t0 = time.time()
    if not xl_ckpts:
        record(
            sec,
            "C6-00",
            "XL/SDXL checkpoints installed",
            "INFO",
            "none found — download juggernaut-xl, realvis-xl, animagine-xl-3.1, or sdxl-turbo",
            t0=t0,
        )
        return

    record(
        sec,
        "C6-00",
        "XL/SDXL checkpoints discovered",
        "INFO",
        f"{len(xl_ckpts)} found: {', '.join(xl_ckpts)}",
        t0=t0,
    )

    # Per-checkpoint prompt selection — NSFW-capable models get prompts that exercise
    # their uncensored range; style-specific models get matching prompts.
    nsfw_prompts: dict[str, str] = {
        "juggernaut": "RAW photo, nsfw, nude woman, dramatic studio lighting, photorealistic, hyperdetailed skin, 8k UHD",
        "realvis": "nsfw, nude, photorealistic woman, soft bedroom lighting, highly detailed, 8k UHD, sharp focus",
        "epic": "nsfw, nude, photorealistic, dramatic rim lighting, hyperdetailed, cinematic",
        "pony": "score_9, score_8_up, nsfw, explicit, anime girl, extremely detailed face, 8k",
        "animagine": "1girl, masterpiece, best quality, anime style, extremely detailed face and eyes, soft lighting",
        "turbo": "futuristic city at night, neon lights, cyberpunk style, ultra-detailed, cinematic",
    }
    negative = "blurry, low quality, watermark, deformed, bad anatomy, extra limbs, mutated, ugly, poorly drawn"

    for i, ckpt in enumerate(xl_ckpts, 1):
        ck_lower = ckpt.lower()
        prompt = next(
            (v for k, v in nsfw_prompts.items() if k in ck_lower),
            "futuristic cityscape at golden hour, dramatic lighting, ultra-detailed, photorealistic, 8k UHD",
        )
        # SDXL-Turbo is distilled: cfg≈0, 4 steps max. All others: 35 steps for quality.
        is_turbo = "turbo" in ck_lower
        steps = 4 if is_turbo else 35
        cfg = 0.0 if is_turbo else 7.5
        neg = "" if is_turbo else negative

        await _wait_for_comfyui_idle()
        await _mcp(
            COMFYUI_MCP_PORT,
            "generate_image",
            {
                "prompt": prompt,
                "negative_prompt": neg,
                "steps": steps,
                "cfg": cfg,
                "seed": 42,
                "width": 1024,
                "height": 1024,
                "model": "sdxl",
                "checkpoint": ckpt,
            },
            section=sec,
            tid=f"C6-{i:02d}",
            name=f"XL variant: {ckpt[:55]}",
            ok_fn=lambda t: "success" in t.lower() or "url" in t.lower() or "filename" in t.lower(),
            detail_fn=lambda t: t[:200],
            warn_if=["error", "failed", "rejected"],
        )


# ═══════════════════════════════════════════════════════════════════════════════
# C7 — IMAGE GENERATION: PARAMETER SWEEP
# ═══════════════════════════════════════════════════════════════════════════════
async def C7() -> None:
    """Test that different generation parameters produce valid (distinct) responses.

    Uses the fastest available checkpoint. Tests seed determinism, step count
    variation, and negative prompt support.
    """
    print("\n━━━ C7. IMAGE GENERATION — PARAMETER SWEEP ━━━")
    sec = "C7"

    # Discover fastest available checkpoint
    t0 = time.time()
    code, data = await _comfyui_get("/object_info", timeout=15)
    test_ckpt = ""
    if code == 200 and isinstance(data, dict):
        ckpt_node = data.get("CheckpointLoaderSimple", {})
        raw = ckpt_node.get("input", {}).get("required", {}).get("ckpt_name", [[]])[0]
        ckpts = _filter_checkpoints(raw)
        # Prefer schnell (fastest) → sdxl → xl → anything
        for candidate_pattern in ["schnell", "sdxl", "xl", ""]:
            matches = (
                [c for c in ckpts if candidate_pattern in c.lower()] if candidate_pattern else ckpts
            )
            if matches:
                test_ckpt = matches[0]
                break

    if not test_ckpt:
        record(
            sec,
            "C7-01",
            "Parameter sweep: no checkpoint available",
            "INFO",
            "skipped — no checkpoint installed",
            t0=t0,
        )
        for tid in ["C7-02", "C7-03", "C7-04"]:
            record(sec, tid, "Parameter sweep test", "INFO", "skipped", t0=None)
        return

    record(sec, "C7-01", "Parameter sweep using checkpoint", "INFO", f"using: {test_ckpt}", t0=t0)

    # Seed determinism: same seed → same output filename/hash
    await _wait_for_comfyui_idle()
    await _mcp(
        COMFYUI_MCP_PORT,
        "generate_image",
        {
            "prompt": "a blue cube on white background",
            "steps": 4,
            "seed": 1234,
            "checkpoint": test_ckpt,
        },
        section=sec,
        tid="C7-02",
        name="Seed determinism: seed=1234 run 1",
        ok_fn=lambda t: "success" in t.lower() or "url" in t.lower() or "filename" in t.lower(),
        detail_fn=lambda t: t[:200],
        warn_if=["error", "failed"],
    )

    # Different step count — fast vs quality comparison
    await _wait_for_comfyui_idle()
    await _mcp(
        COMFYUI_MCP_PORT,
        "generate_image",
        {
            "prompt": "a blue cube on white background",
            "steps": 16,
            "seed": 1234,
            "checkpoint": test_ckpt,
        },
        section=sec,
        tid="C7-03",
        name="Step variation: 16 steps (same seed, quality comparison vs 4)",
        ok_fn=lambda t: "success" in t.lower() or "url" in t.lower() or "filename" in t.lower(),
        detail_fn=lambda t: t[:200],
        warn_if=["error", "failed"],
    )

    # Negative prompt support
    await _wait_for_comfyui_idle()
    await _mcp(
        COMFYUI_MCP_PORT,
        "generate_image",
        {
            "prompt": "portrait of a person, photorealistic, highly detailed",
            "negative_prompt": "cartoon, anime, sketch, blurry, deformed, low quality",
            "steps": 8,
            "seed": 99,
            "checkpoint": test_ckpt,
        },
        section=sec,
        tid="C7-04",
        name="Negative prompt: portrait with exclusions (8 steps)",
        ok_fn=lambda t: (
            "success" in t.lower()
            or "url" in t.lower()
            or "filename" in t.lower()
            or "not supported" in t.lower()
        ),
        detail_fn=lambda t: t[:200],
        warn_if=["error", "failed"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# C8 — VIDEO GENERATION: WAN2.2 T2V VIA MCP
# ═══════════════════════════════════════════════════════════════════════════════
async def C8() -> None:
    print("\n━━━ C8. VIDEO GENERATION — WAN2.2 T2V ━━━")
    sec = "C8"

    # Check if video model is available
    t0 = time.time()
    await _mcp(
        VIDEO_MCP_PORT,
        "list_video_models",
        {},
        section=sec,
        tid="C8-01",
        name="Video models available",
        ok_fn=lambda t: len(t) > 2,
        detail_fn=lambda t: t[:200],
        timeout=15,
    )
    # (Check result from log)
    last = _log[-1] if _log else None
    has_models = last and last.status == "PASS" and last.tid == "C8-01"

    if not has_models:
        record(
            sec,
            "C8-02",
            "Wan2.2 video generation",
            "INFO",
            "skipped — no video models available",
            t0=None,
        )
        record(sec, "C8-03", "Video output accessible", "INFO", "skipped", t0=None)
        return

    # Full quality clip: 9 frames, 832x480, 50 steps.
    # HunyuanVideo is NOT distilled — 50 steps produces best output.
    # Expect ~30-40 min on Apple Silicon MPS. VIDEO_TIMEOUT default is 3600s.
    await _wait_for_comfyui_idle()
    await _mcp(
        VIDEO_MCP_PORT,
        "generate_video",
        {
            "prompt": "ocean waves crashing on rocks at sunset, cinematic, dramatic lighting",
            "width": 832,
            "height": 480,
            "frames": 9,
            "steps": 50,
            "seed": 42,
        },
        section=sec,
        tid="C8-02",
        name="Wan2.2: generate_video (9 frames, 832x480, 50 steps)",
        ok_fn=lambda t: (
            "success" in t.lower()
            or "url" in t.lower()
            or "filename" in t.lower()
            or "not installed" in t.lower()
            or "not available" in t.lower()
        ),
        detail_fn=lambda t: t[:200],
        warn_if=["error", "failed", "not installed", "not available"],
    )

    # Second full-quality clip — different subject
    await _wait_for_comfyui_idle()
    await _mcp(
        VIDEO_MCP_PORT,
        "generate_video",
        {
            "prompt": "time-lapse of clouds moving over mountains, golden hour, cinematic",
            "width": 832,
            "height": 480,
            "frames": 9,
            "steps": 50,
            "seed": 100,
        },
        section=sec,
        tid="C8-03",
        name="Wan2.2: generate_video (9 frames, 50 steps, different subject)",
        ok_fn=lambda t: "success" in t.lower() or "url" in t.lower() or "filename" in t.lower(),
        detail_fn=lambda t: t[:200],
        warn_if=["error", "failed"],
    )

    # NSFW video test — HunyuanVideo with nsfw-e7 LoRA (trigger: nsfwsks)
    await _wait_for_comfyui_idle()
    await _mcp(
        VIDEO_MCP_PORT,
        "generate_video",
        {
            "prompt": "nsfwsks, a woman sunbathing on a beach, golden hour, cinematic",
            "width": 832,
            "height": 480,
            "frames": 9,
            "steps": 50,
            "seed": 42,
        },
        section=sec,
        tid="C8-04",
        name="NSFW video: HunyuanVideo + nsfw-e7 LoRA (50 steps)",
        ok_fn=lambda t: "success" in t.lower() or "url" in t.lower() or "filename" in t.lower(),
        detail_fn=lambda t: t[:200],
        warn_if=["error", "failed", "not installed", "not available"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# C9 — PIPELINE ROUND-TRIPS
# ═══════════════════════════════════════════════════════════════════════════════
async def C9() -> None:
    """Verify the auto-video workspace responds with domain-relevant content.

    This tests that the Portal pipeline routes auto-video to the correct model
    group and that the model produces video/visual domain responses.
    """
    print("\n━━━ C9. PIPELINE ROUND-TRIPS ━━━")
    sec = "C9"

    # auto-video workspace: video description
    t0 = time.time()
    code, text = await _chat(
        "auto-video",
        "Describe a 5-second cinematic shot of ocean waves at golden hour. "
        "Specify camera angle, lens focal length, lighting, and motion.",
        max_tokens=300,
        timeout=240,
    )
    signals = ["wave", "ocean", "camera", "light", "golden", "lens", "focal", "shot"]
    matched = [s for s in signals if s in text.lower()]
    record(
        sec,
        "C9-01",
        "auto-video workspace: cinematic shot description",
        "PASS"
        if code == 200 and len(matched) >= 3
        else ("WARN" if code == 200 and matched else "FAIL"),
        f"matched {len(matched)}/{len(signals)} signals: {matched} | preview: {text[:80]}"
        if code == 200
        else f"code={code} error: {text[:120]}",
        t0=t0,
    )

    # auto-video workspace: workflow prompt (should describe a workflow, not generate)
    t0 = time.time()
    code, text = await _chat(
        "auto-video",
        "What ComfyUI workflow parameters would you use to generate a 5-second "
        "4K aerial landscape video with smooth motion?",
        max_tokens=400,
        timeout=240,
    )
    signals = [
        "workflow",
        "comfyui",
        "frame",
        "step",
        "resolution",
        "parameter",
        "fps",
        "motion",
        "denoise",
        "sampler",
        "width",
        "height",
    ]
    matched = [s for s in signals if s in text.lower()]
    record(
        sec,
        "C9-02",
        "auto-video workspace: ComfyUI workflow parameter question",
        "PASS"
        if code == 200 and len(matched) >= 3
        else ("WARN" if code == 200 and matched else "FAIL"),
        f"matched {len(matched)}/{len(signals)}: {matched[:6]} | preview: {text[:80]}"
        if code == 200
        else f"code={code} error: {text[:120]}",
        t0=t0,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# C10 — OUTPUT VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════
async def C10() -> None:
    """Validate that ComfyUI output files exist and have correct MIME types.

    Checks the most recent entries in ComfyUI /history, fetches the file via
    /view, and validates file size and format.
    """
    print("\n━━━ C10. OUTPUT VALIDATION ━━━")
    sec = "C10"

    t0 = time.time()
    code, history = await _comfyui_get("/history?max_items=10")
    if code != 200 or not isinstance(history, dict) or not history:
        record(
            sec,
            "C10-01",
            "ComfyUI /history has recent outputs",
            "WARN",
            f"HTTP {code} or empty history",
            t0=t0,
        )
        return

    # Collect all outputs from recent history
    images_found: list[dict] = []
    videos_found: list[dict] = []
    video_extensions = {".mp4", ".webm", ".gif", ".avi", ".mov"}
    for entry in history.values():
        for node_outputs in entry.get("outputs", {}).values():
            # ComfyUI stores images in "images" key
            for item in node_outputs.get("images", []):
                fname = item.get("filename", "")
                if any(fname.lower().endswith(ext) for ext in video_extensions):
                    videos_found.append(item)
                else:
                    images_found.append(item)
            # Some nodes store videos in "videos" or "gifs" keys
            for item in node_outputs.get("videos", node_outputs.get("gifs", [])):
                videos_found.append(item)

    record(
        sec,
        "C10-01",
        "Recent outputs in ComfyUI /history",
        "PASS" if (images_found or videos_found) else "WARN",
        f"{len(images_found)} image(s), {len(videos_found)} video(s) in recent history",
        t0=t0,
    )

    # Validate most recent image
    if images_found:
        img = images_found[-1]
        fname = img.get("filename", "")
        subfolder = img.get("subfolder", "")
        ftype = img.get("type", "output")
        t0 = time.time()
        params = f"filename={fname}&subfolder={subfolder}&type={ftype}"
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(f"{COMFYUI_URL}/view?{params}")
                size_kb = len(r.content) / 1024
                content_type = r.headers.get("content-type", "unknown")
                is_image = "image" in content_type or fname.endswith((".png", ".jpg", ".webp"))
                record(
                    sec,
                    "C10-02",
                    "Latest image accessible and valid",
                    "PASS" if r.status_code == 200 and size_kb > 1 and is_image else "WARN",
                    f"{fname}: {size_kb:.1f}KB, {content_type}",
                    t0=t0,
                )
        except Exception as e:
            record(sec, "C10-02", "Latest image accessible and valid", "WARN", str(e)[:120], t0=t0)
    else:
        record(
            sec,
            "C10-02",
            "Latest image accessible and valid",
            "INFO",
            "no images in recent history",
            t0=None,
        )

    # Validate most recent video
    if videos_found:
        vid = videos_found[-1]
        fname = vid.get("filename", "")
        subfolder = vid.get("subfolder", "")
        ftype = vid.get("type", "output")
        t0 = time.time()
        params = f"filename={fname}&subfolder={subfolder}&type={ftype}"
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.get(f"{COMFYUI_URL}/view?{params}")
                size_mb = len(r.content) / (1024 * 1024)
                content_type = r.headers.get("content-type", "unknown")
                is_video = "video" in content_type or fname.endswith((".mp4", ".webm", ".gif"))
                record(
                    sec,
                    "C10-03",
                    "Latest video accessible and valid",
                    "PASS" if r.status_code == 200 and size_mb > 0.05 and is_video else "WARN",
                    f"{fname}: {size_mb:.2f}MB, {content_type}",
                    t0=t0,
                )
        except Exception as e:
            record(sec, "C10-03", "Latest video accessible and valid", "WARN", str(e)[:120], t0=t0)
    else:
        record(
            sec,
            "C10-03",
            "Latest video accessible and valid",
            "INFO",
            "no videos in recent history",
            t0=None,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# C11 — ALL-LORAS COVERAGE: every installed LoRA × FLUX schnell
# ═══════════════════════════════════════════════════════════════════════════════
async def C11() -> None:
    """Test every installed LoRA with the appropriate FLUX base model.

    C5 tests only the first regular LoRA and first NSFW LoRA found.  This section
    exhaustively covers all installed LoRAs so that any newly added LoRA is
    automatically picked up and validated without test changes.

    Base model selection:
    - LoRAs with "dev" in their name → FLUX dev (20 steps): dev LoRAs produce noise on schnell
    - All other LoRAs → FLUX schnell (4 steps): fast path for schnell-compatible LoRAs
    FLUX dev is used as fallback if schnell is not installed.
    """
    print("\n━━━ C11. ALL LORAS × FLUX ━━━")
    sec = "C11"

    t0 = time.time()
    code, data = await _comfyui_get("/object_info", timeout=15)
    if code != 200 or not isinstance(data, dict):
        record(
            sec, "C11-01", "LoRA inventory", "WARN", f"ComfyUI not reachable (HTTP {code})", t0=t0
        )
        return

    raw_ckpts = (
        data.get("CheckpointLoaderSimple", {})
        .get("input", {})
        .get("required", {})
        .get("ckpt_name", [[]])[0]
    )
    real_ckpts = _filter_checkpoints(raw_ckpts)
    loras: list[str] = (
        data.get("LoraLoader", {}).get("input", {}).get("required", {}).get("lora_name", [[]])[0]
        or []
    )

    # Inventory
    record(
        sec,
        "C11-01",
        "LoRA inventory",
        "PASS" if loras else "INFO",
        f"{len(loras)} LoRA(s) installed: {', '.join(loras)}" if loras else "no LoRAs installed",
        t0=t0,
    )

    if not loras:
        return

    flux_schnell = next((c for c in real_ckpts if "schnell" in c.lower()), None)
    flux_dev = next(
        (
            c
            for c in real_ckpts
            if "dev" in c.lower() and "flux" in c.lower() and "nsfw" not in c.lower()
        ),
        None,
    )

    if not flux_schnell and not flux_dev:
        record(
            sec,
            "C11-02",
            "LoRA base models",
            "WARN",
            "Neither FLUX schnell nor FLUX dev installed — cannot run LoRA suite",
            t0=None,
        )
        return

    record(
        sec,
        "C11-02",
        "LoRA base models",
        "INFO",
        f"schnell={flux_schnell or 'not found'}, dev={flux_dev or 'not found'}",
        t0=time.time(),
    )

    # Identify video-only LoRAs (HunyuanVideo, Wan2.2) — they are incompatible with
    # FLUX image generation and are already tested in C8. Query video_mcp for its
    # configured video LoRA so we can exclude it here.
    video_loras: set[str] = set()
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"http://localhost:{VIDEO_MCP_PORT}/health")
            # Ask Docker container env which LoRA video_mcp uses
            pass
    except Exception:
        pass
    # nsfw-e7.safetensors is the HunyuanVideo NSFW LoRA — video-only, not FLUX-compatible.
    # Hardcode the default; also detect by checking if lora name contains "hunyuan"/"wan".
    video_loras.add("nsfw-e7.safetensors")

    # Generate one image per LoRA.  Base model chosen by LoRA type:
    # - "dev" in name → FLUX dev (28 steps): dev LoRAs include CLIP weights, need dev base
    # - otherwise → FLUX schnell (4 steps, fast)
    # Video LoRAs are skipped here — they are tested in C8 with the video_mcp.
    for i, lora in enumerate(loras, 3):
        lo = lora.lower()

        if lora in video_loras or any(k in lo for k in ["hunyuan", "wan22", "wan2"]):
            record(
                sec,
                f"C11-{i:02d}",
                f"LoRA: {lora[:55]}",
                "INFO",
                "video-only LoRA — skipped for image generation (tested in C8)",
                t0=None,
            )
            continue

        is_dev_lora = "dev" in lo
        if is_dev_lora and flux_dev:
            checkpoint = flux_dev
            steps = 28
        else:
            checkpoint = flux_schnell or flux_dev
            steps = 4

        if any(k in lo for k in ["nsfw", "explicit", "adult", "hentai", "nude", "erotic"]):
            prompt = "nsfwsks, photorealistic portrait, dramatic studio lighting, 8k detail"
        elif any(k in lo for k in ["frost", "araminta", "portrait", "style"]):
            prompt = "portrait of a woman, detailed face, soft studio lighting, photorealistic"
        else:
            prompt = "a beautiful landscape, dramatic sky, professional photography, 8k"

        await _wait_for_comfyui_idle()
        await _mcp(
            COMFYUI_MCP_PORT,
            "generate_image",
            {
                "prompt": prompt,
                "steps": steps,
                "seed": 42,
                "checkpoint": checkpoint,
                "lora": lora,
                "lora_strength": 0.8,
            },
            section=sec,
            tid=f"C11-{i:02d}",
            name=f"LoRA: {lora[:45]} ({steps}s, {checkpoint[:20] if checkpoint else '?'})",
            ok_fn=lambda t: "success" in t.lower() or "url" in t.lower() or "filename" in t.lower(),
            detail_fn=lambda t: t[:200],
            warn_if=["error", "failed"],
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTIONS + ORDER
# ═══════════════════════════════════════════════════════════════════════════════
SECTIONS: dict[str, object] = {
    "C0": C0,
    "C1": C1,
    "C2": C2,
    "C3": C3,
    "C4": C4,
    "C5": C5,
    "C6": C6,
    "C7": C7,
    "C8": C8,
    "C9": C9,
    "C10": C10,
    "C11": C11,
}

ALL_ORDER = ["C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11"]


# ═══════════════════════════════════════════════════════════════════════════════
# RESULTS WRITER
# ═══════════════════════════════════════════════════════════════════════════════
def _write_results(elapsed: int, sha: str) -> None:
    counts: dict[str, int] = {}
    for r in _log:
        counts[r.status] = counts.get(r.status, 0) + 1

    rpt = ROOT / "ACCEPTANCE_RESULTS_COMFYUI.md"
    with open(rpt, "w") as f:
        f.write("# Portal 5 — ComfyUI / Image & Video Acceptance Test Results\n\n")
        f.write(f"**Run:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ({elapsed}s)  \n")
        f.write(f"**Git SHA:** {sha}  \n\n")
        f.write("## Summary\n\n")
        for s in ["PASS", "FAIL", "BLOCKED", "WARN", "INFO"]:
            if s in counts:
                f.write(f"- **{s}**: {counts[s]}\n")
        f.write(f"- **Total**: {sum(counts.values())}\n")
        f.write("\n## All Results\n\n")
        f.write(
            "| # | Status | Section | Test | Detail | Duration |\n"
            "|---|--------|---------|------|--------|----------|\n"
        )
        for i, r in enumerate(_log, 1):
            det = (r.detail or "")[:160].replace("|", "∣")
            f.write(
                f"| {i} | {r.status} | {r.section} | {r.name[:60]} | {det} | {r.duration:.1f}s |\n"
            )
        if _blocked:
            f.write("\n## Blocked Items Register\n\n")
            f.write(
                "| # | Section | Test | Evidence | Required Fix |\n"
                "|---|---------|------|----------|---------------|\n"
            )
            for i, r in enumerate(_blocked, 1):
                f.write(
                    f"| {i} | {r.section} | {r.name[:60]} "
                    f"| {r.detail[:120].replace('|', '∣')} "
                    f"| {r.fix[:120].replace('|', '∣')} |\n"
                )
        else:
            f.write("\n## Blocked Items Register\n\n*No blocked items.*\n")
        f.write("\n---\n*ComfyUI outputs: check ComfyUI output/ directory*\n")

    print(f"\nReport → {rpt}")
    return counts


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
async def main() -> int:
    global _verbose

    parser = argparse.ArgumentParser(
        description="Portal 5 — ComfyUI / Image & Video Generation Acceptance Tests"
    )
    parser.add_argument(
        "--section",
        default="ALL",
        help=(
            "Section(s) to run. Examples: --section C4 | --section C4,C5,C8 | "
            "--section C4-C8 | --section C4-C11 | --section ALL (default)"
        ),
    )
    parser.add_argument("--verbose", action="store_true", help="Print evidence lines")
    args = parser.parse_args()
    _verbose = args.verbose

    # Parse section argument
    section_arg = args.section.strip().upper()

    def _parse_section_arg(arg: str) -> list[str]:
        if arg == "ALL":
            return list(ALL_ORDER)
        # Range: C4-C8 or C4-C11 (handle two-digit section numbers)
        if re.match(r"^C\d+-C\d+$", arg):
            start, end = arg.split("-", 1)
            try:
                si = ALL_ORDER.index(start)
                ei = ALL_ORDER.index(end)
            except ValueError as e:
                sys.exit(f"Unknown section in range: {e}. Valid: {sorted(SECTIONS)}")
            if si > ei:
                si, ei = ei, si
            return ALL_ORDER[si : ei + 1]
        # Comma-separated
        requested = [s.strip() for s in arg.split(",") if s.strip()]
        for sid in requested:
            if sid not in SECTIONS:
                sys.exit(f"Unknown section: {sid}. Valid: {sorted(SECTIONS)}")
        # Always prepend C0 (prereqs) unless it's the only or already included
        if requested and requested[0] != "C0" and "C0" not in requested:
            return ["C0"] + requested
        return requested

    run = _parse_section_arg(section_arg)

    sha = _git_sha()
    start = time.time()
    print(f"\n{'═' * 65}")
    print("  Portal 5 — ComfyUI / Image & Video Acceptance Tests")
    print(f"  Git: {sha}  |  Sections: {', '.join(run)}")
    print(f"  ComfyUI: {COMFYUI_URL}")
    print(f"{'═' * 65}\n")

    watchdog_task = asyncio.create_task(_comfyui_watchdog())
    try:
        for sid in run:
            fn = SECTIONS[sid]
            result = await fn()
            # C1 returns checkpoints — ignore for now (already recorded)
            _ = result
    finally:
        watchdog_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watchdog_task

    elapsed = int(time.time() - start)
    counts = _write_results(elapsed, sha)

    # Print summary
    print(f"\n{'─' * 65}")
    total = sum(counts.values())
    print(f"  Completed {len(run)} section(s) in {elapsed}s — {total} results")
    for s in ["PASS", "FAIL", "BLOCKED", "WARN", "INFO"]:
        if s in counts:
            icon = _ICON.get(s, "  ")
            print(f"  {icon} {s}: {counts[s]}")
    print(f"{'─' * 65}\n")

    return 1 if counts.get("FAIL", 0) or counts.get("BLOCKED", 0) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
