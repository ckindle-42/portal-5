"""Music MCP — ACE-Step 1.5 XL-Turbo primary, MiniMax-Music3 8-bit fallback.

Each job is a subprocess (`music_worker`) so Metal memory dies with the child.
Port 8912. Apple Silicon only. The `music` module ships disabled.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import random
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from portal.modules.media.tools._admission import admit
from portal.modules.media.tools._jobs import (
    DEFAULT_STATUS_WAIT_S,
    STATUS_TOOL_TIMEOUT_S,
    MediaJobManager,
    start_reply,
)
from portal.platform.mcp_host import resolve_upload_path
from portal.platform.mcp_host.eval_scope import bind_native_context
from portal.platform.mcp_host.owui_files import publish_file
from portal.platform.mcp_host.workspace import get_generated_dir

logger = logging.getLogger(__name__)

port = int(os.getenv("MUSIC_MCP_PORT", os.getenv("MUSIC_MINIMAX_PORT", "8912")))
mcp = MCPServer("music")
_route: Callable[
    ...,
    Callable[[Callable[..., Awaitable[Response]]], Callable[..., Awaitable[Response]]],
] = mcp.custom_route

_ACE_ROOT = Path(os.environ.get("MUSIC_ACE_ROOT", Path.home() / ".portal5/music/ACE-Step-1.5"))
_PYTHON = Path(os.environ.get("MUSIC_PYTHON", str(_ACE_ROOT / ".venv/bin/python")))
_DIT = os.environ.get("MUSIC_ACE_DIT", "acestep-v15-xl-turbo")
_LM = os.environ.get("MUSIC_ACE_LM", "acestep-5Hz-lm-1.7B")
_MINIMAX_MODEL = os.environ.get("MUSIC_MINIMAX_MODEL", "mlx-community/MiniMax-Music3-8bit")
_JOB_TIMEOUT_S = float(os.environ.get("MUSIC_JOB_TIMEOUT_S", "900"))
_MAX_FILES = int(os.environ.get("MAX_MUSIC_FILES", "20"))
_NEEDS_SOURCE = frozenset({"repaint", "cover", "extend"})
_TASKS = {
    "text2music": "text2music",
    "repaint": "repaint",
    "cover": "cover",
    "extend": "complete",
}
_ADMISSION = {"acestep": "music:acestep-xl-turbo", "minimax": "music:minimax3-8bit"}
_weights_resident = False


def release_idle() -> bool:
    """True once the job subprocess has exited and no music weights are resident."""
    return not _weights_resident


_JOBS = MediaJobManager(
    idle_timeout_s=float(os.environ.get("MUSIC_IDLE_TIMEOUT_S", "180")),
    on_idle=release_idle,
)


def admission_key(engine: str) -> str:
    """Map a tool engine name to the memory-budget key."""
    return _ADMISSION.get(engine, f"music:{engine}")


def _engine_ready(engine: str) -> tuple[bool, str]:
    if not _PYTHON.is_file():
        return False, f"music venv missing at {_PYTHON}. Run: ./launch.sh install-music"
    if engine == "acestep" and not (_ACE_ROOT / "checkpoints" / _DIT).is_dir():
        return False, f"ACE-Step checkpoint missing at {_ACE_ROOT / 'checkpoints' / _DIT}"
    return True, ""


def _resolve_source(source: str | None) -> Path | None:
    """An upload name, or a basename already under generated/music. Never a raw path."""
    if not source:
        return None
    if "/" not in source and source.endswith(".wav"):
        candidate = get_generated_dir("music") / source
        if candidate.is_file():
            return candidate
    resolved = resolve_upload_path(source)
    if resolved is None:
        raise ValueError("source must be an upload filename or a .wav basename in generated/music")
    return resolved


def _bounds(engine: str, seconds: float, steps: int | None) -> tuple[float, int]:
    if engine == "minimax":
        return max(10.0, min(300.0, float(seconds))), max(1, min(30, int(steps or 30)))
    return max(10.0, min(600.0, float(seconds))), max(1, min(20, int(steps or 8)))


def _cleanup_old() -> None:
    files = sorted(
        get_generated_dir("music").glob("music_*.wav"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for old in files[_MAX_FILES:]:
        with contextlib.suppress(OSError):
            old.unlink()


def _worker_env() -> dict[str, str]:
    env = os.environ.copy()
    root = str(Path(__file__).resolve().parents[4])
    env["PYTHONPATH"] = root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["MUSIC_ACE_ROOT"] = str(_ACE_ROOT)
    env["MUSIC_ACE_DIT"] = _DIT
    env["MUSIC_ACE_LM"] = _LM
    env["MUSIC_MINIMAX_MODEL"] = _MINIMAX_MODEL
    return env


async def run_worker(spec: dict[str, Any]) -> dict[str, Any]:
    """Spawn the engine subprocess and return its JSON result."""
    global _weights_resident
    proc = await asyncio.create_subprocess_exec(
        str(_PYTHON),
        "-m",
        "portal.modules.media.tools.music_worker",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_worker_env(),
    )
    _weights_resident = True
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(json.dumps(spec).encode()), timeout=_JOB_TIMEOUT_S
        )
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        return {"success": False, "error": f"music worker timed out after {int(_JOB_TIMEOUT_S)}s"}
    finally:
        _weights_resident = False
    if proc.returncode != 0 and not out:
        tail = (err or b"").decode("utf-8", "replace")[-800:]
        return {"success": False, "error": tail or f"worker exit {proc.returncode}"}
    try:
        parsed = json.loads(out.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        tail = (err or out or b"").decode("utf-8", "replace")[-800:]
        return {"success": False, "error": tail or "worker returned non-JSON"}
    return parsed if isinstance(parsed, dict) else {"success": False, "error": "bad worker JSON"}


async def _finish(spec: dict[str, Any], progress: Callable[[int, str], None]) -> dict[str, Any]:
    progress(1, "Checking memory before model load…")
    refusal = await admit(admission_key(str(spec["engine"])))
    if refusal:
        return refusal
    progress(2, f"Generating ({spec['engine']}, {spec['steps']} steps)…")
    result = await run_worker(spec)
    if not result.get("success"):
        return result
    path = Path(str(result.get("artifact_path") or spec["output_path"]))
    pub = await publish_file(path)
    if pub.get("error") and not pub.get("url"):
        return {"success": False, "error": pub["error"]}
    url = str(pub.get("url") or "")
    _cleanup_old()
    result.update(
        url=url,
        download_url=url,
        filename=pub.get("filename", path.name),
        artifact_path=str(path),
    )
    return result


def _reject_request(
    prompt: str, engine: str, task_type: str, source: str | None
) -> dict[str, Any] | None:
    if not prompt.strip():
        return {"success": False, "error": "prompt is required"}
    if engine not in _ADMISSION:
        return {"success": False, "error": f"engine must be one of {sorted(_ADMISSION)}"}
    if task_type not in _TASKS:
        return {"success": False, "error": f"task_type must be one of {sorted(_TASKS)}"}
    if task_type in _NEEDS_SOURCE and not source:
        return {"success": False, "error": f"{task_type} requires source"}
    ready, err = _engine_ready(engine)
    if not ready:
        return {"success": False, "error": err}
    return None


@_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": "music-mcp",
            "engine": "acestep",
            "fallback": "minimax",
            "weights_resident": _weights_resident,
        }
    )


@mcp.tool()
async def music_start(
    prompt: str,
    lyrics: str = "[Instrumental]",
    seconds: float = 30.0,
    steps: int | None = None,
    seed: int | None = None,
    engine: str = "acestep",
    task_type: str = "text2music",
    source: str | None = None,
    repaint_start: float = 0.0,
    repaint_end: float = -1.0,
) -> dict[str, Any]:
    """Start one song job. Poll music_status with the returned job_id."""
    rejected = _reject_request(prompt, engine, task_type, source)
    if rejected:
        return rejected
    try:
        src = _resolve_source(source)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    bounded_s, bounded_steps = _bounds(engine, seconds, steps)
    chosen = random.randint(0, 2**31 - 1) if seed is None else int(seed)
    if not _JOBS.is_busy:
        early = await admit(admission_key(engine))
        if early:
            return early
    holder: dict[str, str] = {}

    async def _run(progress: Callable[[int, str], None]) -> dict[str, Any]:
        spec = {
            "engine": engine,
            "upstream_task": _TASKS[task_type],
            "prompt": prompt.strip(),
            "lyrics": lyrics,
            "seconds": bounded_s,
            "steps": bounded_steps,
            "seed": chosen,
            "source_path": str(src) if src else None,
            "repaint_start": float(repaint_start),
            "repaint_end": float(repaint_end),
            "output_path": str(get_generated_dir("music") / f"music_{holder['id']}.wav"),
        }
        return await _finish(spec, progress)

    job_id = _JOBS.start(_run, extra_fields={"engine": engine, "seed": chosen})
    holder["id"] = job_id
    return start_reply(
        job_id,
        "music_status",
        f"engine={engine}, task={task_type}, {int(bounded_s)}s, {bounded_steps} steps",
        engine=engine,
        seed=chosen,
    )


@mcp.tool(meta={"portal5/timeout_s": STATUS_TOOL_TIMEOUT_S})
async def music_status(job_id: str, wait_s: float = DEFAULT_STATUS_WAIT_S) -> dict[str, Any]:
    """Long-poll a music job up to wait_s seconds for progress or the artifact."""
    return await _JOBS.status(job_id, wait_s=wait_s)


@mcp.tool()
async def music_models() -> dict[str, Any]:
    """List the music engines and whether their install is present."""
    ace_ok, ace_err = _engine_ready("acestep")
    mini_ok = _PYTHON.is_file()
    return {
        "primary": "acestep",
        "engines": {
            "acestep": {
                "model": _DIT,
                "lm": _LM,
                "steps_default": 8,
                "sample_rate": 48000,
                "license": "MIT",
                "tasks": sorted(_TASKS),
                "available": ace_ok,
                "error": ace_err or None,
                "admission_key": admission_key("acestep"),
            },
            "minimax": {
                "model": _MINIMAX_MODEL,
                "steps_default": 30,
                "sample_rate": 44100,
                "license": "MiniMax-Music3 Community License",
                "tasks": ["text2music"],
                "available": mini_ok,
                "error": None if mini_ok else ace_err,
                "admission_key": admission_key("minimax"),
            },
        },
    }


bind_native_context(mcp)

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
