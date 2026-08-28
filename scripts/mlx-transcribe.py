#!/usr/bin/env python3
"""
MLX Transcribe Server — Portal 5 (TASK-TRANSCRIBE-001)

Host-native transcription server for Apple Silicon.
- Fast ASR: Parakeet-TDT-v3 (Metal-accelerated, word-level timestamps)
- Diarized: VibeVoice-ASR 9B — text + speaker labels + timestamps in one pass (no HF token)
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
# Add the repo root to sys.path so this host-native script can import portal.platform.mcp_host
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

# ASR (fast, no diarization) — Parakeet-TDT-v3, word-level timestamps.
PARAKEET_MODEL = os.getenv("MLX_PARAKEET_MODEL", "mlx-community/parakeet-tdt-0.6b-v3")
# Diarized transcription (text + speaker + timestamps, single pass) — VibeVoice-ASR 9B.
VIBEVOICE_MODEL = os.getenv("MLX_VIBEVOICE_MODEL", "mlx-community/VibeVoice-ASR-bf16")
# pyannote + HF_TOKEN diarization gate and the Voxtral path are retired
# (TASK_TRANSCRIBE_VIBEVOICE_PARAKEET_REPLACE) — VibeVoice diarizes in one pass, ungated.

# ── Model cache ────────────────────────────────────────────────────────────────

_parakeet_model: Any = None
_vibevoice_model: Any = None
_pipeline_lock = asyncio.Semaphore(1)  # GPU-heavy; serialize.


def _get_parakeet() -> Any:
    """Lazy-load and cache Parakeet-TDT-v3 (fast ASR, word timestamps)."""
    global _parakeet_model
    if _parakeet_model is None:
        from mlx_audio.stt.utils import load

        logger.info("Loading Parakeet ASR: %s", PARAKEET_MODEL)
        _parakeet_model = load(PARAKEET_MODEL)
        logger.info("Parakeet ready")
    return _parakeet_model


def _get_vibevoice() -> Any:
    """Lazy-load and cache VibeVoice-ASR (9B; text + speaker + timestamps, single pass)."""
    global _vibevoice_model
    if _vibevoice_model is None:
        from mlx_audio.stt.utils import load

        logger.info("Loading VibeVoice-ASR (9B, first load is slow): %s", VIBEVOICE_MODEL)
        _vibevoice_model = load(VIBEVOICE_MODEL)
        logger.info("VibeVoice-ASR ready")
    return _vibevoice_model


def _vibevoice_segments_to_canonical(segments: list) -> list[dict]:
    """Map VibeVoice segment keys to canonical {start, end, speaker, text}.

    Phase 0 confirmed this build's parsed shape is {"start","end","speaker_id","text"}
    (speaker_id absent on non-speech segments); the raw JSON shape is
    {"Start","End","Speaker","Content"}. Handle all three key spellings so a minor
    version bump doesn't silently break the adapter.

    Non-speech marker segments (VibeVoice emits a standalone "[Silence]", "[Music]",
    etc. with no speaker_id) are dropped — they carry no transcript content and
    would otherwise inflate speaker_count via SPEAKER_UNKNOWN.
    """
    out: list[dict] = []
    for s in segments:
        start = s.get("start", s.get("start_time", s.get("Start", 0.0)))
        end = s.get("end", s.get("end_time", s.get("End", 0.0)))
        spk = s.get("speaker_id", s.get("Speaker"))
        text = s.get("text", s.get("Content", "")).strip()
        if spk is None and re.fullmatch(r"\[[^\]]*\]", text):
            continue
        out.append(
            {
                "start": round(float(start), 2),
                "end": round(float(end), 2),
                "speaker": f"SPEAKER_{int(spk):02d}" if spk is not None else "SPEAKER_UNKNOWN",
                "text": text,
            }
        )
    return out


def _vibevoice_untranscribed_seconds(segments: list) -> float:
    """Total seconds VibeVoice-ASR marked as speech but did not transcribe.

    On long single-speaker stretches VibeVoice sometimes stops early and emits a
    standalone ``[Speech]`` marker segment (no speaker_id) covering the remainder.
    That span carries no transcript, so the caller should warn and steer the user
    to ``transcribe_audio`` (Parakeet) for a complete non-diarized transcript.
    """
    total = 0.0
    for s in segments:
        spk = s.get("speaker_id", s.get("Speaker"))
        text = s.get("text", s.get("Content", "")).strip().lower()
        if spk is None and text in ("[speech]", "[speaker]"):
            start = float(s.get("start", s.get("start_time", s.get("Start", 0.0))))
            end = float(s.get("end", s.get("end_time", s.get("End", 0.0))))
            total += max(0.0, end - start)
    return round(total, 2)


# ── Core pipeline ──────────────────────────────────────────────────────────────


def _transcribe(audio_path: str, language: str | None) -> dict:
    """Fast ASR via Parakeet-TDT-v3. Returns {text, language, duration, segments}."""
    model = _get_parakeet()
    result = model.generate(audio_path)
    segments = [
        {"start": round(float(s.start), 2), "end": round(float(s.end), 2), "text": s.text.strip()}
        for s in getattr(result, "sentences", [])
    ]
    duration = segments[-1]["end"] if segments else 0.0
    return {
        "text": result.text.strip(),
        "language": language or "en",
        "duration": round(duration, 2),
        "segments": segments,
    }


def _diarized_transcribe(audio_path: str, num_speakers: int | None, language: str | None) -> dict:
    """Single-pass diarized transcription via VibeVoice-ASR (text + speaker + timestamps).

    num_speakers is accepted for API compatibility; VibeVoice infers speakers itself.
    Returns {text, language, duration, speaker_count, segments}.
    """
    model = _get_vibevoice()
    result = model.generate(audio=audio_path, max_tokens=8192, temperature=0.0)
    raw_segments = getattr(result, "segments", [])
    merged = _vibevoice_segments_to_canonical(raw_segments)
    speaker_count = len({s["speaker"] for s in merged}) if merged else 0
    duration = merged[-1]["end"] if merged else 0.0
    text = getattr(result, "text", "") or " ".join(s["text"] for s in merged)
    out = {
        "text": text.strip(),
        "language": language or "en",
        "duration": round(duration, 2),
        "speaker_count": speaker_count,
        "segments": merged,
    }
    dropped = _vibevoice_untranscribed_seconds(raw_segments)
    if dropped >= 5.0:
        out["warning"] = (
            f"VibeVoice-ASR left ~{dropped:.0f}s of speech untranscribed (emitted a "
            f"[Speech] placeholder, common on long single-speaker stretches). "
            f"Use transcribe_audio for a complete non-diarized transcript."
        )
        logger.warning("VibeVoice truncation: %.0fs of speech left untranscribed", dropped)
    return out


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
    """Synchronous diarized pipeline (VibeVoice single pass). Caller wraps in asyncio.to_thread."""
    t0 = time.time()
    diarized = _diarized_transcribe(audio_path, num_speakers, language)
    total_s = round(time.time() - t0, 2)

    merged = diarized["segments"]
    speaker_count = diarized["speaker_count"]

    meta = {
        "text": diarized["text"],
        "language": diarized["language"],
        "duration": diarized["duration"],
        "speaker_count": speaker_count,
        "timing": {
            "transcribe_s": total_s,  # single pass — transcription and diarization are one call
            "diarize_s": 0.0,
            "total_s": total_s,
        },
    }
    if diarized.get("warning"):
        meta["warning"] = diarized["warning"]

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
    return result


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
            "asr_model": PARAKEET_MODEL,
            "diarization_model": VIBEVOICE_MODEL,
            "parakeet_loaded": _parakeet_model is not None,
            "vibevoice_loaded": _vibevoice_model is not None,
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
        path, source_name = _resolve_audio_input(file_arg)
        if path is None:
            return JSONResponse({"error": source_name})
        async with _pipeline_lock:
            try:
                result = await asyncio.to_thread(
                    _run_pipeline, str(path), language, num_speakers, source_name
                )
                result["engine"] = "vibevoice-asr"
                return JSONResponse(result)
            except Exception as e:
                logger.error("invoke_tool transcribe_with_speakers failed: %s", e, exc_info=True)
                return JSONResponse({"error": str(e)}, status_code=500)
    elif tool_name == "transcribe_audio":
        file_arg = arguments.get("file", arguments.get("audio_path", ""))
        language = arguments.get("language")
        path, source_name = _resolve_audio_input(file_arg)
        if path is None:
            return JSONResponse({"error": source_name})
        async with _pipeline_lock:
            try:
                result = await asyncio.to_thread(_transcribe, str(path), language)
                result["engine"] = "parakeet-tdt-v3"
                return JSONResponse(result)
            except Exception as e:
                logger.error("invoke_tool transcribe_audio failed: %s", e, exc_info=True)
                return JSONResponse({"error": str(e)}, status_code=500)
    else:
        return JSONResponse({"error": f"Unknown tool: {tool_name}"}, status_code=404)


@app.get("/tools")
async def list_tools() -> JSONResponse:
    return JSONResponse(
        {
            "tools": [
                {
                    "name": "transcribe_audio",
                    "description": (
                        "Fast, accurate transcription (Parakeet-TDT-v3, word-level timestamps, "
                        "no speaker labels). Call with no arguments to auto-detect the most "
                        "recently uploaded audio file."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file": {
                                "type": "string",
                                "description": "Audio file reference: OWUI file ID, filename in uploads/, or absolute path. Omit to auto-detect most recent upload.",
                            },
                            "language": {
                                "type": "string",
                                "description": "ISO language code (e.g. 'en'). Auto-detected if omitted.",
                            },
                        },
                        "required": [],
                    },
                },
                {
                    "name": "transcribe_with_speakers",
                    "description": (
                        "Transcribe an audio file with speaker identification in a single pass "
                        "(VibeVoice-ASR): text + speaker labels + timestamps, up to ~60 min. No "
                        "separate diarization step and no HuggingFace token required. Call with "
                        "no arguments to auto-detect the most recently uploaded audio file."
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
                                "description": "Optional expected speaker count hint (VibeVoice infers speakers itself).",
                            },
                            "language": {
                                "type": "string",
                                "description": "ISO language code (e.g. 'en'). Auto-detected if omitted.",
                            },
                        },
                        "required": [],
                    },
                },
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

from mcp.server import MCPServer  # noqa: E402

mcp = MCPServer("mlx-transcribe")


@mcp.tool()
async def transcribe_audio(file: str = "", language: str | None = None) -> dict:
    """
    Fast transcription (Parakeet-TDT-v3, word-level timestamps, no speaker labels).

    Args:
        file: Audio reference. Omit to auto-detect the most recent upload; otherwise an
              OWUI file ID, a filename in uploads/, or an absolute host path.
        language: ISO language code (e.g. 'en'). Auto-detected if omitted.
    """
    path, source_name = _resolve_audio_input(file)
    if path is None:
        return {"error": source_name}
    async with _pipeline_lock:
        try:
            result = await asyncio.to_thread(_transcribe, str(path), language)
            result["engine"] = "parakeet-tdt-v3"
            result["source"] = source_name
            return result
        except Exception as e:
            logger.error("MCP transcribe_audio failed: %s", e, exc_info=True)
            return {"error": str(e)}


@mcp.tool()
async def transcribe_with_speakers(
    file: str = "",
    num_speakers: int | None = None,
    language: str | None = None,
) -> dict:
    """
    Transcribe an audio file with speaker identification in a single pass (VibeVoice-ASR).

    Produces a transcript and saves both JSON and Markdown to the workspace
    generated/transcripts/ directory. The full markdown is included in the response.

    Args:
        file: Audio file reference. Omit (or leave empty) to auto-detect the
              most recently uploaded audio file. Otherwise accepts:
              - OWUI file ID from a chat attachment (e.g., 'abc-123-def')
              - Filename in the uploads directory (e.g., 'meeting.mp3')
              - Absolute path on the host (e.g., '/Users/me/audio.wav')
        num_speakers: Optional expected speaker count hint. Auto-detected if omitted.
        language: ISO language code (e.g., 'en'). Auto-detected if omitted.

    (Diarization is single-pass via VibeVoice-ASR — no engine selection, no HF token.)

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
        "transcribe_with_speakers called: file=%r num_speakers=%r language=%r",
        file,
        num_speakers,
        language,
    )
    path, source_name = _resolve_audio_input(file)
    if path is None:
        logger.warning("file not resolved: %r — %s", file, source_name)
        return {"error": source_name}

    async with _pipeline_lock:
        try:
            result = await asyncio.to_thread(
                _run_pipeline, str(path), language, num_speakers, source_name
            )
            result["engine"] = "vibevoice-asr"
            return result
        except Exception as e:
            logger.error("MCP transcribe_with_speakers failed: %s", e, exc_info=True)
            return {"error": str(e)}


# Initialize session manager (must happen after tool definitions, before app start).
# streamable_http_app() lazily creates _session_manager; we surface it so the
# parent lifespan (_lifespan above) can run the task group.
_mcp_sub_app = mcp.streamable_http_app(host=HOST, streamable_http_path="/")
_mcp_session_manager = mcp.session_manager  # noqa: F821 — defined above
app.mount("/mcp", _mcp_sub_app)


# ── Entrypoint ─────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    logger.info("Starting mlx-transcribe on %s:%d", HOST, PORT)
    logger.info("ASR (fast): %s", PARAKEET_MODEL)
    logger.info("Diarized (single-pass): %s", VIBEVOICE_MODEL)
    logger.info("Output dir: %s", get_generated_dir("transcripts"))
    logger.info("Models load lazily on first request. No HF token required for diarization.")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
