"""
Whisper MCP Server
Wraps faster-whisper for audio transcription as an MCP tool.
"""

import asyncio
import contextlib
import logging
import os
from pathlib import Path

import httpx

from portal.platform.data_loader import load_data
from portal.platform.mcp_host.owui_files import publish_file
from portal.platform.mcp_host.workspace import get_generated_dir

logger = logging.getLogger(__name__)


async def _attach_transcript_urls(res: dict) -> dict:
    """Publish the transcript files the host wrote so the user gets download links.

    The host returns absolute paths on its own filesystem; the same files are
    visible here under the shared workspace mount, keyed by basename.
    """
    tdir = get_generated_dir("transcripts")
    for path_key, url_key in (("json_path", "json_url"), ("md_path", "md_url")):
        p = res.get(path_key)
        if not p:
            continue
        local = tdir / Path(p).name
        if local.is_file():
            pub = await publish_file(local)
            res[url_key] = pub.get("url") or pub.get("error", "publish failed")
    return res


# Primary transcription path is the host MLX server (Parakeet + Sortformer) on :8924.
# This module proxies there first and only falls back to the in-Docker faster-whisper
# path (below) on non-Apple-Silicon nodes where the host server is unreachable.
MLX_TRANSCRIBE_URL = os.getenv("MLX_TRANSCRIBE_URL", "http://host.docker.internal:8924").rstrip("/")


async def _try_host(tool_name: str, arguments: dict) -> dict | None:
    """Proxy to the host MLX transcribe server; return None if unreachable so the
    caller can fall back to the in-Docker faster-whisper path."""
    url = f"{MLX_TRANSCRIBE_URL}/tools/{tool_name}"
    # 30 min, matching AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA — a 2 h recording is
    # ~3-4 min of host work, but a loaded box or a longer file needs the headroom.
    try:
        async with httpx.AsyncClient(
            timeout=float(os.getenv("WHISPER_PROXY_TIMEOUT", "1800"))
        ) as c:
            r = await c.post(url, json={"arguments": arguments})
            if r.status_code == 200:
                return r.json()
            return {"error": f"host transcribe server {r.status_code}: {r.text[:200]}"}
    except Exception:
        return None  # host unreachable → caller uses Docker fallback


from mcp.server import MCPServer
from starlette.responses import JSONResponse

mcp = MCPServer("whisper-transcription")


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "whisper-mcp"})


@mcp.custom_route("/v1/audio/transcriptions", methods=["POST"])
async def openai_audio_transcriptions(request):
    """OpenAI-compatible STT endpoint.

    Open WebUI sends multipart/form-data with 'file' field containing audio.
    Required for AUDIO_STT_ENGINE=openai integration.
    """
    import tempfile

    tmp_path: str | None = None
    try:
        form = await request.form()
        audio_file = form.get("file")
        if audio_file is None:
            return JSONResponse({"error": "No file provided"}, status_code=400)

        # Save uploaded audio to a temp file
        contents = await audio_file.read()
        suffix = ".wav"
        # Detect format from filename if available
        fname = getattr(audio_file, "filename", "") or ""
        for ext in [".webm", ".ogg", ".mp4", ".m4a", ".wav", ".mp3"]:
            if fname.endswith(ext):
                suffix = ext
                break

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

    except Exception as e:
        return JSONResponse({"error": f"Upload failed: {e}"}, status_code=400)

    # Transcribe
    result = await transcribe_audio(file_path=tmp_path)

    # Clean up temp file (only if one was created)
    with contextlib.suppress(Exception):
        if tmp_path:
            os.unlink(tmp_path)

    if "error" in result:
        return JSONResponse(result, status_code=500)

    text = result.get("text", result.get("transcription", ""))
    return JSONResponse({"text": text})


@mcp.custom_route("/v1/models", methods=["GET"])
async def openai_models(request):
    """OpenAI-compatible models list for STT model selection."""
    from starlette.responses import JSONResponse

    return JSONResponse(
        {"object": "list", "data": [{"id": "whisper-1", "object": "model", "owned_by": "portal-5"}]}
    )


# Tool manifest for discovery
TOOLS_MANIFEST = load_data("config/inference", "tools_manifest_whisper_mcp")


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})


