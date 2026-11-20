# FINDING — B3 seat failures after the residency fix (post080_fix3, 2026-11-20)

Run: `~/.portal5/omlx080/post080_fix3` (B3 `speed_bench --engine pipeline`, 24 seats,
sizes 2000/8000/32000, Pipeline log `~/.portal5/omlx080/evidence/pipeline_post080_fix3.log`,
oMLX log `~/.omlx/logs/server.log`). All evidence below is from those files; no live
request was made by this lane.

## Summary

Of the 24 B3 seats, **none has a seat-level pipeline routing defect**. The 35 INVALID
rows come from four causes, only one of which is a real pipeline defect:

| cause | rows | real defect? |
| --- | --- | --- |
| The Pipeline echoes the requested `workspace::variant` as the SSE `model`; the bench read that instead of `x-portal-route` | 22 of the 34 `WRONG ENGINE` strings name the echo | **bench bug** |
| Hot-seat prefix-cache protection reorders the seat to its Ollama GGUF twin (intended policy, `hot_seat_protect_s: 900`) | 8 rows | not a defect — bench must pin the seat |
| Size/schema exceeds the seat's declared `context_limit`; Pipeline refuses locally | 17 rows | **bench bug** (must skip + report) |
| Seats whose module is disabled (`security_redteam`) answer 404 by design | 3 seats × 3 sizes | **bench roster bug** |

Two further pipeline defects were found and fixed in this lane:

1. A pending Ollama admission could unload the very copy it was loading
   (`_free_idle_memory` → `_free_ollama(..., last_models={model})`).
2. A cold oMLX load still evicted the same seat's idle Ollama fallback
   ("requested seat copy", the path `46499b93b` intended to remove).

## Per-seat cause table

`intended` is the config-resolved seat (`resolve_intended_seat`, now config-only order,
independent of live health). `ctx` is the seat's declared `context_limit`.

