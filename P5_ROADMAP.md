# P5_ROADMAP.md — Portal 5 v7 Future Enhancements

<!-- WIKI:GENERATED unit=unit-p5-roadmap-p5-roadmap-md-portal-5-v7-future-enhancements -->
```
Portal 5 v7 Roadmap
===================
Last updated: 2026-06-25
Version: 8.0.0 (production-ready)

LEGEND: P1=Critical, P2=High, P3=Medium
STATUS: DONE, BLOCKED, CANCELED
```

All v5.0–v6.1.0 items are marked DONE in CHANGELOG.md. This document tracks
genuinely open future work. Completed items are kept for reference only.

---
<!-- /WIKI:GENERATED -->

---

## Future Considerations (Not Yet Implemented)

<!-- WIKI:GENERATED unit=unit-p5-roadmap-future-considerations-not-yet-implemented -->
This table contains only genuinely open work. Completed, canceled, and retired
items remain available through git history and their dedicated canonical units;
they are not kept in the active queue.

| ID | Priority | Title | Status | Next decision or action |
|----|----------|-------|--------|-------------------------|
| P5-FUT-PROMPT-GUARD-INLINE | P3 | Input-side prompt-injection guardrail | OPEN | Scope an input filter under `portal/platform/inference/router/`; coordinate it with the model-layer security controls. |
| P5-FUT-WS-FROM-MODULE | P3 | Derive served workspace from `module` | DECISION NEEDED | Choose a module-level disambiguator or formally retain `workspace_model` as the canonical selector. |
| P5-FUT-MODEL-CHAINWALK | P2 | Live `preferred_models` chain-walk | OPEN | Add cached Ollama availability, bounded chain resolution, and a served-chain-position metric. |
| P5-FUT-RBP-MCP-SECURITY | P2 | MCP Security Assessment challenge class | DESIGN NEEDED | Define malicious/instrumented MCP lab fixtures and scoring for tool-layer compromise. |
| P5-FUT-RBP-LLM-SECURITY-EXPAND | P2 | Expand OWASP LLM Top 10 coverage | DESIGN NEEDED | Extend `portal/modules/security/core/llm_redteam.py` beyond the current thin probe set and replace substring-only grading. |
| P5-FUT-ABLATION-CAPTURE-PERSIST | P2 | Persist Expert/Hunter handoffs in the corpus driver | OPEN | Save each handoff beside the existing raw verdict so future model-swap studies do not require a full rerun. |
<!-- /WIKI:GENERATED -->

---

### Speculative Decoding / MTP — RETIRED (commit 3a0c58e)

<!-- WIKI:GENERATED unit=unit-p5-roadmap-speculative-decoding-mtp-retired-commit-3a0c58e -->
The MLX-proxy speculative-decoding and MTP unblock paths described here were removed with the proxy. See the MOOT rows in the table above. Any future work targets Ollama's native path, not MLX.
<!-- /WIKI:GENERATED -->

---

### workspace-clean Utility (LOW priority)

<!-- WIKI:GENERATED unit=unit-p5-roadmap-workspace-clean-utility-low-priority -->
`${AI_OUTPUT_DIR}` grows unbounded. Planned command `./launch.sh workspace-clean --age=Nd` deletes generated artifacts older than N days. Not yet implemented.

---
<!-- /WIKI:GENERATED -->

---

### P5-FUT-004: Webhook-Based Event Notifications

<!-- WIKI:GENERATED unit=unit-p5-roadmap-p5-fut-004-webhook-based-event-notifications -->
IMPLEMENTED: `WebhookChannel` (`portal/platform/inference/notifications/channels/webhook.py`) sends
JSON POST to any user-defined HTTP endpoint on all alert and daily summary events.
Configure via `WEBHOOK_URL` and optional `WEBHOOK_HEADERS` (JSON object) env vars.
Live-verified: a `config_error` test event was confirmed delivered to a listening endpoint.
<!-- /WIKI:GENERATED -->

