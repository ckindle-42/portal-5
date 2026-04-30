# TASK: Diarized Transcription — MLX Primary + Docker Fallback (Revised v2)

**Task ID:** TASK-TRANSCRIBE-001
**Version target:** v6.1.0
**Priority:** Normal — adds new capability, no existing behavior changes (after workspace foundation)
**Category:** Feature / New MCP Server + New Persona
**Protected files touched:** `docs/HOWTO.md` (append-only via str_replace at named anchor)
**Estimated risk:** Low — primary path is a new host-native server (parallel to `mlx-speech.py`); fallback path is an additive tool on existing `whisper_mcp.py`. Workspace foundation already handles file bridging.
**Depends on:** **TASK-WORKSPACE-001 must be merged and verified first.** This task uses `portal_mcp.core.workspace` helpers and assumes the OWUI uploads bind mount is live.

---

## Why This Is "v2"

The original TASK-TRANSCRIBE-001 design (drafted before TASK-WORKSPACE-001) had to solve file-bridging, OpenAI auto-STT redirection, and inline speaker label encoding all at once. Those concerns evaporate with the workspace foundation in place:

- File access: `resolve_upload_path(file_id)` returns the absolute path; OWUI-dropped audio is readable directly by the MCP server.
- Auto-STT redirect: not needed. `AUDIO_STT_ENGINE` is disabled at the OWUI level (TASK-WORKSPACE-001). Audio files dropped in chat stay as attachments. The persona explicitly invokes the diarization tool.
- Output paths: `get_generated_dir("transcripts")` returns the canonical category directory; no per-MCP path conventions.

The result is a smaller, cleaner task. Both the MLX primary and Docker fallback paths use the same helper module. The tool surface is one function with one file parameter that accepts file IDs, filenames, or absolute paths — the helper handles the resolution.

## Problem Statement

Portal 5 lacks `transcribe_with_speakers` capability anywhere in the stack. The host-native `mlx-speech.py` runs Qwen3-ASR which does not emit segment timestamps (so it cannot be the basis for diarization). The Docker `whisper_mcp.py` runs `faster-whisper` which has timestamps but is CPU-bound on Apple Silicon (~4–8 min for a 10-min file).

This task adds:
1. **Apple Silicon primary path:** new host-native `scripts/mlx-transcribe.py` using mlx-whisper + pyannote.audio 3.1 on MPS. ~60–130s for a 10-min file on M4 Pro.
2. **Cross-platform fallback path:** extend Docker `whisper_mcp.py` with the same tool name (`transcribe_with_speakers`) using faster-whisper + pyannote on CPU/CUDA.
3. **New persona:** `transcriptanalyst` in `auto-documents` workspace. Detects audio attachments in chat, calls the MCP tool with the resolved file ID, formats output, optionally chains to `create_word_document`.

Both paths share output conventions (workspace-helper-managed) and tool contract.

## Decision Log

| Decision | Choice | Why |
|---|---|---|
| Transcription backend (primary) | `mlx-whisper` (large-v3-turbo) | Metal-accelerated on Apple Silicon; emits Whisper-format `segments[]` with `start/end/text`; pure Python (CUDA-portable later via faster-whisper swap) |
| Diarization backend | `pyannote.audio 3.1` on MPS | Mature, well-documented, MPS support via PyTorch; same code path as future CUDA |
| Container vs host-native | Host-native `scripts/mlx-transcribe.py` | MLX requires macOS — cannot run in Linux Docker. Mirrors `mlx-speech.py` pattern. |
| Port | 8924 | First free port after the speech/embedding/MCP block (8917=embedding, 8918=mlx-speech, 8919-8923=MCPs) |
| Tool name | `transcribe_with_speakers` | Distinct from existing `transcribe_audio`; both can coexist |
| Tool input | Single `file` parameter (id, filename, OR absolute path) | Workspace helper resolves all three forms. No client logic differentiating them. |
| Output destination | `portal_mcp.core.get_generated_dir("transcripts")` | Workspace helper owns path conventions |
| Tool response | Includes full markdown content inline | Persona can render directly without an extra tool call to read the file |
| Cross-platform fallback | Same tool name on Docker `whisper_mcp.py` | Linux/CUDA nodes get identical capability via the existing service |
| Persona | New `transcriptanalyst` in `auto-documents` workspace | Consumes attachment metadata, calls tool, formats; chains to `create_word_document` for docx |
| Workspace | None new — uses existing `auto-documents` | Avoids `WORKSPACES`/`backends.yaml` churn |
| HTTP endpoint | Keep `/v1/audio/transcribe-with-speakers` for direct uploads | Curl path for long files, batch scripts, external integrations |

## Performance Targets (M4 Pro, 10-min 2-speaker audio)

| Stage | Target | Notes |
|---|---|---|
| mlx-whisper large-v3-turbo (Metal) | 30–90s | First-segment <2s |
| pyannote 3.1 diarization (MPS) | 25–40s | ~2–3× faster on MPS than CPU |
| Merge + write JSON+MD | <1s | In-memory |
| **End-to-end** | **60–130s** | 5–7× faster than Docker fallback |

Validation: a 10-min file MUST complete in <180s on the target M4 Pro. >180s indicates a pyannote MPS device-placement issue.

## Audio Length

No hard limit. Time scales roughly linearly:

| Audio length | Expected end-to-end | Notes |
|---|---|---|
| 1 min | ~10–15s | Includes pyannote cold-start on first call |
| 10 min | 60–130s | Steady-state target |
| 35 min | ~3.5–7.5 min | Practical maximum for synchronous OWUI tool call |
| 1 hour | ~6–13 min | Operator must raise `TOOL_SERVER_REQUEST_TIMEOUT` |
| 2+ hours | ~12–26 min | Pyannote DER degrades; pass `num_speakers` if known |

For files >15 min, pass `num_speakers` if the count is known — pyannote occasionally splits one speaker into multiple IDs across long silence gaps. The `transcriptanalyst` persona surfaces suspicious counts and offers re-processing.

For long files, OWUI's MCP tool timeout becomes the constraint. Operator should set `TOOL_SERVER_REQUEST_TIMEOUT=1800` in `.env` for files up to 30 min, higher for longer.

## HuggingFace Model Gating (Pre-flight Required)

Pyannote diarization models are gated:

1. Visit `https://huggingface.co/pyannote/segmentation-3.0` and accept user conditions
2. Visit `https://huggingface.co/pyannote/speaker-diarization-3.1` and accept user conditions
3. Generate an HF read token at `https://huggingface.co/settings/tokens`
4. Add to `.env`: `HF_TOKEN=hf_...`

