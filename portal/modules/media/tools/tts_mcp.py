"""
TTS MCP Server — Portal 5

Persona-facing TTS tools (speak, clone_voice, register_voice, list_voices). Runs in Docker
and cannot run MLX, so it proxies to the host mlx-speech.py server (:8918 — Chatterbox clone,
trainer profiles, Kokoro narration), the same host hop OWUI's built-in TTS uses. As of
TASK_SPEECH_CHATTERBOX_CLONE_REPLACE the prior kokoro-onnx local backend and the
never-functional fish-speech clone path are removed.

Start with: python -m portal.modules.media.tools.tts_mcp
"""

from __future__ import annotations

import base64
import contextlib
import logging
import os
import re
import secrets
from pathlib import Path

import httpx
from mcp.server import MCPServer
from starlette.responses import FileResponse, JSONResponse, Response

from portal.platform.data_loader import load_data
from portal.platform.mcp_host.owui_files import publish_file
from portal.platform.mcp_host.workspace import (
    get_generated_dir,
    get_uploads_dir,
    resolve_upload_path,
)

logger = logging.getLogger(__name__)
port = int(os.getenv("TTS_MCP_PORT", "8916"))
mcp = MCPServer("tts-generation")

SPEECH_URL = os.getenv("MLX_SPEECH_URL", "http://host.docker.internal:8918").rstrip("/")
PUBLIC_URL = os.getenv("TTS_PUBLIC_URL", f"http://localhost:{port}/files/tts").rstrip("/")
HTTP_TIMEOUT = float(os.getenv("TTS_PROXY_TIMEOUT", "120"))
_AUDIO_EXTS = (".wav", ".flac", ".ogg", ".mp3", ".m4a", ".aac", ".webm", ".aiff", ".aif")
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._-]+\.wav$")


