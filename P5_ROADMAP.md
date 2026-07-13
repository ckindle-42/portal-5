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
| P5-FUT-PARITY-001 | P2 | Source/verify GGUF for Foundation-Sec-8B + ToolACE-2.5, or formally accept substitutes | DONE | MLX-only specialists lost in 3a0c58e, both now dispositioned. Foundation-Sec RESTORED to auto-security's 'blueteam' variant production (TASK_PARITY_FOUNDATION_SEC_V1, first-party fdtn-ai Q8_0 GGUF). ToolACE-2.5 EVALUATED AND DROPPED — granite4.1:8b accepted as the tools-specialist model (no verified ToolACE-2.5 GGUF; self-quant + Ollama tool-template risk not justified). Acceptance of the substitute was an allowed resolution per this item's title. See KNOWN_LIMITATIONS § Model Parity. |
| P5-FUT-PARITY-002 | P3 | Scrub residual MLX-inference references in persona YAML comments | DONE | Done in TASK_PARITY_FOUNDATION_SEC_V1. Dead-proxy comment clauses (mlx_only, mlx_model_hint) removed/replaced with retirement notes across persona YAMLs; verified zero `mlx_only`/`mlx_model_hint` remain. Retained-audio/vision MLX comments (mlx_vlm/mlx_audio/voxtral/granite-speech/nemotron-omni/gemma vision) intentionally preserved — those runtimes are live (:8917/:8918/:8924/:8925). |
| P5-FUT-PROMPT-GUARD-INLINE | P3 | Input-side prompt-injection guardrail (Llama-Prompt-Guard-86M) |  | Feature request from V13 model review (2026-07-08). Meta's Llama-Prompt-Guard-86M (86M classifier, meta-llama repo) classifies input for prompt-injection attempts. Would require new pipeline stage under portal/platform/inference/router/ (input-side filter, runs before router) — this is architecture work, NOT model intake, so not a workspace. Related: V13-D intake of Meta-SecAlign-8B addresses the SAME threat class (prompt-injection) but at the model layer rather than the pipeline layer; these are complementary, not substitutes. Consider building after reasoning-depth eval framework lands (see DESIGN_REASONING_DEPTH_V1.md) since an input-side guard is a natural companion piece. |
| P5-FUT-TOOL-PRESELECT | P2 | Query-level tool-schema preselection | BUILT NOT DEPLOYED — closed | TASK_BUILD_TOOL_PRESELECT_V1 (2026-07-12). Module built at `portal/platform/inference/tool_preselect/` (config, prompt/parser, Ollama-call preselector, metrics, self-healing auto-disable state — 54 unit tests, 90% coverage), feature-flagged off (`PORTAL5_TOOL_PRESELECT=0`). Halted at the Phase 2 gate, then given a full extended diagnostic pass the same day before closing for good: 3 distinct models (both original 1B candidates plus `qwen2.5:1.5b`, this project's own proven compact router-bench performer) across 7 elicitation techniques (natural-language prompt, grammar-constrained JSON, system-prompt framing, `think:false` reasoning suppression, single-choice simplification, few-shot in-context examples, position-bias control) all converge on the same negative result — no sub-2B model tested can reliably rank tools by relevance, regardless of prompting or output-format strategy. See KNOWN_LIMITATIONS.md § P5-TOOLPRESELECT-001 for the full per-technique record. No pipeline integration, observability, or validation harness (Phases 3-5) built — would sit atop a preselector proven not to work. Revisit only with a materially larger (3B+) or purpose-built tool-ranking model; the built Phase 1+2 code is reusable as-is. |
| P5-FUT-WS-FROM-MODULE | P3 | Derive served workspace from `module` (retire `workspace_model`) |  | Follow-on from surface collapse (BUILD_PROGRAM_COLLAPSE_V1 Phase 8, commit 214a16f). DESIGN_COLLAPSE_V1 §D6 called for retiring persona `workspace_model`; the build kept it because `module` alone is ambiguous for modules that map to several post-collapse workspaces (general → auto-daily/auto-math/auto-reasoning/tools-specialist; media → auto-creative/-music/-video/-audio). Retiring `workspace_model` needs a disambiguator: either a `default_workspace` per module (in unit-module-<name>) plus a persona-level `mode`/`role`/`variant` selector that the router resolves to a concrete workspace, OR keeping `workspace_model` as the disambiguator and just documenting it as the canonical field (i.e. accept the field, close the "retire" intent). Low urgency — `workspace_model` works correctly today. Decide direction before building. |
| P5-FUT-MODEL-CHAINWALK | P2 | Live `preferred_models` chain-walk (auto-failover) |  | Follow-on from surface collapse (BUILD_PROGRAM_COLLAPSE_V1 Phase 8, commit 214a16f). Today `preferred_models` is advisory metadata; `?model=<hint>` is the only way to act on it, and it's manual. This item makes the chain automatic: a live-availability check (poll Ollama's loaded/pullable model set) walks each persona's `preferred_models` in order and serves the first available, so a persona degrades gracefully when its lead model isn't resident instead of failing or forcing a manual override. Requires: (1) an availability source (Ollama `/api/tags` + resident-model introspection, cached with a short TTL — event-driven refresh preferred over a fixed poll interval per project convention), (2) chain-walk resolution in the router's model-selection path (reuse the bounded synthetic-cache-merge pattern from `_resolve_model_override` in preinject.py), (3) a metric for which chain position served (observability into how often the lead model was unavailable). This is the piece that turns the collapse's `preferred_models` investment into a working reliability feature. P2 because it directly affects served-request success rate. |
| P5-FUT-ALIAS-SHIM-RETIRE | P3 | Retire the legacy workspace-alias shim fully (resolve the 3 remaining holdouts) |  | **IN PROGRESS** (CLOSEOUT_ALIAS_REMOVAL.md, 2026-07-13 finish pass). Holdout 1 (Incalmo) done: `docker-compose.lab.yml`'s `OPENAI_MODEL` default migrated to canonical `auto-security::redteam`. Holdout 2 (opencode) in progress: 8 new + 3 reused thin variant-personas created, `/v1/models` now advertises `ide_expose: true` personas, `opencode.jsonc`'s 20-entry picker re-keyed to persona slugs/bare base ids (no more `auto-coding-agentic`/`auto-redteam`/etc. as picker keys) — `pipeline_mcp.py`'s `get_workspace_recommendation()` and the CLI docs/wrappers (`MCP_DEV_TOOLING.md`, `cc-local.sh`, `oc-portal.sh`) migration still pending. Holdout 3 (security bench harness — thread `variant` through `call_pipeline`/`call_pipeline_exec`, re-key `PER_WORKSPACE_TIMEOUT`/`EXECUTION_WORKSPACES` to canonical `::` strings) not yet started. Once all 3 are fully migrated, the plan is a real live-traffic deprecation trip (`PORTAL_ALIAS_TRIP=1` on the running server, zero `ALIAS_RESOLVED` across every path), then delete `_LEGACY_WORKSPACE_ALIASES`/`_resolve_legacy_workspace_alias`'s alias branch (keep `::` unpacking) and tighten check AT into a hard zero-live-alias assertion. See `docs/_archive_execdocs/PHASE6_TRIP_FINDINGS_20260713.md` for the original investigation. |

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
