# FINDING — failover protection pinned the model that FAILED (live, 2026-11-20)

Evidence: `~/.portal5/omlx080/evidence/failover_protect_bug_20261120.log` (main `f248f58af`,
oMLX 0.8.0). Every claim below is read from that log or from the code at that commit; this
lane made no live request.

## Summary

`protect_failover()` was called from the **failure** path with the model that had just
failed, so a failed hop put a 300 s eviction shield on its own memory. In the live sequence a
Nemotron GGUF that returned an empty completion was protected at 22.9 GiB, and oMLX then
refused the healthy `Qwen3.8-27B-oQ4e-mtp` seat for the next request ("projected memory
16.6 GiB would exceed host headroom 9.0 GiB; blocked by …Nemotron… (22.9 GiB, failover
protected)") — HTTP 507, then "failed on every backend". The user got no answer from a seat
that was healthy.

## Root cause

Pre-fix, at `f248f58af`:

| what | where |
| --- | --- |
| non-streaming marked the failed backend | `router/non_streaming.py:243-251` `_protect_failed_model` → `load_guard.protect_failover(backend.type, target_model)`, called at `:1579` (any HTTP/parse failure) and `:1628` (timeout) |
| streaming marked the failed backend | `router/streaming.py:3262` `protect_failover(getattr(backend, "type", ""), target_model)` under `if stream_failed:` |
| the shield itself | `load_guard.py:492-501` `protect_failover` → `protect(..., failover=True)` → `_failover_protected` for `FAILOVER_PROTECT_S` (300 s) |
| why it blocked memory | `load_guard.py:993` `_ollama_hold_reason` returns `"failover protected"`, and `_yield_protected_idle` (`:1996-2002`) only yields **keeper**-protected residents, so a failover-protected resident is never freed; `_refuse_blocked_omlx` (`:2471`) then names it as the blocker |

Both call sites passed `target_model` — the model of the backend that had just failed — so the
shield always named the failed source. The P-2 intent (commit `567036559`, extended in
`e64014c2e`) was to stop an eviction cascade; it achieved that by protecting the one seat the
request had already given up on.

## Fixes

1. **The failure marks the failed model as the first eviction candidate** (`load_guard.py:511`
   `note_failure`, `LoadGuard.note_failure` at `:866`, window `FAILED_EVICT_S` 300 s):
   a model that just failed or answered empty is evicted before anything else
   (`_free_ollama`, `_free_omlx`, `_unfreed_idle_ollama` sort failure first) and the call
   also drops any failover shield that model already had.
2. **Protection now names the seat that SERVED**:
   `non_streaming.py:1613`/`:1652` call `_protect_served_model` only when an earlier attempt
   for the same request failed (`_failover_hop = bool(tried)`, `:1139`);
   `streaming.py:3165` protects the fallback candidate that answered
   (`_record_fallback_route`, which already reads the served model from `x-portal-route`).
   The failure path calls `note_failure` instead (`non_streaming.py:1619`, `:1670`;
   `streaming.py:3263`).
3. **An empty reply's cause is reported** (`non_streaming.py:761-790`): a reply that is empty,
   `finish_reason='length'`, with the reasoning channel non-empty is reported as
   `max_tokens=16 ran out on reasoning before any answer`, counted as
   `empty_completion_budget`, and distinct from `content empty, no tool_calls,
   finish_reason='stop'` (a model that genuinely returns nothing). Because the budget, not the
   tools, swallowed the answer, the "asking once with tools off" retry is skipped
   (`non_streaming.py:832`) instead of spending a second identical turn.
4. **The give-up message carries the cause** (no code change needed once (3) is in the
   `tried` reason): the chat-UI path (`handlers._give_up` → `no_answer.chat_reply`) already
   answers with `⚠️ **`<model>` could not be served, so this turn has no answer.** … **Why:**
   <reason>`, and an API client gets HTTP 502 with the same detail.

### What Nemotron actually returned

`finish_reason='length', reasoning=True`, content empty — twice (with tools attached, and on
the tools-off retry). The whole 16-token budget went to the reasoning channel, so this is
**not** a tool-schema or thinking-template defect under tools: the live `max_tokens: 16`
(tiny, an OWUI task-shaped call) with a reasoning model is the cause. Fix (3) names it; no
template change was made.

## Orchestrator's live repro

Pipeline on `main` with this lane merged and the image rebuilt (`./launch.sh rebuild && ./launch.sh up`),
`PIPELINE_API_KEY` from `.env`. Both requests are non-streaming, as in the live log.

```bash
cd /Users/chris/projects/portal-5 && set -a && . ./.env && set +a
EVID=~/.portal5/omlx080/evidence; mkdir -p "$EVID"

# 1. auto-daily at max_tokens 16 — the request whose empty answer is now a budget finding
curl -s -X POST http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer ${PIPELINE_API_KEY}" -H 'Content-Type: application/json' \
  -H 'x-portal-client: api' \
  -d '{"model":"auto-daily","max_tokens":16,"messages":[{"role":"user","content":"name this chat"}]}' \
  | tee "$EVID/repro_1_auto_daily.json"

# 2. auto-coding::heavy — the healthy oMLX seat that must now load
curl -s -X POST http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer ${PIPELINE_API_KEY}" -H 'Content-Type: application/json' \
  -H 'x-portal-client: api' \
  -d '{"model":"auto-coding::heavy","max_tokens":64,"messages":[{"role":"user","content":"say ok"}]}' \
  | tee "$EVID/repro_2_auto_coding_heavy.json"
```

Read the Pipeline log (`docker logs portal5-pipeline --since 5m`), not the JSON alone.

**Pass** — after request 1:

```
load_guard: ollama:hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k failed — first eviction candidate for 300s
Non-stream: workspace=auto-daily model=…Nemotron…:Q4_K_M-ctx32k answered nothing because max_tokens=16 ran out on reasoning before any answer (finish_reason='length'); asking with tools off cannot help
Non-stream: workspace=auto-daily model=…Nemotron…:Q4_K_M-ctx32k returned an empty completion (max_tokens=16 ran out on reasoning before any answer (finish_reason='length')); treating it as a failed hop
```

and **no** `protecting ollama:…Nemotron… after it served a failover` line for it.

After request 2: `load_guard: evicted …Nemotron… on ollama … (reason=idle LRU)` (or the failure-first
equivalent) followed by `Backend omlx-coding succeeded for workspace=auto-coding::heavy
model=Qwen3.8-27B-oQ4e-mtp` — request 2 returns an answer, not 507.

**Fail** — any of:

- `load_guard: protecting ollama:hf.co/…Nemotron…:` for the **failed** model (the shield is
  still on the failure path), or
- `Cannot load Qwen3.8-27B-oQ4e-mtp: projected memory … blocked by …Nemotron… (…, failover
  protected)` and `HTTP/1.1 507` for request 2, or
- `returned an empty completion (content empty, no tool_calls, finish_reason='length',
  reasoning=True)` — the pre-fix wording, which does not name the budget.

To also see the served-seat protection (a request that really fails over needs a broken
primary), the log line to expect is
`load_guard: protecting <engine>:<model> for 300s after it served a failover`.

## Tests

- `tests/unit/test_load_guard.py` — `test_a_failed_model_is_the_first_eviction_candidate_not_a_shield`,
  `test_a_failure_drops_a_failover_shield_the_model_already_had`,
  `test_a_protected_failed_model_refuses_the_healthy_seat` (reproduces the live 22.9/16.6 GiB
  refusal verbatim), `test_the_model_that_just_failed_is_evicted_and_the_healthy_seat_loads`.
- `tests/unit/test_failover_protection_and_empty_hop.py` —
  `test_the_failed_hop_is_never_protected_and_the_served_seat_is`,
  `test_a_spent_reasoning_budget_is_reported_as_that_cause`,
  `test_a_spent_budget_does_not_spend_the_toolless_retry`,
  `test_the_toolless_retry_still_runs_when_the_engine_returned_nothing`,
  `test_every_hinted_backend_failing_gives_the_chat_ui_the_cause` (drives
  `handlers._dispatch_non_streaming` end-to-end and reads the JSON OWUI would receive), plus
  the updated streaming tests: a failed stream marks the failed model for eviction, and the
  fallback candidate that served is the protected seat.

## Not proven here

- The live behaviour after the merge: no service was restarted and no request was made from
  this lane (division of labour).
- What OWUI itself displayed for the two live requests: the log carries no `no candidate could
  serve` line, so the audience branch (`no_answer.chat_ui()` true vs false) cannot be read
  from it; the property-4 test covers both audiences' messages from the code, and the
  orchestrator's repro above reads the real response with `x-portal-client: api`.
- Whether protecting a *served* seat for 300 s can block a later cold load the way the failed
  one did. It can in principle (same shield mechanism); the difference is that it protects a
  seat that is answering. If a live run shows it blocking a healthy seat, the next step is to
  drop `FAILOVER_PROTECT_S` to 0 or exclude the served seat from non-serving admissions.