Without this, diarization calls return 500 on first model load.

---

## Pre-Flight Checks

Run before any code changes. STOP if any fails.

```bash
cd ~/portal-5
git status                          # clean working tree
git rev-parse --abbrev-ref HEAD     # main
git pull --ff-only

# 1. TASK-WORKSPACE-001 must be merged and verified
python3 -c "
from portal_mcp.core.workspace import get_workspace_root, get_generated_dir, resolve_upload_path
print('✅ Workspace helpers importable')
print('Root:', get_workspace_root())
print('Transcripts dir:', get_generated_dir('transcripts'))
"

# 2. OWUI uploads bind mount is live (file written from host visible inside OWUI container)
echo "transcribe-pretask probe $(date)" > "${AI_OUTPUT_DIR:-${HOME}/AI_Output}/uploads/.transcribe_probe"
docker compose -f deploy/portal-5/docker-compose.yml exec -T open-webui \
  cat /app/backend/data/uploads/.transcribe_probe | grep -q "transcribe-pretask probe" || \
  { echo "FAIL: workspace bind mount not live. Verify TASK-WORKSPACE-001 was merged correctly."; exit 1; }
rm -f "${AI_OUTPUT_DIR:-${HOME}/AI_Output}/uploads/.transcribe_probe"
echo "✅ OWUI uploads bind mount verified"

# 3. mcp-whisper container has /workspace mount (TASK-WORKSPACE-001 added it)
docker compose -f deploy/portal-5/docker-compose.yml exec -T mcp-whisper \
  test -d /workspace || \
  { echo "FAIL: mcp-whisper missing /workspace mount. Re-verify TASK-WORKSPACE-001."; exit 1; }
echo "✅ mcp-whisper /workspace mount verified"

# 4. AUDIO_STT_ENGINE is empty (TASK-WORKSPACE-001 disabled it)
docker compose -f deploy/portal-5/docker-compose.yml exec -T open-webui \
  sh -c 'test -z "${AUDIO_STT_ENGINE}"' || \
  { echo "FAIL: AUDIO_STT_ENGINE is set. Should be empty per TASK-WORKSPACE-001."; exit 1; }
echo "✅ Auto-STT correctly disabled"

# 5. Workspace consistency baseline
python3 -c "
import yaml
from portal_pipeline.router.workspaces import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe_ids = set(WORKSPACES.keys())
yaml_ids = set(cfg['workspace_routing'].keys())
assert pipe_ids == yaml_ids, f'Mismatch: pipe={pipe_ids-yaml_ids} yaml={yaml_ids-pipe_ids}'
print('✅ Workspace IDs consistent (baseline)')
"

# 6. Tests + lint baseline
pytest tests/unit/ -q --tb=no
ruff check . && ruff format --check .

# 7. HF_TOKEN gating
test -n "${HF_TOKEN:-}" && [[ "${HF_TOKEN}" =~ ^hf_ ]] || \
  { echo "FAIL: HF_TOKEN not set or invalid. See §HuggingFace Model Gating."; exit 1; }

# 8. Pyannote license acceptance verified
for model in pyannote/speaker-diarization-3.1 pyannote/segmentation-3.0; do
  curl -sf -o /dev/null \
    -H "Authorization: Bearer ${HF_TOKEN}" \
    "https://huggingface.co/api/models/${model}" || \
    { echo "FAIL: ${model} not accessible. Accept license at https://huggingface.co/${model}"; exit 1; }
done
echo "✅ Pyannote models accessible"

# 9. Port 8924 free
lsof -nP -iTCP:8924 -sTCP:LISTEN && \
  { echo "FAIL: Port 8924 in use"; exit 1; } || echo "✅ Port 8924 free"

# 10. Disk space (~2 GB for whisper-large-v3-turbo + pyannote)
df -h ~ | awk 'NR==2 {print $4}' | grep -qE '^[1-9][0-9]?G|^[1-9][0-9]+G|^[0-9]+T' || \
  { echo "FAIL: Less than 1 GB free in home dir"; exit 1; }
```

---

## Phase 0 — Branch & Test Fixture

```bash
git checkout -b feat/transcribe-diarize
mkdir -p tests/fixtures/audio
```

Create a 10-second 2-speaker fixture:

```bash
brew list espeak >/dev/null 2>&1 || brew install espeak
espeak -s 175 -p 30 "Hello, this is the first speaker testing the transcription system." -w /tmp/spk1.wav
espeak -s 175 -p 70 "And I am the second speaker, responding with a different voice tone." -w /tmp/spk2.wav

# Concatenate via ffmpeg (sox optional)
ffmpeg -y -i "concat:/tmp/spk1.wav|/tmp/spk2.wav" -c copy tests/fixtures/audio/two_speaker_10s.wav 2>/dev/null
test -f tests/fixtures/audio/two_speaker_10s.wav && echo "✅ Fixture created"
```

If `espeak` is unavailable, drop a 10-second real recording at `tests/fixtures/audio/two_speaker_10s.wav` before proceeding. Tests check for existence and skip cleanly if missing.

---

## Phase 1 — Apple Silicon Primary: `scripts/mlx-transcribe.py`

### File 1: `scripts/mlx-transcribe.py` (NEW)

```python
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
        pipeline = Pipeline.from_pretrained(DIARIZATION_MODEL, use_auth_token=HF_TOKEN)
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
    """Run pyannote diarization. Returns sorted list of {start, end, speaker}."""
    pipeline = _get_diarization_pipeline()
    kwargs: dict[str, Any] = {}
    if num_speakers is not None:
        kwargs["num_speakers"] = num_speakers
    diarization = pipeline(audio_path, **kwargs)
    turns = [
        {
            "start": round(turn.start, 2),
            "end": round(turn.end, 2),
            "speaker": speaker,
        }
        for turn, _, speaker in diarization.itertracks(yield_label=True)
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
    speaker_turns = _diarize(audio_path, num_speakers)
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

    return {
        **meta,
        "segments": merged,
        "markdown": markdown,
        "json_path": str(json_path),
        "md_path": str(md_path),
        "json_url": f"http://host.docker.internal:{PORT}/files/{json_path.name}",
        "md_url": f"http://host.docker.internal:{PORT}/files/{md_path.name}",
    }


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


@app.get("/files/{filename}")
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
```

**Verification:**
```bash
ruff check scripts/mlx-transcribe.py
ruff format --check scripts/mlx-transcribe.py
python3 -c "import ast; ast.parse(open('scripts/mlx-transcribe.py').read()); print('Syntax OK')"
# Confirm workspace helper imports cleanly:
python3 -c "
import sys; sys.path.insert(0, '.')
from portal_mcp.core.workspace import resolve_upload_path, get_generated_dir
print('Workspace helpers reachable from script context')
"
```

