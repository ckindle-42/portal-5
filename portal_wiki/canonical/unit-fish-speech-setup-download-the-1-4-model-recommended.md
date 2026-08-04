---
id: unit-fish-speech-setup-download-the-1-4-model-recommended
kind: what
title: Fish Speech 1.4 checkpoint path is hardcoded
sources:
- type: code
  path: portal/modules/media/tools/tts_mcp.py
- type: code
  path: portal/modules/media/tools/utils.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.538661
updated_at: 1784946220.538661
---

The Fish Speech 1.4 checkpoint location is a hardcoded contract in the TTS MCP:
`_fish_speech_sync` loads `Text2Speech` with `load_from_checkpoint` using the
checkpoint path `models/fish_speech/fish-speech-1.4`, and `_fish_clone_sync`
calls `from_pretrained` on the same relative string. Both resolve from the
container working directory, so the 1.4 weights must live at that exact location.
Unlike Kokoro, whose files `_ensure_kokoro_models` fetches automatically on first
use, Fish Speech has no download helper in the repository; a missing checkpoint
makes the loader raise and the tool return an error dictionary.

## Why

The exact directory is not a suggestion, it is what two separate loaders assert,
so placing the weights anywhere else turns every Fish Speech request into an
exception. Calling out the contrast with the Kokoro auto-download keeps operators
from assuming the heavy backend self-provisions, which only the built-in one does.
