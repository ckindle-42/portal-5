# FINDING — oMLX 0.8.0 seat thrash: empty answer counted, hot-seat flips to the GGUF copy

Lane `lane/omlx080-seat-thrash`, base `e37b1f769` (2026-11-20). Operator decision: stay on oMLX
0.8.0; fix the Pipeline. Code is complete and gate-green; every live claim below is for the
orchestrator to re-prove with `~/.portal5/omlx080/run_baseline.sh post080_fix2`.

## Property 1 — an empty completion is not success

**Live evidence.** `pipeline_b2_20261120T1530Z.log:5026-5031` — auto-coding non-stream with 17
tools: "answered nothing with tools attached; asking once with tools off" → toolless retry
`0 tool_calls, content=''` → **"Backend omlx-general succeeded"**. Same shape at `:4729-4734`
(auto-daily).

**Cause.** The only non-stream request in the B2 run is the bench warm-up
(`tests/benchmarks/bench/runners.py:309` → `tests/benchmarks/bench/measure.py:65-70`), which
sends `max_tokens: 1`. The seat's `think: true` (config/portal.yaml auto-coding) makes that one
token a thinking token. oMLX 0.8.0 reports `finish_reason=length` with the unterminated thinking
block kept in the reasoning channel (`~/.omlx/logs/server.log:9002`, 09:32:43 — the matching
engine-side line: `1 tokens in 0.51s ... prompt: 6466, finish_reason=length, max_tokens=1`), so
the engine legitimately returns `content=null` and no tool call. Verified by the engine's own
`extract_thinking(..., truncated=True)` path (`api/thinking.py:216-235` in the 0.8.0 wheel).
That is the "0.8.0 thinking/chat-template behaviour vs our request shape": the *request shape*
is the one-token warm-up.

**Fix.**
- `portal/platform/inference/router/non_streaming.py:744-764` (`_empty_completion`,
  `_empty_reply_reason`); `:1274-1291` — a 200 with no visible content and no `tool_calls` is
  now a failed hop: logged with finish_reason/reasoning, recorded as `empty_completion`, and
  `None` returned so the caller tries the next candidate. A tool-loop synthesis that spent its
  tokens on reasoning (tools already dispatched) keeps the existing `NO_ANSWER_MESSAGE` — a
  retry there would re-run side effects.
- `tests/benchmarks/bench/measure.py:65-75` — the warm-up now asks both wire shapes for no
  thinking (`think: false`, `chat_template_kwargs.enable_thinking: false`), so a one-token load
  probe returns a visible token instead of an empty 200.

## Property 2 — the seat's Ollama copy never leads while the oMLX copy is healthy/loaded

**Live evidence.** `pipeline_b2_20261120T1530Z.log:5031-5033` — the oMLX copy (Qwen3.8-27B-oQ4e-mtp)
has just served; the next stream request routes `ollama-general model=...GGUF:Q4_K_M-ctx96k
(1/12 candidates)`. At `:5067-5100` the guard evicts the oMLX copy (`reason=requested seat copy`)
and the GGUF still does not fit (29.1 GiB > 23.5 available), so it routes back to oMLX at `:5474`.

**Cause.** `placement.protect_hot_seat` judged the literal `candidates[0]` (omlx-coding), which
does not serve auto-coding's ctx96k hint at all — both dispatchers skip it and use omlx-general,
which serves the *same* model that is hot. The literal head's default model (Qwen3-Coder) differs
from the hot model, so the policy demoted the request to the first non-oMLX candidate that serves
the hint: the seat's Ollama GGUF copy. Reproduced offline against the shipped config
(`coding_task/scratch/repro_candidates.py`): before the fix the order became
`ollama-general, omlx-coding, ollama-coding, omlx-general, …`; after it stays unchanged and
streaming selects `omlx-general → Qwen3.8-27B-oQ4e-mtp`.

