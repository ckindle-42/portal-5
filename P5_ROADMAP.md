# P5_ROADMAP.md — Portal 5 Future Enhancements

```
Portal 6.1.0 Roadmap
==================
Last updated: May 14, 2026
Version: 6.1.0 (production-ready)

LEGEND: P1=Critical, P2=High, P3=Medium
STATUS: DONE, BLOCKED, CANCELED
```

All v5.0–v6.1.0 items are marked DONE in CHANGELOG.md. This document tracks
genuinely open future work. Completed items are kept for reference only.

---

## Future Considerations (Not Yet Implemented)

| ID | Priority | Title | Status | Notes |
|----|----------|-------|--------|-------|
| P5-FUT-003 | P3 | Usage analytics dashboard | DONE | Grafana portal5_overview.json v3: 6 new panels — workspace request trends, tokens by workspace, top workspaces, model×workspace breakdown, request rate. All queries use existing Prometheus metrics. Per-user blocked — Open WebUI doesn't expose user IDs to Pipeline. |
| P5-FUT-004 | P3 | Webhook-based event notifications | DONE | WebhookChannel implemented (portal_pipeline/notifications/channels/webhook.py). Env vars: WEBHOOK_URL, WEBHOOK_HEADERS. POSTs JSON to arbitrary HTTP endpoint on all alert and summary events. Live-verified 2026-03-30. |
| P5-FUT-005 | P2 | Weighted keyword scoring for content-aware routing | DONE | Replaced regex-based `_detect_workspace` with weighted keyword scoring. Each keyword carries weight 1-3 (weak/medium/strong), workspaces have activation thresholds, highest score above threshold wins. Handles overlapping signals naturally (e.g. "exploit in Python" → security wins, not coding). Implemented in v5.2.1. |
| P5-FUT-006 | P1 | LLM-based intent routing (replaces keyword matching) | DONE | DONE in v6.0.0. hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF (uncensored), JSON schema enforcement, keyword fallback on confidence < 0.5 or timeout. |
| P5-FUT-009 | P2 | Model-size-aware admission control (MLX proxy) | DONE | DONE in v6.0.0. MODEL_MEMORY dict (16 entries), MEMORY_HEADROOM_GB (10GB), HTTP 503 with actionable message, unknown-model default. |
| P5-FUT-MATH | P3 | Math/STEM model + persona | DONE | M1: `mlx-community/Qwen2.5-Math-7B-Instruct-4bit` + `mathreasoner` persona + `auto-math` workspace. |
| P5-FUT-REASONING | P2 | Reasoning content passthrough to OWUI | DONE | M1: `reasoning_content` SSE field forwarded; `emits_reasoning: True` flag on workspaces. |
| P5-FUT-PERSONAS-M1 | P3 | 18 frontier-gap personas | DONE | M1: compliance/language/workplace/specialty/vision personas added. |
| P5-FUT-010 | P2 | Abliterated Qwen3.5 Ollama upgrade | DONE | `huihui_ai/qwen3.5-abliterated:9b` is line 1 of ollama-general (TASK_TOOL_SUPPORT_AUDIT_V1, commit de96984). `huihui_ai/Qwen3.6-abliterated:27b` added as V6 larger fallback. |
| P5-FUT-011 | P2 | Uncensored Qwen3.5-35B-A3B MLX conversion | CANCELED | `auto-compliance` primary is now `granite-4.1-30b-mxfp4` (IBM GRC-trained, Apache 2.0, BFCL V3 73.7, 7.8 t/s). Granite won the V5 ladder bench over all Qwen3.5 variants. Uncensored MLX conversion no longer needed for this slot. |
| P5-FUT-012 | P3 | Speech pipeline upgrade (mlx-audio) | DONE | Host-native `scripts/mlx-speech.py` using mlx-audio. Qwen3-TTS (1.7B, 3 variants: CustomVoice, VoiceDesign, Base/Clone) + Qwen3-ASR (1.7B) + Kokoro (82M). Voice cloning from 3s audio, emotion control, voice design from text, 10 languages, streaming. Docker TTS/ASR kept as fallback. |
| P5-FUT-013 | P3 | OMLX evaluation — MLX inference tier upgrade | CANCELED | Full bake-off completed 2026-04-25 (see OMLX_DECISION.md). Decision: RETIRE. KV cache not functional (warm TTFT 31% slower than cold). mlx-proxy wins on TPS and stability. |
| P5-FUT-SPEC | P2 | Speculative decoding for large MLX targets | BLOCKED | Draft models cataloged and proxy logic built, but `speculative_decoding.draft_models: {}` in backends.yaml — disabled because mlx_lm 0.31.2 changed default cache to ArraysCache which is not trimmable. Re-enable when mlx_lm fixes cache trimming. |
| P5-FUT-015 | P2 | Unified shared workspace | DONE | TASK-WORKSPACE-001. Single `${AI_OUTPUT_DIR}` root mounted into OWUI (uploads overlay) and all participating MCPs (`/workspace`). New `portal_mcp.core.workspace` helper module. AUDIO_STT_ENGINE disabled — voice-input loss documented. Foundation for TASK-TRANSCRIBE-001 and future file-handling MCPs. |
| P5-FUT-014 | P3 | Diarized transcription (speaker-labeled) | DONE | TASK-TRANSCRIBE-001 (built on TASK-WORKSPACE-001 foundation). Host-native `scripts/mlx-transcribe.py` (mlx-whisper + pyannote.audio on MPS) primary on Apple Silicon, port 8924. Docker `whisper_mcp.py` extended with same `transcribe_with_speakers` tool for cross-platform fallback. New `transcriptanalyst` persona in `auto-documents` workspace handles full flow: detects audio attachments, calls tool, formats output, chains to `create_word_document` for docx. Uses `portal_mcp.core.workspace` helpers for file resolution. HF_TOKEN required (gated pyannote models). |