### File 2: `pyproject.toml` (MODIFY — add MLX-only deps)

**Find the `apple-silicon` extra:**
```
apple-silicon = [
    # MLX dual-server: mlx-lm for text-only models, mlx-vlm for VLM models.
    # mlx-lm must be <0.31 to keep qwen3_next support (moved to mlx_vlm in 0.31+).
    "mlx-lm<0.31",
    "mlx-vlm>=0.1.0",
    # MLX Speech: unified TTS (Kokoro + Qwen3-TTS) + ASR (Qwen3-ASR) on Apple Silicon
    "mlx-audio>=0.3.0",
    # Kokoro TTS phonemizer dependencies (required by mlx-audio Kokoro backend)
    "misaki>=0.1.0",
    "num2words>=0.5.0",
    "spacy>=3.5.0",
    "phonemizer>=3.2.0",
]
```

**Replace with:**
```
apple-silicon = [
    # MLX dual-server: mlx-lm for text-only models, mlx-vlm for VLM models.
    # mlx-lm must be <0.31 to keep qwen3_next support (moved to mlx_vlm in 0.31+).
    "mlx-lm<0.31",
    "mlx-vlm>=0.1.0",
    # MLX Speech: unified TTS (Kokoro + Qwen3-TTS) + ASR (Qwen3-ASR) on Apple Silicon
    "mlx-audio>=0.3.0",
    # MLX Transcribe: diarized transcription on Apple Silicon (TASK-TRANSCRIBE-001)
    # mlx-whisper emits Whisper-format segments with timestamps (Metal-accelerated)
    # pyannote.audio runs on MPS via PyTorch; HF token required for gated models
    "mlx-whisper>=0.4.0",
    "pyannote.audio>=3.1.0",
    "torch>=2.1.0",
    "torchaudio>=2.1.0",
    # Kokoro TTS phonemizer dependencies (required by mlx-audio Kokoro backend)
    "misaki>=0.1.0",
    "num2words>=0.5.0",
    "spacy>=3.5.0",
    "phonemizer>=3.2.0",
]
```

**Verification:**
```bash
uv pip install -e ".[apple-silicon,dev]" 2>&1 | tail -5
python3 -c "import mlx_whisper; print('mlx-whisper OK')"
python3 -c "from pyannote.audio import Pipeline; print('pyannote.audio OK')"
python3 -c "import torch; print('MPS:', torch.backends.mps.is_available())"
```

### File 3: `launch.sh` (MODIFY — add start-transcribe / stop-transcribe)

Three insertions, mirroring the `start-speech` / `stop-speech` pattern.

**Change 3a — Status block.** Locate the existing speech status check (search for `/tmp/portal-mlx-speech.pid` near line 730). Add immediately after the speech block ends:

```bash
        # MLX Transcribe service status
        if [ -f /tmp/portal-mlx-transcribe.pid ] && kill -0 "$(cat /tmp/portal-mlx-transcribe.pid)" 2>/dev/null; then
            printf "    ✅  %-28s %s\n" "MLX Transcribe" "running (PID $(cat /tmp/portal-mlx-transcribe.pid), :8924)"
        elif [ -f scripts/mlx-transcribe.py ]; then
            printf "    ❌  %-28s %s\n" "MLX Transcribe" "installed but not running — ./launch.sh start-transcribe"
        fi
```

**Change 3b — Command blocks.** Locate `start-speech)` (around line 3230). Add `start-transcribe)` and `stop-transcribe)` blocks after the matching `;;` of `stop-speech)`:

```bash
  start-transcribe)
    PORTAL_ROOT="${PORTAL_ROOT:-$(pwd)}"
    mkdir -p "$HOME/.portal5/logs"
    PID_FILE="/tmp/portal-mlx-transcribe.pid"
    LOG_FILE="$HOME/.portal5/logs/mlx-transcribe.log"
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "MLX Transcribe already running (PID $(cat "$PID_FILE"))"
      exit 0
    fi
    if [ ! -f "$PORTAL_ROOT/scripts/mlx-transcribe.py" ]; then
      echo "❌ scripts/mlx-transcribe.py not found"
      exit 1
    fi
    if [ -z "${HF_TOKEN:-}" ]; then
      echo "⚠️  HF_TOKEN not set — diarization will fail on first call."
      echo "   Set in .env after accepting pyannote model licenses on HuggingFace."
    fi
    echo "Starting MLX Transcribe (port 8924)..."
    nohup python3 "$PORTAL_ROOT/scripts/mlx-transcribe.py" >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 2
    if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "✅ MLX Transcribe started (PID $(cat "$PID_FILE"))"
      echo "   Log: $LOG_FILE"
    else
      echo "❌ Failed to start. Check $LOG_FILE"
      rm -f "$PID_FILE"
      exit 1
    fi
    ;;

  stop-transcribe)
    PID_FILE="/tmp/portal-mlx-transcribe.pid"
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      kill "$(cat "$PID_FILE")" 2>/dev/null || true
      rm -f "$PID_FILE"
      echo "MLX Transcribe stopped"
    else
      echo "MLX Transcribe not running"
      rm -f "$PID_FILE"
    fi
    ;;
```

**Change 3c — Help text & usage line.** Find `Usage: ./launch.sh [up|down|...|stop-speech|...]` and append `|start-transcribe|stop-transcribe`. Add help lines after the speech help:

```
    echo "  start-transcribe      Start MLX Transcribe server (mlx-whisper + pyannote diarization, :8924)"
    echo "  stop-transcribe       Stop MLX Transcribe server"
```

**Change 3d — Model pull list.** Find existing Qwen3-ASR pull entry (around line 3562):

**Find:**
```
        "mlx-community/Qwen3-ASR-1.7B-8bit"                    # ~0.8GB — speech recognition (replaces faster-whisper)
```

**Add line after it:**
```
        "mlx-community/whisper-large-v3-turbo"                 # ~1.5GB — Whisper transcription with timestamps (TASK-TRANSCRIBE-001)
```

**Verification:**
```bash
bash -n launch.sh && echo "✅ launch.sh syntax OK"
./launch.sh 2>&1 | grep -E "start-transcribe|stop-transcribe" | head -5
```

---

## Phase 2 — Cross-Platform Fallback: Extend `whisper_mcp.py`

Adds the same `transcribe_with_speakers` tool name to the existing Docker container so future Linux/CUDA nodes have the capability via the existing fallback path.

