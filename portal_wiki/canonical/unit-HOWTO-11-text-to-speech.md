---
id: unit-HOWTO-11-text-to-speech
kind: why
title: "HOWTO \u2014 11. Text-to-Speech"
sources:
- type: code
  path: scripts/mlx-speech.py
- type: code
  path: scripts/lib/services.sh
- type: code
  path: config/portal.yaml
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.846459
updated_at: 1787922000
---

**What:** Convert text to spoken audio using MLX-native speech (Kokoro narration + Chatterbox voice cloning).

**Activate:** Select `Music Producer` (`auto-music`) from the model dropdown. The TTS tools (`speak`, `clone_voice`, `register_voice`, `list_voices`) are granted by `auto-music`'s `tools` list in `config/portal.yaml` — they are not available in every workspace.

**How:** The host-native MLX speech server (`scripts/mlx-speech.py`, port 8918) provides Kokoro narration (default backend, `af_heart` default voice), Chatterbox voice cloning, and Qwen3-TTS CustomVoice/VoiceDesign. Start it with `./launch.sh start-speech` — `_launch_start_speech` in `scripts/lib/services.sh` requires Apple Silicon and `mlx-audio`, warms Chatterbox, and models otherwise load lazily on the first request. The Docker `mcp-tts` container (port 8916, `portal/modules/media/tools/tts_mcp.py`) proxies every tool to port 8918.

**Cloning:** `speak(voice="clone:/path/to/ref.wav")` for a one-off clone from a 5-15s clip, or register a reusable trainer voice once and reuse it as `voice="trainer:<name>"`. Register via the `register_voice` tool, `POST /v1/voices` (`{name, reference_audio, reference_text}`), or `scripts/register_trainer_voice.py --audio <clip> --name <name> --text "<transcript>" --test`, which cleans the recording (mono, silence-trimmed, peak-normalised) before registering. Profiles persist under `${VOICE_PROFILES_DIR:-~/.portal5/voice_profiles}/<name>/`. Chatterbox uses only the first ~10s of the reference for timbre and ~6s for prosody, so a tight, expressive clip beats a long flat one; output is 24 kHz and carries Resemble AI's inaudible PerTh watermark (see KNOWN_LIMITATIONS P5-SPEECH-CLONE-001).

## Why

Speech is an audio runtime, not part of the chat inference tier, so it runs outside Ollama entirely: a native server on Apple Silicon uses the Metal GPU for fast synthesis while the MCP tool layer keeps the model-facing call uniform. Lazy model loading keeps `start-speech` cheap to bring up — the first utterance pays the load cost, not the startup command. Cloning is a separate MIT-licensed English model (Chatterbox) rather than Qwen3-TTS, whose Chinese-accented English was wrong for an American-English trainer voice.
