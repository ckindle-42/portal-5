"""
Whisper MCP Server
Wraps faster-whisper for audio transcription as an MCP tool.
"""

import asyncio
import contextlib
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

from starlette.responses import JSONResponse

from portal_mcp.mcp_server.fastmcp import FastMCP

mcp = FastMCP("whisper-transcription", host="0.0.0.0")


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
TOOLS_MANIFEST = [
    {
        "name": "transcribe_audio",
        "description": (
            "Transcribe audio using faster-whisper. "
            "If the user uploaded an audio file, omit audio_path and the tool will "
            "auto-detect the most recently uploaded file from the workspace."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "audio_path": {
                    "type": "string",
                    "description": "Absolute path to audio file. Omit to auto-detect latest upload.",
                },
                "language": {
                    "type": "string",
                    "description": "Language code (e.g., en, zh)",
                    "default": "auto",
                },
            },
            "required": [],
        },
    },
    {
        "name": "transcribe_with_speakers",
        "description": (
            "Transcribe an audio file with speaker diarization (Docker fallback path). "
            "On Apple Silicon, prefer the host-native MLX path on port 8924 "
            "(mlx-whisper + pyannote on MPS, ~5x faster). This Docker path is the "
            "cross-platform fallback for Linux/CUDA nodes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "Audio reference: OWUI file ID, filename in uploads/, or absolute path",
                },
                "num_speakers": {
                    "type": "integer",
                    "description": "Hint for expected speaker count. Auto-detected if omitted.",
                },
                "language": {
                    "type": "string",
                    "description": "ISO language code. Auto-detected if omitted.",
                },
            },
            "required": ["file"],
        },
    },
]


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


WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")
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
    if file_path is None:
        from portal_mcp.core.workspace import get_uploads_dir

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


# ── Diarization (TASK-TRANSCRIBE-001) ───────────────────────────────────────────
# Cross-platform fallback for transcribe_with_speakers. Apple Silicon primary
# is scripts/mlx-transcribe.py (mlx-whisper + pyannote on MPS). This Docker
# path uses faster-whisper (CPU, or CUDA on Linux nodes) + pyannote.

import json as _json
import time as _time
import uuid as _uuid

from portal_mcp.core.workspace import (
    get_generated_dir as _get_generated_dir,
)
from portal_mcp.core.workspace import (
    resolve_upload_path as _resolve_upload_path,
)

_diarization_pipeline = None


def _get_diarization_pipeline():
    """Lazy-load pyannote diarization pipeline."""
    global _diarization_pipeline
    if _diarization_pipeline is None:
        hf_token = os.getenv("HF_TOKEN", "")
        if not hf_token:
            raise RuntimeError(
                "HF_TOKEN not set. Diarization models are gated — "
                "accept terms at https://huggingface.co/pyannote/speaker-diarization-3.1"
            )
        import torch
        from pyannote.audio import Pipeline

        pipeline = Pipeline.from_pretrained(
            os.getenv("DIARIZATION_MODEL", "pyannote/speaker-diarization-3.1"),
            use_auth_token=hf_token,
        )
        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
        _diarization_pipeline = pipeline
    return _diarization_pipeline


def _merge_speakers(segments: list[dict], speaker_turns: list[dict]) -> list[dict]:
    if not speaker_turns:
        return [{**s, "speaker": "SPEAKER_00"} for s in segments]
    labeled: list[dict] = []
    for seg in segments:
        best_speaker, best_overlap = "SPEAKER_UNKNOWN", 0.0
        for t in speaker_turns:
            overlap = min(seg["end"], t["end"]) - max(seg["start"], t["start"])
            if overlap > best_overlap:
                best_overlap, best_speaker = overlap, t["speaker"]
        labeled.append({**seg, "speaker": best_speaker})
    merged: list[dict] = []
    for seg in labeled:
        if merged and merged[-1]["speaker"] == seg["speaker"]:
            merged[-1]["end"] = seg["end"]
            merged[-1]["text"] = (merged[-1]["text"] + " " + seg["text"]).strip()
        else:
            merged.append(dict(seg))
    return merged


