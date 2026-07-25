---
id: unit-readme-speech-text-to-speech-speech-to-text
kind: what
title: "README \u2014 Speech (Text-to-Speech & Speech-to-Text)"
sources:
- type: doc
  path: README.md
  commit: 05e42ec2
  section: Speech (Text-to-Speech & Speech-to-Text)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.687758
updated_at: 1784946220.687758
---

Portal 5 includes a native MLX speech server on Apple Silicon with:
- **Kokoro TTS** — fast, high-quality English TTS (200+ voices)
- **Qwen3-TTS** — 10 languages, voice cloning, voice design, emotion control
- **Qwen3-ASR** — speech-to-text via MLX

```bash
./launch.sh start-speech    # Start MLX speech server (Apple Silicon)
./launch.sh stop-speech     # Stop MLX speech server
./launch.sh mlx-status      # Check MLX component status (includes speech)
```

> **Kokoro TTS dependencies:** The Kokoro backend requires additional Python
> packages that are not installed automatically. Install them before using Kokoro:
> ```bash
> pip install misaki num2words spacy phonemizer
> python3 -m spacy download en_core_web_sm
> ```
> Qwen3-TTS and Qwen3-ASR work without these dependencies.

---