**Fix.** `portal/platform/inference/router/placement.py:190-203` (`_effective_head_index`),
`:241-259` — hot-seat protection now measures the *effective* head (the first candidate that
serves the workspace hint, i.e. what the dispatchers use) and leaves the order alone when that
head's model is the hot model or is already resident on the engine
(`HotSeatTracker.loaded_models`, populated from oMLX `/v1/models/status` through the existing
`sync_omlx_loaded` call). The reorder now moves the alternative into the effective head's slot
instead of byte-position 0.

## Property 3 — load_guard never evicts a seat's loaded copy for its other-engine copy

**Live evidence.** `pipeline_b2_20261120T1530Z.log:5085` — `load_guard: evicted
Qwen3.8-27B-oQ4e-mtp on omlx, 16.6 GiB freed (reason=requested seat copy)`.

**Cause.** `load_guard._free_idle_memory` excluded the seat copies from the first oMLX LRU pass,
then ran a "last resort" pass (`exclude=other_omlx, last_models=seat_copies`) that evicted exactly
the excluded copies when the Ollama load still did not fit. The guard's failover window already
excludes models the router failed over FROM (`_omlx_idle_models` / `_ollama_hold_reason`), so the
only copies that pass could evict were *healthy* ones.

**Fix.** `portal/platform/inference/load_guard.py:1419-1468` — the last-resort seat-copy pass
(and the `deferred_copy` retry plumbing it fed) is removed. A seat's other-engine copy is never
evicted to load its counterpart; when nothing else frees enough the admission waits and refuses,
and the request cascades to the copy that is already loaded.

## Property 4 — the preferred resident yields to a live oMLX engine

**Live evidence.** `pipeline_b2_20261120T1530Z.log:462` (Nemotron 23.8 GiB resident on
ollama-general), `:4977` (reload attempt during work), `:2322` (reload between cells). The
oMLX guard log (`omlx_guard_reject_0923.log`) shows oMLX's dynamic ceiling down to 23.22 GB with
oMLX itself at 22.15 GB, so a 23.8 GiB Ollama resident leaves no prefill room.

**Cause.** `lifespan._warm_preferred_resident` only checked in-flight requests (`plan.busy`,
`guard.has_activity`). A loaded-but-idle oMLX seat was invisible, so the keeper warmed the 23.8
GiB Nemotron into the engine's working set.

**Fix.** `load_guard.plan` now reports `omlx_live` (any model oMLX reports `loaded`;
`load_guard.py:2538-2551`); `lifespan.py:379-382` waits with
`"waiting for the oMLX engine serving live work"` while it is true, and the residency log
`:468-473` names the config source (`config/backends.yaml defaults.preferred_residents`).
Ollama fallback is untouched — this only stops the *warm-up* from taking a live engine's memory.

## Tests added

- `tests/unit/test_pipeline_hardening.py` — empty 200 without a call is a failed hop (replaces
  the old `test_null_content_reply_is_not_a_failure`, which asserted the opposite).
- `tests/unit/test_router_placement.py` — effective-head order unchanged for the live auto-coding
  shape; different effective head still demoted; a resident copy is never replaced by its
  other-engine copy; loaded-set tracking.
- `tests/unit/test_load_guard.py` — the seat copy is not evicted when it is the only memory; the
  load is refused instead.
- `tests/unit/test_pipeline.py` — the preferred resident waits on a live oMLX engine.

## What proves each property live (post080_fix2 pipeline log)

1. No `Backend <id> succeeded ... model=<m>` immediately after `content=''`; instead
   `returned an empty completion (... finish_reason='length' ... reasoning=True); treating it as
   a failed hop`, and the warm-up no longer produces that pair at all (its request has
   `enable_thinking: false`).
2. For auto-coding: `Stream routing: workspace=auto-coding backend=omlx-general
   model=Qwen3.8-27B-oQ4e-mtp` — never `backend=ollama-general` for the ctx96k hint.
3. No `reason=requested seat copy` line at all; a load that cannot fit waits/refuses.
4. `Preferred resident ...: waiting for the oMLX engine serving live work` (or `resident`)
   while oMLX holds a seat — never `loaded` in the middle of a bench cell.
