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

**What:** Convert text to spoken audio using MLX-native speech (Kokoro narration + Higgs Audio v2 voice cloning).

**Activate:** Select `Music Producer` (`auto-music`) from the model dropdown. The TTS tools (`speak`, `clone_voice`, `register_voice`, `list_voices`) are granted by `auto-music`'s `tools` list in `config/portal.yaml` — they are not available in every workspace.

**How:** The host-native MLX speech server (`scripts/mlx-speech.py`, port 8918) provides Kokoro narration (default backend, `af_heart` default voice), Higgs Audio v2 voice cloning (`MLX_CLONE_MODEL` swaps the engine), and Qwen3-TTS CustomVoice/VoiceDesign. Start it with `./launch.sh start-speech` — `_launch_start_speech` in `scripts/lib/services.sh` requires Apple Silicon and `mlx-audio`, warms the clone model, and models otherwise load lazily on the first request. The Docker `mcp-tts` container (port 8916, `portal/modules/media/tools/tts_mcp.py`) proxies every tool to port 8918. Generated audio is published through Open WebUI's files API when `OWUI_API_KEY` is set (link served on `:8080`); otherwise it lands in `generated/speech/` behind this server's `/files/tts` route.

**Cloning:** `speak(voice="clone:/path/to/ref.wav")` for a one-off clone from a 5-15s clip, or register a reusable trainer voice once and reuse it as `voice="trainer:<name>"`. Register via the `register_voice` tool, `POST /v1/voices` (`{name, reference_audio, reference_text}`), or `scripts/register_trainer_voice.py --audio <clip> --name <name> --text "<transcript>" --test`, which cleans the recording (mono, silence-trimmed, peak-normalised) before registering. In OWUI, upload the clip and call `register_voice` with just the name and transcript — the reference resolves from the upload. Profiles persist under `${VOICE_PROFILES_DIR:-~/.portal5/voice_profiles}/<name>/`. The engine reads only the first ~10-15s of the reference, so a tight, expressive clip beats a long flat one; output is 24 kHz with no provenance watermark (see KNOWN_LIMITATIONS P5-SPEECH-CLONE-001).

**Example prompts (in the `Music Producer` workspace):**

- *Register a trainer voice* — attach a 12-15s recording to the message, then: `Register this as my trainer voice under the name "chris". Transcript: "<the exact words spoken in the clip>"`. The transcript must match the clip verbatim; the reference resolves from the upload, so no file path is needed.
- *Narrate with a registered voice* — `Narrate the following as trainer:chris — "Welcome back. Today we cover incident response drills and the escalation path for a suspected credential compromise."`
- *One-off clone without registering* — attach a clip, then: `Speak this in the attached voice: "Your training module for today is ready."` (uses `clone_voice`, which resolves the most recent upload when no path is given).
- *Plain narration, no cloning* — `Read this aloud in a calm American female voice: "..."` (Kokoro, `af_heart`).
- *List what's available* — `What voices can you speak with?` (calls `list_voices` — Kokoro presets, Qwen3 speakers, and registered trainer profiles).

Re-registering the same name overwrites the profile; `DELETE /v1/voices/<name>` removes it.

## Why

Speech is an audio runtime, not part of the chat inference tier, so it runs outside Ollama entirely: a native server on Apple Silicon uses the Metal GPU for fast synthesis while the MCP tool layer keeps the model-facing call uniform. Lazy model loading keeps `start-speech` cheap to bring up — the first utterance pays the load cost, not the startup command. Cloning is a separate model (Higgs Audio v2) rather than Qwen3-TTS, whose Chinese-accented English was wrong for an American-English trainer voice; the operator picked Higgs over Chatterbox in the fidelity gate.
