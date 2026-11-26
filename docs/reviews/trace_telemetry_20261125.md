# Review — request tracing and telemetry end to end (2026-11-25)

Scope: `portal/platform/inference/router/` (handlers, streaming, placement,
safety_guard), the `/v1/trace` producer (`router/trace.py`), and every consumer:
`tests/qat`, `tests/wfe`, `scripts/bench_*`, `scripts/wfe_*`, the
compliance readers, and the Grafana/Prometheus dashboards. Read-only review of
HEAD `688fdb86b`; every defect that was small and confirmed is fixed in this lane
with tests, as separate commits. Nothing here was run against the live stack —
each finding names the live check that would confirm it.

Governing lesson applied: most project defects came from harness/setup errors,
not model behaviour — every grader, trace match and fixture was treated as
suspect until the code proved it.

## Answers to the brief's four questions

**1. Is the trace record written once, with the correct served engine/model,
outcome, options_applied and timings?**

Nearly. The write path is overwrite-by-design (handler `finally` writes the
routing decision as soon as headers are ready; the streaming generator replaces
that record with the complete one — `trace.py` `TurnTrace.finalize`). The paths
that broke the contract were: a chat turn answered by a capacity-fallback variant
(no outcome, no backend/model — F1), a streaming fallback whose receipt was then
overwritten by `outcome="error"` (F2), a non-streaming chat-UI no-answer notice
with no outcome (F7), and chain turns that name only the primary seat (F6). All
fixed. Council turns still carry no outcome and no top-level served identity
(F8, proposed brief).

**2. Can traces be mis-attributed under concurrency?**

Not across requests: the trace is a ContextVar bound inside the handler and the
records are per-correlation-id files with atomic rename. The real mis-attribution
was **temporal, not concurrent**: Open WebUI's title/tag/follow-up tasks arrive as
ordinary chat turns on the *same workspace* seconds after the graded turn, and
both recency-based matchers (`bench_security_qat.newest_trace`,
`tests/qat/owui_client._trace_row_matches`) pick the newest row — the task call,
not the turn (F3, fixed). A secondary race: a consumer that fires `/v1/trace`
immediately after consuming `[DONE]` can read the handler's partial record before
the streaming generator's final write lands (F11, bounded impact).

**3. Does each consumer parse the fields the producer actually writes?**

One consumer did not: `scripts/compliance/reading_loop_triage.py` read
`trace["served_model"]`, a key only `transport_dialects.PipelineCompat._trace`
invents on *its own* receipt; the raw record's key is `model` — the triage's
`served_model` column was permanently empty (F5, fixed). Two consumers matched
summaries on a field (`requested`) the producer never emitted (F4, fixed). All
other consumers checked read keys the producer writes (matrix below).

**4. Are outcome strings one taxonomy, or several divergent ones?**

Several (F9). Producer values: `ok` (non-streaming success, and streaming
fallback success — `streaming.py:3203`), `complete` (streaming success),
`interrupted`, `error`, `safety_refusal`, `http_<status>`, and now `no_answer`.
Two success strings is load-bearing (consumers accept the pair), but the deeper
divergence is structural: the streaming wrappers stamp the outcome in their
`finally` (`streaming.py:799`, `:2040`, `:2725`) from *how the generator exited*,
not from *what the client received* — a stream that ended with error-as-content
terminal frames (`_error_terminal_frames`) or the no-answer notice exits normally
and records `complete`. Proposed brief (F9).

## Consumer matrix (producer field → consumers)

