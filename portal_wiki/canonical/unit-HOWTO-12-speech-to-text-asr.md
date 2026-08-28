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

**What:** Transcribe audio files to text — MLX-native ASR and a Docker Whisper fallback.

**Activate:** Transcription is available only in workspaces that grant the tools: `transcribe_audio` and `transcribe_with_speakers` appear in `auto-music`, `auto-daily`, `auto-audio`, `auto-vision`, and `auto-documents` (`config/portal.yaml`). It is not enabled in every workspace.

**How:** The host-native MLX Transcribe server (`scripts/mlx-transcribe.py`, port 8924, `./launch.sh start-transcribe`) backs both tools on Apple Silicon: `transcribe_audio` is Parakeet-TDT-v3 (transcript + word timestamps), `transcribe_with_speakers` adds Sortformer speaker diarization merged at the word level — see the Diarized Transcription unit. The Docker `mcp-whisper` server (port 8915, `portal/modules/media/tools/whisper_mcp.py`) proxies there first and only falls back to in-Docker faster-whisper (`large-v3-turbo`, no diarization) on non-Apple-Silicon nodes. The workspace prompts tell the model to call the tool with no file argument so the most recently uploaded audio is auto-detected from the shared workspace `uploads/` directory.

## Why

Transcription availability is deliberately workspace-scoped because ASR is not free — each engine loads a model and takes GPU time, so granting it everywhere would add latency to chat lanes that never transcribe. Scoping by workspace tools means audio-heavy lanes (music, audio analysis, documents) carry the capability while general chat stays lean.
