---
id: unit-scripts-mlx-speech
kind: mixed
title: "Script \u2014 mlx-speech"
sources:
- type: code
  path: scripts/mlx-speech.py
  commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799536.018086
updated_at: 1785799536.018086
---

Host-native speech server for Apple Silicon using mlx-audio, replacing the Docker kokoro-onnx TTS and faster-whisper ASR with Qwen3-TTS and the MLX speech stack.

## Why

The speech tier runs host-native on Apple Silicon because the Docker image could not match the native Metal path; the server replaces two containerised services with one native one that provides TTS, ASR, voice cloning, and the multi-language support. This is MLX *outside* inference — audio, not chat.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