| Producer field (`/v1/trace` record / summary) | Consumers | Verdict |
| --- | --- | --- |
| `correlation_id`, `started_at` | wfe runner `pipeline_served`, bench_security_qat `newest_trace`, qat `_trace_candidates`, memory_canary, proofs/owui_hunt_chat, pipeline_call_site_ledger, seat_screen | ok |
| `workspace`, `persona` | newest_trace (identity match), `_trace_row_matches`, wfe_production_smoke `trace_reasons`, bench_security_qat `trace_failures` | ok |
| `requested` (summary) | newest_trace, `_trace_row_matches` | was missing from the summary (F4, fixed) |
| `backend`, `model` | wfe runner, bench_security_qat, bench_seat_ab `served`, reading_loop_triage, served_turn (P6R), wfe_production_smoke | ok (fallback re-notes; council has none — F8) |
| `outcome` | bench_security_qat (`complete`/`ok`), wfe_production_smoke (`complete` only) | taxonomy divergence F9; capacity-fallback turns had none (F1, fixed) |
| `options_applied` | wfe runner, bench_security_qat, reading_loop_triage, bench_judgment_probe_v6, transport_dialects/reading_transport (compliance receipts) | ok on chat paths; reflects the last chain hop's injection on chain turns (F12) |
| `portal_timings` | wfe runner (`_econ_from_timings`), bench_seat_ab, council_bench (response payload, not trace) | ok; council rollup empty (F8) |
| `spans[].name` = `tool.requested`/`tool.completed` | bench_security_qat, wfe_production_smoke, proofs/owui_hunt_chat, qat poll | ok |
| `spans[].name` = `backend.attempt`/`backend.selected`/`backend.failed` | pipeline_call_site_ledger `_cascade`, compliance receipts | ok; ledger only counts `backend.attempt`, so a streaming-first cascade shows no failed attempts (F17) |
| `spans[].name` = `council.stage` | bench_seat_ab `_council_served` | ok |
| `spans[].name` = `chain.hop` | (new — no consumer yet) | added by F6 |
| summary `owui_task` | (new — the two time-based matchers skip on it) | added by F3 |

Grafana/Prometheus: every metric name referenced by
`config/grafana/dashboards/*.json` resolves to a declared collector
(`router/metrics.py`) or a hand-rendered gauge in `handlers.metrics`
(`portal_backends_healthy`, `portal_backends_total`, `portal_uptime_seconds`,
`portal_workspaces_total`). The dashboards consume the counter pairs the way
`metrics.py` prescribes (`portal_decode_tokens_total / portal_decode_seconds_total`,
`portal_answer_tokens_total / portal_answer_seconds_total`, with `internal-*`
exclusions matching `power.INTERNAL_WORKSPACE_PREFIX`). No producer/consumer
mismatch found on this side.

## Fixed in this lane (with tests, one commit each)

### F1 — A capacity-fallback turn recorded no outcome and no served seat

- `portal/platform/inference/router/capacity_fallback.py` (`try_capacity_fallback`).
- Claim: when every candidate refused a chat-UI turn for memory and a lighter
  declared variant answered, the trace record had no `outcome`, no `backend`, no
  `model` — the candidate loop that normally notes them (`handlers._dispatch_non_streaming`)
  never succeeded on this path.
- Failure scenario: OWUI turn on `auto-security`, seat refused for memory, the
  `::lite` variant answers 200. `bench_security_qat.trace_failures` reads
  `trace.get("outcome")` → `None` → "trace outcome is None, not a success" and
  `served /` — the operator cannot tell *which* seat answered or that the turn
  was served at all; `wfe_production_smoke.trace_reasons` reports
  "trace does not name the served backend and model".
- Severity: breaks-results (for every trace consumer). Confidence: high (code +
  unit tests).
- Fix: the receipt is noted where the variant actually answers —
  `backend`, `model`, `workspace=synthetic_id`, `outcome="ok"`,
  `capacity_fallback=<variant>`, plus a `backend.selected … fallback=True` span.
