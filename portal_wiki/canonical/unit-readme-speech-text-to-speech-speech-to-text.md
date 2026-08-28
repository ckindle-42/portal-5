---
id: unit-readme-speech-text-to-speech-speech-to-text
kind: what
title: "README \u2014 Speech (Text-to-Speech & Speech-to-Text)"
sources:
- type: code
  path: scripts/mlx-speech.py
- type: code
  path: scripts/lib/services.sh
- type: code
  path: launch.sh
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.687758
updated_at: 1787921600
---

Portal 5 includes a native MLX speech server on Apple Silicon
(`scripts/mlx-speech.py`, port `MLX_SPEECH_PORT` default 8918) with three
backends:

- **Kokoro TTS** — the `mlx-community/Kokoro-82M-bf16` model via mlx-audio; voices
  are selected by the Kokoro naming prefix (`af_`, `am_`, `bf_`, `bm_`, `jf_`,
  `jm_`, `zf_`, `zm_`), e.g. `af_heart`, `bm_george`.
- **Chatterbox (English v2)** — voice cloning. One-off via `voice="clone:/path/to/ref.wav"`,
  or register a reusable trainer voice with `POST /v1/voices` (name + reference clip +
  transcript) and then use `voice="trainer:<name>"`. Zero-shot from a 5-15s clip; not a
  fine-tune, so fidelity tracks reference-clip quality. Every clip carries Resemble AI's
  inaudible PerTh watermark.
- **Qwen3-TTS CustomVoice / VoiceDesign** — preset speakers and voice-from-description
  (retained; not used for cloning).
- **Qwen3-ASR** — speech-to-text via `mlx_audio.stt`.

Manage it with the `start-speech` and `stop-speech` subcommands of `launch.sh`
(`scripts/lib/services.sh`): `start-speech` verifies `mlx_audio` is installed,
checks the PID file at `/tmp/portal-mlx-speech.pid`, and launches
`scripts/mlx-speech.py` with nohup, logging to `~/.portal5/logs/mlx-speech.log`;
`stop-speech` kills the recorded PID. Models load lazily on the first TTS or ASR
request.

## Why

TTS and ASR are latency-sensitive and run continuously, so the speech server is a
host-native process on Metal rather than a Docker container: the MPS path keeps
synthesis fast and the models are loaded once and reused. The PID-file plus
`start-speech`/`stop-speech` pairing gives an operator lifecycle control without a
container orchestrator, and Kokoro voices are addressed by the same prefix scheme
the Kokoro model uses.
