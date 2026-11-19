---
id: unit-HOWTO-models
historical: true
kind: why
title: "HOWTO \u2014 Models"
sources:
- type: design
  path: docs/HOWTO.md
  section: Models
confidence: high
tags:
- docs
- HOWTO

---

./launch.sh pull-models     # Pull all Ollama models (30-90 min)
./launch.sh refresh-models  # Re-pull models (update existing)
./launch.sh import-gguf <path> [name]  # Import a local .gguf file into Ollama
./launch.sh start-speech    # Start MLX Speech server (Qwen3-TTS + Qwen3-ASR)
./launch.sh stop-speech     # Stop MLX Speech server