- Live check: `uv run python scripts/bench_security_qat.py --seats auto-security`
  with the oMLX seat's weights evicted so the base seat refuses (or after any run
  that hit `portal5_capacity_fallback_total`):
  `curl -s -H "Authorization: Bearer $PIPELINE_API_KEY" "http://localhost:9099/v1/trace?limit=20" | jq '.data[] | select(.capacity_fallback) | {correlation_id,workspace,backend,model,outcome}'`
  — worked: every row shows `outcome:"ok"`, the variant's backend/model and
  `workspace` naming the `::variant` seat; not worked: rows with null
  `backend`/`model` or missing `outcome`.

### F2 — The streaming exhausted-tail overwrote the fallback receipt with `error`

- `portal/platform/inference/router/streaming.py` (`_stream_with_fallback` tail).
- Claim: the tail stamped `outcome="error"` + `backend.failed` *after* yielding
  `_exhausted_frames` — which is where a chat-UI capacity fallback serves — so a
  turn a lighter variant answered recorded `outcome="error"` with the failed
  first candidate as `backend`.
- Failure scenario: streamed OWUI turn, first candidate 507s, ladder exhausted,
  capacity fallback serves. Record: `outcome:"error"`, `backend=<failed
  candidate>`. `bench_security_qat.trace_failures` reports "trace outcome is
  'error'" although the user got an answer.
- Severity: breaks-results. Confidence: high (code + unit test
  `test_capacity_fallback_receipt_survives_the_error_stamp`).
- Fix: the error stamp + span now happen *before* `_exhausted_frames` runs, so
  the fallback receipt (F1) lands last and wins.
- Live check: same as F1 but for a turn that *streamed*: the trace's span order
  shows `backend.failed` (first candidate) followed by `backend.selected
  fallback=True` (the variant), and `outcome` is `ok`.

### F3 — OWUI task calls are indistinguishable from graded turns

- Producer: `portal/platform/inference/router/handlers.py` (`_resolve_request_route`).
  Consumers: `scripts/bench_security_qat.py` (`newest_trace`),
  `tests/qat/owui_client.py` (`_trace_row_matches`).
- Claim: OWUI's title/tag/follow-up generation arrives as an ordinary chat turn
  on the same workspace (`context_inject._is_owui_task_prompt` exists precisely
  because of this), *after* the user's turn. Both consumers match the newest
  summary row by identity + time — the task call is newer, so the receipt can be
  the title-generation trace: on the QAT runner the tool-then-content graders
  then read a trace with no `tool.requested` spans and grade a correct turn as a
  harness FAIL.
- Failure scenario: `bench_security_qat` s4-tools turn completes at t; OWUI's
  title task traces at t+2s; `send_turn` sleeps 1s and `newest_trace` returns
  the task record → `called=[]` → "did not call lookup_cve" on a turn that did.
- Severity: stability (harness mis-grade). Confidence: high on the mechanism
  (producer + consumers read as written); the task traffic itself is asserted by
  the producer's own detection code — live check to confirm it fires here.
- Fix: the producer marks task-template turns (`trace_note(owui_task=True)`),
  the summary carries `owui_task`, and both time-based matchers skip such rows.
- Live check: `curl -s -H "Authorization: Bearer $PIPELINE_API_KEY" "http://localhost:9099/v1/trace?limit=30" | jq '[.data[] | select(.owui_task)] | length'`
  — >0 confirms OWUI task calls are traced; then
  `uv run python scripts/bench_security_qat.py --seats auto-security` should no
  longer produce rows whose trace has no `tool.requested` spans for a tool task.

### F4 — `/v1/trace` summaries lacked `requested` (two consumers matched on it)

