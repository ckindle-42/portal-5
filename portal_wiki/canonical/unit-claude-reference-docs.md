---
id: unit-claude-reference-docs
kind: why
title: "CLAUDE.md \u2014 Reference Docs"
sources:
- type: design
  path: CLAUDE.md
  section: Reference Docs
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1785348301.194389
updated_at: 1785348301.194389
---


| Topic | Location |
|---|---|
| Model catalog + memory budgets | `config/backends.yaml` (annotated YAML comments) |
| Persona catalog (currently 138 — `ls config/personas/*.yaml \| wc -l`) | `config/personas/*.yaml` |
| Notification system setup | `docs/ALERTS.md` |
| ComfyUI image setup and archived video status | `docs/COMFYUI_SETUP.md` |
| Speech pipeline (Kokoro + Qwen3-TTS/ASR) | `docs/HOWTO.md` (§ MLX Speech) |
| Voice cloning (fish-speech, optional) | `docs/FISH_SPEECH_SETUP.md` |
| Diarized transcription | `docs/HOWTO.md` (§ Transcription) |
| Claude Code / opencode integration + FastContext explorer | `docs/MCP_DEV_TOOLING.md` |
| Cluster scaling | `docs/CLUSTER_SCALE.md` |
| Admin guide | `docs/ADMIN_GUIDE.md` |

---