### File 4: `Dockerfile.mcp` (MODIFY — add pyannote.audio)

Locate the audio dependency block (lines 42–48):

**old_str:**
```
# Audio / speech — kokoro-onnx is zero-setup, fish-speech optional
RUN pip install --no-cache-dir \
    "faster-whisper>=1.0.0" \
    "kokoro-onnx>=0.4.0" \
    "soundfile>=0.12.1" \
    "numpy>=1.24.0" \
    "huggingface_hub>=0.20.0"
```

**new_str:**
```
# Audio / speech — kokoro-onnx is zero-setup, fish-speech optional
# pyannote.audio added for transcribe_with_speakers (TASK-TRANSCRIBE-001)
RUN pip install --no-cache-dir \
    "faster-whisper>=1.0.0" \
    "kokoro-onnx>=0.4.0" \
    "soundfile>=0.12.1" \
    "numpy>=1.24.0" \
    "huggingface_hub>=0.20.0" \
    "pyannote.audio>=3.1.0"
```

`torch` and `torchaudio` are already installed by the music block (lines 54–58).

### File 5: `portal_mcp/generation/whisper_mcp.py` (MODIFY — add transcribe_with_speakers)

Find the section just before `if __name__ == "__main__":` (around lines 165–172):

**old_str:**
```python
    return {
        "text": " ".join(full_text),
        "language": info.language,
        "duration": round(info.duration, 2),
        "segments": segment_list,
    }


if __name__ == "__main__":
```

**new_str:**
```python
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
        from pyannote.audio import Pipeline
        import torch

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
```

**Verification:**
```bash
ruff check portal_mcp/generation/whisper_mcp.py
python3 -c "import ast; ast.parse(open('portal_mcp/generation/whisper_mcp.py').read()); print('Syntax OK')"
```

### File 6: `deploy/portal-5/docker-compose.yml` (no change required)

`mcp-whisper` already has `HF_TOKEN` env (existing line) and `/workspace` mount (added by TASK-WORKSPACE-001). No further compose changes needed.

---

## Phase 3 — MCP Tool Registration

### File 7: `imports/openwebui/tools/portal_mlx_transcribe.json` (NEW)

```json
{
  "id": "portal_mlx_transcribe",
  "name": "Portal MLX Transcribe",
  "type": "mcp",
  "meta": {
    "description": "Diarized transcription with speaker labels (Apple Silicon MLX-accelerated). Drop in an audio file in chat, the persona will transcribe with speaker labels.",
    "manifest": {
      "type": "mcp",
      "url": "http://host.docker.internal:8924/mcp"
    }
  },
  "settings": {
    "api_key": ""
  }
}
```

### File 8: `imports/openwebui/mcp-servers.json` (MODIFY)

**old_str:**
```
    { "name": "Portal Whisper",        "id": "portal_whisper",   "url": "http://host.docker.internal:8915/mcp", "api_key": "" },
    { "name": "Portal TTS",            "id": "portal_tts",       "url": "http://host.docker.internal:8916/mcp", "api_key": "" },
```

**new_str:**
```
    { "name": "Portal Whisper",        "id": "portal_whisper",   "url": "http://host.docker.internal:8915/mcp", "api_key": "" },
    { "name": "Portal MLX Transcribe", "id": "portal_mlx_transcribe", "url": "http://host.docker.internal:8924/mcp", "api_key": "" },
    { "name": "Portal TTS",            "id": "portal_tts",       "url": "http://host.docker.internal:8916/mcp", "api_key": "" },
```

---

## Phase 4 — New Persona: `transcriptanalyst`

### File 9: `config/personas/transcriptanalyst.yaml` (NEW)

```yaml
name: Transcript Analyst
slug: transcriptanalyst
category: writing
source: portal-5
workspace_model: auto-documents
# phi-4-8bit (MLX primary in auto-documents) handles structured doc generation well.
# Persona detects audio attachments, calls transcribe_with_speakers with the file ID,
# and produces formatted output. Chains to create_word_document for .docx export.
system_prompt: |
  You are a transcript analyst. Your job: turn audio recordings into useful
  documents. You handle the full flow — recognizing audio attachments, calling
  the transcription tool, formatting the result.

  AUDIO ATTACHMENT DETECTION:
  When the user message includes an attached audio file (mp3, wav, m4a, ogg,
  flac), you'll see attachment metadata in the message context. The file is
  reachable by ID or filename. To transcribe:

    transcribe_with_speakers(
      file="<file_id_or_filename>",
      num_speakers=<int if specified by user>,
      language=<ISO code if specified, else omit for auto>
    )

  The tool returns:
    - text:           full transcript without speaker labels
    - markdown:       speaker-labeled transcript ready to display
    - segments:       structured per-turn data
    - speaker_count:  detected count
    - duration:       audio length in seconds
    - timing:         processing time
    - json_path, md_path: workspace file paths
    - error:          if anything failed

  WORKFLOW:
  1. Recognize the audio attachment. If the user specified a speaker count
     (e.g., "transcribe with 2 speakers", "this is a 3-person interview"),
     pass num_speakers=N. Otherwise omit it (pyannote auto-detects).
  2. If duration of attached file appears >15 minutes AND the user hasn't
     specified speaker count: briefly ask before processing — "This is
     {duration}-min audio. How many speakers, or shall I auto-detect?"
     Long files occasionally have one speaker split into multiple IDs;
     constraining the count helps.
  3. Call transcribe_with_speakers. Wait for return.
  4. If result has 'error': surface it clearly to the user.
  5. If successful: by default, display the 'markdown' field directly — it's
     ready for chat rendering with speaker labels and timestamps.
  6. Then ask: do you want this as-is, summarized with action items, or as
     a Word document? Adapt to the user's actual ask.

  WORD DOCUMENT FLOW:
  When the user asks for .docx output, call create_word_document with:
    title="Transcript: <source_name from result>"
    content=<the markdown field from the result>
  The documents MCP renders markdown into a styled .docx.

  HARD CONSTRAINTS (never violate):
  - Do not invent transcript content. If a passage is [inaudible] or
    [unclear], preserve that marker.
  - Do not assign real names to SPEAKER_00 / SPEAKER_01 unless the user
    explicitly tells you who each speaker is.
  - Preserve direct quotes exactly when summarizing — paraphrase context,
    not the speakers' actual words within quote marks.
  - If speaker_count seems wrong (e.g., user said 2 but tool detected 5,
    or vice versa), surface it: "Detected {N} speakers — does that match
    what you expected? I can re-run with num_speakers=<your_count>."
  - If the user types a path or filename without dropping a file, try
    that as the file argument — the tool resolves filenames in the uploads
    directory and absolute paths on the host.

  COMMON USER ASKS:
  - "Transcribe this" → call tool, display markdown, ask about format
  - "Transcribe with 2 speakers" → call tool with num_speakers=2, display
  - "Summarize the meeting" → transcribe first, then summarize from markdown
  - "Make me a Word doc" → transcribe, then create_word_document
  - "Who said X?" → search the transcript markdown, quote the speaker exactly
  - "What's the action items?" → extract from markdown, list with timestamps

  PRESENTATION:
  Keep your conversational replies short. The transcript itself is the
  content — don't preface or summarize it unless asked. After displaying,
  one short prompt about next steps is enough.

workspace:
  enabled: true
  description: Transcript Analyst — drop audio, get diarized transcript or Word doc
  suggested_model: dolphin-llama3:8b
tags:
  - writing
  - documentation
  - transcription
  - meetings
  - audio
```

