#!/usr/bin/env python3
"""
MLX Transcribe Server — Portal 5 (TASK-TRANSCRIBE-001)

Host-native diarized transcription server for Apple Silicon.
- Transcription: mlx-whisper (Metal-accelerated, large-v3-turbo)
- Diarization: pyannote.audio 3.1 on MPS
- Output: JSON canonical + Markdown sidecar in workspace generated/transcripts/

Runs on the host (not Docker) — same pattern as mlx-proxy.py and mlx-speech.py.
Open WebUI / Pipeline connects via host.docker.internal:8924.

Usage:
    python scripts/mlx-transcribe.py
    # or via launch.sh:
    ./launch.sh start-transcribe

Files reachable:
- OWUI uploads: ${AI_OUTPUT_DIR}/uploads/<file_id> (resolved via workspace helper)
- Outputs:      ${AI_OUTPUT_DIR}/generated/transcripts/transcript_<uuid>.{json,md}
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

# Workspace helpers — TASK-WORKSPACE-001
# Add the repo root to sys.path so this host-native script can import portal_mcp.core
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from portal.platform.mcp_host.workspace import (  # noqa: E402
    get_generated_dir,
    get_uploads_dir,
    resolve_upload_path,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("mlx-transcribe")

# ── Configuration ──────────────────────────────────────────────────────────────

PORT = int(os.getenv("MLX_TRANSCRIBE_PORT", "8924"))
HOST = os.getenv("MLX_TRANSCRIBE_HOST", "0.0.0.0")

WHISPER_MODEL = os.getenv("MLX_WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")
DIARIZATION_MODEL = os.getenv("DIARIZATION_MODEL", "pyannote/speaker-diarization-3.1")
HF_TOKEN = os.getenv("HF_TOKEN", "")
VOXTRAL_MODEL = os.getenv("MLX_VOXTRAL", "mlx-community/Voxtral-Mini-3B-2507-bf16")

# ── Model cache ────────────────────────────────────────────────────────────────

_diarization_pipeline: Any = None
_voxtral_model: Any = None
_pipeline_lock = asyncio.Semaphore(1)  # GPU-heavy; serialize.


def _get_voxtral_model() -> Any:
    """Lazy-load and cache the Voxtral model via mlx_audio."""
    global _voxtral_model
    if _voxtral_model is None:
        from mlx_audio.stt.utils import load

        logger.info("Loading Voxtral model: %s", VOXTRAL_MODEL)
        _voxtral_model = load(VOXTRAL_MODEL)
        logger.info("Voxtral model ready")
    return _voxtral_model


def _voxtral_transcribe(audio_path: str, language: str | None) -> dict:
    """Transcribe via Voxtral (multilingual, no diarization). Returns same shape as _transcribe()."""
    from mlx_audio.stt.utils import transcribe as voxtral_transcribe_fn

    model = _get_voxtral_model()
    kwargs: dict[str, Any] = {}
    if language:
        kwargs["language"] = language
    result = voxtral_transcribe_fn(model, audio_path, **kwargs)
    # mlx_audio returns {"text": ..., "language": ..., "segments": [...]}
    segments = [
        {
            "start": round(seg.get("start", 0.0), 2),
            "end": round(seg.get("end", 0.0), 2),
            "text": seg.get("text", "").strip(),
        }
        for seg in result.get("segments", [])
    ]
    duration = segments[-1]["end"] if segments else 0.0
    return {
        "text": result.get("text", "").strip(),
        "language": result.get("language", language or "unknown"),
        "duration": round(duration, 2),
        "segments": segments,
    }


def _get_diarization_pipeline() -> Any:
    """Lazy-load and cache the pyannote diarization pipeline on MPS."""
    global _diarization_pipeline
    if _diarization_pipeline is None:
        if not HF_TOKEN:
            raise RuntimeError(
                "HF_TOKEN not set. Diarization models are gated — "
                "accept terms at https://huggingface.co/pyannote/speaker-diarization-3.1 "
                "and set HF_TOKEN in .env"
            )
        import torch
        from pyannote.audio import Pipeline

        logger.info("Loading diarization pipeline: %s", DIARIZATION_MODEL)
        pipeline = Pipeline.from_pretrained(DIARIZATION_MODEL, token=HF_TOKEN)
        if torch.backends.mps.is_available():
            pipeline.to(torch.device("mps"))
            logger.info("Diarization pipeline placed on MPS")
        else:
            logger.warning("MPS unavailable; diarization will run on CPU (slower)")
        _diarization_pipeline = pipeline
        logger.info("Diarization pipeline ready")
    return _diarization_pipeline


# ── Core pipeline ──────────────────────────────────────────────────────────────


def _transcribe(audio_path: str, language: str | None) -> dict:
    """Run mlx-whisper transcription. Returns {text, language, duration, segments}."""
    import mlx_whisper

    kwargs: dict[str, Any] = {"path_or_hf_repo": WHISPER_MODEL}
    if language:
        kwargs["language"] = language
    result = mlx_whisper.transcribe(audio_path, **kwargs)
    segments = [
        {
            "start": round(seg["start"], 2),
            "end": round(seg["end"], 2),
            "text": seg["text"].strip(),
        }
        for seg in result.get("segments", [])
    ]
    duration = segments[-1]["end"] if segments else 0.0
    return {
        "text": result.get("text", "").strip(),
        "language": result.get("language", language or "unknown"),
        "duration": round(duration, 2),
        "segments": segments,
    }


def _diarize(audio_path: str, num_speakers: int | None) -> list[dict]:
    """Run pyannote diarization. Returns sorted list of {start, end, speaker}.

    Converts to 16kHz mono WAV before diarization — pyannote raises ValueError
    on MP3 files where compressed frame boundaries produce sample-count mismatches.
    """
    import shutil
    import subprocess

    pipeline = _get_diarization_pipeline()

    # Convert to 16kHz mono WAV to avoid MP3 chunk-boundary sample-count errors
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    wav_tmp = audio_path + "_diarize.wav"
    try:
        subprocess.run(
            [ffmpeg, "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", wav_tmp],
            check=True,
            capture_output=True,
        )
        diarize_input = wav_tmp
    except Exception as e:
        logger.warning("WAV conversion failed (%s); falling back to original path", e)
        diarize_input = audio_path

    try:
        kwargs: dict[str, Any] = {}
        if num_speakers is not None:
            kwargs["num_speakers"] = num_speakers
        output = pipeline(diarize_input, **kwargs)
        # pyannote 4.x returns DiarizeOutput(speaker_diarization=Annotation, ...)
        # pyannote 3.x returns Annotation directly
        annotation = getattr(output, "speaker_diarization", output)
    finally:
        import os

        if diarize_input != audio_path:
            os.unlink(wav_tmp)

    turns = [
        {
            "start": round(turn.start, 2),
            "end": round(turn.end, 2),
            "speaker": speaker,
        }
        for turn, _, speaker in annotation.itertracks(yield_label=True)
    ]
    turns.sort(key=lambda t: t["start"])
    return turns


def _merge(segments: list[dict], turns: list[dict]) -> list[dict]:
    """Assign each segment to max-overlap speaker, then collapse adjacent same-speaker."""
    if not turns:
        return [{**s, "speaker": "SPEAKER_00"} for s in segments]
    labeled: list[dict] = []
    for seg in segments:
        best_speaker, best_overlap = "SPEAKER_UNKNOWN", 0.0
        for t in turns:
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


def _format_markdown(merged: list[dict], meta: dict, source_name: str = "audio") -> str:
    """Render merged segments as speaker-labeled markdown."""
    lines = [
        f"# Transcript: {source_name}",
        "",
        f"- **Duration**: {meta['duration']:.1f}s",
        f"- **Language**: {meta['language']}",
        f"- **Speakers**: {meta['speaker_count']}",
        f"- **Generated**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "---",
        "",
    ]
    for seg in merged:
        ts = f"[{int(seg['start']) // 60:02d}:{int(seg['start']) % 60:02d}]"
        lines.append(f"**{seg['speaker']}** {ts}")
        lines.append(seg["text"])
        lines.append("")
    return "\n".join(lines)


def _run_pipeline(
    audio_path: str,
    language: str | None,
    num_speakers: int | None,
    source_name: str = "audio",
) -> dict:
    """Synchronous full pipeline. Caller wraps in asyncio.to_thread."""
    t0 = time.time()
    transcript = _transcribe(audio_path, language)
    t_transcribe = time.time() - t0

    t1 = time.time()
    diarization_warning: str | None = None
    try:
        speaker_turns = _diarize(audio_path, num_speakers)
    except Exception as e:
        diarization_warning = (
            f"Diarization unavailable ({type(e).__name__}: {e}); using single-speaker fallback"
        )
        logger.warning(diarization_warning)
        speaker_turns = []
    t_diarize = time.time() - t1

    merged = _merge(transcript["segments"], speaker_turns)
    speaker_count = len({s["speaker"] for s in merged}) if merged else 0

    meta = {
        "text": transcript["text"],
        "language": transcript["language"],
        "duration": transcript["duration"],
        "speaker_count": speaker_count,
        "timing": {
            "transcribe_s": round(t_transcribe, 2),
            "diarize_s": round(t_diarize, 2),
            "total_s": round(time.time() - t0, 2),
        },
    }

    # Persist via workspace helper
    out_dir = get_generated_dir("transcripts")
    uid = uuid.uuid4().hex[:12]
    json_path = out_dir / f"transcript_{uid}.json"
    md_path = out_dir / f"transcript_{uid}.md"

    full_payload = {**meta, "segments": merged, "source": source_name}
    json_path.write_text(json.dumps(full_payload, indent=2))
    markdown = _format_markdown(merged, meta, source_name)
    md_path.write_text(markdown)

    result = {
        **meta,
        "segments": merged,
        "markdown": markdown,
        "json_path": str(json_path),
        "md_path": str(md_path),
        "json_url": f"http://host.docker.internal:{PORT}/files/{json_path.name}",
        "md_url": f"http://host.docker.internal:{PORT}/files/{md_path.name}",
    }
    if diarization_warning:
        result["diarization_warning"] = diarization_warning
    return result


def _run_voxtral_pipeline(
    audio_path: str,
    language: str | None,
    source_name: str = "audio",
) -> dict:
    """Voxtral-only pipeline (no diarization). Caller wraps in asyncio.to_thread."""
    t0 = time.time()
    transcript = _voxtral_transcribe(audio_path, language)
    elapsed = round(time.time() - t0, 2)

    segments = [{**s, "speaker": "SPEAKER_00"} for s in transcript["segments"]]

    meta = {
        "text": transcript["text"],
        "language": transcript["language"],
        "duration": transcript["duration"],
        "speaker_count": 1,
        "timing": {"transcribe_s": elapsed, "diarize_s": 0.0, "total_s": elapsed},
    }

    out_dir = get_generated_dir("transcripts")
    uid = uuid.uuid4().hex[:12]
    json_path = out_dir / f"transcript_{uid}.json"
    md_path = out_dir / f"transcript_{uid}.md"

    full_payload = {**meta, "segments": segments, "source": source_name}
    json_path.write_text(json.dumps(full_payload, indent=2))
    markdown = _format_markdown(segments, meta, source_name)
    md_path.write_text(markdown)

    return {
        **meta,
        "segments": segments,
        "markdown": markdown,
        "json_path": str(json_path),
        "md_path": str(md_path),
        "json_url": f"http://host.docker.internal:{PORT}/files/{json_path.name}",
        "md_url": f"http://host.docker.internal:{PORT}/files/{md_path.name}",
    }


_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".aac", ".mp4"}
_PLACEHOLDER_RE = re.compile(r"^[<\[{].*[>\]}]$")  # matches <file_id>, [filename], {arg}, etc.


def _latest_audio_upload() -> Path | None:
    """Return the most recently modified audio file in the uploads directory."""
    uploads = get_uploads_dir()
    candidates = [
        f for f in uploads.iterdir() if f.is_file() and f.suffix.lower() in _AUDIO_EXTENSIONS
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda f: f.stat().st_mtime)


def _resolve_audio_input(file: str) -> tuple[Path | None, str]:
    """Resolve a tool input to an absolute path.

    Accepts:
      - OWUI file ID (e.g., 'abc-123' or 'abc-123_meeting.mp3')
      - Filename in the uploads directory
      - Absolute path on the host filesystem
      - Empty string or template placeholder → auto-detects most recent upload

    Returns (path, source_name) or (None, error_message).
    """
    # Empty or literal template placeholder (e.g. '<file_id_or_filename>') →
    # OWUI doesn't surface file references to the pipeline, so auto-detect
    # the most recently uploaded audio file.
    if not file or _PLACEHOLDER_RE.match(file.strip()):
        p = _latest_audio_upload()
        if p is not None:
            logger.info("Auto-detected most recent audio upload: %s", p.name)
            return p, p.name
        return None, "no audio file found in uploads directory — please upload an audio file first"

    # Looks like an absolute path
    if file.startswith("/") or file.startswith("~"):
        p = Path(file).expanduser().resolve()
        if p.is_file():
            return p, p.name
        return None, f"file not found at path: {file}"

    # Try resolving as an upload reference (id or filename)
    p = resolve_upload_path(file)
    if p is not None:
        return p, p.name

    # Last resort: fall back to most recent audio upload with a warning
    fallback = _latest_audio_upload()
    if fallback is not None:
        logger.warning(
            "Could not resolve %r — falling back to most recent upload: %s", file, fallback.name
        )
        return fallback, fallback.name
    return None, f"upload not found: {file!r} (no match in uploads directory)"


# ── FastAPI app ────────────────────────────────────────────────────────────────

# MCP is defined later (needs the tool functions), then the session manager
# lifespan is wired in here so mounted sub-apps get their task group initialized.
from contextlib import asynccontextmanager  # noqa: E402


@asynccontextmanager
async def _lifespan(app: FastAPI):
    async with _mcp_session_manager.run():
        yield


app = FastAPI(title="Portal 5 MLX Transcribe", version="1.0.0", lifespan=_lifespan)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": "mlx-transcribe",
            "whisper_model": WHISPER_MODEL,
            "voxtral_model": VOXTRAL_MODEL,
            "diarization_model": DIARIZATION_MODEL,
            "diarization_loaded": _diarization_pipeline is not None,
            "voxtral_loaded": _voxtral_model is not None,
        }
    )


@app.post("/tools/{tool_name}")
async def invoke_tool(tool_name: str, request: Request) -> JSONResponse:
    """REST dispatch endpoint used by portal-pipeline tool_registry."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    arguments = body.get("arguments", {})

    if tool_name == "transcribe_with_speakers":
        file_arg = arguments.get("file", "")
        num_speakers = arguments.get("num_speakers")
        language = arguments.get("language")
        engine = arguments.get("engine", "whisper-large-v3-turbo")
        path, source_name = _resolve_audio_input(file_arg)
        if path is None:
            return JSONResponse({"error": source_name})
        async with _pipeline_lock:
            try:
                if engine == "voxtral-mini-3b":
                    result = await asyncio.to_thread(
                        _run_voxtral_pipeline, str(path), language, source_name
                    )
                else:
                    result = await asyncio.to_thread(
                        _run_pipeline, str(path), language, num_speakers, source_name
                    )
                result["engine"] = engine
                return JSONResponse(result)
            except Exception as e:
                logger.error("invoke_tool transcribe_with_speakers failed: %s", e, exc_info=True)
                return JSONResponse({"error": str(e)}, status_code=500)
    else:
        return JSONResponse({"error": f"Unknown tool: {tool_name}"}, status_code=404)


