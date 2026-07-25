---
id: unit-known-limitations-diarized-transcription-task-transcribe-001
kind: what
title: "KNOWN_LIMITATIONS \u2014 Diarized Transcription (TASK-TRANSCRIBE-001)"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: Diarized Transcription (TASK-TRANSCRIBE-001)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.674855
updated_at: 1784946220.674855
---

- **Pyannote model gating.** Diarization requires accepting HuggingFace user agreements for `pyannote/segmentation-3.0` and `pyannote/speaker-diarization-3.1`. Without `HF_TOKEN` in `.env` and licenses accepted, diarization calls return 500.
- **Overlapping speech.** Pyannote 3.1 underperforms when multiple speakers talk simultaneously. Segments are assigned to a single speaker by maximum overlap.
- **Speaker count drift on long recordings.** For recordings >15–30 min, pyannote may split one speaker into two IDs after long silence gaps. Pass `num_speakers=N` if known.
- **OWUI tool-call timeout for long files.** OWUI's default MCP timeout is shorter than processing time for files >5 min. Raise `TOOL_SERVER_REQUEST_TIMEOUT` (e.g., 1800s) or use the direct endpoint at `:8924`.
- **MLX path is macOS-only.** `scripts/mlx-transcribe.py` requires Apple Silicon. The Docker `whisper_mcp.py` fallback (faster-whisper + pyannote on CPU/CUDA) is the cross-platform alternative.

---