### File 10: `portal_pipeline/router/workspaces.py` (MODIFY — add tool to auto-documents)

**old_str:**
```python
    "auto-documents": {
        "name": "📄 Portal Document Builder",
        "description": "Create Word, Excel, PowerPoint via MCP tools",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "mlx-community/phi-4-8bit",
        "tools": [
            "create_word_document",
            "create_excel",
            "create_powerpoint",
            "read_word_document",
            "read_excel",
            "read_powerpoint",
            "read_pdf",
        ],
    },
```

**new_str:**
```python
    "auto-documents": {
        "name": "📄 Portal Document Builder",
        "description": "Create Word, Excel, PowerPoint via MCP tools; diarized transcription",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "mlx-community/phi-4-8bit",
        "tools": [
            "create_word_document",
            "create_excel",
            "create_powerpoint",
            "read_word_document",
            "read_excel",
            "read_powerpoint",
            "read_pdf",
            "transcribe_with_speakers",
        ],
    },
```

### File 11: `config/routing_descriptions.json` (MODIFY)

**old_str:**
```
  "auto-documents": "Creating Word documents, Excel spreadsheets, PowerPoint presentations using MCP tool servers.",
```

**new_str:**
```
  "auto-documents": "Creating Word documents, Excel spreadsheets, PowerPoint presentations, and diarized audio transcripts (with speaker labels) using MCP tool servers.",
```

### File 12: `config/routing_examples.json` (MODIFY)

Append two new examples to the `examples` array:

```json
    {"message": "transcribe this meeting recording with speaker labels", "workspace": "auto-documents", "confidence": 0.94},
    {"message": "who said what in this audio file?", "workspace": "auto-documents", "confidence": 0.92},
```

---

## Phase 5 — Acceptance Tests

### File 13: `tests/portal5_acceptance_v6.py` (MODIFY — extend S9)

Locate the S9 function (around line 2741). After the existing S9-02 block (around line 2772), add:

```python
        # S9-03: MLX Transcribe service health
        t0 = time.time()
        code, data = await _get(f"http://localhost:8924/health", timeout=5)
        record(
            sec,
            "S9-03",
            "MLX Transcribe health",
            "PASS" if code == 200 else "INFO",
            f"HTTP {code}" if code == 200 else "not running (start with ./launch.sh start-transcribe)",
            t0=t0,
        )

        # S9-04: MLX Transcribe end-to-end with fixture (only if service is up)
        if code == 200:
            t0 = time.time()
            fixture = Path("tests/fixtures/audio/two_speaker_10s.wav")
            if not fixture.exists():
                record(sec, "S9-04", "MLX Transcribe diarization", "INFO", "fixture missing", t0=t0)
            else:
                try:
                    async with httpx.AsyncClient(timeout=300.0) as client:
                        with open(fixture, "rb") as f:
                            files = {"file": (fixture.name, f, "audio/wav")}
                            r = await client.post(
                                "http://localhost:8924/v1/audio/transcribe-with-speakers",
                                files=files,
                                data={"num_speakers": "2"},
                            )
                    if r.status_code == 200:
                        result = r.json()
                        spk_count = result.get("speaker_count", 0)
                        total_s = result.get("timing", {}).get("total_s", 0)
                        if spk_count >= 2 and total_s < 60:
                            record(sec, "S9-04", "MLX Transcribe diarization",
                                   "PASS", f"{spk_count} speakers in {total_s:.1f}s", t0=t0)
                        elif spk_count >= 2:
                            record(sec, "S9-04", "MLX Transcribe diarization",
                                   "WARN", f"{spk_count} speakers but slow ({total_s:.1f}s)", t0=t0)
                        else:
                            record(sec, "S9-04", "MLX Transcribe diarization",
                                   "WARN", f"only {spk_count} speaker(s) detected", t0=t0)
                    else:
                        record(sec, "S9-04", "MLX Transcribe diarization",
                               "FAIL", f"HTTP {r.status_code}: {r.text[:100]}", t0=t0)
                except Exception as e:
                    record(sec, "S9-04", "MLX Transcribe diarization", "FAIL", str(e)[:100], t0=t0)

        # S9-05: MCP tool resolves OWUI-style upload (workspace integration)
        if code == 200:
            t0 = time.time()
            fixture = Path("tests/fixtures/audio/two_speaker_10s.wav")
            if not fixture.exists():
                record(sec, "S9-05", "Workspace upload resolution", "INFO", "fixture missing", t0=t0)
            else:
                # Place fixture in workspace uploads as if OWUI dropped it
                from portal_mcp.core.workspace import get_uploads_dir
                uploads = get_uploads_dir()
                test_id = f"test_{uuid.uuid4().hex[:8]}"
                target = uploads / f"{test_id}_two_speaker.wav"
                target.write_bytes(fixture.read_bytes())
                try:
                    # Call MCP tool with file ID (no full path)
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        r = await client.post(
                            "http://localhost:8924/mcp/tools/transcribe_with_speakers",
                            json={"file": test_id, "num_speakers": 2},
                        )
                    if r.status_code == 200 and "error" not in r.text:
                        record(sec, "S9-05", "Workspace upload resolution",
                               "PASS", "file ID resolved", t0=t0)
                    else:
                        record(sec, "S9-05", "Workspace upload resolution",
                               "WARN", f"HTTP {r.status_code}", t0=t0)
                except Exception as e:
                    record(sec, "S9-05", "Workspace upload resolution",
                           "FAIL", str(e)[:100], t0=t0)
                finally:
                    with contextlib.suppress(Exception):
                        target.unlink()
```

### File 14: `tests/unit/test_transcribe_diarize.py` (NEW)

Pure-Python unit tests for the merge / format / resolve logic.

