# P5_ROADMAP.md — Portal 5 Future Enhancements

```
Portal 5.2.1+ Roadmap
==================
Last updated: April 7, 2026
Version: 5.2.1 (production-ready)

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
| P5-FUT-006 | P1 | LLM-based intent routing (replaces keyword matching) | FUTURE | Use llama3.2:3b-instruct (already in Ollama) as an intent router. Workspace descriptions + few-shot examples + JSON schema constraint. ~100ms latency, 93-94% accuracy, falls back to keywords on low confidence. See implementation notes. |
| P5-FUT-009 | P2 | Model-size-aware admission control (MLX proxy) | FUTURE | Add `MODEL_MEMORY` dict to `mlx-proxy.py` mapping each model → estimated GB. In `ensure_server()`, compare against `_get_available_memory_gb()` before load. Reject with clear 503 if insufficient. Makes CLAUDE.md coexistence rules self-enforcing — prevents OOM from conflicting model+ComfyUI loads. |

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

Use llama3.2:3b-instruct (already in Ollama) as an intent router. Replaces keyword-based
workspace detection with semantic understanding of user intent.

**Architecture:**
- System prompt: workspace descriptions (grounds the model in what each workspace does)
- Few-shot examples: 3-5 edge cases per workspace (handles "Splunk query" → auto-spl vs auto-coding)
- JSON schema constraint: Ollama grammar-enforced decoding — output is guaranteed valid workspace ID + confidence
- `temperature: 0`, `num_predict: 20`, `num_ctx: 512` — deterministic, fast
- `keep_alive: "-1"` — model stays loaded, no cold-start penalty
- Falls back to existing `_detect_workspace()` keywords on `confidence < 0.5` or timeout

**Expected accuracy:**

| Workspace | + 3 few-shot | + 5 few-shot |
|---|---|---|
| auto-coding | ~95% | ~95% |
| auto-security | ~92% | ~93% |
| auto-spl | ~90% | ~92% |
| auto-reasoning | ~90% | ~91% |
| auto (fallback) | ~97% | ~97% |
| **Overall** | **~93%** | **~94%** |

**Training data loop:**
- Log every routing decision: user message, LLM choice, keyword choice, confidence
- Disagreements between LLM and keywords = labeled training data
- Periodically update few-shot examples from confirmed correct routes
- Fine-tuning path (6+ months): export logs as JSONL, LoRA fine-tune with mlx_lm on Apple Silicon

**Configuration (`.env`):**
```
LLM_ROUTER_ENABLED=true
LLM_ROUTER_MODEL=llama3.2:3b-instruct-q4_K_M
LLM_ROUTER_CONFIDENCE_THRESHOLD=0.5
LLM_ROUTER_TIMEOUT_MS=500
```

**Files changed:**
- `portal_pipeline/router_pipe.py` — add `_route_with_llm()`, keep `_detect_workspace()` as fallback
- `config/routing_examples.json` — few-shot examples (operator-editable)
- `config/routing_descriptions.json` — workspace capability descriptions (operator-editable)
- `tests/unit/test_routing.py` — LLM routing tests with mocked Ollama

### P5-FUT-009: Model-Size-Aware Admission Control (MLX Proxy)

FUTURE: Self-enforcing memory coexistence rules in `scripts/mlx-proxy.py`.
Currently CLAUDE.md coexistence table (e.g. "Qwen3-Coder-Next-4bit (~46GB) + Ollama only —
no concurrent ComfyUI") is documentation only — nothing prevents loading a 46GB model while
ComfyUI is using 18GB, causing OOM.

Implementation:
- `MODEL_MEMORY` dict: model tag → estimated GB (sourced from CLAUDE.md catalog)
- `ensure_server()` pre-flight: `_get_available_memory_gb()` vs `MODEL_MEMORY[model] + headroom`
- Reject with HTTP 503 + actionable message ("Model X needs ~46GB, only 30GB free — stop ComfyUI or unload Ollama first")
- Log rejection as structured event for notification pipeline (P5-027)
- Optional: enrich `/v1/models` response with `memory_estimate_gb` and `safe_concurrent_with`

The existing 10GB generic floor remains as secondary safety net. This replaces ad-hoc
"operator knows" with deterministic admission control.

---

## Score History

| Date | Score | Notes |
|------|-------|-------|
| 2026-03-30 | 100/100 | v5.2.0 — all production items complete |
| 2026-03-30 | 100/100 | v5.2.1-unreleased — P5-FUT-003 (analytics dashboard) + P5-FUT-004 (webhook channel) implemented, verified live |
| 2026-04-04 | 100/100 | v5.2.1 — P5-FUT-005 (weighted keyword routing), S18-S22 acceptance tests, persona prompt/signal fixes, documentation updates |
| 2026-04-07 | 100/100 | P5-FUT-009 (model-size-aware admission control) + P5-FUT-006 (LLM-based intent routing) added to roadmap. P5-FUT-001/002 removed. |

---

*Last updated: 2026-04-07*
*Part of Portal 5.2.1 release documentation*