@mcp.custom_route("/tools/{tool_name}", methods=["POST"])
async def invoke_tool(request):
    """REST dispatch endpoint used by portal-pipeline tool_registry."""
    tool_name = request.path_params["tool_name"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    arguments = body.get("arguments", {})

    try:
        if tool_name == "transcribe_audio":
            import inspect

            valid = set(inspect.signature(transcribe_audio).parameters.keys())
            filtered = {k: v for k, v in arguments.items() if k in valid}
            result = await transcribe_audio(**filtered)
            return JSONResponse(result)
        elif tool_name == "transcribe_with_speakers":
            import inspect

            valid = set(inspect.signature(transcribe_with_speakers).parameters.keys())
            filtered = {k: v for k, v in arguments.items() if k in valid}
            result = await transcribe_with_speakers(**filtered)
            return JSONResponse(result)
        else:
            return JSONResponse({"error": f"Unknown tool: {tool_name}"}, status_code=404)
    except Exception as e:
        import logging as _log

        _log.getLogger(__name__).exception("Tool invocation failed for %s", tool_name)
        return JSONResponse({"error": str(e)}, status_code=500)


# Docker fallback only (non-Apple-Silicon nodes). Primary is the host MLX server
# (Parakeet + Sortformer) via MLX_TRANSCRIBE_URL. 'base' was a real accuracy floor.
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL", "large-v3-turbo")
_model = None


def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(WHISPER_MODEL_SIZE, device="auto", compute_type="auto")
    return _model


@mcp.tool()
async def transcribe_audio(file_path: str | None = None, language: str | None = None) -> dict:
    """
    Transcribe an audio file using Whisper.

    Args:
        file_path: Absolute path to the audio file (mp3, wav, m4a, ogg, flac).
                   Omit to auto-detect the most recently uploaded file from the workspace.
        language: Language code (e.g. 'en', 'es'). Auto-detected if not provided.

    Returns:
        dict with 'text' (full transcript) and 'segments' (timestamped segments)
    """
    host_args: dict = {}
    if file_path is not None:
        host_args["file"] = file_path
    if language is not None:
        host_args["language"] = language
    res = await _try_host("transcribe_audio", host_args)
    if res is not None:
        return res

    if file_path is None:
        from portal.platform.mcp_host.workspace import get_uploads_dir

        uploads = get_uploads_dir()
        audio_exts = [".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"]
        candidates = [p for ext in audio_exts for p in uploads.glob(f"*{ext}") if p.is_file()]
        if not candidates:
            return {
                "error": "Audio file not found in workspace uploads. Please provide audio_path."
            }
        file_path = str(max(candidates, key=lambda p: p.stat().st_mtime))
        logger.info("transcribe_audio: auto-detected latest upload: %s", file_path)

    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}

    model = get_model()
    segments, info = await asyncio.to_thread(
        model.transcribe,
        str(path),
        language=language,
        beam_size=5,
    )

    segment_list = []
    full_text = []
    for seg in segments:
        segment_list.append(
            {
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
            }
        )
        full_text.append(seg.text.strip())

    return {
        "text": " ".join(full_text),
        "language": info.language,
        "duration": round(info.duration, 2),
        "segments": segment_list,
    }


# ── Diarized transcription (TASK_TRANSCRIBE_VIBEVOICE_PARAKEET_REPLACE) ─────────
# Runs on the host MLX server (:8924): Parakeet transcript + Sortformer speaker
# diarization, merged at the word level. No in-Docker diarizer — pyannote and the
# HF_TOKEN gate are retired.


@mcp.tool()
async def transcribe_with_speakers(
    file: str = "",
    num_speakers: int | None = None,
    language: str | None = None,
) -> dict:
    """
    Transcribe an audio file and label who is speaking.

    Runs on the host MLX server (port 8924): full transcript (Parakeet-TDT-v3) plus
    speaker turns (Sortformer diarization), merged at the word level. A monologue
    returns one speaker; a conversation returns SPEAKER_00/SPEAKER_01/... per turn
    (up to 4). No HuggingFace token. Speaker labelling is Apple-Silicon-only — on
    nodes where the host server is unreachable this returns an error rather than an
    unlabeled transcript (use transcribe_audio there).

    Args:
        file: Audio reference. Omit to auto-detect the most recent upload; otherwise
              an OWUI file ID, filename in uploads/, or absolute path.
        num_speakers: Optional cap on the speaker count (folds over-segmented
              speakers into the nearest kept one). Inferred when omitted.
        language: ISO language code. Auto-detected if omitted.

    Returns:
        dict with text, language, duration, speaker_count, segments, markdown,
        json_path, md_path, timing, engine; ``warning`` if diarization was skipped.
    """
    host_args: dict = {"file": file}
    if num_speakers is not None:
        host_args["num_speakers"] = num_speakers
    if language is not None:
        host_args["language"] = language
    res = await _try_host("transcribe_with_speakers", host_args)
    if res is not None:
        return await _attach_transcript_urls(res)
    return {
        "error": "speaker labelling requires the host MLX transcribe server (:8924) — "
        "unreachable; use transcribe_audio for a transcript without speaker labels"
    }


# ── End diarized transcription ────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("WHISPER_MCP_PORT", "8915"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