@app.get("/tools")
async def list_tools() -> JSONResponse:
    return JSONResponse(
        {
            "tools": [
                {
                    "name": "transcribe_with_speakers",
                    "description": (
                        "Transcribe an audio file using MLX. Default engine: whisper-large-v3-turbo "
                        "with pyannote speaker diarization. Use engine='voxtral-mini-3b' for "
                        "multilingual transcription (en/fr/de/es/it/pt/nl/ru, no diarization). "
                        "Call with no arguments to auto-detect the most recently uploaded audio file."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file": {
                                "type": "string",
                                "description": "Audio file reference: OWUI file ID, filename in uploads/, or absolute path. Omit to auto-detect most recent upload.",
                            },
                            "num_speakers": {
                                "type": "integer",
                                "description": "Expected speaker count (whisper engine only). Auto-detected if omitted. Recommended for >15 min audio.",
                            },
                            "language": {
                                "type": "string",
                                "description": "ISO language code (e.g. 'en', 'fr'). Auto-detected if omitted.",
                            },
                            "engine": {
                                "type": "string",
                                "enum": ["whisper-large-v3-turbo", "voxtral-mini-3b"],
                                "description": "Transcription engine. 'whisper-large-v3-turbo' (default): speaker-diarized English-optimized. 'voxtral-mini-3b': Mistral multilingual (8 languages), no diarization.",
                            },
                        },
                        "required": [],
                    },
                }
            ]
        }
    )


