# P5_ROADMAP.md — Portal 5 Future Enhancements

```
Portal 6.0.0 Roadmap
==================
Last updated: April 7, 2026
Version: 6.0.0 (production-ready)

LEGEND: P1=Critical, P2=High, P3=Medium
STATUS: DONE, IN_PROGRESS, FUTURE
```

All v5.0–v5.2 items are marked DONE in CHANGELOG.md. This document tracks
genuinely open future work beyond the current stable release.

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
| P5-FUT-010 | P2 | Abliterated Qwen3.5 Ollama upgrade | FUTURE | Replace `qwen3.5:9b` and `deepseek-r1:32b-q4_k_m` Ollama slots with `huihui_ai/qwen3.5-abliterated` variants (same trusted provider as existing baronllm-abliterated and tongyi-deepresearch-abliterated). Sizes: 9B for coding/documents, 35B-A3B for reasoning/compliance. Uncensored — 0 refusals on standard abliteration benchmarks. |
| P5-FUT-011 | P2 | Uncensored Qwen3.5-35B-A3B MLX conversion | FUTURE | Self-convert `huihui-ai/Huihui-Qwen3.5-35B-A3B-abliterated` to MLX via `mlx_lm.convert` for `auto-compliance` primary slot. Replaces Jackrong Claude-4.6-Opus distillation with native uncensored Qwen3.5 (vision, thinking mode, 262K context). Alternatively use `HauhauCS/Qwen3.5-35B-A3B-Uncensored-HauhauCS-Aggressive` GGUF via Ollama as fallback. |
| P5-FUT-012 | P3 | Speech pipeline upgrade (mlx-audio) | DONE | Host-native `scripts/mlx-speech.py` using mlx-audio. Qwen3-TTS (1.7B, 3 variants: CustomVoice, VoiceDesign, Base/Clone) + Qwen3-ASR (1.7B) + Kokoro (82M). Voice cloning from 3s audio, emotion control, voice design from text, 10 languages, streaming. Docker TTS/ASR kept as fallback. |
| P5-FUT-013 | P3 | OMLX evaluation — MLX inference tier upgrade | FUTURE | Evaluate jundot/omlx (github.com/jundot/omlx, Apache 2.0) as replacement for scripts/mlx-proxy.py. Key benefits: continuous batching (up to 4.14x at 8x concurrency per their benchmarks), SSD KV cache persistence (TTFT 30-90s → 1-3s for repeated contexts), multi-model LRU eviction with pinning, native VLM + embedding + reranker support, OpenAI + Anthropic API compat, DFlash speculative decoding (experimental, Qwen3.5 only). Risks: Must preserve existing admission control (MODEL_MEMORY checks), VLM routing (VLM_MODELS set), big-model-mode orchestration (BIG_MODEL_SET eviction), and mlx-lm<0.31 version pin for qwen3_next architecture. OMLX uses its own mlx-lm fork — version compatibility requires investigation. Approach: Install OMLX alongside existing proxy on a separate port, benchmark same model set, compare TPS and switch latency. Do not replace mlx-proxy.py until parity is confirmed on all workspaces. |

---

## Implementation Notes

### P5-FUT-003: Usage Analytics Dashboard

IMPLEMENTED: `portal5_overview.json` v3 adds 6 new Usage Analytics panels (ids 13-18):
workspace request trends, tokens by workspace, top workspaces, model×workspace matrix, and
current request rate. All use existing Prometheus metrics — no new instrumentation needed.

Per-user analytics remain blocked: Open WebUI does not expose user IDs to the Pipeline.

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

### P5-FUT-013: OMLX Evaluation

**NOT YET STARTED** — spike evaluation only, not a replacement commitment.

**What OMLX offers** (validated from repo, v0.3.x as of 2026-04-20):
- Continuous batching via mlx-lm BatchGenerator (configurable concurrency, default: 8)
- Two-tier KV cache: hot (RAM) + cold (SSD, safetensors format), survives restarts
- Multi-model serving: LLMs, VLMs, embeddings, rerankers in one process
- LRU eviction + model pinning + per-model TTL + process memory enforcement
- OpenAI /v1/chat/completions + Anthropic API compatible
- Native macOS menu bar app (PyObjC, not Electron) OR CLI `omlx serve`
- DFlash speculative decoding (experimental, 3-4x speedup on supported models)
- mlx-audio integration: STT (Whisper, Qwen3-ASR), TTS (Qwen3-TTS, Kokoro)
- Built-in admin dashboard with benchmarking

**What Portal 5 would need to verify**:
1. Can OMLX enforce the MODEL_MEMORY admission control checks?
   - OMLX has `--max-model-memory` and `--max-process-memory` — may cover this
2. Can OMLX replicate the VLM_MODELS routing (mlx_lm ↔ mlx_vlm auto-switch)?
   - OMLX has VLMEngine with auto-detection — likely yes, needs testing
3. Can OMLX handle BIG_MODEL_SET eviction (unload everything, load 46GB model)?
   - OMLX has manual load/unload + LRU eviction — likely yes
4. Does OMLX work with mlx-lm<0.31 pin (qwen3_next architecture)?
   - OMLX uses its own mlx-lm fork — version compatibility unknown
5. Does OMLX respect the 0.0.0.0 binding requirement for LAN access?
   - CLI supports `--host 0.0.0.0` — yes
6. Can OMLX integrate with existing Prometheus metrics?
   - OMLX has persistent stats — may need a metrics bridge
7. Does OMLX's mlx-audio subsystem overlap/conflict with mlx-speech.py?
   - Both use Qwen3-TTS/Kokoro — potential consolidation opportunity

**Evaluation approach**: Install OMLX on host alongside existing mlx-proxy on port 8000
(proxy stays on 8081). Run the same bench_tps.py benchmark against both. Compare TPS,
model switch latency, and memory behavior. If parity + improvement confirmed, plan
migration as a separate task file.

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