| seat | intended engine/model | ctx | failing rows | cause |
| --- | --- | --- | --- | --- |
| auto-coding::bigfix | omlx-coding / Qwen3-Coder-30B-A3B-Instruct-4bit | 16384 | 2k, 8k | hot-seat reorder → `ollama-coding` GGUF ctx16k (log 54656: routed 1/12 to ollama-coding) |
| auto-coding::bigfix | " | " | 32k | context refusal (`estimated=37383 > 16384`, log 54781); bench sent 32k to a 16k seat |
| auto-coding::cad | omlx-coding / Qwen3-Coder-30B-A3B-Instruct-4bit | 32768 | 2k | engine error mid-stream: `Model output contains an unrecoverable tool call` (log 54970) → reasoning/no answer, not wrong engine |
| auto-coding::cad | " | " | 32k | context refusal (`estimated=44278 > 32768`, log 55083) |
| auto-coding::heavy | omlx-coding / Qwen3.8-27B-oQ4e-mtp | 131072 | — | ok on all sizes |
| auto-coding::laguna | omlx-coding / Laguna-XS-2.1-4bit | 131072 | 2k | hot-seat reorder → `ollama-coding`; hop returned `finish_reason=length` with no answer (log 50545), then oMLX served it. `served_model` echo masked both facts |
| auto-coding::qwen38coder-dflash | omlx-coding / Qwen3.8-27B-4bit | 262144 | — | all rows oMLX; 4.4 tok/s is real decode, see below |
| auto-coding::qwen38coder | omlx-coding / Qwen3.8-27B-oQ4e-mtp | 262144 | 2k | hot-seat reorder → `ollama-coding` GGUF |
| auto-coding::uncensored-agentic | omlx-coding / Huihui-Qwen3.6-27B-abliterated-MLX-4bit | 131072 | 8k | engine produced reasoning only (128 completion tokens, `answer_tps=0.0`); Pipeline appended `NO_ANSWER_MESSAGE` |
| auto-compliance::reading | omlx-general / mlx-community--gemma-4-26b-a4b-it-4bit | 131072 | 2k, 8k, 32k | hot-seat reorder → `ollama-general` (its own GGUF twin, `gemma4:26b…ctx128k`). **This seat is meant to be oMLX**: `omlx-general` aliases that exact tag (config/backends.yaml:780), so it is not an Ollama seat |
| auto-daily::deep | omlx-general / Qwen3.8-27B-oQ4e-mtp | 98304 | — | ok |
| auto-daily::fast | omlx-general / unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit | 98304 | — | ok |
| auto-daily::gemma-fast | omlx-general / gemma-4-26b-a4b-it-QAT-4bit | 32768 | 32k | context refusal (est > 32768) |
| auto-general-uncensored::creative | omlx-general / Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit | 8192 | 2k | served `ollama-general` ctx8k. The bench's *own* intent in this run also said `ollama-general` (its health-dependent resolver disagreed with the config), so this row was a **false pass**, not a detection; on the merged config the alias resolves on `omlx-general` (backends.yaml:719–726, 785) |
| auto-general-uncensored::creative | " | " | 8k, 32k | context refusal (`8192` seat; log 60527/60538) |
| auto-reasoning::deep | omlx-reasoning / Qwen3.8-27B-oQ4e-mtp | 32768 | 2k, 8k | hot-seat reorder → `ollama-reasoning` GGUF ctx32k |
| auto-reasoning::deep | " | " | 32k | context refusal (`estimated=42672 > 32768`, log 55516) |
| auto-research::data | omlx-reasoning / unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit | 32768 | 2k, 8k | hot-seat reorder → `ollama-reasoning` GGUF ctx32k; `served_model` echo also produced a false `WRONG ENGINE` |
| auto-research::data | " | " | 32k | context refusal (log 57426) |
| auto-security::blueteam-council | omlx-security / VulnLLM-R-7B-4bit | 8192 | 8k, 32k | context refusal (8k seat); council roster = multi-hop (2k row is fine) |
| auto-security::blueteam-orchestrated | omlx-security / VulnLLM-R-7B-4bit | 8192 | 8k, 32k | context refusal; `tool_model` roster = multi-hop |
| auto-security::bully-handoff-drafter | omlx-general / granite-4.1-30b-4bit | 16384 | 32k | context refusal |
| auto-security::pentest | omlx-security / Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit | 24576 | 2k | hot-seat reorder → `ollama-creative` GGUF ctx24k; hop 1 `finish_reason=length` with no answer (log 58030), then oMLX |
| auto-security::pentest | " | " | 8k | served oMLX; only the SSE echo made it look wrong |
| auto-security::pentest | " | " | 32k | context refusal (`estimated=38314 > 24576`, log 58192) |
| auto-security::purpleteam | omlx-security / huihui-ai--Huihui-Qwen3.5-9B-abliterated-mlx-4bit | 8192 | 2k | multi-hop (2-hop chain): served model is the final `granite4.1:8b-ctx8k` hop, not the seat hint |
| auto-security::purpleteam | " | " | 8k, 32k | context refusal |
| auto-security::purpleteam-deep | omlx-security / huihui-ai--Huihui-Qwen3.5-9B-abliterated-mlx-4bit | 65536 | 2k, 8k, 32k | multi-hop (4-hop chain): served model is the IR hop `qwen3.6:27b-q4_K_M`; prompt_tokens ≈ 622 on every size because the last hop sees the previous hop's output, not the filler |
| auto-security::purpleteam-exec | omlx-security / Jiunsong--supergemma4-26b-uncensored-mlx-4bit-v2 | 65536 | 2k, 8k, 32k | HTTP 404: variant module `security_redteam` is disabled (`config/portal.yaml` modules) |
| auto-security::redteam | omlx-security / huihui-ai--…-9B-abliterated | 8192 | 2k, 8k, 32k | HTTP 404: `security_redteam` disabled |
| auto-security::redteam-deep | omlx-security / Jiunsong--supergemma4-26b-uncensored-mlx-4bit-v2 | 65536 | 2k, 8k, 32k | HTTP 404: `security_redteam` disabled |
| auto-security::security-council-granite41-30b | omlx-general / granite-4.1-30b-4bit | 16384 | 32k | context refusal |

## dflash 4.4 tok/s — not speculative decoding

Verified from the live settings and engine log (read-only):

- `~/.omlx/model_settings.json` for `Qwen3.8-27B-4bit`: `dflash_enabled: false`,
  `mtp_enabled: false`. No other model has DFlash enabled, and no
  `dflash_draft_model` key exists (`coding_task/DFLASH2_080_PLAN.md` documents the same
  state).
- `~/.omlx/logs/server.log` at the 12:26 load says:
  `mlx-vlm runtime MTP patch applied … checkpoint ships no mtp.* weights; MTPModule
  attachment skipped`, and there is **no** `Speculative backend selected` line for this
  checkpoint (that line appears only for `Qwen3.8-27B-oQ4e-mtp`, the MTP seat).

