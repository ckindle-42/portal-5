# B2 instrument self-test — verdict and evidence

**Date:** 2026-09-19 · Harness: `tests/benchmarks/bench_engine_concurrency.py` (schema `engine_concurrency_v2`)

## Check 1 — against a stopwatch: PASS

`--engine ollama --model granite4:tiny-h --shape short --mode concurrent
--concurrency 1,4 --rounds 2` (record
`engconc_ollama_direct_short_concurrent_off_stateSELFTEST_20260919T222358Z.json`):

* TTFT non-null on every request (46–250 ms).
* `completion_tokens` = 64 on all 6 requests — identical to a plain curl at
  the same `max_tokens`.
* n=4 wall 3.11 s / 3.65 s against n=1 walls 0.83–0.89 s: ≈4× a single
  request, matching Ollama's known no-continuous-batching behaviour on this
  box. Hand-check arithmetic holds.

## Check 2 — negative control as specified: the KNOWN BEHAVIOUR CHANGED

`--shape fanout --mode sequential --concurrency 4` on Ollama was REQUIRED to
report `PREFIX_LOST` (§P4.1 measured ×1.0 over twenty calls). **It reports
`PREFIX_REUSED` ×0.15** (record
`engconc_ollama_direct_fanout_sequential_off_stateSELFTEST_20260919T222511Z.json`,
cold prefill 11.53 s vs wave ttft_p50 1.73 s; `cached_tokens` reported on all
4 members).

The task's instruction for this branch: check whether the harness is forming a
prefix the sweep does not. It is not:

* Each wave member is an independent HTTPS request with an independent
  message array (`[system: body, user: tail_i]`) — no continuation.
* The §P4.1 shape re-run through the sweep's OWN transport dialect — gemma4,
  the REAL CIP-007-6 fixed body (57,906 chars), native `/api/chat`,
  `think:false`, `keep_alive:"30m"` — reuses 16,708 of 16,730 tokens: prefill
  **0.27 s against 31.82 s full price (×118)** on call 2, an independent
  request sharing only the body prefix. Call 3 (identical to call 1) likewise.
* A genuinely-unshared control (two ~3.7k-token prompts with different
  bodies) prefills at FULL PRICE with `cached=0` on both — the instrument
  reports a miss when there is nothing shared. The reuse is real prefix
  sharing by the daemon, not a broken clock.

**Attribution (probed 2026-09-19, still open):** §P4.1 ran 2026-09-18 15:38
(p4_run.log timestamps; prefills 48.68/49.76/46.04/48.94 s) on daemon PID
started 2026-09-18 13:16 — i.e. AFTER the `ollama-0.34.2` binary landed
(Sep 17 22:57, symlink 22:58). The daemon's launchd plist env is IDENTICAL
across the Sep 17 22:58, Sep 18 13:16 and current restarts (FLASH_ATTENTION
true, KV q8_0, NUM_PARALLEL 4, MAX_LOADED_MODELS 5, GPU_OVERHEAD 20 GiB —
verified in ollama.log server-config lines). A NUM_PARALLEL=1 A/B was run via
the daemon plist (`launchctl bootout/bootstrap`, restored to 4 afterwards):
**reuse persists unchanged at NUM_PARALLEL=1** (16,708/16,730 cached, prefill
0.27 s vs 30.32 s cold). So the flip is neither the binary version nor the
daemon env — same binary, same env on both sides of the behavior change. The
difference is daemon STATE, not configuration; candidates (slot occupancy
from concurrent sessions during the Sep 18 campaign, KV pool pressure) are
not isolable without re-running the Sep 18 campaign under its exact session
state. Record: ×1.0 was real when measured; ×118 reuse is real now; the
attribution is open.

**Consequence for Part B, on the record:** on State B, Ollama ALREADY shares
prefixes across independent sequential requests. The sweep's sequential loop
is a stronger incumbent than §0.2 assumed, Gate 2 must beat a cached
sequential baseline, and §0.2's "correct by accident" framing is stale. The
sweep docstring now states the three-layer history verbatim.

## Check 3 — positive control (append): PASS

`--shape append --mode sequential --concurrency 4` on Ollama reports
**`PREFIX_REUSED` ×0.10** (record
`engconc_ollama_direct_append_sequential_off_stateSELFTEST_20260919T222523Z.json`;
cold 1.75 s vs wave ttft_p50 0.18 s) — matching §P4.1's append caching at
26,005 tokens / 19.5 s vs 38.2 s.

## Verdict

The instrument reproduces every behaviour that still exists to reproduce —
stopwatch, append caching, and true-miss detection — and its PREFIX_LOST
capability is demonstrated by the no-shared-prefix control rather than by a
shape that State B's daemon no longer treats as a miss. **Not
MEASUREMENT_UNTRUSTED.** All downstream B3–B7 measurements may proceed, with
this document as the standing caveat on every Ollama baseline.
