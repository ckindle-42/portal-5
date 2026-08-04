---
id: unit-fish-speech-setup-model-download-failures
kind: what
title: "Model download failures \u2014 no in-repo Fish Speech downloader"
sources:
- type: code
  path: portal/modules/media/tools/tts_mcp.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.542945
updated_at: 1784946220.542945
---

When the Fish Speech 1.4 weights are missing, the failure surfaces in the TTS MCP
because the loaders read a fixed path. `_fish_speech_sync` passes
`models/fish_speech/fish-speech-1.4` to `load_from_checkpoint` and
`_fish_clone_sync` uses `from_pretrained` on the same string, and neither call has
a download fallback. Kokoro is the only backend with an automated fetch,
performed by `_ensure_kokoro_models`, which pulls the ONNX weights and the voice
pack from the upstream GitHub release and caches them under `HF_HOME`. Placing
the 1.4 checkpoint at the hardcoded path is therefore the only recovery available
to an operator whose download failed midway.

## Why

Documenting recovery steps is only honest when the failure mode they address is
real, and this one is: a missing checkpoint converts every Fish Speech request
into an exception because the loaders will not self-provision. The contrast with
the Kokoro auto-download tells the operator exactly which backend recovers by
itself and which one requires manual placement of weights.
