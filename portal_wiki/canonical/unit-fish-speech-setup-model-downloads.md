---
id: unit-fish-speech-setup-model-downloads
kind: what
title: "Model downloads \u2014 checkpoint path contract"
sources:
- type: code
  path: portal/modules/media/tools/tts_mcp.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.538356
updated_at: 1784946220.538356
---

Fish Speech requires its weights at a path the code asserts, not one the operator
chooses: the TTS MCP loads `Text2Speech` from `models/fish_speech/fish-speech-1.4`
in both `_fish_speech_sync` and `_fish_clone_sync`. The leading directory is
`models/fish_speech` inside the container working directory, not the source-tree
layout the older guide described. Kokoro, by contrast, downloads its own model
and voices on first use through `_ensure_kokoro_models` and caches them under
`HF_HOME`, so the built-in backend has no manual download step at all and never
requires the operator to create a model directory by hand.

## Why

The old path carried a source-checkout prefix that the containerised MCP does not
have, and repeating it would misdirect anyone placing weights by hand. Spelling
out the exact relative path the two loaders share keeps the manual step aligned
with the one location the code will actually read at synthesis time.
