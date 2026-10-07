"""build123d engine bridge for the CAD module (TASK_CAD_ARM_REDEVELOP_V1).

The CAD MCP (cad_render_mcp.py, :8926) speaks Portal's pipeline tool protocol
(GET /tools, POST /tools/<name>). The BREP engine is build123d-mcp
(pzfreo/build123d-mcp, Apache-2.0), which speaks MCP streamable-HTTP. This module
runs build123d-mcp as a private child process bound to 127.0.0.1 inside the CAD
container (never host-exposed) and adapts a small, curated, Portal-named tool
surface onto it. The model never sees build123d-mcp's 50-tool surface (~13K
tokens of schema); it sees the cad_* tools declared in
config/inference/tools_manifest_cad_render_mcp.json.

Isolation: every call carries ``Mcp-Cad-Session: <handle>``; build123d-mcp keeps
one worker subprocess per handle (``--max-sessions``), so concurrent chats never
share a model. The handle is the pipeline's per-request correlation id, so one
user turn = one CAD session; the deliverable script/STEP/STL persist on disk.

Composite tools exist on purpose: like generate_scad's one-call loop, a local
model does better with "build = reset+execute+measure+validate" and
"finalize = validate+export+printability+render+script" than with eight
separate round-trips it has to sequence itself.
"""

from __future__ import annotations

import asyncio
import atexit
import base64
import contextlib
import json
import logging
import os
import re
import shutil
import subprocess  # noqa: S404 — fixed argv, no shell
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ENGINE_HOST = "127.0.0.1"
_ENGINE_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "PYOPENGL_PLATFORM",
    "VTK_DEFAULT_OPENGL_WINDOW",
)
ENGINE_PORT = int(os.getenv("CAD_B3D_ENGINE_PORT", "18123"))
ENGINE_URL = f"http://{ENGINE_HOST}:{ENGINE_PORT}/mcp"
ENGINE_MAX_SESSIONS = int(os.getenv("CAD_B3D_MAX_SESSIONS", "4"))
ENGINE_EXEC_TIMEOUT_S = int(os.getenv("CAD_B3D_EXEC_TIMEOUT_S", "120"))
ENGINE_MEMORY_LIMIT_MB = int(os.getenv("CAD_B3D_MEMORY_LIMIT_MB", "3072"))
ENGINE_IDLE_TIMEOUT_S = int(os.getenv("CAD_B3D_IDLE_TIMEOUT_S", "900"))
CALL_TIMEOUT_S = float(os.getenv("CAD_B3D_CALL_TIMEOUT_S", "300"))
PROTOCOL_VERSION = "2025-11-25"
_MAX_TEXT = 6000  # chars of engine text returned to the model per field

_engine_proc: subprocess.Popen[bytes] | None = None

PublishFn = Callable[[Path], Awaitable[str]]


# ── engine lifecycle ─────────────────────────────────────────────────────────


def engine_binary() -> str | None:
    return shutil.which(os.getenv("CAD_B3D_ENGINE_BIN", "build123d-mcp"))


def start_engine(workdir: Path, wait_s: float = 90.0) -> bool:
    """Spawn build123d-mcp (HTTP, loopback only) with cwd=workdir. Idempotent.

    cwd matters: build123d-mcp only writes under its cwd and /tmp, so exports
    land directly in the CAD output directory. Returns True once tools/list
    answers 200, False if the binary is missing or never comes up.
    """
    global _engine_proc
    if engine_alive():
        return True
    binary = engine_binary()
    if not binary:
        logger.error("build123d-mcp binary not found on PATH; cad_* tools disabled")
        return False
    workdir.mkdir(parents=True, exist_ok=True)
    # The engine executes model-authored Python: hand it an explicit allowlist, never
    # the server's environment (which carries OWUI_API_KEY and other credentials).
    env = {k: os.environ[k] for k in _ENGINE_ENV_ALLOWLIST if k in os.environ}
    env.update(
        {
            "BUILD123D_TRANSPORT": "http",
            "BUILD123D_HOST": ENGINE_HOST,
            "BUILD123D_PORT": str(ENGINE_PORT),
            "BUILD123D_MAX_SESSIONS": str(ENGINE_MAX_SESSIONS),
            "BUILD123D_EXEC_TIMEOUT": str(ENGINE_EXEC_TIMEOUT_S),
            "BUILD123D_MEMORY_LIMIT_MB": str(ENGINE_MEMORY_LIMIT_MB),
            "BUILD123D_SESSION_IDLE_TIMEOUT": str(ENGINE_IDLE_TIMEOUT_S),
        }
    )
    _engine_proc = subprocess.Popen(  # noqa: S603 — fixed argv
        [
            binary,
            "--transport",
            "http",
            "--host",
            ENGINE_HOST,
            "--port",
            str(ENGINE_PORT),
            "--max-sessions",
            str(ENGINE_MAX_SESSIONS),
        ],
        cwd=str(workdir),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # The engine's sessions are only reachable through handles this process
    # knows; an engine that outlived its bridge would hold slots nobody can
    # free. Tie its lifetime to ours.
    atexit.register(stop_engine)
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        if _engine_proc.poll() is not None:
            logger.error("build123d-mcp exited during startup (rc=%s)", _engine_proc.returncode)
            return False
        if engine_alive():
            return True
        time.sleep(1.0)
    return False


def stop_engine() -> None:
    global _engine_proc
    if _engine_proc is not None and _engine_proc.poll() is None:
        _engine_proc.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            _engine_proc.wait(timeout=10)
    _engine_proc = None
    _live.clear()


def engine_alive() -> bool:
    try:
        r = httpx.post(
            ENGINE_URL,
            headers=_headers(None),
            json={"jsonrpc": "2.0", "id": 0, "method": "tools/list", "params": {}},
            timeout=5.0,
        )
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def _headers(session: str | None) -> dict[str, str]:
    """Request headers. session=None omits Mcp-Cad-Session (used by the health
    probe: a header-less tools/list does not allocate a CAD worker)."""
    h = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
    }
    if session:
        h["Mcp-Cad-Session"] = session
    return h


