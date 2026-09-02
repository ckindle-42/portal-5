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
created_at: 1783195000.84798
updated_at: 1787931459.0
---

**What:** Transcribe audio files to text — MLX-native ASR, with a Docker Whisper fallback for non-Apple-Silicon nodes.

**Activate:** Pick the **🎙️ Portal Audio Analyst** workspace (`auto-audio`) — it is the transcription home and grants both `transcribe_audio` (plain) and `transcribe_with_speakers` (speaker-labelled). `transcribe_audio` is also granted in `auto-music`, `auto-daily`, and `auto-vision` for lanes that occasionally need a quick transcript (`config/portal.yaml`); it is not enabled everywhere.

**How:** Drop the audio file in the chat and ask ("transcribe this" / "who said what"). The host-native MLX Transcribe server (`scripts/mlx-transcribe.py`, port 8924, `./launch.sh start-transcribe`) backs both tools on Apple Silicon: `transcribe_audio` is Parakeet-TDT-v3 (transcript + word timestamps), `transcribe_with_speakers` adds Sortformer speaker diarization merged at the word level — see the Diarized Transcription unit. Either tool auto-detects the most recently uploaded file when called with no argument, and **always writes three sidecars** — JSON, Markdown, and Word (`.docx`) — into `~/AI_Output/generated/transcripts/`, returning `md_url` / `docx_url` download links in the response. The Docker `mcp-whisper` server (port 8915, `portal/modules/media/tools/whisper_mcp.py`) proxies to :8924 first and only falls back to in-Docker faster-whisper (`large-v3-turbo`, no diarization) on non-Apple-Silicon nodes.

## Why

The server emits the Markdown and `.docx` alongside the canonical JSON in the same step as the transcription itself, rather than leaving the Word document to a second model-driven `create_word_document` call. That makes the artifacts deterministic — they exist whether or not the model completes the chat turn — and collapses what used to be a two-workspace, persona-chained flow into one tool call. Transcription stays workspace-scoped because ASR is not free — each engine loads a model and takes GPU time — so the capability rides audio-heavy lanes while general chat stays lean.