---
id: unit-fish-speech-setup-fish-speech-presets
kind: what
title: Fish Speech preset voice IDs exposed by the TTS MCP
sources:
- type: code
  path: portal/modules/media/tools/tts_mcp.py
- type: code
  path: .env.example
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.539945
updated_at: 1784946220.539945
---

The TTS MCP exposes exactly two Fish Speech preset voice IDs. In `list_voices`
the `fish_speech` entry lists `female_zhang` and `male_yun`, and adds a third
`custom` entry that is served by cloning a voice from a reference recording
rather than by a fixed preset. The other identifiers from the older guide such as
english_alice, english_marcus and japanese_yuki do not appear anywhere in the
repository, so they are not returned by `list_voices` and cannot be relied on.
Voice selection for Fish Speech flows through the `speak` tool's `voice`
argument once `TTS_BACKEND=fish_speech`.

## Why

Listing presets that no code defines is exactly the kind of documented fantasy
the grounding pass exists to remove. The two IDs that `list_voices` actually
returns are the only safe ones to advertise, and the custom entry points at the
real extension path, cloning, which is the feature that justifies Fish Speech at
all.