So the DFlash seat is **plain decode on 0.8.0**, not speculative. The engine's own log
agrees with the bench: `91 tokens in 56.89s (4.4 tok/s), prompt: 4725, ttft 36.16` and
`14 tokens in 164.95s (4.4 tok/s), prompt 26544, ttft 161.80`. The 8k row's `14.6` is a
14-token sample (0.96 s window) — too short to be a rate. B1 direct measured the same
checkpoint at 15.26 / 15.16 / 13.71 tok/s, so 4.4 is a real engine-side decode slowdown
on those two rows, most consistent with the first request after a cold load (2k) and the
paged-SSD KV path at 26.5k prompt (32k). It is **not** DFlash overhead; proving the
engine cause needs the ON/OFF A/B in `DFLASH2_080_PLAN.md` plus a longer decode sample.
The bench now records `completion_tokens` and `raw_decode_tps` so a 14-token sample is
visible as such.

## The surviving "requested seat copy" eviction

The five lines in `pipeline_post080_fix3.log` (45613, 48722, 50560, 51216, 58045) evict
the **Ollama GGUF twin of the oMLX seat that is already resident** and about to prefill
(`_free_for_resident_omlx`). They are not the Ollama-admission pass that `46499b93b`
removed: each follows a served oMLX request (e.g. 50548 routes `auto-coding::laguna` to
`omlx-coding/Laguna-XS-2.1-4bit`, 50549 is the 200 `POST`, 50560 the eviction), and the
evicted model is exactly `_counterpart_models(OMLX, model)`.

Two real defects were still present and are fixed here:

- `_free_idle_memory` passed the admitted model itself as `last_models`, so a pending
  Ollama admission could unload the copy it was waiting to load. Eviction candidates now
  exclude the incoming model.
- `_check_omlx_ollama_capacity` (cold oMLX load) passed the counterpart copies as
  `last_models` and could evict them. They are now excluded, matching the commit's stated
  policy: refuse and let the router serve the copy that is already loaded.

The resident-prefill release is kept **on purpose**: it frees headroom so oMLX 0.8.0 does
not abort mid-prefill; removing it would trade a 20 GiB reload for a failed request. It
is flagged for the operator in OPEN.

## Fixes in this lane

`portal/platform/inference/load_guard.py`

- `_free_ollama` / `_unfreed_idle_ollama` take `exclude`; `_free_idle_memory` excludes
  the model being admitted; `_check_omlx_ollama_capacity` excludes the seat's
  cross-engine copies.

`scripts/speed_bench.py`

- `served_model` is the `x-portal-route` model (the SSE echo is kept as
  `response_model`); a response with neither is reported as `NO SERVED MODEL`, not
  `WRONG ENGINE`.
- Pipeline requests pin the seat's declared backend with `portal_backend`
  (`--no-backend-pin` opts into the routed path).
- Sizes `>= context_limit` are skipped and reported; a local context refusal, a
  `NO_ANSWER` reply, and a chain/council later hop are classified as
  `skipped_context` / `no_answer` / `multi_hop`, not `WRONG ENGINE`.
- Intended engine/model resolves from config order, not live health (a failed probe used
  to flip an oMLX seat to Ollama and mark every oMLX row wrong).
- Rows record `completion_tokens`, `reasoning_tokens`, `answer_tps`, `raw_decode_tps`.

`scripts/speed_gate.py`

- B3 roster omits seats whose module is disabled and lists them in
  `roster.skipped_seats`.
- B3 notes (`skipped_context`, `multi_hop`) do not make a cell invalid; comparison
  ignores non-`ok` rows.
- `run --phases B3` runs one phase.

## Re-run command and pass criteria

```bash
uv run python scripts/speed_gate.py run post080_fix4 --out-dir ~/.portal5/omlx080 --phases B3
uv run python scripts/speed_gate.py compare post080_fix4 --against pre080_run1 --out-dir ~/.portal5/omlx080
```

Pass criteria:

- `run.json` → `roster.b3_seats` has 21 seats (24 minus the 3 disabled
  `security_redteam` variants); `roster.skipped_seats` lists
  `auto-security::redteam`, `auto-security::redteam-deep`,
  `auto-security::purpleteam-exec`.
- Every cell `status` is `ok`; `invalid_engine` and `failed` are absent. Per-size notes
  are expected where 8k/32k exceeds a seat's declared window.
- Each `b3_*.json` row has `seat_status` in `ok`/`skipped_context`/`no_answer`/`multi_hop`
  and, for `ok`, `backend` = the intended backend and `served_model` = the intended
  oMLX id (not `workspace::variant`).
- `compare` prints `INVALID (0)`, `FAILED (0)`; only genuine regressions remain.
- `grep -c "reason=requested seat copy"` on the new Pipeline log should show no
  **cold-load** evictions. Resident-prefill releases may still appear; each must name
  the counterpart of the seat in the immediately preceding route line.
