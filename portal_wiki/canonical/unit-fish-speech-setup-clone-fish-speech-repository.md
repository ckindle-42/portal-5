---
id: unit-fish-speech-setup-clone-fish-speech-repository
kind: what
title: Fish Speech is an external, non-vendored package
sources:
- type: code
  path: portal/modules/media/tools/tts_mcp.py
- type: code
  path: Dockerfile.mcp
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5373251
updated_at: 1784946220.5373251
---

The Portal 5 tree does not clone or vendor the upstream Fish Speech source, and
no install step in this repository fetches it. The TTS MCP discovers the
capability at import time: `_check_fish_speech` attempts `import fish_speech`
and surfaces the result on the health route, so the package's presence controls
the `fish_speech` backend. `Dockerfile.mcp` deliberately installs only
`kokoro-onnx` for speech, which is why the zero-setup path works without any
source checkout; obtaining the Python package and its checkpoint is an operator
action that happens outside the image build.

## Why

Keeping Fish Speech an import-time optional dependency rather than vendoring a
repository tree is what lets the MCP container stay small and lets Kokoro answer
`speak` calls even when the optional package is missing. The discovery mechanism
treats the package as a feature flag, so the fallback path is exercised by the
same code every deployment runs.
