---
id: unit-known-limitations-phi4-reasoning-plus-crashes-ollama-s-llama-server-on-this-host-confirmed-not-a-corrupted-download
kind: what
title: "KNOWN_LIMITATIONS \u2014 phi4-reasoning:plus crashes Ollama's llama-server\
  \ on this host \u2014 CONFIRMED NOT a corrupted download"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/personas/phi4stemanalyst.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 3cdc95603cf1faa41ddd64aa3eaad1ec45a113ce
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.673387
updated_at: 1784946220.673387
---

- **ID**: P5-MODEL-PHI4REASONING-001
- **Description**: `phi4-reasoning:plus` crashes Ollama's llama-server on this host — the runtime reports `llama-server process has terminated: signal: abort trap` on direct generation. `config/backends.yaml` records the confirmed exclusion: the `reasoning` group deliberately omits `phi4-reasoning:plus-ctx32k` with a comment saying the model crashes Ollama's llama-server on load and must not be made reachable from any production workspace until resolved upstream. This is a local Ollama/model-file incompatibility (llama.cpp device-memory-fitting at load on the Apple Silicon Metal backend), not a routing or pipeline bug.
- **Root cause confirmed**: a full `ollama rm` plus re-pull of the base model and rebuild of the ctx-tagged variants reproduced the identical abort — not a corrupted download.
- **Impact**: The `phi4stemanalyst` persona was re-identified generically: `config/personas/phi4stemanalyst.yaml` has no `model_pin` and documents the crash, serving `auto-reasoning`'s pool default (`DeepSeek-R1-0528-Qwen3-8B`) instead of Phi-4-reasoning-plus.
- **Do not add** `phi4-reasoning:plus` or `phi4-reasoning:plus-ctx32k` to a reachable backend group without first resolving this crash. Re-pulling alone will NOT fix it — already tried and reproduced.
- **Mitigation options not yet tried**: upgrade/downgrade Ollama to a different llama.cpp vendor commit and retest; try a different quantization/source GGUF; file upstream against Ollama/llama.cpp with the log excerpt.

## Why

A model that aborts during load is indistinguishable from a corrupted download without the reproduction, so the re-pull experiment was necessary to prove it is a real incompatibility between this GGUF and the installed llama-server build. Recording the confirmed crash and the persona's generic re-identification keeps the persona honest about what it serves and prevents anyone from "fixing" the model by re-adding it to the reachable catalog.
