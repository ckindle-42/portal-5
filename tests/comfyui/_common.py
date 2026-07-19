"""Shared infrastructure for Portal 5 comfyui acceptance section modules."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import httpx

# ── Re-export from tests/lib so section modules have one import point ────────
from tests.lib.results import (  # noqa: F401
    _ICON,
    R,
    _blocked,
    _emit,
    _git_sha,
    _log,
    record,
)

ROOT = Path(__file__).parent.parent.resolve()
REPO_ROOT = ROOT.parent


# ── Load .env ─────────────────────────────────────────────────────────────────
def _load_env() -> None:
    # Hermetic-test guard — same class of bug as bench/config.py's _load_env.
    if os.environ.get("UNIT_TEST_MODE") == "1":
        return
    for candidate in [ROOT / ".env", REPO_ROOT / ".env"]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())
            break


_load_env()

# ── Service URLs ─────────────────────────────────────────────────────────────
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
    """Remove non-checkpoint files from the checkpoints folder."""
    exclude = ["lora"]
    return [c for c in ckpts if not any(e in c.lower() for e in exclude)]


# ── Memory management ─────────────────────────────────────────────────────────
async def _unload_ollama_models() -> None:
    """Evict all Ollama models from unified memory via keep_alive=0."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{OLLAMA_URL}/api/ps")
            if r.status_code != 200:
                return
            models = [m["name"] for m in r.json().get("models", [])]
        if not models:
            print("  \u2139\ufe0f  No Ollama models loaded \u2014 nothing to evict")
            return
        print(
            f"  \u2500\u2500 Evicting {len(models)} Ollama model(s) from unified memory \u2500\u2500"
        )
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
        print(f"  \u26a0\ufe0f  Ollama eviction failed: {e}")


async def _free_memory_for_comfyui() -> None:
    """Unload Ollama models before ComfyUI tests."""
    print("  \u2500\u2500 Freeing unified memory for ComfyUI \u2500\u2500")
    await _unload_ollama_models()


async def _clear_comfyui_queue() -> None:
    """Interrupt running tasks and clear pending queue."""
    print("  \u2500\u2500 Clearing ComfyUI queue \u2500\u2500")
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{COMFYUI_URL}/queue")
            if r.status_code == 200:
                q = r.json()
                running = len(q.get("queue_running", []))
                pending = len(q.get("queue_pending", []))
                if running == 0 and pending == 0:
                    print("    Queue already empty \u2014 nothing to clear")
                    return
                print(f"    Found {running} running + {pending} pending tasks \u2014 clearing")
            await c.post(f"{COMFYUI_URL}/interrupt")
            await c.post(
                f"{COMFYUI_URL}/free",
                json={"unload_models": False, "free_memory": False},
            )
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
    """Wait for ComfyUI queue to be empty. Returns True if idle."""
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
    """Call an MCP tool and record the result."""
    t0 = time.time()
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        url = f"http://localhost:{port}/mcp"
        async with (
            streamablehttp_client(url) as (read, write, _),
            ClientSession(read, write) as session,
        ):
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

    except TimeoutError:
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
    """GET from the ComfyUI API."""
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
    """POST to the ComfyUI API."""
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
    """Poll ComfyUI /history until the prompt_id appears (generation complete)."""
    deadline = time.time() + timeout
    queued_confirmed = False

    while time.time() < deadline:
        code, history = await _comfyui_get(f"/history/{prompt_id}")
        if code == 200 and isinstance(history, dict) and prompt_id in history:
            entry = history[prompt_id]
            outputs = entry.get("outputs", {})
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
            status_info = entry.get("status", {})
            status_str = status_info.get("status_str", "unknown")
            return False, f"completed with status={status_str}, no output files"

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
                code2, history2 = await _comfyui_get(f"/history/{prompt_id}")
                if code2 == 200 and isinstance(history2, dict) and prompt_id in history2:
                    entry = history2[prompt_id]
                    outputs = entry.get("outputs", {})
                    files = []
                    for node_outputs in outputs.values():
                        for key in ("images", "videos", "gifs"):
                            for item in node_outputs.get(key, []):
                                fname = item.get("filename", "")
                                subfolder = item.get("subfolder", "")
                                ftype = item.get("type", "output")
                                files.append(f"{ftype}/{subfolder}/{fname}".strip("/"))
                    if files:
                        return True, f"{len(files)} output(s): {', '.join(files[:3])}"
                return False, "completed but no output files found"

        await asyncio.sleep(2)

    return False, f"timeout after {timeout}s"


async def _comfyui_watchdog(interval: int = 60, stall_limit: int = 2400) -> None:
    """Background task that prints periodic progress for long-running generations."""
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
                    f"  \u23f3 ComfyUI generating\u2026 {elapsed_min}m{elapsed_sec:02d}s elapsed"
                    f"  (queue: {len(pending)} pending)"
                )
                if elapsed > stall_limit:
                    print(
                        f"  \u26a0\ufe0f  WATCHDOG: same job running for >{stall_limit // 60}min \u2014 "
                        "may be stuck. Check ComfyUI logs."
                    )
            else:
                last_running_id = ""
                stall_start = 0.0
        except Exception:
            pass
