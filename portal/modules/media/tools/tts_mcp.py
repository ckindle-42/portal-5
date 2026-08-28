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

import logging
import os

import httpx
from mcp.server import MCPServer
from starlette.responses import JSONResponse, Response

from portal.platform.data_loader import load_data

logger = logging.getLogger(__name__)
port = int(os.getenv("TTS_MCP_PORT", "8916"))
mcp = MCPServer("tts-generation")

SPEECH_URL = os.getenv("MLX_SPEECH_URL", "http://host.docker.internal:8918").rstrip("/")
HTTP_TIMEOUT = float(os.getenv("TTS_PROXY_TIMEOUT", "120"))


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
        return {
            "status": "success",
            "voice": voice,
            "audio_bytes": len(r.content),
            "message": f"Spoke {len(text)} chars with voice '{voice}'.",
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
    Convert text to speech via the host MLX speech server.

    Args:
        text: The text to speak.
        voice: A Kokoro voice (af_heart, am_adam, ...), a saved trainer voice as
               "trainer:<name>", or a one-off clone as "clone:/path/to/ref.wav".
    """
    if not text.strip():
        return {"error": "text is required"}
    return await _speech_speak(text, voice)


@mcp.tool()
async def clone_voice(reference_audio: str, text: str) -> dict:
    """
    Speak text in a voice cloned from a reference clip (one-off, not persisted).
    For a recurring trainer voice, use register_voice once, then speak(voice="trainer:<name>").

    Args:
        reference_audio: Path to a 5-15s clean reference clip (host-visible path).
        text: Text to speak in the cloned voice.
    """
    if not reference_audio or not text.strip():
        return {"error": "reference_audio and text are required"}
    return await _speech_speak(text, f"clone:{reference_audio}")


@mcp.tool()
async def register_voice(name: str, reference_audio: str, reference_text: str) -> dict:
    """
    Register a persisted trainer-voice profile so training sessions can be narrated in that
    voice. Register once; then speak(voice="trainer:<name>") in any later session.

    Args:
        name: Short profile name (lowercase letters, digits, _ or -).
        reference_audio: Path to 10-15s of the trainer's clean speech (host-visible path).
        reference_text: Exact transcript of the reference clip (improves fidelity).
    """
    if not name or not reference_audio:
        return {"error": "name and reference_audio are required"}
    url = f"{SPEECH_URL}/v1/voices"
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.post(
                url,
                json={
                    "name": name,
                    "reference_audio": reference_audio,
                    "reference_text": reference_text,
                },
            )
            return r.json()
    except Exception as e:
        return {"error": f"host speech server unreachable at {SPEECH_URL}: {e}"}


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
