---
id: unit-p5-roadmap-future-considerations-not-yet-implemented
kind: what
title: "P5_ROADMAP \u2014 Future Considerations (Not Yet Implemented)"
sources:
- type: doc
  path: P5_ROADMAP.md
  commit: 05e42ec2
  section: Future Considerations (Not Yet Implemented)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.589484
updated_at: 1784946220.589484
---

| ID | Priority | Title | Status | Notes |
|----|----------|-------|--------|-------|
| P5-FUT-003 | P3 | Usage analytics dashboard | DONE | Grafana portal5_overview.json v3: 6 new panels — workspace request trends, tokens by workspace, top workspaces, model×workspace breakdown, request rate. All queries use existing Prometheus metrics. Per-user blocked — Open WebUI doesn't expose user IDs to Pipeline. |
| P5-FUT-004 | P3 | Webhook-based event notifications | DONE | WebhookChannel implemented (portal_pipeline/notifications/channels/webhook.py). Env vars: WEBHOOK_URL, WEBHOOK_HEADERS. POSTs JSON to arbitrary HTTP endpoint on all alert and summary events. Live-verified 2026-03-30. |
| P5-FUT-005 | P2 | Weighted keyword scoring for content-aware routing | DONE | Replaced regex-based `_detect_workspace` with weighted keyword scoring. Each keyword carries weight 1-3 (weak/medium/strong), workspaces have activation thresholds, highest score above threshold wins. Handles overlapping signals naturally (e.g. "exploit in Python" → security wins, not coding). Implemented in v5.2.1. |
| P5-FUT-006 | P1 | LLM-based intent routing (replaces keyword matching) | DONE | DONE in v6.0.0. Original: `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF`. Upgraded (router bench 2026-06-17): PRIMARY=`gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M` (82.2% acc, ~840ms); STANDBY=`llama3.2:3b`; FALLBACK=`qwen2.5:1.5b`. Selectable via `LLM_ROUTER_MODEL` in `.env`. |
| P5-FUT-009 | P2 | Model-size-aware admission control (MLX proxy) | MOOT | MLX proxy retired in 3a0c58e; TASK_MLX_RETIRE_TRUEUP_V1. |
| P5-FUT-MATH | P3 | Math/STEM model + persona | DONE | M1: `mlx-community/Qwen2.5-Math-7B-Instruct-4bit` + `mathreasoner` persona + `auto-math` workspace. V8 update: replaced by `phi4-mini-reasoning` (RL-trained, emits_reasoning=True — see P5-MATH-001 in KNOWN_LIMITATIONS resolved). |
| P5-FUT-REASONING | P2 | Reasoning content passthrough to OWUI | DONE | M1: `reasoning_content` SSE field forwarded; `emits_reasoning: True` flag on workspaces. |
| P5-FUT-PERSONAS-M1 | P3 | 18 frontier-gap personas | DONE | M1: compliance/language/workplace/specialty/vision personas added. |
| P5-FUT-010 | P2 | Abliterated Qwen3.5 Ollama upgrade | DONE | `huihui_ai/qwen3.5-abliterated:9b` is line 1 of ollama-general (TASK_TOOL_SUPPORT_AUDIT_V1, commit de96984). `huihui_ai/Qwen3.6-abliterated:27b` added as V6 larger fallback. |
| P5-FUT-011 | P2 | Uncensored Qwen3.5-35B-A3B MLX conversion | CANCELED | `auto-compliance` primary is now `granite4.1:30b` (IBM GRC-trained, Ollama GGUF, Apache 2.0, BFCL V3 73.7). Granite won the V5 ladder bench over all Qwen3.5 variants. Uncensored MLX conversion no longer needed for this slot. Note: granite-4.1-30b-mxfp4 was the retired MLX variant; the Ollama equivalent is the production model. |
| P5-FUT-012 | P3 | Speech pipeline upgrade (mlx-audio) | DONE | Host-native `scripts/mlx-speech.py` using mlx-audio. Qwen3-TTS (1.7B, 3 variants: CustomVoice, VoiceDesign, Base/Clone) + Qwen3-ASR (1.7B) + Kokoro (82M). Voice cloning from 3s audio, emotion control, voice design from text, 10 languages, streaming. Docker TTS/ASR kept as fallback. |
| P5-FUT-013 | P3 | OMLX evaluation — MLX inference tier upgrade | MOOT | **Update 2026-06-09 (TASK_MLX_RETIRE_TRUEUP_V1):** MLX inference proxy fully retired in commit 3a0c58e. P5-FUT-SPEC (speculative decoding via the MLX proxy) and P5-FUT-009 (MLX admission control) are now MOOT — the proxy they depended on no longer exists. Any future speculative-decoding work targets Ollama's native MTP path instead. |
| P5-FUT-SPEC | P2 | Speculative decoding for large MLX targets | MOOT | **Update 2026-06-09 (TASK_MLX_RETIRE_TRUEUP_V1):** MLX proxy retired. MTP speculative decoding now targets Ollama's native MTP path (llama.cpp b9180+). |
| P5-FUT-015 | P2 | Unified shared workspace | DONE | TASK-WORKSPACE-001. Single `${AI_OUTPUT_DIR}` root mounted into OWUI (uploads overlay) and all participating MCPs (`/workspace`). New `portal_mcp.core.workspace` helper module. AUDIO_STT_ENGINE disabled — voice-input loss documented. Foundation for TASK-TRANSCRIBE-001 and future file-handling MCPs. |
| P5-FUT-014 | P3 | Diarized transcription (speaker-labeled) | DONE | TASK-TRANSCRIBE-001 (built on TASK-WORKSPACE-001 foundation). Host-native `scripts/mlx-transcribe.py` (mlx-whisper + pyannote.audio on MPS) primary on Apple Silicon, port 8924. Docker `whisper_mcp.py` extended with same `transcribe_with_speakers` tool for cross-platform fallback. New `transcriptanalyst` persona in `auto-documents` workspace handles full flow: detects audio attachments, calls tool, formats output, chains to `create_word_document` for docx. Uses `portal_mcp.core.workspace` helpers for file resolution. HF_TOKEN required (gated pyannote models). |
| P5-FUT-PARITY-001 | P2 | Source/verify GGUF for Foundation-Sec-8B + ToolACE-2.5, or formally accept substitutes | DONE | MLX-only specialists lost in 3a0c58e, both now dispositioned. Foundation-

[Content truncated — see full doc]
