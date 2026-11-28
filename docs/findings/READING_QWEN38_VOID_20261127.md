# Finding: `auto-compliance::reading-qwen38` Probe Void — oMLX 100k Prefill Exceeds 900s Turn Budget

- **Date:** 2026-11-27
- **Brief:** `coding_task/BRIEF_READING_QWEN38_VOID_20261127.md`
- **Probe commit:** `3d6534f673857817034e2a73627304dc73baa001`
- **Artifacts:** `portal/modules/compliance/data/private/local/reports/compliance/acceptance/3d6534f673857817034e2a73627304dc73baa001/workspace__auto-compliance-reading-qwen38__*.json`
- **Verdict:** **Stop condition triggered (oMLX / 27B dense prefill speed limitation — incumbent stays).** The Pipeline setup, `tool_choice: required`, `think: false`, `reasoning_effort: medium`, compliance MCP dispatch, and ~100k material delivery all worked identically to the incumbent. No config or code fix in the Pipeline can make `Qwen3.8-27B-oQ4e-mtp` prefill ~95–100k tokens on oMLX inside the 900s product turn budget.

## 1. Root Cause

The harness reported `prompt_tokens_high_water` of `4466–4563` and empty (or hop-1-preamble-only) answers because **every turn aborted at the 900.0s harness budget (`TURN_BUDGET_S=900`, `scripts/compliance_acceptance.py:619`) while oMLX was still prefilling hop 2 (~100k tokens)**. Because hop 2 never emitted a single token or usage chunk before `client_disconnect`, the harness only ever recorded hop 1's usage.

On a quiet host with zero memory throttling (`parent` hop 2), `Qwen3.8-27B-oQ4e-mtp` (27B dense hybrid Gated DeltaNet + attention on oMLX `VLMBatchedEngine`) prefilled **95,605 new tokens in 1,100.03s (86.9 tok/s)**:

- **Hop 1 (`parent`, 4,466 tokens, cold):** 35.28s TTFT (**126.6 tok/s**), `finish_reason=tool_calls` — clean tool calls `['compliance_context', 'compliance_search']`.
- **Hop 2 (`parent`, 100,064 tokens, 4,459 reused / 95,605 new):** **1,100.03s TTFT (18m 20s, 86.9 tok/s)** — exceeded the 900.0s turn budget by 200s before generating a single token.
- **Cascading pileup:** After the harness disconnected at 900.56s (`20:28:51`), oMLX did not cancel in-flight chunked prefill `addf832b` (it ran until `20:33:28`, 277s past disconnect). Subsequent turns (`choice`, `interval`, `read_check`) queued behind orphaned prefills and triggered `adaptive_prefill_throttle` (`chunk 2048 -> 1024`, `usage 32.21–32.46GB vs sizing target 38.43–39.13GB`), pushing `choice` hop 2 to **1,319.46s TTFT (22m 00s, 72.1 tok/s)**.

This matches the independently measured cold-prefill floor for `Qwen3.8-27B-oQ4e-mtp` on this M4 Pro 64 GB host (`docs/findings/TURN_LATENCY_CHURN_AUDIT_20261126.md` §Q1/Q4: `~126–155 tok/s` at 4–11k tokens, degrading to ~87 tok/s at 100k).

## 2. Hypotheses Ruled Out

| Hypothesis | Finding | Evidence |
|---|---|---|
| Hop 1 `tool_choice: required` unsupported/ignored on oMLX | **Ruled out** | 4/4 turns produced valid tool calls on hop 1 (`finish_reason=tool_calls`). `followup_tool_choice` (`portal/platform/inference/router/tool_repeat.py:319`) transitioned hop 2 to `"auto"`. |
| Runaway reasoning (`reasoning_effort: xhigh` / `think` leak) | **Ruled out** | All 4 traces record `options_applied.enable_thinking=false`, `options_applied.reasoning_effort="medium"`, `reasoning_tokens=0`, `reasoning_chars=0`. Hop 1 decode was 52–127 tokens; hop 2 decode (when it finished on oMLX) was 57–75 tokens. |
| Compliance MCP call hung | **Ruled out** | `compliance_context` completed in `0.42s–0.46s` (`tool_s: 0.417882` on `choice`, `0.462212` on `read_check`); `compliance_search` on `parent` took `10.78s`. |
| Material payload dropped or truncated before oMLX | **Ruled out** | oMLX received `100,064` (`parent`), `99,633` (`choice`), `104,830` (`interval`), and `99,732` (`read_check`) prompt tokens on hop 2. The 1 `Context fit ... shrunk=tool[6] 335,379→328,212 chars` line occurred only on `interval` because the model called `compliance_context` twice in hop 1. |
| Why `interval` and `read_check` passed `answer_nonempty` | **Explained** | Hop 1 emitted short preamble text alongside its tool call (103 chars on `interval`, 150 chars on `read_check`), which streamed before hop 2 stalled in prefill. |

