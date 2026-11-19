---
id: unit-HOWTO-12-speech-to-text-asr
kind: why
title: "HOWTO \u2014 12. Speech-to-Text (ASR)"
sources:
- type: code
  path: portal/modules/media/tools/whisper_mcp.py
- type: code
  path: config/portal.yaml
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1

---

**What:** Transcribe audio files to text — MLX-native ASR, with a Docker Whisper fallback for non-Apple-Silicon nodes.

**Activate:** Pick the **🎙️ Portal Audio Analyst** workspace (`auto-audio`) — it is the transcription home and grants both `transcribe_audio` (plain) and `transcribe_with_speakers` (speaker-labelled). `transcribe_audio` is also granted in `auto-music`, `auto-daily`, and `auto-vision` for lanes that occasionally need a quick transcript (`config/portal.yaml`); it is not enabled everywhere.

**How:** Drop the audio file in the chat and ask ("transcribe this" / "who said what"). The host-native MLX Transcribe server (`scripts/mlx-transcribe.py`, port 8924, `./launch.sh start-transcribe`) backs both tools on Apple Silicon: `transcribe_audio` is Parakeet-TDT-v3 (transcript + word timestamps), `transcribe_with_speakers` adds Sortformer speaker diarization merged at the word level — see the Diarized Transcription unit. Either tool auto-detects the most recently uploaded file when called with no argument, and **always writes three sidecars** — JSON, Markdown, and Word (`.docx`) — into `~/AI_Output/generated/transcripts/`, returning `md_url` / `docx_url` download links in the response. The Docker `mcp-whisper` server (port 8915, `portal/modules/media/tools/whisper_mcp.py`) proxies to :8924 first and only falls back to in-Docker faster-whisper (`large-v3-turbo`, no diarization) on non-Apple-Silicon nodes.

**Open WebUI transcription:** OWUI's microphone input and audio-upload transcription use this same server through its OpenAI-compatible `POST /v1/audio/transcriptions`. `deploy/portal-5/docker-compose.yml` sets `AUDIO_STT_ENGINE=openai` with `AUDIO_STT_OPENAI_API_BASE_URL=http://host.docker.internal:8924/v1` (OWUI appends `/audio/transcriptions`, so the base carries `/v1`), `AUDIO_STT_MODEL=parakeet-tdt-0.6b-v3` and a placeholder bearer (`portal-stt` — the service authenticates nothing). That path returns `{"text": …}` from Parakeet with no sidecars and no speaker labels; diarization stays with the `transcribe_with_speakers` tool.

**Pre-flight:** `./launch.sh pull-asr-models` (or `.venv/bin/python3 scripts/fetch_mlx_asr_models.py`, `--check` to verify only) — idempotent: each model id is verified in the configured `HF_HUB_CACHE` / `HF_HOME` cache and only missing ones are downloaded. Both host audio services run under `HF_HUB_OFFLINE=1`, so nothing can be fetched at request time; without this step neither can serve. It fetches the three ids the services load: `mlx-community/parakeet-tdt-0.6b-v3` and `mlx-community/diar_sortformer_4spk-v1-fp32` for :8924, `mlx-community/Qwen3-ASR-1.7B-8bit` for :8918.

**Fallback when a model is missing:** `/health` reports `asr_available: false` (and `diarization_available`), and `/v1/audio/transcriptions` answers an honest `503` with `reason: asr_model_not_cached` and the fetch command in the body — never a blind 500. Open WebUI itself keeps working: chat, uploads, and the MCP transcription tools (which reach in-Docker faster-whisper through `mcp-whisper`) are unaffected; only OWUI's own mic/auto-STT call fails, with the fix named in the error. Run the fetch, then `./launch.sh start-transcribe` so the service restarts onto the warmed cache.

## Why

The server emits the Markdown and `.docx` alongside the canonical JSON in the same step as the transcription itself, rather than leaving the Word document to a second model-driven `create_word_document` call. That makes the artifacts deterministic — they exist whether or not the model completes the chat turn — and collapses what used to be a two-workspace, persona-chained flow into one tool call. Transcription stays workspace-scoped because ASR is not free — each engine loads a model and takes GPU time — so the capability rides audio-heavy lanes while general chat stays lean.