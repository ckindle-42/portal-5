---
id: unit-HOWTO-12-speech-to-text-asr
kind: why
title: "HOWTO \u2014 12. Speech-to-Text (ASR)"
sources:
- type: code
  path: portal/modules/media/tools/whisper_mcp.py
- type: code
  path: config/portal.yaml
last_generated_commit: 64c5f5f41652bf67e97863ee1a6285289eaeea00
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.84798
updated_at: 1783195000.84798
---

**What:** Transcribe audio files to text — MLX-native ASR and a Docker Whisper fallback.

**Activate:** Transcription is available only in workspaces that grant the tools: `transcribe_audio` and `transcribe_with_speakers` appear in `auto-music`, `auto-daily`, `auto-audio`, `auto-vision`, and `auto-documents` (`config/portal.yaml`). It is not enabled in every workspace.

**How:** Two engines back the tools. The Docker `mcp-whisper` server (port 8915, `portal/modules/media/tools/whisper_mcp.py`) handles plain transcription. The host-native MLX speech server (`scripts/mlx-speech.py`, port 8918) includes Qwen3-ASR (MLX-native). For speaker-labeled transcripts use `./launch.sh start-transcribe` (mlx-transcribe, port 8924) — see the Diarized Transcription unit. The `auto-music` prompt tells the model to call `transcribe_audio` with no file argument so the most recently uploaded audio is auto-detected from the shared workspace `uploads/` directory.

## Why

Transcription availability is deliberately workspace-scoped because ASR is not free — each engine loads a model and takes GPU time, so granting it everywhere would add latency to chat lanes that never transcribe. Scoping by workspace tools means audio-heavy lanes (music, audio analysis, documents) carry the capability while general chat stays lean.