# Handles this bridge has opened, most-recently-used last. build123d-mcp caps live
# sessions (--max-sessions) and only reaps on its idle TTL, so without eviction a
# busy day of one-turn-one-session traffic hits HTTP 503 at the cap. Before a
# call on a NEW handle at capacity, the least-recently-used handle is destroyed.
_live: dict[str, float] = {}


def session_handle(request_id: str | None) -> str:
    """Engine session handle for one pipeline request (one user turn)."""
    rid = re.sub(r"[^A-Za-z0-9_.-]", "", request_id or "")[:64]
    return rid or f"anon-{uuid.uuid4().hex[:12]}"


# ── raw engine call ──────────────────────────────────────────────────────────


def _parse_rpc_body(text: str) -> dict[str, Any]:
    """Accept either a JSON body or an SSE stream; return the last JSON-RPC message."""
    stripped = text.lstrip()
    if stripped.startswith("{"):
        raw = stripped
    else:
        data_lines = [ln[5:].strip() for ln in text.splitlines() if ln.startswith("data:")]
        if not data_lines:
            raise ValueError("engine returned neither JSON nor SSE data")
        raw = data_lines[-1]
    msg = json.loads(raw)
    if not isinstance(msg, dict):
        raise ValueError("engine returned a non-object JSON-RPC message")
    return msg