## 3. Quoted Log Evidence

### oMLX (`~/.omlx/logs/server.log`, 2026-11-27 20:14–21:18)

`parent` hop 1 and hop 2 (quiet host, zero throttling):
```text
2026-11-27 20:14:39,596 - omlx.server - INFO - [-] - Chat completion: model=Qwen3.8-27B-oQ4e-mtp, 89 tokens in 37.92s (33.7 tok/s), prompt: 4466, finish_reason=tool_calls, max_tokens=24576, request_max_tokens=24576, stream_model_ttft=35.28s, stream_visible_ttft=36.84s
2026-11-27 20:14:51,261 - omlx.scheduler - INFO - [-] - prefix cache: request addf832b-2a65-40b0-944c-0aed13c9656e re-prefills 95605 of 100064 tokens (reused 4459); closest stored sequence 19dbdd99-2cff-4ee9-bf40-267dbce9180c shares the first 4459 of 4459 comparable tokens before diverging
2026-11-27 20:14:51,466 - omlx.scheduler - INFO - [-] - Reserved prefill capacity for 100064 tokens across 16 caches (+5.84GB)
2026-11-27 20:33:11,336 - omlx.patches.mlx_lm_mtp.batch_generator - INFO - [-] - MTP path activated for uid=1 (model has mtp_forward, batch=1, primed=100064)
2026-11-27 20:33:28,773 - omlx.server - INFO - [-] - Chat completion: model=Qwen3.8-27B-oQ4e-mtp, 57 tokens in 1117.62s (3.2 tok/s), prompt: 100064, finish_reason=tool_calls, max_tokens=24576, request_max_tokens=24576, stream_model_ttft=1100.03s, stream_visible_ttft=1117.61s
```

`choice` hop 1 (queued behind orphaned `parent` hop 2) and hop 2 (throttled when `interval` overlapped):
```text
2026-11-27 20:33:21,321 - omlx.server - INFO - [-] - Chat completion: model=Qwen3.8-27B-oQ4e-mtp, 52 tokens in 269.40s (6.9 tok/s), prompt: 4497, finish_reason=tool_calls, max_tokens=24576, request_max_tokens=24576, stream_model_ttft=261.88s, stream_visible_ttft=269.40s
2026-11-27 20:33:22,944 - omlx.scheduler - INFO - [-] - prefix cache: request 53222463-54ec-46ea-8186-cbf51e4cb7b6 re-prefills 95143 of 99633 tokens (reused 4490); closest stored sequence 73d46eda-6018-4fb7-adf6-586d7388d30a shares the first 4490 of 4490 comparable tokens before diverging
2026-11-27 20:46:22,638 - omlx.scheduler - INFO - [-] - Prefill throttled for 53222463-54ec-46ea-8186-cbf51e4cb7b6: chunk 2048 -> 1024 (usage 32.21GB vs sizing target 38.43GB, dynamic ceiling 41.77GB, per_token=3237.7KB, floor=32).
2026-11-27 20:55:30,270 - omlx.server - INFO - [-] - Chat completion: model=Qwen3.8-27B-oQ4e-mtp, 75 tokens in 1328.34s (8.4 tok/s), prompt: 99633, finish_reason=tool_calls, max_tokens=24576, request_max_tokens=24576, stream_model_ttft=1319.46s, stream_visible_ttft=1328.34s
```

### Pipeline (`docker logs portal5-pipeline`)

