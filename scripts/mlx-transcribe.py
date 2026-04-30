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
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse

# Workspace helpers — TASK-WORKSPACE-001
# Add the repo root to sys.path so this host-native script can import portal_mcp.core
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from portal_mcp.core.workspace import get_generated_dir, resolve_upload_path  # noqa: E402

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

# ── Model cache ────────────────────────────────────────────────────────────────

_diarization_pipeline: Any = None
_pipeline_lock = asyncio.Semaphore(1)  # GPU-heavy; serialize.


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
        from pyannote.audio import Pipeline
        import torch

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
    import subprocess, shutil

    pipeline = _get_diarization_pipeline()

    # Convert to 16kHz mono WAV to avoid MP3 chunk-boundary sample-count errors
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    wav_tmp = audio_path + "_diarize.wav"
    try:
        subprocess.run(
            [ffmpeg, "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", wav_tmp],
            check=True, capture_output=True,
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
        diarization_warning = f"Diarization unavailable ({type(e).__name__}: {e}); using single-speaker fallback"
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


def _resolve_audio_input(file: str) -> tuple[Path | None, str]:
    """Resolve a tool input to an absolute path.

    Accepts:
      - OWUI file ID (e.g., 'abc-123' or 'abc-123_meeting.mp3')
      - Filename in the uploads directory
      - Absolute path on the host filesystem

    Returns (path, source_name) or (None, error_message).
    """
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
    return None, f"upload not found: {file!r} (no match in uploads directory)"


# ── FastAPI app ────────────────────────────────────────────────────────────────

app = FastAPI(title="Portal 5 MLX Transcribe", version="1.0.0")


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": "mlx-transcribe",
            "whisper_model": WHISPER_MODEL,
            "diarization_model": DIARIZATION_MODEL,
            "diarization_loaded": _diarization_pipeline is not None,
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

from portal_mcp.mcp_server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("mlx-transcribe", host=HOST)


@mcp.tool()
async def transcribe_with_speakers(
    file: str,
    num_speakers: int | None = None,
    language: str | None = None,
) -> dict:
    """
    Transcribe an audio file with speaker diarization.

    Produces a transcript with [SPEAKER_00], [SPEAKER_01], ... labels and
    saves both JSON and Markdown to the workspace generated/transcripts/
    directory. The full markdown is included in the response.

    Args:
        file: Audio file reference. Accepts:
              - OWUI file ID from a chat attachment (e.g., 'abc-123-def')
              - Filename in the uploads directory (e.g., 'meeting.mp3')
              - Absolute path on the host (e.g., '/Users/me/audio.wav')
        num_speakers: Hint for expected speaker count. Auto-detected if omitted.
                      Recommended for files >15 min if count is known —
                      pyannote occasionally splits one speaker across long gaps.
        language: ISO language code (e.g., 'en', 'es'). Auto-detected if omitted.

    Returns:
        dict with:
          - text: full transcript (no speaker labels)
          - language, duration, speaker_count
          - segments: list of {start, end, speaker, text}
          - markdown: full speaker-labeled markdown content (ready to display)
          - json_path, md_path: workspace file paths
          - json_url, md_url: download URLs (port :8924)
          - timing: {transcribe_s, diarize_s, total_s}

        On error: {"error": "..."}
    """
    path, source_name = _resolve_audio_input(file)
    if path is None:
        return {"error": source_name}  # source_name carries the error message

    async with _pipeline_lock:
        try:
            return await asyncio.to_thread(
                _run_pipeline, str(path), language, num_speakers, source_name
            )
        except Exception as e:
            logger.error("MCP transcribe_with_speakers failed: %s", e, exc_info=True)
            return {"error": str(e)}


# Mount MCP at /mcp
app.mount("/mcp", mcp.streamable_http_app())


# ── Entrypoint ─────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    logger.info("Starting mlx-transcribe on %s:%d", HOST, PORT)
    logger.info("Whisper model: %s", WHISPER_MODEL)
    logger.info("Diarization model: %s", DIARIZATION_MODEL)
    logger.info("Output dir: %s", get_generated_dir("transcripts"))
    if not HF_TOKEN:
        logger.warning("HF_TOKEN not set — diarization will fail on first call")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
