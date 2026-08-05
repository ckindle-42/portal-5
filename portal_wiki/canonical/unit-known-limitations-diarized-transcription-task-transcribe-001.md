---
id: unit-known-limitations-diarized-transcription-task-transcribe-001
kind: what
title: "KNOWN_LIMITATIONS \u2014 Diarized Transcription (TASK-TRANSCRIBE-001)"
sources:
- type: code
  path: scripts/mlx-transcribe.py
- type: code
  path: portal/modules/media/tools/whisper_mcp.py
- type: code
  path: .env.example
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.674855
updated_at: 1784946220.674855
---

- **Pyannote model gating.** `scripts/mlx-transcribe.py` gates diarization on `HF_TOKEN` (env `DIARIZATION_MODEL` defaults to `pyannote/speaker-diarization-3.1`); without it the pipeline returns an error telling the operator to accept the HF agreements and set `HF_TOKEN` in `.env`. The Docker fallback `portal/modules/media/tools/whisper_mcp.py` gates on the same token.
- **Overlapping speech.** Pyannote underperforms when multiple speakers talk simultaneously; segments are assigned to a single speaker by maximum overlap.
- **Speaker count drift on long recordings.** For long recordings pyannote may split one speaker into two IDs after long silence gaps. Pass `num_speakers=N` when known; both `scripts/mlx-transcribe.py` and `whisper_mcp.py` forward it to the diarization pipeline.
- **OWUI tool-call timeout for long files.** OWUI's MCP tool-call ceiling can fire before a long file finishes. Raise `AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA` (set to 1800 in `.env.example`) or use the direct endpoint on port `8924`.
- **MLX path is Apple-Silicon-specific.** `scripts/mlx-transcribe.py` is the host-native MPS path (mlx-whisper + pyannote on MPS, ~5x faster). The Docker `whisper_mcp.py` fallback (faster-whisper + pyannote on CPU, or CUDA on Linux nodes) is the cross-platform alternative.

## Why

Diarization lives behind HuggingFace gated model agreements, so the code fails fast with a token hint instead of a mysterious 500; that keeps the failure mode self-diagnosing. Keeping the fast MPS path and the portable Docker path side by side, with the token gate shared between them, means one operational prerequisite (`HF_TOKEN`) governs both routes and the platform choice is left to the host.