async def engine_call(
    name: str,
    arguments: dict[str, Any],
    session: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Call one build123d-mcp tool. Returns {"is_error", "texts", "images"}; never raises."""
    payload = {
        "jsonrpc": "2.0",
        "id": uuid.uuid4().hex[:8],
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    own = client is None
    c = client or httpx.AsyncClient(timeout=CALL_TIMEOUT_S)
    try:
        if session not in _live and len(_live) >= ENGINE_MAX_SESSIONS:
            await _evict_lru(c)
        _live[session] = time.monotonic()
        r = await c.post(ENGINE_URL, headers=_headers(session), json=payload)
        # destroy_session detaches at once but closes the worker asynchronously,
        # so a call right after an eviction can still see the cap (live-tested).
        for delay in (1.0, 2.0, 4.0):
            if r.status_code != 503 or "session limit" not in r.text:
                break
            await asyncio.sleep(delay)
            r = await c.post(ENGINE_URL, headers=_headers(session), json=payload)
        if r.status_code != 200:
            return {
                "is_error": True,
                "texts": [f"engine HTTP {r.status_code}: {r.text[:300]}"],
                "images": [],
            }
        msg = _parse_rpc_body(r.text)
    except (httpx.HTTPError, ValueError) as e:
        return {
            "is_error": True,
            "texts": [f"engine unreachable: {type(e).__name__}: {e}"],
            "images": [],
        }
    finally:
        if own:
            await c.aclose()
    if "error" in msg:
        return {"is_error": True, "texts": [json.dumps(msg["error"])[:_MAX_TEXT]], "images": []}
    result = msg.get("result", {})
    texts: list[str] = []
    images: list[bytes] = []
    for item in result.get("content", []):
        if item.get("type") == "text":
            t = item.get("text", "")
            if t.startswith("[SEND:"):
                continue  # engine-local file pointer; the bridge publishes its own copy
            texts.append(t)
        elif item.get("type") == "image" and item.get("data"):
            images.append(base64.b64decode(item["data"]))
    return {"is_error": bool(result.get("isError")), "texts": texts, "images": images}


async def _evict_lru(c: httpx.AsyncClient) -> None:
    victim = min(_live, key=lambda k: _live[k])
    _live.pop(victim, None)
    with contextlib.suppress(httpx.HTTPError):
        await c.post(
            ENGINE_URL,
            headers=_headers(victim),
            json={
                "jsonrpc": "2.0",
                "id": "evict",
                "method": "tools/call",
                "params": {"name": "destroy_session", "arguments": {}},
            },
        )


def _text(res: dict[str, Any]) -> str:
    return "\n".join(res["texts"])[:_MAX_TEXT]


def failed(res: dict[str, Any]) -> bool:
    """build123d-mcp reports many tool failures as isError=false with an
    "Error:" text or an {"error": ...} JSON body; treat all three as failure."""
    if res["is_error"]:
        return True
    head = _text(res).lstrip()
    if head.startswith("Error"):
        return True
    tail = _json_tail(head) if head.startswith("{") else None
    return isinstance(tail, dict) and "error" in tail and len(tail) == 1


_NO_SHAPE_HINT = (
    "No solid is registered in the session. End your build123d code with "
    "show(part, 'part') (or assign the final solid and call show on it) so it can "
    "be measured, validated and exported."
)


def _json_tail(text: str) -> Any:
    """Parse the JSON object an engine tool appends after its verdict line, if any."""
    start = text.find("{")
    if start < 0:
        return None
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError:
        return None


async def _diagnose(session: str, error_text: str, client: httpx.AsyncClient) -> dict[str, Any]:
    last = await engine_call("last_error", {}, session, client)
    hints = await engine_call("repair_hints", {"error_text": error_text[:2000]}, session, client)
    return {"last_error": _text(last), "repair_hints": _text(hints)}


def safe_basename(name: str | None) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]", "_", (name or "").strip())[:48].strip("_")
    return base or "part"


# ── model-facing tools (Portal names) ────────────────────────────────────────


async def cad_build(code: str, session: str, out_dir: Path) -> dict[str, Any]:
    """Fresh build: reset → execute(code) → measure → validate, one call."""
    async with httpx.AsyncClient(timeout=CALL_TIMEOUT_S) as c:
        await engine_call("reset", {}, session, c)
        ex = await engine_call("execute", {"code": code}, session, c)
        if failed(ex):
            err = _text(ex)
            return {
                "ok": False,
                "stage": "execute",
                "error": err,
                **(await _diagnose(session, err, c)),
            }
        meas = await engine_call("measure", {}, session, c)
        if failed(meas):
            return {"ok": False, "stage": "measure", "error": _text(meas), "hint": _NO_SHAPE_HINT}
        val = await engine_call("validate", {}, session, c)
        vtext = _text(val)
        return {
            "ok": not failed(val) and "PASS" in vtext.split("\n", 1)[0],
            "stage": "validated",
            # Build success is not delivery: the user receives no files until cad_finalize.
            "delivered": False,
            "execute": _text(ex),
            "measure": _json_tail(_text(meas)) or _text(meas),
            "validate": _json_tail(vtext) or vtext,
            "next": "NOT DELIVERED YET — the user has no files until you call cad_finalize now (or fix and call cad_build again)",
        }


async def cad_execute(code: str, session: str, out_dir: Path) -> dict[str, Any]:
    """Incremental: run more build123d code in the existing session."""
    async with httpx.AsyncClient(timeout=CALL_TIMEOUT_S) as c:
        ex = await engine_call("execute", {"code": code}, session, c)
        if failed(ex):
            err = _text(ex)
            return {"ok": False, "error": err, **(await _diagnose(session, err, c))}
        return {"ok": True, "execute": _text(ex)}


async def cad_measure(object_name: str, session: str, out_dir: Path) -> dict[str, Any]:
    res = await engine_call("measure", {"object_name": object_name}, session)
    return {"ok": not failed(res), "measure": _json_tail(_text(res)) or _text(res)}


async def cad_find_holes(object_name: str, session: str, out_dir: Path) -> dict[str, Any]:
    res = await engine_call("find_holes", {"object_name": object_name}, session)
    return {"ok": not failed(res), "holes": _json_tail(_text(res)) or _text(res)}


async def cad_render(
    direction: str, object_name: str, session: str, out_dir: Path, publish: PublishFn
) -> dict[str, Any]:
    res = await engine_call(
        "render_view", {"direction": direction or "iso", "objects": object_name}, session
    )
    if failed(res) or not res["images"]:
        return {"ok": False, "error": _text(res) or "render produced no image"}
    png = out_dir / f"b3d_{session[-12:]}_{uuid.uuid4().hex[:6]}_{safe_basename(direction)}.png"
    png.write_bytes(res["images"][0])
    return {"ok": True, "png_path": str(png), "png_url": await publish(png), "note": _text(res)}


async def cad_finalize(
    object_name: str, basename: str, session: str, out_dir: Path, publish: PublishFn
) -> dict[str, Any]:
    """Validate → export STEP+STL → printability → iso render → save script; publish all."""
    stem = f"{safe_basename(basename)}_{uuid.uuid4().hex[:6]}"
    async with httpx.AsyncClient(timeout=CALL_TIMEOUT_S) as c:
        val = await engine_call("validate", {"object_name": object_name}, session, c)
        vtext = _text(val)
        if failed(val) or "PASS" not in vtext.split("\n", 1)[0]:
            return {
                "ok": False,
                "stage": "validate",
                "validate": _json_tail(vtext) or vtext,
                **(await _diagnose(session, vtext, c)),
            }
        exp = await engine_call(
            "export",
            # Bare stem: for a comma-separated format list build123d-mcp appends
            # each extension itself ("x.step" would yield x.step + x.step.stl).
            {"filename": str(out_dir / stem), "format": "step,stl", "object_name": object_name},
            session,
            c,
        )
        if failed(exp):
            return {"ok": False, "stage": "export", "error": _text(exp)}
        pr = await engine_call("analyze_printability", {"object_name": object_name}, session, c)
        meas = await engine_call("measure", {"object_name": object_name}, session, c)
        await engine_call("script", {"save_to": str(out_dir / f"{stem}.py")}, session, c)
        rend = await engine_call(
            "render_view", {"direction": "iso", "objects": object_name}, session, c
        )
    step_path, stl_path, py_path = (out_dir / f"{stem}.{ext}" for ext in ("step", "stl", "py"))
    png_path = out_dir / f"{stem}.png"
    if rend["images"]:
        png_path.write_bytes(rend["images"][0])
    result: dict[str, Any] = {
        "ok": step_path.exists() and stl_path.exists(),
        "stage": "finalized",
        "measure": _json_tail(_text(meas)) or _text(meas),
        "printability": _text(pr),
        "step_path": str(step_path),
        "stl_path": str(stl_path),
        "script_path": str(py_path) if py_path.exists() else None,
    }
    for key, p in (
        ("step_url", step_path),
        ("stl_url", stl_path),
        ("script_url", py_path),
        ("png_url", png_path),
    ):
        if p.exists():
            result[key] = await publish(p)
    if not result["ok"]:
        result["error"] = f"export reported success but files missing: {_text(exp)[:300]}"
    return result


# ── pipeline dispatch table ──────────────────────────────────────────────────

TOOL_NAMES = (
    "cad_build",
    "cad_execute",
    "cad_measure",
    "cad_find_holes",
    "cad_render",
    "cad_finalize",
)


async def dispatch(
    name: str,
    args: dict[str, Any],
    request_id: str | None,
    out_dir: Path,
    publish: PublishFn,
) -> dict[str, Any]:
    """Route one pipeline tool call (POST /tools/<name>) to its handler. Never raises."""
    session = session_handle(request_id)
    try:
        if name == "cad_build":
            return await cad_build(str(args.get("code", "")), session, out_dir)
        if name == "cad_execute":
            return await cad_execute(str(args.get("code", "")), session, out_dir)
        if name == "cad_measure":
            return await cad_measure(str(args.get("object_name", "")), session, out_dir)
        if name == "cad_find_holes":
            return await cad_find_holes(str(args.get("object_name", "")), session, out_dir)
        if name == "cad_render":
            return await cad_render(
                str(args.get("direction", "iso")),
                str(args.get("object_name", "")),
                session,
                out_dir,
                publish,
            )
        if name == "cad_finalize":
            return await cad_finalize(
                str(args.get("object_name", "")),
                str(args.get("basename", "part")),
                session,
                out_dir,
                publish,
            )
    except Exception as e:  # noqa: BLE001 — a tool failure must not break the SSE stream
        logger.exception("cad bridge %s failed", name)
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": False, "error": f"unknown cad tool {name!r}"}