```python
"""Unit tests for transcribe_with_speakers logic (TASK-TRANSCRIBE-001).

Covers deterministic in-memory parts: merge, markdown formatting, file
resolution. Model loading and audio I/O are out of scope (covered by
acceptance tests S9-03 / S9-04 / S9-05 with fixtures).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "mlx-transcribe.py"


@pytest.fixture(scope="module")
def transcribe_module():
    """Load mlx-transcribe.py with heavy deps stubbed."""
    # Stub imports that pull MLX/PyTorch
    sys.modules.setdefault("mlx_whisper", type(sys)("mlx_whisper"))
    sys.modules.setdefault("pyannote", type(sys)("pyannote"))
    sys.modules.setdefault("pyannote.audio", type(sys)("pyannote.audio"))
    sys.modules.setdefault("torch", type(sys)("torch"))

    spec = importlib.util.spec_from_file_location("mlx_transcribe", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_merge_no_diarization_falls_back_to_single_speaker(transcribe_module):
    segments = [
        {"start": 0.0, "end": 2.0, "text": "Hello"},
        {"start": 2.0, "end": 4.0, "text": "World"},
    ]
    merged = transcribe_module._merge(segments, [])
    assert len(merged) == 2
    assert all(s["speaker"] == "SPEAKER_00" for s in merged)


def test_merge_assigns_max_overlap_speaker(transcribe_module):
    segments = [
        {"start": 0.0, "end": 5.0, "text": "First turn"},
        {"start": 5.0, "end": 10.0, "text": "Second turn"},
    ]
    turns = [
        {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
        {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01"},
    ]
    merged = transcribe_module._merge(segments, turns)
    assert merged[0]["speaker"] == "SPEAKER_00"
    assert merged[1]["speaker"] == "SPEAKER_01"


def test_merge_collapses_adjacent_same_speaker(transcribe_module):
    segments = [
        {"start": 0.0, "end": 2.0, "text": "Hello"},
        {"start": 2.0, "end": 4.0, "text": "world"},
        {"start": 4.0, "end": 6.0, "text": "again"},
    ]
    turns = [{"start": 0.0, "end": 6.0, "speaker": "SPEAKER_00"}]
    merged = transcribe_module._merge(segments, turns)
    assert len(merged) == 1
    assert merged[0]["text"] == "Hello world again"


def test_merge_handles_partial_overlap(transcribe_module):
    segments = [{"start": 0.0, "end": 4.0, "text": "mostly speaker 0"}]
    turns = [
        {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00"},
        {"start": 3.0, "end": 5.0, "speaker": "SPEAKER_01"},
    ]
    merged = transcribe_module._merge(segments, turns)
    assert merged[0]["speaker"] == "SPEAKER_00"


def test_format_markdown_includes_metadata(transcribe_module):
    merged = [
        {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00", "text": "Hello there"},
        {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01", "text": "General Kenobi"},
    ]
    meta = {"duration": 10.0, "language": "en", "speaker_count": 2}
    md = transcribe_module._format_markdown(merged, meta, "audio.wav")
    assert "Transcript: audio.wav" in md
    assert "**Duration**: 10.0s" in md
    assert "**Speakers**: 2" in md
    assert "**SPEAKER_00**" in md
    assert "**SPEAKER_01**" in md


def test_format_markdown_timestamps(transcribe_module):
    merged = [{"start": 65.0, "end": 70.0, "speaker": "SPEAKER_00", "text": "After a minute"}]
    meta = {"duration": 70.0, "language": "en", "speaker_count": 1}
    md = transcribe_module._format_markdown(merged, meta)
    assert "[01:05]" in md


def test_resolve_audio_input_absolute_path(transcribe_module, tmp_path):
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"fake audio")
    path, name = transcribe_module._resolve_audio_input(str(audio))
    assert path is not None
    assert path == audio.resolve()
    assert name == "test.wav"


def test_resolve_audio_input_missing_path(transcribe_module):
    path, err = transcribe_module._resolve_audio_input("/nonexistent/foo.wav")
    assert path is None
    assert "not found" in err
```

**Verification:**
```bash
pytest tests/unit/test_transcribe_diarize.py -v
# Expected: 8 passed
```

---

## Phase 6 — Documentation

### File 15: `docs/HOWTO.md` (MODIFY — protected, append-only via str_replace)

Find the speech section's ending. Insert this section after it (the agent should grep for `Verify: curl http://localhost:8918/health` or similar to locate the precise anchor).

**Insert this section:**

```markdown
## Diarized Transcription (Speaker-Labeled Transcripts)

**What:** Drop an audio file in OWUI chat, get back a transcript with speaker labels (SPEAKER_00, SPEAKER_01, ...). Outputs JSON + Markdown to the shared workspace at `~/AI_Output/generated/transcripts/`.

**Pre-flight (one-time):**

1. Visit `https://huggingface.co/pyannote/segmentation-3.0` — accept user conditions
2. Visit `https://huggingface.co/pyannote/speaker-diarization-3.1` — accept user conditions
3. Generate read token at `https://huggingface.co/settings/tokens`
4. Add to `.env`: `HF_TOKEN=hf_...`

**Start the service (Apple Silicon primary):**
```bash
./launch.sh start-transcribe
# First run downloads ~1.5 GB whisper-large-v3-turbo + ~30 MB pyannote
```

**Workflow A — Drop in chat (recommended for files <15 min):**

1. Open WebUI → select `Transcript Analyst` persona (Documents workspace)
2. Drag-drop an audio file (mp3, wav, m4a, ogg, flac) into the chat input
3. Type instructions, e.g., "transcribe with 2 speakers" or "summarize this meeting"
4. Hit submit
5. Persona detects the attachment, calls the transcription tool, displays the labeled transcript

The `transcriptanalyst` persona accepts:
- `"transcribe this"` — auto-detects speaker count
- `"transcribe with N speakers"` — passes `num_speakers=N` to constrain pyannote
- `"summarize this meeting"` — transcribe first, then produce a summary with decisions/action items
- `"make me a Word doc"` — transcribe, then chain to `create_word_document` for .docx output

**Workflow B — Long files (>15 min) or batch processing:**

For files where OWUI's tool timeout might bite (or for scripted use), call the HTTP endpoint directly:
```bash
curl -X POST http://localhost:8924/v1/audio/transcribe-with-speakers \
  -F "file=@long_meeting.mp3" \
  -F "num_speakers=3" | jq -r '.md_path'
# /Users/you/AI_Output/generated/transcripts/transcript_a3f2b1c4d5e6.md
```

Then in OWUI, ask the persona to "format the transcript at <md_path>".

