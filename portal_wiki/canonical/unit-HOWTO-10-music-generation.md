---
id: unit-HOWTO-10-music-generation
kind: why
title: "HOWTO \u2014 10. Music Generation"
sources:
- type: code
  path: portal/modules/media/tools/music_mcp.py
- type: code
  path: scripts/lib/services.sh
last_generated_commit: 9623f6b25b3e922bd0cf4b3885a926a4728b26a1
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.8455648
updated_at: 1783195000.8455648
---

**What:** Generate music clips from text descriptions using HuggingFace MusicGen.

**Activate:** Select `Music Producer` (`auto-music`) from the model dropdown. The Music tools — `generate_music`, `generate_continuation`, `list_music_models`, plus the speech and transcription tools — are granted by `auto-music`'s `tools` list in `config/portal.yaml`, so they are available when that workspace is selected.

**How:** `portal/modules/media/tools/music_mcp.py` runs the MusicGen models through the `transformers` library, not AudioCraft — AudioCraft's `torchtext`/`xformers` dependencies have no aarch64 wheels. Model sizes `small`, `medium`, `large` download to the HuggingFace cache on first use. The server runs host-native on Apple Silicon (install with `./launch.sh install-music`, auto-started by `up` through `_ensure_native_services`); the port is 8912. Clips write to the shared workspace `generated/music/` and the tool returns a download URL. Duration is capped at 30 seconds per clip; `generate_continuation` extends an existing WAV using a melody as conditioning.

## Why

Music generation is a large, cold model that Docker would run on CPU, so it is a host-native service kept out of the container set and auto-started only when installed. Routing the tools through the `auto-music` workspace rather than globally keeps the heavy models out of everyday chat while still exposing them to any persona that binds to that workspace.