def _format_md(merged: list[dict], meta: dict, source_name: str = "audio") -> str:
    lines = [
        f"# Transcript: {source_name}",
        "",
        f"- **Duration**: {meta['duration']:.1f}s",
        f"- **Language**: {meta['language']}",
        f"- **Speakers**: {meta['speaker_count']}",
        f"- **Generated**: {_time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "---",
        "",
    ]
    for s in merged:
        ts = f"[{int(s['start']) // 60:02d}:{int(s['start']) % 60:02d}]"
        lines.append(f"**{s['speaker']}** {ts}")
        lines.append(s["text"])
        lines.append("")
    return "\n".join(lines)


def _resolve_audio(file: str) -> tuple[Path | None, str]:
    """Resolve a file ID, filename, or absolute path to a Path."""
    if file.startswith("/") or file.startswith("~"):
        p = Path(file).expanduser().resolve()
        if p.is_file():
            return p, p.name
        return None, f"file not found at path: {file}"
    p = _resolve_upload_path(file)
    if p is not None:
        return p, p.name
    return None, f"upload not found: {file!r}"


@mcp.tool()
async def transcribe_with_speakers(
    file: str,
    num_speakers: int | None = None,
    language: str | None = None,
) -> dict:
    """
    Transcribe an audio file with speaker diarization (Docker fallback path).

    On Apple Silicon, prefer the host-native MLX path on port 8924
    (mlx-whisper + pyannote on MPS, ~5x faster). This Docker path is the
    cross-platform fallback for Linux/CUDA nodes.

    Args:
        file: Audio reference. Accepts OWUI file ID, filename in uploads/,
              or absolute path.
        num_speakers: Hint for expected speaker count. Auto-detected if omitted.
        language: ISO language code. Auto-detected if omitted.

    Returns:
        dict with text, language, duration, speaker_count, segments,
        markdown, json_path, md_path, timing.
    """
    path, source_name = _resolve_audio(file)
    if path is None:
        return {"error": source_name}

    t0 = _time.time()
    base = await transcribe_audio(file_path=str(path), language=language)
    if "error" in base:
        return base
    t_transcribe = _time.time() - t0

    t1 = _time.time()
    try:
        pipeline = await asyncio.to_thread(_get_diarization_pipeline)
        kwargs = {"num_speakers": num_speakers} if num_speakers is not None else {}
        diarization = await asyncio.to_thread(pipeline, str(path), **kwargs)
        speaker_turns = [
            {"start": round(turn.start, 2), "end": round(turn.end, 2), "speaker": spk}
            for turn, _, spk in diarization.itertracks(yield_label=True)
        ]
        speaker_turns.sort(key=lambda t: t["start"])
    except Exception as e:
        return {"error": f"diarization failed: {e}"}
    t_diarize = _time.time() - t1

    merged = _merge_speakers(base["segments"], speaker_turns)
    speaker_count = len({s["speaker"] for s in merged}) if merged else 0

    meta = {
        "text": base["text"],
        "language": base["language"],
        "duration": base["duration"],
        "speaker_count": speaker_count,
        "timing": {
            "transcribe_s": round(t_transcribe, 2),
            "diarize_s": round(t_diarize, 2),
            "total_s": round(_time.time() - t0, 2),
        },
    }

    out_dir = _get_generated_dir("transcripts")
    uid = _uuid.uuid4().hex[:12]
    json_path = out_dir / f"transcript_{uid}.json"
    md_path = out_dir / f"transcript_{uid}.md"
    full_payload = {**meta, "segments": merged, "source": source_name}
    json_path.write_text(_json.dumps(full_payload, indent=2))
    markdown = _format_md(merged, meta, source_name)
    md_path.write_text(markdown)

    return {
        **meta,
        "segments": merged,
        "markdown": markdown,
        "json_path": str(json_path),
        "md_path": str(md_path),
    }


# ── End diarization additions ──────────────────────────────────────────────────


if __name__ == "__main__":
    port = int(os.getenv("WHISPER_MCP_PORT", "8915"))
    mcp.settings.port = port
    mcp.run(transport="streamable-http")