**Tool timeout for long files:** OWUI's default MCP tool timeout is shorter than processing time for files >5 min. To raise it:
```bash
echo "TOOL_SERVER_REQUEST_TIMEOUT=1800" >> .env  # 30 minutes
./launch.sh restart open-webui
```

**Performance (M4 Pro, 10-min 2-speaker audio):** ~60–130s end-to-end. Versus Docker fallback path: ~4–8 min (CPU-bound). Time scales roughly linearly with audio length.

**Speaker count drift:** for files >15 min, pyannote can occasionally split one speaker into multiple IDs across long silences. If the result has more speakers than you expected, ask the persona to re-run with `num_speakers=<your_count>` to constrain.

**Verify:**
```bash
curl http://localhost:8924/health
# {"status":"ok","service":"mlx-transcribe","whisper_model":"...","diarization_loaded":false}
# (diarization_loaded becomes true after first call)
```

**Output files:**
- `~/AI_Output/generated/transcripts/transcript_<id>.json` — structured data
- `~/AI_Output/generated/transcripts/transcript_<id>.md` — speaker-labeled markdown

Both also downloadable via `http://localhost:8924/files/<filename>`.

---
```

### File 16: `KNOWN_LIMITATIONS.md` (MODIFY — append)

```markdown
## Diarized Transcription (TASK-TRANSCRIBE-001)

- **Pyannote model gating.** Diarization models (`pyannote/segmentation-3.0`, `pyannote/speaker-diarization-3.1`) require accepting their HuggingFace user agreements before download. Without `HF_TOKEN` in `.env` and licenses accepted, the service starts but diarization calls return 500. Upstream licensing, not a Portal 5 limitation.
- **Overlapping speech.** Pyannote 3.1 under-performs when multiple speakers talk simultaneously. The merge logic assigns each transcribed segment to a single speaker by maximum overlap; rapid alternation may surface as one merged turn.
- **Speaker count drift on long recordings.** For recordings >15–30 min, pyannote may register the same speaker as two separate IDs after long silence gaps. Pass `num_speakers=N` if the count is known. The `transcriptanalyst` persona surfaces suspicious counts and offers re-processing.
- **No hard length limit, but practical scaling.** 10 min ≈ 60–130s; 35 min ≈ 3.5–7.5 min; 1 hour ≈ 6–13 min. Memory comfortable up to multi-hour files on 64 GB.
- **OWUI tool-call timeout for long files.** OWUI's default MCP timeout is shorter than processing time for files >5 min. Operator must raise `TOOL_SERVER_REQUEST_TIMEOUT` (e.g., 1800s) or use the direct curl endpoint at `:8924`.
- **First-call latency.** Pyannote pipeline takes ~10–15s to load on first call. `/health` returns `diarization_loaded: false` until then. Subsequent calls reuse the loaded pipeline.
- **MLX path is macOS-only.** `scripts/mlx-transcribe.py` requires Apple Silicon. The Docker `whisper_mcp.py` fallback (faster-whisper + pyannote on CPU/CUDA) is the cross-platform alternative; significantly slower on Apple Silicon (CPU-bound).
- **First-run model download.** Whisper-large-v3-turbo (~1.5 GB) + pyannote weights (~36 MB) download on first transcription. Subsequent calls use cached weights in `~/.cache/huggingface/`.
```

### File 17: `P5_ROADMAP.md` (MODIFY — add row)

```
| P5-FUT-014 | P3 | Diarized transcription (speaker-labeled) | DONE | TASK-TRANSCRIBE-001 (built on TASK-WORKSPACE-001 foundation). Host-native `scripts/mlx-transcribe.py` (mlx-whisper + pyannote.audio on MPS) primary on Apple Silicon, port 8924. Docker `whisper_mcp.py` extended with same `transcribe_with_speakers` tool for cross-platform fallback. New `transcriptanalyst` persona in `auto-documents` workspace handles full flow: detects audio attachments, calls tool, formats output, chains to `create_word_document` for docx. Uses `portal_mcp.core.workspace` helpers for file resolution. HF_TOKEN required (gated pyannote models). |
```

### File 18: `CHANGELOG.md` (MODIFY)

Add to the `[6.1.0]` block (which TASK-WORKSPACE-001 created):

```markdown
### Added (continued from TASK-WORKSPACE-001)
- **Diarized transcription** (TASK-TRANSCRIBE-001):
  - New host-native MCP server `scripts/mlx-transcribe.py` on port 8924 (mlx-whisper large-v3-turbo + pyannote.audio 3.1 on MPS). Apple Silicon primary path.
  - `whisper_mcp.py` extended with `transcribe_with_speakers` tool (faster-whisper + pyannote on CPU/CUDA) — cross-platform fallback.
  - New persona `transcriptanalyst` in `auto-documents` workspace; detects audio attachments, calls tool, displays markdown, chains to `create_word_document` for docx output.
  - New launch commands: `./launch.sh start-transcribe` / `stop-transcribe`.
  - Output: JSON + Markdown sidecar in workspace at `${AI_OUTPUT_DIR}/generated/transcripts/`. Both downloadable via `:8924/files/<name>`.
  - Performance: ~60–130s for 10-min 2-speaker audio on M4 Pro (vs ~4–8 min on Docker fallback path).
  - Tool surface: `transcribe_with_speakers(file, num_speakers, language)` — `file` accepts OWUI file ID, filename in uploads/, or absolute path (resolved via workspace helper).
  - Pyannote models gated; requires accepting HuggingFace licenses + `HF_TOKEN` in `.env`.

### Models pulled (via `./launch.sh pull-mlx-models`)
- `mlx-community/whisper-large-v3-turbo` (~1.5 GB)
- `pyannote/speaker-diarization-3.1` (~30 MB, gated)
- `pyannote/segmentation-3.0` (~6 MB, gated)
```

---

## Phase 7 — Final Verification

```bash
# 1. Workspace consistency (CLAUDE.md Rule 6) — should remain consistent
python3 -c "
import yaml
from portal_pipeline.router.workspaces import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe_ids = set(WORKSPACES.keys())
yaml_ids = set(cfg['workspace_routing'].keys())
assert pipe_ids == yaml_ids, f'Mismatch: pipe={pipe_ids-yaml_ids} yaml={yaml_ids-pipe_ids}'
print('✅ Workspace IDs consistent')
"

# 2. Lint + format
ruff check . && echo "✅ ruff check passed"
ruff format --check . && echo "✅ ruff format passed"

# 3. Type check
mypy portal_pipeline/ portal_mcp/ 2>&1 | tail -10

