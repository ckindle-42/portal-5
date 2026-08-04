---
id: unit-fish-speech-setup-voice-cloning
kind: what
title: Voice cloning from reference audio
sources:
- type: code
  path: portal/modules/media/tools/tts_mcp.py
- type: code
  path: scripts/mlx-speech.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.540705
updated_at: 1784946220.540705
---

Voice cloning in the TTS MCP is implemented by the `clone_voice` tool, which
requires the `fish_speech` package: `_check_fish_speech` gates it, and when the
package is absent the tool returns an unavailable error with an `install_docs`
pointer rather than crashing. The reference audio should be a short clean
recording, five to thirty seconds, matching the parameter help, and the tool
passes the path into `_fish_clone_sync`, which loads the 1.4 checkpoint via
`from_pretrained` and writes a clone file into the output directory. A separate
cloning route exists on the host-native speech server: `scripts/mlx-speech.py`
sends a `clone:` voice prefix to the Qwen3-TTS Base model, which also clones from
a reference file without Fish Speech.

## Why

Cloning is the entire reason Fish Speech is worth installing, so its unit must
name the exact gating mechanism and the failure mode when the package is missing.
Documenting both the MCP tool and the Qwen3-TTS alternative prevents an operator
from assuming cloning is unavailable whenever Fish Speech is absent, when a
second route exists at the host speech server.