---

## Open Items

### P5-FUT-SPEC: Speculative Decoding — Waiting on mlx_lm Cache Fix

Infrastructure is built (draft models in `backends.yaml`, proxy logic in `mlx-proxy.py`) but disabled. `mlx_lm 0.31.2` changed the default cache to `ArraysCache` which is not trimmable — speculative decoding requires a trimmable cache to function. Re-enable by setting `draft_models` in `config/backends.yaml` once the mlx_lm upstream fix lands.

### P5-MTP-001: Multi-Token Prediction Proxy Support (LOW priority)

MTP speculative decoding (3.94× speedup verified at temp=0) requires passing `--draft-model` and `--draft-kind mtp` to `mlx_lm.server`. The proxy does not currently support this. Deprioritized because even with MTP, BF16 path (~12 TPS) is slower than 4-bit MoE alternatives (25–40 TPS). Create TASK_MTP_PROXY_V1.md to implement if this changes.

### workspace-clean Utility (LOW priority)

`${AI_OUTPUT_DIR}` grows unbounded. Planned command `./launch.sh workspace-clean --age=Nd` deletes generated artifacts older than N days. Not yet implemented.

---

## Implementation Notes (completed items)

### P5-FUT-004: Webhook-Based Event Notifications

IMPLEMENTED: `WebhookChannel` (`portal_pipeline/notifications/channels/webhook.py`) sends
JSON POST to any user-defined HTTP endpoint on all alert and daily summary events.
Configure via `WEBHOOK_URL` and optional `WEBHOOK_HEADERS` (JSON object) env vars.
Live-verified: a `config_error` test event was confirmed delivered to a listening endpoint.

### P5-FUT-006: LLM-Based Intent Routing

IMPLEMENTED in v6.0.0 (`portal_pipeline/router_pipe.py`). `_route_with_llm()` uses
`hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF` as a semantic intent classifier, replacing keyword-based
workspace detection for the primary routing path.

**What was built:**
- `_route_with_llm()` in `router_pipe.py` — Ollama grammar-enforced JSON output (guaranteed valid workspace ID + confidence)
- `temperature: 0`, `num_predict: 20`, `num_ctx: 512` — deterministic, fast; `keep_alive: "-1"` keeps model loaded
- Falls back to `_detect_workspace()` on `confidence < 0.5` or timeout
- `config/routing_descriptions.json` — operator-editable workspace capability descriptions
- `config/routing_examples.json` — 25 few-shot routing examples (operator-editable)
- 16 unit tests in `tests/unit/test_routing.py` (mocked Ollama)

**Configuration (`.env`):**
```
LLM_ROUTER_ENABLED=true
LLM_ROUTER_MODEL=hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF
LLM_ROUTER_CONFIDENCE_THRESHOLD=0.5
LLM_ROUTER_TIMEOUT_MS=500
LLM_ROUTER_OLLAMA_URL=http://localhost:11434
```

### P5-FUT-009: Model-Size-Aware Admission Control (MLX Proxy)

IMPLEMENTED in v6.0.0 (`scripts/mlx-proxy.py`). The CLAUDE.md coexistence table is now
self-enforcing — the proxy rejects model loads that would exceed available memory before
evicting the current model.

**What was built:**
- `MODEL_MEMORY` dict: 16 model tags → estimated GB (sourced from CLAUDE.md catalog)
- `_check_memory_for_model()`: pre-flight check in `ensure_server()` before any model switch
- Rejects with HTTP 503 + actionable message (e.g. "Model needs ~46GB, only 30GB free — stop ComfyUI or unload Ollama first")
- `MEMORY_HEADROOM_GB` env var replaces the hardcoded 10GB floor
- `MLX_MEMORY_UNKNOWN_DEFAULT_GB` env var controls the assumed size for unrecognized models
- 9 unit tests in `tests/unit/test_mlx_proxy.py` (mocked memory reads)

**Configuration (`.env`):**
```
MLX_MEMORY_HEADROOM_GB=10
MLX_MEMORY_UNKNOWN_DEFAULT_GB=20
```

---

### P5-FUT-013: OMLX Evaluation — CANCELED

Full bake-off completed 2026-04-25. Decision: **RETIRE**. See `OMLX_DECISION.md` for full results. KV cache persistence not functional (warm TTFT 31% *slower* than cold). mlx-proxy retains the production inference role.

---

## Score History

| Date | Score | Notes |
|------|-------|-------|
| 2026-03-30 | 100/100 | v5.2.0 — all production items complete |
| 2026-03-30 | 100/100 | v5.2.1-unreleased — P5-FUT-003 (analytics dashboard) + P5-FUT-004 (webhook channel) implemented, verified live |
| 2026-04-04 | 100/100 | v5.2.1 — P5-FUT-005 (weighted keyword routing), S18-S22 acceptance tests, persona prompt/signal fixes, documentation updates |
| 2026-04-07 | 100/100 | P5-FUT-009 (model-size-aware admission control) + P5-FUT-006 (LLM-based intent routing) added to roadmap. P5-FUT-001/002 removed. |
| 2026-04-07 | 100/100 | v6.0.0 — P5-FUT-006 (LLM intent routing) + P5-FUT-009 (MLX admission control) implemented |

---

*Last updated: 2026-04-07*
*Part of Portal 6.0.0 release documentation*