async def _save_speech(content: bytes, voice: str) -> tuple[str, str]:
    """Persist generated speech and return (filename, download_url).

    Preferred path: publish through Open WebUI so the link rides the one port
    the tunnel exposes (:8080). Fallback (no OWUI_API_KEY): the local file +
    this server's /files/tts route.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", voice.lower()).strip("-") or "voice"
    fname = f"speak_{slug}_{secrets.token_hex(16)}.wav"
    path = get_generated_dir("speech") / fname
    path.write_bytes(content)
    published = await publish_file(path, content_type="audio/wav")
    if published:
        return fname, published["url"]
    return fname, f"{PUBLIC_URL}/{fname}"


def _resolve_reference(reference_audio: str) -> Path | None:
    """Resolve a reference-audio argument to a container-visible file.

    Accepts an OWUI file id / stored name / original filename (looked up in the
    shared workspace uploads dir), a container path, or "" to pick the most
    recent upload. Returns None if nothing resolves — the caller then passes the
    raw string through for the host to resolve (a host-visible path from the CLI).
    """
    if reference_audio:
        hit = resolve_upload_path(reference_audio)
        if hit and hit.is_file():
            return hit
        p = Path(reference_audio)
        if p.is_file():
            return p
        return None
    try:
        uploads = get_uploads_dir()
    except Exception:
        return None
    cands = [p for p in uploads.iterdir() if p.is_file() and p.suffix.lower() in _AUDIO_EXTS]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


async def _post_register(name: str, ref: Path | None, raw: str, reference_text: str) -> dict:
    """POST a profile registration to the host — audio bytes if we resolved a
    readable file, else the raw path string for the host to resolve."""
    payload: dict = {"name": name, "reference_text": reference_text}
    if ref is not None:
        payload["reference_audio_b64"] = base64.b64encode(ref.read_bytes()).decode()
        payload["reference_audio_name"] = ref.name
    else:
        payload["reference_audio"] = raw
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.post(f"{SPEECH_URL}/v1/voices", json=payload)
            return r.json()
    except Exception as e:
        return {"error": f"host speech server unreachable at {SPEECH_URL}: {e}"}


async def _speech_speak(text: str, voice: str) -> dict:
    """POST /v1/audio/speech; the endpoint returns raw WAV on success, JSON on error."""
    url = f"{SPEECH_URL}/v1/audio/speech"
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.post(url, json={"input": text, "voice": voice})
    except Exception as e:
        return {"error": f"host speech server unreachable at {SPEECH_URL}: {e}"}
    if r.status_code == 200 and not r.headers.get("content-type", "").startswith(
        "application/json"
    ):
        try:
            fname, url = await _save_speech(r.content, voice)
        except Exception as e:  # noqa: BLE001 — still hand back the bytes count
            return {
                "status": "success",
                "voice": voice,
                "audio_bytes": len(r.content),
                "message": f"Spoke {len(text)} chars with '{voice}' (could not save file: {e}).",
            }
        return {
            "status": "success",
            "voice": voice,
            "filename": fname,
            "download_url": url,
            "audio_bytes": len(r.content),
            "message": f"Spoke {len(text)} chars with '{voice}'. [Download audio]({url})",
        }
    if r.headers.get("content-type", "").startswith("application/json"):
        return r.json()
    return {"error": f"speech server {r.status_code}: {r.text[:200]}"}


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    reachable, detail = False, ""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{SPEECH_URL}/health")
            reachable = r.status_code == 200
            detail = r.text[:200]
    except Exception as e:
        detail = str(e)
    return JSONResponse(
        {
            "status": "ok",
            "service": "tts-mcp",
            "backend": "proxy:mlx-speech",
            "speech_backend_reachable": reachable,
            "detail": detail,
        }
    )


@mcp.custom_route("/v1/audio/speech", methods=["POST"])
async def openai_audio_speech(request):
    """OpenAI-compatible TTS — proxies to the host mlx-speech.py server (:8918)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    text = body.get("input", body.get("text", ""))
    voice = body.get("voice", "af_heart")
    if not text:
        return JSONResponse({"error": "No input text provided"}, status_code=400)
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.post(
                f"{SPEECH_URL}/v1/audio/speech", json={"input": text, "voice": voice}
            )
    except Exception as e:
        return JSONResponse(
            {"error": f"host speech server unreachable at {SPEECH_URL}: {e}"}, status_code=503
        )
    if r.status_code == 200 and not r.headers.get("content-type", "").startswith(
        "application/json"
    ):
        return Response(
            content=r.content,
            media_type="audio/wav",
            headers={"Content-Disposition": "attachment; filename=speech.wav"},
        )
    payload = (
        r.json()
        if r.headers.get("content-type", "").startswith("application/json")
        else {"error": f"speech server {r.status_code}: {r.text[:200]}"}
    )
    return JSONResponse(payload, status_code=r.status_code if r.status_code >= 400 else 503)


@mcp.custom_route("/files/tts/{filename:path}", methods=["GET"])
async def serve_generated_speech(request):
    """Serve a generated speech file for the download link in a tool result."""
    filename = request.path_params["filename"]
    if not _SAFE_FILENAME.match(filename):
        return JSONResponse({"error": "Invalid filename"}, status_code=400)
    file_path = get_generated_dir("speech") / filename
    if not file_path.is_file():
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(path=str(file_path), filename=filename, media_type="audio/wav")


