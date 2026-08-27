"""Thin MCP HTTP proxy for the separately-running ACE-Step-1.5 API server."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx
from mcp.server import MCPServer
from starlette.responses import FileResponse, JSONResponse

from portal.modules.media.tools._admission import admit
from portal.platform.data_loader import load_data

port = int(os.getenv("MUSIC_ACE_MCP_PORT", "8933"))
mcp = MCPServer("music-ace")
ACESTEP_URL = os.getenv("ACESTEP_URL", "http://127.0.0.1:8001").rstrip("/")
PUBLIC_URL = os.getenv("MUSIC_PUBLIC_URL", f"http://localhost:{port}/files/music").rstrip("/")
SAFE_FILENAME = re.compile(r"^[\w\-\.\s]+$")
logger = logging.getLogger(__name__)
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "data/generated"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MAX_MUSIC_FILES = int(os.getenv("MAX_MUSIC_FILES", "20"))


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "music-ace-mcp"})


@mcp.custom_route("/files/music/{filename:path}", methods=["GET"])
async def serve_generated_file(request):
    filename = request.path_params["filename"]
    if not SAFE_FILENAME.match(filename):
        return JSONResponse({"error": "Invalid filename"}, status_code=400)
    file_path = OUTPUT_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        return JSONResponse({"error": "File not found"}, status_code=404)
    media_type = "audio/mpeg" if file_path.suffix.lower() == ".mp3" else "audio/wav"
    return FileResponse(path=str(file_path), filename=filename, media_type=media_type)


TOOLS_MANIFEST = load_data("config/inference", "tools_manifest_music_ace_mcp")


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})


@mcp.custom_route("/tools/ace_generate", methods=["POST"])
async def ace_generate_endpoint(request):
    return JSONResponse(await ace_generate(**(await request.json()).get("arguments", {})))


@mcp.custom_route("/tools/ace_status", methods=["POST"])
async def ace_status_endpoint(request):
    args = (await request.json()).get("arguments", {})
    return JSONResponse(await ace_status(job_id=args.get("job_id", "")))


@mcp.custom_route("/tools/ace_models", methods=["POST"])
async def ace_models_endpoint(request):
    return JSONResponse(await ace_models())


def _cleanup_old_music_files() -> None:
    import contextlib

    music_files = sorted(
        OUTPUT_DIR.glob("music_*.*"), key=lambda f: f.stat().st_mtime, reverse=True
    )
    for old_file in music_files[MAX_MUSIC_FILES:]:
        with contextlib.suppress(OSError):
            old_file.unlink()


@mcp.tool()
async def ace_generate(
    prompt: str,
    lyrics: str = "[Instrumental]",
    seconds: float = 60.0,
    task_type: str = "text2music",
    vocal_language: str = "en",
    src_audio_path: str | None = None,
    repainting_start: float = 0.0,
    repainting_end: float | None = None,
    model: str = "acestep-v15-sft",
    steps: int = 30,
) -> dict:
    """Start an ACE-Step song generation or edit job; poll ace_status."""
    seconds = max(10.0, min(600.0, float(seconds)))
    steps = max(1, int(steps))
    refusal = await admit("music:acestep-sft")
    if refusal:
        return refusal
    payload: dict[str, Any] = {
        "prompt": prompt,
        "lyrics": lyrics,
        "audio_duration": seconds,
        "vocal_language": vocal_language,
        "task_type": task_type,
        "inference_steps": steps,
        "model": model,
        "thinking": True,
    }
    if task_type != "text2music":
        if not src_audio_path:
            return {"success": False, "error": f"task_type={task_type} requires src_audio_path"}
        source = Path(src_audio_path)
        resolved = (
            source.resolve() if source.is_absolute() else (OUTPUT_DIR / source.name).resolve()
        )
        if not str(resolved).startswith(str(OUTPUT_DIR.resolve()) + os.sep):
            return {"success": False, "error": "src_audio_path must be within the output directory"}
        if not resolved.exists():
            return {"success": False, "error": f"Source audio not found: {src_audio_path}"}
        payload["repainting_start"] = repainting_start
        if repainting_end is not None:
            payload["repainting_end"] = repainting_end
    try:
        async with httpx.AsyncClient(base_url=ACESTEP_URL, timeout=30.0) as client:
            if task_type == "text2music":
                response = await client.post("/release_task", json=payload)
            else:
                form = {
                    key: (str(value).lower() if isinstance(value, bool) else str(value))
                    for key, value in payload.items()
                }
                files = {
                    "src_audio": (
                        resolved.name,
                        resolved.read_bytes(),
                        "audio/mpeg" if resolved.suffix.lower() == ".mp3" else "audio/wav",
                    )
                }
                response = await client.post("/release_task", data=form, files=files)
            if response.is_error:
                return {
                    "success": False,
                    "error": f"ACE-Step server rejected the task ({response.status_code}): {response.text[:500]}",
                }
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        logger.exception("ACE-Step release_task failed")
        return {"success": False, "error": f"ACE-Step server error: {exc}"}
    if data.get("code") != 200:
        return {"success": False, "error": data.get("error") or "ACE-Step server rejected the task"}
    task_id = data["data"]["task_id"]
    return {
        "success": True,
        "job_id": task_id,
        "message": f"Generation started (job {task_id}). Poll ace_status to check progress.",
    }


@mcp.tool()
async def ace_status(job_id: str) -> dict:
    """Check an ACE-Step generation job and copy completed audio locally."""
    try:
        async with httpx.AsyncClient(base_url=ACESTEP_URL, timeout=15.0) as client:
            response = await client.post("/query_result", json={"task_id_list": [job_id]})
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        return {"status": "unknown", "job_id": job_id, "message": f"ACE-Step server error: {exc}"}
    results = data.get("data") or []
    if not results:
        return {
            "status": "unknown",
            "job_id": job_id,
            "message": "No such job on the ACE-Step server.",
        }
    entry = results[0]
    if entry.get("status") == 0:
        return {"status": "running", "job_id": job_id}
    if entry.get("status") == 2:
        return {
            "status": "error",
            "job_id": job_id,
            "error": "ACE-Step reported generation failure",
        }
    try:
        parsed = json.loads(entry["result"])
        item = parsed[0] if isinstance(parsed, list) else parsed
        remote_path = item["file"]
    except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
        return {
            "status": "error",
            "job_id": job_id,
            "error": f"Could not parse ACE-Step result: {exc}",
        }
    if not remote_path:
        detail = (
            entry.get("progress_text") or item.get("stage") or "ACE-Step returned no audio file"
        )
        return {"status": "error", "job_id": job_id, "error": str(detail)}
    try:
        async with httpx.AsyncClient(base_url=ACESTEP_URL, timeout=60.0) as client:
            audio_response = await client.get(remote_path)
            audio_response.raise_for_status()
    except httpx.HTTPError as exc:
        return {
            "status": "error",
            "job_id": job_id,
            "error": f"Could not fetch generated audio: {exc}",
        }
    ext = Path(remote_path.split("?path=")[-1]).suffix or ".mp3"
    output_file = OUTPUT_DIR / f"music_{job_id}{ext}"
    output_file.write_bytes(audio_response.content)
    _cleanup_old_music_files()
    download_url = f"{PUBLIC_URL}/{output_file.name}"
    metas = item.get("metas", {}) or {}
    return {
        "status": "done",
        "job_id": job_id,
        "filename": output_file.name,
        "download_url": download_url,
        "duration_seconds": metas.get("duration"),
        "bpm": metas.get("bpm"),
        "key_scale": metas.get("keyscale"),
        "model": item.get("dit_model"),
        "message": f"Music generated. [Download]({download_url})",
    }


@mcp.tool()
async def ace_models() -> dict:
    """List models loaded by the ACE-Step server."""
    try:
        async with httpx.AsyncClient(base_url=ACESTEP_URL, timeout=10.0) as client:
            response = await client.get("/v1/models")
            response.raise_for_status()
            data = response.json()
        return {
            "backend": "ACE-Step-1.5 (native MLX with automatic PyTorch/MPS fallback)",
            "available": True,
            "models": data.get("data", {}),
            "note": "Job-based; non-turbo acestep-v15-sft defaults to 60s/30 steps. repaint edits or extends clips; cover performs style transfer.",
        }
    except httpx.HTTPError as exc:
        return {
            "backend": "ACE-Step-1.5",
            "available": False,
            "error": f"ACE-Step server not reachable at {ACESTEP_URL}: {exc}",
        }


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