---

### P5-FUT-006: LLM-Based Intent Routing

<!-- WIKI:GENERATED unit=unit-p5-roadmap-p5-fut-006-llm-based-intent-routing -->
IMPLEMENTED in v6.0.0. `_route_with_llm()` now lives in
`portal/platform/inference/router/routing.py` and uses the model selected by
`LLM_ROUTER_MODEL` as the primary semantic intent classifier.

**What was built:**
- `_route_with_llm()` in `router/routing.py` — Ollama grammar-enforced JSON output (guaranteed valid workspace ID + confidence)
- `temperature: 0`, `num_predict: 20`, `num_ctx: 512` — deterministic, fast; `keep_alive: "-1"` keeps model loaded
- Falls back to `_detect_workspace()` on `confidence < 0.5` or timeout
- `config/routing_descriptions.json` — operator-editable workspace capability descriptions
- `config/routing_examples.json` — 25 few-shot routing examples (operator-editable)
- 16 unit tests in `tests/unit/test_routing.py` (mocked Ollama)

**Configuration (`.env`):**
```
LLM_ROUTER_ENABLED=true
LLM_ROUTER_MODEL=hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M
LLM_ROUTER_CONFIDENCE_THRESHOLD=0.5
LLM_ROUTER_TIMEOUT_MS=1000
LLM_ROUTER_OLLAMA_URL=http://host.docker.internal:11434
```
<!-- /WIKI:GENERATED -->

---

### P5-FUT-009: Model-Size-Aware Admission Control (MLX Proxy)

<!-- WIKI:GENERATED unit=unit-p5-roadmap-p5-fut-009-model-size-aware-admission-control-mlx-proxy -->
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
<!-- /WIKI:GENERATED -->

---

### P5-FUT-013: OMLX Evaluation — CANCELED

<!-- WIKI:GENERATED unit=unit-p5-roadmap-p5-fut-013-omlx-evaluation-canceled -->
Full bake-off completed 2026-04-25. Decision: **RETIRE**. See `OMLX_DECISION.md` for full results. KV cache persistence not functional (warm TTFT 31% *slower* than cold). mlx-proxy retains the production inference role.

**Update 2026-05-28 (TASK_OMLX_REEVAL_V2):** oMLX v0.3.12 full re-evaluation completed. KV cache STILL broken (warm 2× slower than cold on 3B and 30B). MTP speedup clears 1.5× gate (1.55×-1.65×). 30B model now loads (memory fix works). 70B borderline (HTTP 507 on cold load). Decision: PROBE_AGAIN_NARROWLY. Status: REMAINS RETIRED. See OMLX_DECISION.md "Re-evaluation 2026-05-28" section and `tests/benchmarks/results/omlx_reeval_20260528T145902Z.md` for detail. Next re-evaluation trigger: MTP stability probe (TASK_OMLX_MTP_STABILITY_V1).

---
<!-- /WIKI:GENERATED -->

---

### P5-FUT-014-V7: Model Refresh Waterline

<!-- WIKI:GENERATED unit=unit-p5-roadmap-p5-fut-014-v7-model-refresh-waterline -->
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
<!-- /WIKI:GENERATED -->

---

### P5-FUT-EMBED-001: EmbeddingGemma Migration Seed

<!-- WIKI:GENERATED unit=unit-p5-roadmap-p5-fut-embed-001-embeddinggemma-migration-seed -->
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
<!-- /WIKI:GENERATED -->

---

### P5-FUT-SPEECH-002: Speech-Model Shootout

<!-- WIKI:GENERATED unit=unit-p5-roadmap-p5-fut-speech-002-speech-model-shootout -->
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
<!-- /WIKI:GENERATED -->

---

## Score History

<!-- WIKI:GENERATED unit=unit-p5-roadmap-score-history -->
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
<!-- /WIKI:GENERATED -->

---