@mcp.custom_route("/v1/models", methods=["GET"])
async def openai_models(request):
    """OpenAI-compatible models list — proxies to the host mlx-speech.py server (:8918)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{SPEECH_URL}/v1/models")
            if r.status_code == 200:
                return JSONResponse(r.json())
    except Exception:
        pass
    return JSONResponse({"object": "list", "data": []})


TOOLS_MANIFEST = load_data("config/inference", "tools_manifest_tts_mcp")


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})


@mcp.custom_route("/tools/speak", methods=["POST"])
async def speak_endpoint(request):
    a = (await request.json()).get("arguments", {})
    return JSONResponse(await speak(text=a.get("text", ""), voice=a.get("voice", "af_heart")))


@mcp.custom_route("/tools/clone_voice", methods=["POST"])
async def clone_voice_endpoint(request):
    a = (await request.json()).get("arguments", {})
    return JSONResponse(
        await clone_voice(reference_audio=a.get("reference_audio", ""), text=a.get("text", ""))
    )


@mcp.custom_route("/tools/register_voice", methods=["POST"])
async def register_voice_endpoint(request):
    a = (await request.json()).get("arguments", {})
    return JSONResponse(
        await register_voice(
            name=a.get("name", ""),
            reference_audio=a.get("reference_audio", ""),
            reference_text=a.get("reference_text", ""),
        )
    )


@mcp.custom_route("/tools/list_voices", methods=["POST"])
async def list_voices_endpoint(request):
    return JSONResponse(await list_voices())


@mcp.tool()
async def speak(text: str, voice: str = "af_heart") -> dict:
    """
    Convert text to speech via the host MLX speech server. Returns a download_url
    for the generated .wav — surface it to the user as the Markdown link in `message`.

    Args:
        text: The text to speak.
        voice: A Kokoro voice (af_heart, am_adam, ...), a saved trainer voice as
               "trainer:<name>", or a one-off clone as "clone:/path/to/ref.wav".
    """
    if not text.strip():
        return {"error": "text is required"}
    return await _speech_speak(text, voice)


@mcp.tool()
async def clone_voice(reference_audio: str = "", text: str = "") -> dict:
    """
    Speak text in a voice cloned from a reference clip (one-off, not persisted).
    For a recurring trainer voice, use register_voice once, then speak(voice="trainer:<name>").

    Args:
        reference_audio: The uploaded reference clip — an OWUI file id, its filename,
            or a path. Leave empty to use the most recently uploaded audio.
        text: Text to speak in the cloned voice.
    """
    if not text.strip():
        return {"error": "text is required"}
    ref = _resolve_reference(reference_audio)
    if ref is None and not reference_audio:
        return {"error": "No reference audio — upload a clip or pass reference_audio."}
    if ref is None:
        # Host-visible path (CLI/direct): let the host clone from it directly.
        return await _speech_speak(text, f"clone:{reference_audio}")

    ephemeral = f"oneoff-{secrets.token_hex(4)}"
    reg = await _post_register(ephemeral, ref, "", "one-off clone reference")
    if reg.get("status") != "success":
        return reg
    try:
        return await _speech_speak(text, f"trainer:{ephemeral}")
    finally:
        with contextlib.suppress(Exception):
            async with httpx.AsyncClient(timeout=10) as client:
                await client.delete(f"{SPEECH_URL}/v1/voices/{ephemeral}")


@mcp.tool()
async def register_voice(name: str, reference_audio: str = "", reference_text: str = "") -> dict:
    """
    Register a persisted trainer-voice profile so training sessions can be narrated in that
    voice. Register once; then speak(voice="trainer:<name>") in any later session.

    Args:
        name: Short profile name (lowercase letters, digits, _ or -).
        reference_audio: The trainer's uploaded reference clip — an OWUI file id, its
            filename, or a path. Leave empty to use the most recently uploaded audio.
            10-15s of clean continuous speech works best.
        reference_text: Exact transcript of the reference clip (improves fidelity).
    """
    if not name:
        return {"error": "name is required"}
    ref = _resolve_reference(reference_audio)
    if ref is None and not reference_audio:
        return {"error": "No reference audio — upload a clip or pass reference_audio."}
    return await _post_register(name, ref, reference_audio, reference_text)


@mcp.tool()
async def list_voices() -> dict:
    """List built-in voices and registered trainer-voice profiles."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{SPEECH_URL}/v1/voices")
            return r.json() if r.status_code == 200 else {"error": f"speech server {r.status_code}"}
    except Exception as e:
        return {"error": f"host speech server unreachable at {SPEECH_URL}: {e}"}


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