# 4. Unit tests
pytest tests/unit/ -v --tb=short
# Expected: all pass, including test_transcribe_diarize.py and test_workspace.py

# 5. Persona YAML valid
python3 -c "
import yaml
data = yaml.safe_load(open('config/personas/transcriptanalyst.yaml'))
assert data['slug'] == 'transcriptanalyst'
assert data['workspace_model'] == 'auto-documents'
assert 'system_prompt' in data
print('✅ transcriptanalyst.yaml valid')
"

# 6. Routing JSONs valid + new examples present
python3 -c "
import json
json.load(open('config/routing_descriptions.json'))
data = json.load(open('config/routing_examples.json'))
assert any('transcribe' in ex['message'].lower() for ex in data['examples']), 'transcribe example missing'
print('✅ routing JSONs valid')
"

# 7. mcp-servers.json contains the new entry
python3 -c "
import json
data = json.load(open('imports/openwebui/mcp-servers.json'))
ids = [s['id'] for s in data['tool_servers']]
assert 'portal_mlx_transcribe' in ids
print('✅ portal_mlx_transcribe registered')
"

# 8. End-to-end smoke (requires HF_TOKEN + licenses + workspace)
./launch.sh start-transcribe
sleep 8
curl -sf http://localhost:8924/health | jq

# 9. Test the workspace integration: place a file in uploads, call MCP via file_id
TEST_ID="acc-test-$(date +%s)"
cp tests/fixtures/audio/two_speaker_10s.wav \
  "${AI_OUTPUT_DIR:-${HOME}/AI_Output}/uploads/${TEST_ID}.wav" 2>/dev/null

# Direct curl with file ID (no path)
curl -sf -X POST http://localhost:8924/mcp/tools/transcribe_with_speakers \
  -H "Content-Type: application/json" \
  -d "{\"file\": \"${TEST_ID}\", \"num_speakers\": 2}" | jq '{speaker_count, duration, timing}'

# Cleanup
rm -f "${AI_OUTPUT_DIR:-${HOME}/AI_Output}/uploads/${TEST_ID}.wav"

# 10. Acceptance test S9 (extended with S9-03/04/05)
python3 tests/portal5_acceptance_v6.py --section S9
# Expected: S9-01 through S9-05 PASS or INFO (no FAIL)
```

---

## Rollback Procedure

```bash
./launch.sh stop-transcribe 2>/dev/null || true
rm -f /tmp/portal-mlx-transcribe.pid

# Revert via git
git checkout main
git branch -D feat/transcribe-diarize

# If already merged: revert
git log --oneline | grep -iE "transcribe-diarize|TASK-TRANSCRIBE-001" | head -1
git revert <commit-sha> --no-edit
git push

# Models stay on disk; remove if disk-pressure:
rm -rf ~/.cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo
rm -rf ~/.cache/huggingface/hub/models--pyannote--*

# Docker fallback path: rebuild without pyannote
git checkout main -- Dockerfile.mcp portal_mcp/generation/whisper_mcp.py
docker compose -f deploy/portal-5/docker-compose.yml build mcp-whisper
docker compose -f deploy/portal-5/docker-compose.yml up -d mcp-whisper
```

The workspace foundation (TASK-WORKSPACE-001) is unaffected by this rollback — it remains in place for other future MCPs to use.

---

## Commit Message

```
feat(transcribe): diarized transcription on workspace foundation

Adds speaker-labeled transcription as a first-class capability, building
on TASK-WORKSPACE-001's shared workspace foundation.

- New host-native scripts/mlx-transcribe.py on port 8924
  (mlx-whisper large-v3-turbo + pyannote.audio 3.1 on MPS).
  ~60-130s for 10-min 2-speaker audio on M4 Pro.

- whisper_mcp.py extended with transcribe_with_speakers tool
  (faster-whisper + pyannote on CPU/CUDA) — cross-platform fallback.

- Both paths use portal_mcp.core.workspace helpers:
  - resolve_upload_path(file_id) reads OWUI-dropped attachments
  - get_generated_dir("transcripts") writes outputs

- New persona transcriptanalyst in auto-documents workspace.
  Detects audio attachments in chat, calls tool with file ID,
  displays markdown directly, chains to create_word_document for docx.

- launch.sh: new commands start-transcribe / stop-transcribe.

- Tool surface: transcribe_with_speakers(file, num_speakers, language).
  File parameter accepts OWUI file ID, filename, or absolute path.

- Acceptance tests S9-03 / S9-04 / S9-05 added (health, end-to-end,
  workspace integration).

- Pyannote models gated; HF_TOKEN required.

Refs: TASK-TRANSCRIBE-001 (depends on TASK-WORKSPACE-001)
```

---

## Operator Checklist (Post-Merge)

- [ ] Confirm TASK-WORKSPACE-001 has been merged and `./launch.sh workspace-status` shows the structure
- [ ] Accept HuggingFace licenses for `pyannote/segmentation-3.0` and `pyannote/speaker-diarization-3.1`
- [ ] Generate HF read token, add to `.env` as `HF_TOKEN=hf_...`
- [ ] Run `./launch.sh pull-mlx-models` (downloads whisper-large-v3-turbo + pyannote weights)
- [ ] Run `./launch.sh start-transcribe`
- [ ] Verify health: `curl http://localhost:8924/health`
- [ ] Open WebUI → Admin → Tools → confirm `Portal MLX Transcribe` is registered
- [ ] Open WebUI → Workspaces → `Documents` → `Transcript Analyst` persona present
- [ ] **For long-file workflow (>5 min audio):** set `TOOL_SERVER_REQUEST_TIMEOUT=1800` in `.env` and `./launch.sh restart open-webui`
- [ ] **End-to-end smoke (Workflow A):** drop a 1-min audio file in OWUI chat, select `Transcript Analyst`, type "transcribe this with 2 speakers", confirm output appears with speaker labels
- [ ] **End-to-end smoke (Workflow B, your 35-min file):**
  ```bash
  time curl -sf -X POST http://localhost:8924/v1/audio/transcribe-with-speakers \
    -F "file=@your_35min.mp3" \
    -F "num_speakers=2" | jq '.timing, .speaker_count, .duration, .md_path'
  ```
  Expected: `total_s` 210–500s; `speaker_count=2`; markdown file at the printed path.
- [ ] Open the resulting `.md` file in OWUI: drop it in chat with `Transcript Analyst`, ask for a Word document export
- [ ] Run `python3 tests/portal5_acceptance_v6.py --section S9` — expect S9-03/04/05 PASS

---

**End of TASK-TRANSCRIBE-001 (revised v2).**