@app.get("/files/{filename}", response_model=None)
async def serve_file(filename: str) -> FileResponse | JSONResponse:
    """Serve generated transcript artifacts for browser download."""
    if "/" in filename or ".." in filename:
        return JSONResponse({"error": "invalid filename"}, status_code=400)
    out_dir = get_generated_dir("transcripts")
    path = out_dir / filename
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path)


@app.post("/v1/audio/transcribe-with-speakers")
async def http_transcribe(
    file: UploadFile = File(...),  # noqa: B008
    language: str = Form(default="auto"),  # noqa: B008
    num_speakers: int | None = Form(default=None),  # noqa: B008
) -> JSONResponse:
    """Direct HTTP entry point (curl, scripts, batch jobs).

    Accepts a multipart upload, processes synchronously, returns JSON.
    For OWUI integration, use the MCP tool instead.
    """
    tmp_path: str | None = None
    try:
        contents = await file.read()
        suffix = ".wav"
        fname = file.filename or ""
        for ext in [".webm", ".ogg", ".mp4", ".m4a", ".wav", ".mp3", ".flac"]:
            if fname.lower().endswith(ext):
                suffix = ext
                break
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
    except Exception as e:
        return JSONResponse({"error": f"upload failed: {e}"}, status_code=400)

    try:
        async with _pipeline_lock:
            lang = None if language == "auto" else language
            source_name = file.filename or "upload.wav"
            result = await asyncio.to_thread(
                _run_pipeline, tmp_path, lang, num_speakers, source_name
            )
        return JSONResponse(result)
    except Exception as e:
        logger.error("Transcription failed: %s", e, exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        if tmp_path:
            with contextlib.suppress(Exception):
                os.unlink(tmp_path)


# ── MCP wrapper ────────────────────────────────────────────────────────────────

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("mlx-transcribe", host=HOST, streamable_http_path="/")


@mcp.tool()
async def transcribe_with_speakers(
    file: str = "",
    num_speakers: int | None = None,
    language: str | None = None,
    engine: str = "whisper-large-v3-turbo",
) -> dict:
    """
    Transcribe an audio file with speaker diarization (whisper) or multilingual
    recognition (voxtral).

    Produces a transcript and saves both JSON and Markdown to the workspace
    generated/transcripts/ directory. The full markdown is included in the response.

    Args:
        file: Audio file reference. Omit (or leave empty) to auto-detect the
              most recently uploaded audio file. Otherwise accepts:
              - OWUI file ID from a chat attachment (e.g., 'abc-123-def')
              - Filename in the uploads directory (e.g., 'meeting.mp3')
              - Absolute path on the host (e.g., '/Users/me/audio.wav')
        num_speakers: Hint for expected speaker count (whisper engine only).
                      Auto-detected if omitted. Recommended for files >15 min.
        language: ISO language code (e.g., 'en', 'es', 'fr'). Auto-detected if
                  omitted. Voxtral supports: en, fr, de, es, it, pt, nl, ru.
        engine: Transcription engine to use.
                - "whisper-large-v3-turbo" (default): mlx-whisper + pyannote
                  diarization, English-optimized, speaker labels
                - "voxtral-mini-3b": Mistral Voxtral, 8-language multilingual,
                  no diarization, requires PULL_VOXTRAL=1 download first

    Returns:
        dict with:
          - text: full transcript (no speaker labels)
          - language, duration, speaker_count
          - segments: list of {start, end, speaker, text}
          - markdown: full speaker-labeled markdown content (ready to display)
          - json_path, md_path: workspace file paths
          - json_url, md_url: download URLs (port :8924)
          - timing: {transcribe_s, diarize_s, total_s}
          - engine: which engine was used

        On error: {"error": "..."}
    """
    logger.info(
        "transcribe_with_speakers called: file=%r num_speakers=%r language=%r engine=%r",
        file,
        num_speakers,
        language,
        engine,
    )
    path, source_name = _resolve_audio_input(file)
    if path is None:
        logger.warning("file not resolved: %r — %s", file, source_name)
        return {"error": source_name}

    async with _pipeline_lock:
        try:
            if engine == "voxtral-mini-3b":
                result = await asyncio.to_thread(
                    _run_voxtral_pipeline, str(path), language, source_name
                )
            else:
                result = await asyncio.to_thread(
                    _run_pipeline, str(path), language, num_speakers, source_name
                )
            result["engine"] = engine
            return result
        except Exception as e:
            logger.error("MCP transcribe_with_speakers failed: %s", e, exc_info=True)
            return {"error": str(e)}


# Initialize session manager (must happen after tool definitions, before app start).
# streamable_http_app() lazily creates _session_manager; we surface it so the
# parent lifespan (_lifespan above) can run the task group.
_mcp_sub_app = mcp.streamable_http_app()
_mcp_session_manager = mcp.session_manager  # noqa: F821 — defined above
app.mount("/mcp", _mcp_sub_app)


# ── Entrypoint ─────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    logger.info("Starting mlx-transcribe on %s:%d", HOST, PORT)
    logger.info("Whisper model: %s", WHISPER_MODEL)
    logger.info("Voxtral model: %s (lazy-loaded on first voxtral-mini-3b request)", VOXTRAL_MODEL)
    logger.info("Diarization model: %s", DIARIZATION_MODEL)
    logger.info("Output dir: %s", get_generated_dir("transcripts"))
    if not HF_TOKEN:
        logger.warning("HF_TOKEN not set — diarization will fail on first call")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