```text
INFO:portal.platform.inference.router.streaming:Stream routing: workspace=auto-compliance::reading-qwen38 backend=omlx-reasoning model=Qwen3.8-27B-oQ4e-mtp (1/12 candidates)
INFO:portal.platform.inference.router.streaming:Tool loop hop=1/5 workspace=auto-compliance::reading-qwen38 tools_called=['compliance_context', 'compliance_search']
INFO:portal.platform.inference.router.streaming:Tool loop hop=1/5 workspace=auto-compliance::reading-qwen38 tools_called=['compliance_context']
INFO:portal.platform.inference.router.streaming:Tool loop hop=1/5 workspace=auto-compliance::reading-qwen38 tools_called=['compliance_context', 'compliance_context']
WARNING:portal.platform.inference.router.context_budget:Context fit: workspace=auto-compliance::reading-qwen38 model=Qwen3.8-27B-oQ4e-mtp engine=omlx estimated=108417→106369 tokens limit=131072 prompt_budget=106496 shrunk=tool[6] 335,379→328,212 chars
INFO:portal.platform.inference.router.streaming:Tool loop hop=1/5 workspace=auto-compliance::reading-qwen38 tools_called=['compliance_context']
```

### Incumbent Comparison (same oMLX server, 2026-11-27 19:06–19:24, commit `e3cd1d1ec`)

`mlx-community--gemma-4-26b-a4b-it-4bit` is a **26B-A4B MoE (4B active)** model; on the same ~98k–100k dual-document payloads it prefilled **5.0× faster** and finished every turn well inside 900s:

```text
2026-11-27 19:10:29,747 - omlx.server - INFO - [-] - Chat completion: model=mlx-community--gemma-4-26b-a4b-it-4bit, 25 tokens in 220.16s (11.0 tok/s), prompt: 98176, finish_reason=tool_calls, max_tokens=24576, request_max_tokens=24576, stream_model_ttft=217.89s, stream_visible_ttft=220.16s
2026-11-27 19:18:51,396 - omlx.server - INFO - [-] - Chat completion: model=mlx-community--gemma-4-26b-a4b-it-4bit, 925 tokens in 304.15s (11.0 tok/s), prompt: 99548, finish_reason=stop, max_tokens=24576, request_max_tokens=24576, stream_model_ttft=220.38s, stream_visible_ttft=220.38s
2026-11-27 19:23:55,844 - omlx.server - INFO - [-] - Chat completion: model=mlx-community--gemma-4-26b-a4b-it-4bit, 575 tokens in 273.88s (11.0 tok/s), prompt: 100718, finish_reason=stop, max_tokens=24576, request_max_tokens=24576, stream_model_ttft=221.65s, stream_visible_ttft=221.65s
```

| Case | Incumbent (`gemma-4-26b-a4b-it-4bit`, oMLX) | Candidate (`Qwen3.8-27B-oQ4e-mtp`, oMLX) |
|---|---|---|
| `parent` | hop-2 TTFT `217.89s` (~430 tok/s), `wall_s=405.22s`, high-water `98,214` | hop-2 TTFT `1,100.03s` (86.9 tok/s), aborted @ `900.56s` |
| `choice` | hop-2 TTFT `220.38s` (~422 tok/s), `wall_s=321.84s`, high-water `99,548` | hop-2 TTFT `1,319.46s` (72.1 tok/s), aborted @ `900.41s` |
| `interval` | hop-2 TTFT `221.65s` (~419 tok/s), `wall_s=292.01s`, high-water `100,718` | hop-2 `104,830` tok, aborted @ `905.61s` |
| `read_check` | `wall_s=28.64s`, high-water `8,441` (no material re-fetch) | hop-2 `99,732` tok, aborted @ `904.21s` |

## 4. Disposition & Next Options

Per `BRIEF_READING_QWEN38_VOID_20261127.md` stop condition and `docs/MODEL_SEAT_PROCESS.md`:
- **Incumbent (`auto-compliance::reading` → `gemma4:26b-a4b-it-q4_K_M-t0p0-ctx128k` / `mlx-community--gemma-4-26b-a4b-it-4bit`) stays.** `Qwen3.8-27B-oQ4e-mtp` cannot complete a single 100k dual-document prefill inside the 900s product bar on oMLX (`1,100s` uncontended prefill alone, before any decode or third hop).
- **If the orchestrator wants a future reading candidate** that fits the 900s bar at 100k tokens on this M4 Pro 64 GB host, it needs either:
  1. A **sparse MoE** candidate (small active parameter count → ~400+ tok/s prefill, like Gemma 4 26B-A4B or Qwen3.6-35B-A3B), or
  2. An explicit live prefill check of oMLX's `qwen35_ane_prefill_enabled: true` (currently `false` in `~/.omlx/model_settings.json`) or the Ollama GGUF path (`hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx128k`) on a single 100k prompt — neither is proven to bring 27B dense 100k prefill under 900s.
