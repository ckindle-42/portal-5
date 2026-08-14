---
id: unit-media-tools-torch-device
kind: mixed
title: "Media tools utils \u2014 torch device selection"
sources:
- type: code
  path: portal/modules/media/tools/utils.py
  commit: 1a0e2df4
claims: []
confidence: high
tags:
- authored-v1
- module
- media
- tools
created_at: 1785794902.9590242
updated_at: 1785794902.9590242
---

`get_torch_device()` is the shared device-selection helper for the
portal_mcp generation servers (TTS via Fish Speech and music via Stable
Audio). It returns `mps`, `cuda`, or `cpu` depending on what the torch build
reports available, so each generation server gets the same device priority
without duplicating the probe.

## Why

Device selection must be consistent across every generation server, and the
priority order — MPS on Apple Silicon first, then CUDA on NVIDIA, then CPU —
matches the hardware the fleet actually runs on. Centralising it here means a
machine with MPS and a machine with CUDA both get the right backend without
each server embedding its own availability checks, and a machine with neither
falls back to CPU rather than crashing.

## Interfaces

`get_torch_device()` takes no arguments and returns one of the three device
strings. It probes `torch.backends.mps.is_available()` before
`torch.cuda.is_available()`, which is why MPS wins on Apple Silicon even
though CUDA checks are historically more common first.
