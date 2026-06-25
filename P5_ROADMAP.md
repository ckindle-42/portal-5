# P5_ROADMAP.md — Portal 5 v7 Future Enhancements

```
Portal 5 v7 Roadmap
===================
Last updated: 2026-06-25
Version: 7.6.0 (production-ready)

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
| P5-FUT-009 | P2 | Model-size-aware admission control (MLX proxy) | MOOT | MLX proxy retired in 3a0c58e; TASK_MLX_RETIRE_TRUEUP_V1. |
| P5-FUT-MATH | P3 | Math/STEM model + persona | DONE | M1: `mlx-community/Qwen2.5-Math-7B-Instruct-4bit` + `mathreasoner` persona + `auto-math` workspace. |
| P5-FUT-REASONING | P2 | Reasoning content passthrough to OWUI | DONE | M1: `reasoning_content` SSE field forwarded; `emits_reasoning: True` flag on workspaces. |
| P5-FUT-PERSONAS-M1 | P3 | 18 frontier-gap personas | DONE | M1: compliance/language/workplace/specialty/vision personas added. |
| P5-FUT-010 | P2 | Abliterated Qwen3.5 Ollama upgrade | DONE | `huihui_ai/qwen3.5-abliterated:9b` is line 1 of ollama-general (TASK_TOOL_SUPPORT_AUDIT_V1, commit de96984). `huihui_ai/Qwen3.6-abliterated:27b` added as V6 larger fallback. |
| P5-FUT-011 | P2 | Uncensored Qwen3.5-35B-A3B MLX conversion | CANCELED | `auto-compliance` primary is now `granite4.1:30b` (IBM GRC-trained, Ollama GGUF, Apache 2.0, BFCL V3 73.7). Granite won the V5 ladder bench over all Qwen3.5 variants. Uncensored MLX conversion no longer needed for this slot. Note: granite-4.1-30b-mxfp4 was the retired MLX variant; the Ollama equivalent is the production model. |
| P5-FUT-012 | P3 | Speech pipeline upgrade (mlx-audio) | DONE | Host-native `scripts/mlx-speech.py` using mlx-audio. Qwen3-TTS (1.7B, 3 variants: CustomVoice, VoiceDesign, Base/Clone) + Qwen3-ASR (1.7B) + Kokoro (82M). Voice cloning from 3s audio, emotion control, voice design from text, 10 languages, streaming. Docker TTS/ASR kept as fallback. |
| P5-FUT-013 | P3 | OMLX evaluation — MLX inference tier upgrade | MOOT | **Update 2026-06-09 (TASK_MLX_RETIRE_TRUEUP_V1):** MLX inference proxy fully retired in commit 3a0c58e. P5-FUT-SPEC (speculative decoding via the MLX proxy) and P5-FUT-009 (MLX admission control) are now MOOT — the proxy they depended on no longer exists. Any future speculative-decoding work targets Ollama's native MTP path instead. |
| P5-FUT-SPEC | P2 | Speculative decoding for large MLX targets | MOOT | **Update 2026-06-09 (TASK_MLX_RETIRE_TRUEUP_V1):** MLX proxy retired. MTP speculative decoding now targets Ollama's native MTP path (llama.cpp b9180+). |
| P5-FUT-015 | P2 | Unified shared workspace | DONE | TASK-WORKSPACE-001. Single `${AI_OUTPUT_DIR}` root mounted into OWUI (uploads overlay) and all participating MCPs (`/workspace`). New `portal_mcp.core.workspace` helper module. AUDIO_STT_ENGINE disabled — voice-input loss documented. Foundation for TASK-TRANSCRIBE-001 and future file-handling MCPs. |
| P5-FUT-014 | P3 | Diarized transcription (speaker-labeled) | DONE | TASK-TRANSCRIBE-001 (built on TASK-WORKSPACE-001 foundation). Host-native `scripts/mlx-transcribe.py` (mlx-whisper + pyannote.audio on MPS) primary on Apple Silicon, port 8924. Docker `whisper_mcp.py` extended with same `transcribe_with_speakers` tool for cross-platform fallback. New `transcriptanalyst` persona in `auto-documents` workspace handles full flow: detects audio attachments, calls tool, formats output, chains to `create_word_document` for docx. Uses `portal_mcp.core.workspace` helpers for file resolution. HF_TOKEN required (gated pyannote models). |
| P5-FUT-PARITY-001 | P2 | Source/verify GGUF for Foundation-Sec-8B + ToolACE-2.5, or formally accept substitutes | DONE | MLX-only specialists lost in 3a0c58e, both now dispositioned. Foundation-Sec RESTORED to auto-blueteam production (TASK_PARITY_FOUNDATION_SEC_V1, first-party fdtn-ai Q8_0 GGUF). ToolACE-2.5 EVALUATED AND DROPPED — granite4.1:8b accepted as the tools-specialist model (no verified ToolACE-2.5 GGUF; self-quant + Ollama tool-template risk not justified). Acceptance of the substitute was an allowed resolution per this item's title. See KNOWN_LIMITATIONS § Model Parity. |
| P5-FUT-PARITY-002 | P3 | Scrub residual MLX-inference references in persona YAML comments | DONE | Done in TASK_PARITY_FOUNDATION_SEC_V1. Dead-proxy comment clauses (mlx_only, mlx_model_hint) removed/replaced with retirement notes across persona YAMLs; verified zero `mlx_only`/`mlx_model_hint` remain. Retained-audio/vision MLX comments (mlx_vlm/mlx_audio/voxtral/granite-speech/nemotron-omni/gemma vision) intentionally preserved — those runtimes are live (:8917/:8918/:8924/:8925). |

---

## Open Items

### Speculative Decoding / MTP — RETIRED (commit 3a0c58e)

The MLX-proxy speculative-decoding and MTP unblock paths described here were removed with the proxy. See the MOOT rows in the table above. Any future work targets Ollama's native path, not MLX.

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

IMPLEMENTED in v6.0.0 (`scripts/mlx-proxy.py`). Note: the MLX proxy was subsequently retired
at commit 3a0c58e — this note is historical. Ollama's native model-load behavior now handles
memory pressure via OLLAMA_MAX_LOADED_MODELS and OLLAMA_MEMORY_LIMIT (see Admin Guide).

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

**Update 2026-05-28 (TASK_OMLX_REEVAL_V2):** oMLX v0.3.12 full re-evaluation completed. KV cache STILL broken (warm 2× slower than cold on 3B and 30B). MTP speedup clears 1.5× gate (1.55×-1.65×). 30B model now loads (memory fix works). 70B borderline (HTTP 507 on cold load). Decision: PROBE_AGAIN_NARROWLY. Status: REMAINS RETIRED. See OMLX_DECISION.md "Re-evaluation 2026-05-28" section and `tests/benchmarks/results/omlx_reeval_20260528T145902Z.md` for detail. Next re-evaluation trigger: MTP stability probe (TASK_OMLX_MTP_STABILITY_V1).

---

### P5-FUT-014-V7: Model Refresh Waterline

TASK_MODEL_REFRESH_V7 (2026-05-27) added 6 bench workspaces (one since
removed from the fleet): bench-voxtral-realtime, bench-voxtral-tts,
bench-granite-speech, bench-qwen36-27b-ud, bench-qwen36-35b-a3b-ud.

**Promotion gates** (each model is bench-only until):

1. `bench-qwen36-{27b,35b-a3b}-ud` → replace stock 4-bit in respective
   bench pins: must show ≥1-point improvement on Creative Coder CC-01
   AND match-or-improve coding-shootout-v2.
2. `bench-granite-speech` → new `auto-transcribe-domain` lane: must
   outperform mlx-whisper-large-v3-turbo on a domain-vocab keyword-biased
   benchmark.
3. `bench-voxtral-realtime` / `bench-voxtral-tts` → defer to dedicated
   P5-FUT-SPEECH-002 speech-shootout task.

---

### P5-FUT-EMBED-001: EmbeddingGemma Migration Seed

Current production: scripts/embedding-server.py with
microsoft/harrier-oss-v1-0.6b on :8917 (ARM64). Candidate:
google/embeddinggemma-300M (outperforms Qwen3-Embedding-0.6B on multiple
MTEB v2 categories at half the size).

Migration blockers (out of scope for V7):

1. LanceDB index at /Volumes/data01/portal5_lance/ is bound to current
   embedding dimensionality. Switching requires full re-ingestion of
   every RAG source under /Volumes/data01/portal5_kb_sources/.
2. Need shadow-index A/B test to validate retrieval quality before flip.
3. Need rollback procedure (keep Harrier index on disk 14 days post-cutover
   with a feature flag in RAG MCP to flip back).

Note: mlx-community/Qwen3-Embedding-0.6B-4bit-DWQ is already in the
default pull list (pre-positioned by an earlier task). Whether the
migration target is EmbeddingGemma or Qwen3-Embedding is itself part of
the P5-FUT-EMBED-001 scope.

---

### P5-FUT-SPEECH-002: Speech-Model Shootout

Current production speech stack: mlx-transcribe.py (mlx-whisper-large-v3-turbo
+ Voxtral-Mini-3B-2507-bf16 lazy-loaded + pyannote 3.1 on MPS, :8924),
mlx-speech.py (Kokoro 82M + Qwen3-TTS Custom/Design/Base on :8918).

V7 added 3 bench-only candidates:

- Voxtral-Mini-4B-Realtime-2602 (streaming ASR, ~570ms TTFT claim)
- Voxtral-4B-TTS-2603 (20 voices × 9 languages)
- Granite-Speech-4.1-2B (#1 OpenASR, keyword biasing)

A dedicated speech-shootout task should:

1. Build a probe driver exercising each model with the same audio corpus
   (multilingual, domain-vocab, streaming-vs-batched).
2. Score on WER, keyword F1, TTFT, and (for TTS) subjective Likert.
3. Produce a Pareto frontier for the speech lane equivalent to bench_tps.py
   for the text lane.
4. Promote winners to production replacement candidates only after the
   Pareto shows clear wins.

bench_tps.py is the wrong tool for this — its text-prompt harness does
not exercise streaming ASR or TTS rendering.

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

*Last updated: 2026-06-25*
*Part of Portal 5 v7 release documentation*
