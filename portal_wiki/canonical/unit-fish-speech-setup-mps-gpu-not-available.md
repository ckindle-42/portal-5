---
id: unit-fish-speech-setup-mps-gpu-not-available
kind: what
title: "MPS unavailable \u2014 get_torch_device falls back to CPU"
sources:
- type: code
  path: portal/modules/media/tools/utils.py
- type: code
  path: portal/modules/media/tools/tts_mcp.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.54262
updated_at: 1784946220.54262
---

Device selection for Fish Speech in the TTS MCP is not a command-line flag; it is
the `get_torch_device` helper in the shared media utilities. That function checks
`torch.backends.mps.is_available` first, then `torch.cuda.is_available`, and
returns `mps`, `cuda` or `cpu` in that order of preference. The Fish Speech
loaders forward the result into `load_from_checkpoint` and `from_pretrained`, so
a machine without MPS simply runs inference on `cpu`, which is slower but
functional. The old `--device` flag belongs to an upstream CLI that Portal 5 does
not invoke, because the MCP loads Fish Speech in-process rather than spawning the
upstream API.

## Why

A backend whose acceleration path is decided by one shared helper is easier to
reason about than one controlled by flags scattered through startup scripts.
Recording the fallback order makes it predictable that a Mac without a usable MPS
context still synthesises, just slower, and names the exact function an operator
should read when performance is poor.