- `portal/platform/inference/router/trace.py` (`recent_traces`).
- Claim: `bench_security_qat.newest_trace` builds its identity set as
  `{workspace, requested, persona, model}` and `tests/qat/owui_client._trace_row_matches`
  as `{workspace, requested, persona}` — but the summary only carried
  `workspace/persona/backend/model/outcome/tool_calls`, so the `requested`
  fallback never fired (it is dead code today, masked because `persona` carries
  the client's model string on every chat turn).
- Failure scenario: any turn whose client model id differs from the resolved
  workspace id *and* whose `persona` note is absent (e.g. a refusal turn, where
  routing never runs) cannot be matched by recency+identity.
- Severity: nit. Confidence: high (code).
- Fix: the summary now carries `requested` (and `owui_task`, F3).
- Live check: `curl -s -H "Authorization: Bearer $PIPELINE_API_KEY" "http://localhost:9099/v1/trace?limit=5" | jq '.data[0]'`
  — the summary now shows `requested` and `owui_task` keys.

### F5 — Compliance triage read a field the raw record never carries

- `scripts/compliance/reading_loop_triage.py` (`_public_row`).
- Claim: `trace.get("served_model")` — the raw `/v1/trace` record's key is
  `model`; `served_model` exists only in `transport_dialects.PipelineCompat._trace`'s
  renamed receipt. The triage's public `served_model` column was permanently
  `""` for every row.
- Failure scenario: any sampling-arm triage run — the CSV/JSON column that
  should name the served seat is empty, so a served-model drift across arms is
  invisible in the public artifact.
- Severity: breaks-results (for that consumer's output). Confidence: high.
- Fix: read `trace.get("model")`.
- Live check: `uv run python scripts/compliance/reading_loop_triage.py --help`
  and one pipeline-arm question; the public row's `served_model` matches the
  trace's `model` instead of `""`.

### F6 — Chain hops left no served-engine evidence in the record

- `portal/platform/inference/router/non_streaming.py` (`resolve_hop_target`),
  used by both the streaming chain (`streaming.py`) and the non-streaming chain.
- Claim: a chain hop is re-resolved to the first healthy backend that serves the
  hop's model (which is the entire point of the function — the primary may be
  oMLX while the hop's model is an Ollama tag), and the trace said nothing about
  it: the record's `backend`/`model` stay the primary's, and no span names the
  hop's engine.
- Failure scenario: `auto-purpleteam-deep` 4-hop turn — hop 1 (blue) served by an
  Ollama seat while the record says `omlx-security/Inkling…`; an operator
  auditing a purple-team turn cannot tell which engine produced the blue-team
  text.
- Severity: missing-feature. Confidence: high.
- Fix: `resolve_hop_target` notes a `chain.hop` span (`requested`, `backend`,
  `model`; `unresolved=True` + null backend when no backend serves the hop).
- Live check: run one purpleteam chain turn;
  `curl -s -H "Authorization: Bearer $PIPELINE_API_KEY" "http://localhost:9099/v1/trace/<cid>" | jq '[.spans[] | select(.name=="chain.hop")]'`
  — one span per hop naming each serving backend/model.

### F7 — A non-streaming chat-UI no-answer notice had no outcome

- `portal/platform/inference/router/handlers.py` (`_give_up`).
- Claim: when no candidate could serve and the audience is a chat UI, the turn
  ends as a 200 completion whose trace has no `outcome` at all (only the API
  client path raises, and that one is stamped `http_<status>`).
- Failure scenario: all candidates refuse a chat turn; the record shows the
  failed `backend.attempt` spans and nothing else — an operator filtering
  outcomes cannot distinguish "served, notice appended" from "record truncated".
- Severity: nit. Confidence: high.
- Fix: `trace_note(outcome="no_answer")` before the notice completion.
- Live check: same query shape as F1 but filtering `outcome=="no_answer"` after
  forcing an all-fail turn (e.g. stop Ollama and oMLX, send a chat-UI turn).

## Findings reported, not fixed (proposed briefs / operator decisions)

### F8 — Council turns: no outcome, no top-level served identity, empty request rollup (proposed brief)

- `handlers.py` `_dispatch_council`; `council.py` (`_span_stage` :617,
  `trace_note(portal_council_timings=…)` :1427).
- Claim: the council path never notes `outcome` or top-level `backend`/`model`;
  stage identity lives only in `council.stage` spans. It also never calls
  `add_model_turn`, so the request rollup (`current_portal_timings`) stays empty
  and the closing SSE `portal_timings` frame for a streamed council is all-`null`.
- Failure scenario: any consumer applying the chat-turn contract (outcome
  present, filled timings) to a council record reads nothing; `speed_bench`-style
  consumers of the closing frame would error ("stream carried no portal_timings
  frame" — the frame is present but empty).
- Severity: missing-feature. Confidence: high.
- Why not fixed here: choosing the outcome string and whether stage timings
  roll into `portal_timings` is a design decision (two timing rollups already
  exist: `portal_timings` vs `portal_council_timings`).
- Live check: one council turn; the trace shows `outcome: null` and
  `portal_timings` all-null while `spans` carry every stage.

### F9 — Outcome ownership is split; terminal error/notice streams record `complete` (proposed brief)

- `streaming.py:781-802`, `:2029-2043`, `:2718-2728` (wrapper `finally`s stamp
  how the generator exited); `_error_terminal_frames` :498, `_no_answer_frames`
  :555.
- Claim: a standalone (no-cascade) backend error ending or the empty-turn
  no-answer notice exits the generator normally, so `_stream_with_tool_loop` /
  `_stream_with_preamble` stamp `outcome="complete"` although the client
  received an error/notice. The two success strings (`ok`/`complete`) are
  consumer-known, but "complete on an error the client saw" is mis-attribution.
- Failure scenario: oMLX returns an in-band error on a single-candidate stream;
  `_record_error` counts it, the client sees the error as content, and the trace
  says `complete` — an operator grepping `outcome=="complete"` sees only
  successes, and one that *was not*.
- Severity: stability. Confidence: high.
- Live check: stop the oMLX engine, send one non-cascadable (e.g. 400-shaped)
  streamed turn as an API client, read its trace: `outcome` today reads
  `complete` while the answer content is the pipeline error notice.

### F10 — Safety-refusal records name the *requested* model as `workspace` (report; operator call)

- `safety_guard.py:290-295` (`record_refusal` → `trace_note(workspace=refusal.model, …)`).
- Claim: the guard fires before routing, so there is no resolved workspace yet;
  the record's `workspace` holds the client's model string (persona slug, alias
  or `auto`), while every non-refused turn's `workspace` is the resolved id. A
  summary filtered by workspace id misses refusals addressed by slug.
- Severity: nit. Confidence: high (code); deliberate-or-not needs the operator
  (the metric `_record_safety_refusal` also uses the requested model).
- Live check: send a CBRN-form turn addressed by persona slug;
  `curl -s … /v1/trace?limit=5 | jq '.data[0]'` — `workspace` is the slug, not
  the resolved workspace id.

### F11 — `pipeline_served` can read the handler's partial record (report; bounded)

- `handlers.py:154-195` (`_with_portal_timings` finalizes after the last byte);
  `tests/wfe/runner.py:894-909, 1123-1128`.
- Claim: a client that reads `[DONE]` and immediately GETs the trace races the
  server's final write and can fetch the handler-written record (routing
  decision, `options_applied`, `backend`/`model` — but no `portal_timings`, no
  `outcome`). Bounded: the WFE runner already carries the SSE closing frame's
  timings and only *overwrites* econ fields when the trace supplies them.
- Severity: nit. Confidence: high on the mechanism, low on observed frequency.
- Live check: run a WFE row 20×; count rows whose `pipeline_served` came back
  without `portal_timings` (the runner log/row field would show stream-derived
  timings only).

### F12 — `options_applied` after a multi-hop turn reflects the last hop's injection (report)

- `non_streaming.py` `resolve_hop_target` re-injects per hop →
  `validation._note_applied_options` (the receipt is "the last body built").
- Claim: caller-supplied engine-specific keys (`think`, `chat_template_kwargs`,
  `options`, `repetition_penalty`) are popped and rebuilt from the workspace for
  the hop, so a chain turn's receipt can differ from the primary's applied
  options even though the *primary* answered first.
- Severity: nit. Confidence: high.
- Live check: chain workspace turn with caller `temperature` and
  `chat_template_kwargs.enable_thinking=false`; compare `options_applied` with a
  single-hop turn on the same workspace.

### F13 — The eviction-retry is invisible in the trace (report)

- `streaming.py:342-352` (`_retry_after_omlx_abort`), `:2208-2226` (free + re-issue).
- Claim: a mid-prefill abort frees Ollama and silently re-issues the same
  request; the record shows one model call whose timings span both attempts and
  no span marks the abort/retry.
- Severity: missing-feature (small). Confidence: high.
- Live check: reproduce an oMLX memory abort under load; the trace's
  `portal_timings.total_s` covers the free+retry while no span explains it.

### F14 — `_with_portal_timings` detects engine usage by byte substring (report)

- `handlers.py:176-181` (`if b'"usage"' in raw: usage_seen = True`).
- Claim: the marker matches escaped `"usage"` inside answer text (e.g. a JSON
  echo in the answer), suppressing the redundant terminal usage injection.
  Mostly harmless: `_with_closing_usage` (`streaming.py:598`, parsed check)
  already guarantees the frame on engine paths; the paths without it (council
  stream, `_json_completion_to_sse` fallback) could skip a *requested* usage
  frame when the answer text contains `"usage"`.
- Severity: nit. Confidence: high on the false positive, low on impact.
- Live check: stream `stream_options.include_usage=true` with a prompt whose
  answer contains the literal text `"usage"` on a council/fallback-served turn;
  the closing usage frame is missing.

### F15 — Native Ollama passthroughs and `/v1/embeddings` are not traced (report; likely by design)

- `app.py:61-77`; `ollama_passthrough.py` (no `start_trace`).
- Claim: `/ollama/api/chat|generate` (MCP clients' native dialect) and
  `/v1/embeddings` produce no trace records; they are counted in metrics
  (`native-passthrough` / `native-embed` workspaces) but invisible to the trace
  store. `/v1/messages` traces (it routes through `chat_completions`).
- Severity: missing-feature (low) / by-design. Confidence: high.
- Live check: `POST /ollama/api/chat` then `GET /v1/trace?limit=3` — no record
  for the call.

### F16 — A failed trace write leaves tmp litter that `_prune` never counts (report)

- `trace.py:266-292` (`tmp.write_text` … `tmp.replace(target)`), `_prune` counts
  `*.json` only.
- Claim: an exception between write and replace (disk full, tmpfs limit) leaves
  `.<cid>.<pid>.tmp` files that accumulate; `_prune` only unlinks `*.json`.
- Severity: nit. Confidence: high (code), needs a fault to observe.
- Live check: fill the trace tmpfs (or fault-inject) and list
  `$PORTAL_TRACE_DIR` for `.tmp` strays.

### F17 — The compliance ledger's cascade reads only `backend.attempt` spans (report)

- `scripts/compliance/pipeline_call_site_ledger.py:75-90`.
- Claim: streaming-first turns emit `backend.failed` (per attempt, from
  `non_streaming._run_request`) rather than `backend.attempt` (only the
  non-streaming loop emits those), so a streaming call-site's `failed_attempts`
  is empty even when several candidates failed; `fell_back` then reads false.
- Severity: nit (evidence completeness). Confidence: high.
- Live check: run the ledger against a streaming call site whose first candidate
  fails; the row's `cascade.failed_attempts` is `[]` while `backend.failed`
  spans exist in the trace.

## Verification ladder status

- Per-commit gate (`uv run pytest tests/unit/ -q && uv run ruff check . && uv run
  ruff format --check .`): run in this lane; results in the lane's report.
- Live: **not run** — this lane never touches the stack. Every finding names the
  orchestrator check above.
