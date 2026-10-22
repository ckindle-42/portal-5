# Load Guard whole-module review

**Audit base:** `15120e8919f9d80858a6d27a93e9a9d2d67d48c0` (`plan/guard-review`, clean at start). Reviewed `load_guard.py` end to end, the native Ollama transport, request wait-header wiring, capacity cascades, lifespan warmup/wiring, the complete load-guard unit file, the two named Known Limitations, and the admission history. The wiki fact-unit tools were not available in this worker session; discovery used the current source and those authored records.

## State machine at the audit base

The guard has no persisted admission state. Each `LoadGuard` had its own `asyncio.Lock`, busy counter keyed by `(engine, model)`, observed Ollama footprints, and per-admission pending-free records. The Pipeline lifespan constructs a guard per worker. `PIPELINE_WORKERS` defaults to two in compose, so the original lock and busy counter did not coordinate workers.

1. **Bypass or already resident.** `LOAD_GUARD=0` or an empty model bypasses admission; transport still starts/ends request tracking when a guard exists. A model found in Ollama `/api/ps` or reported loaded by oMLX skips the cold-load lock. An unreadable initial Ollama process list, unavailable oMLX status, or unknown Ollama model size fails open.
2. **Cold admission lock.** Ollama admission reads resident models and size tags, acquires the cold-load lock, then rechecks residency and capacity. oMLX cold admission checks status, acquires the same lock, and checks status again. The lock covers cross-engine cold loads in one guard; it is released when the model becomes resident (up to 600 seconds) or when its request ends.
3. **Capacity measurement.** `need` is the larger of tag size × `LOAD_GUARD_FACTOR` and the largest previously observed Ollama footprint. Capacity is oMLX headroom plus reclaimable idle Ollama memory minus `LOAD_GUARD_MARGIN_GB`. `LOAD_GUARD_CEILING_GB`, when set, supplies the headroom ceiling in place of oMLX's live `final_ceiling`.
4. **One free pass.** If an Ollama model does not fit, one pass unloads idle oMLX models in LRU order (200 is synchronous, 202 is queued and credited only as the oMLX memory counter drops). If that does not free enough, it asks Ollama to unload idle models. The admission then remeasures; it does not repost a sticky unload.
5. **Wait or return.** If oMLX reports a reachable model transition, the guard releases the cold lock, polls transition state, reacquires, and remeasures. Otherwise it checks foreign oMLX activity and waits for tracked request completion, a counter change, or pending frees only when such activity can change capacity. A quiet host with no pending change is refused immediately. On a real wait, it polls at most every five seconds and remeasures after reacquiring.
6. **Request lifetime.** The transport calls `begin` before sending to the engine. The idempotent end closure clears busy state, releases cross-worker activity tracking, and wakes local waiters. The streaming wrapper owns the same end/release callbacks until stream close. A background poll releases a cold-load lock as soon as `/api/ps` or oMLX status reports the model resident.
7. **Plan.** `plan()` measures a requested set against current residents, idle Ollama models, and freeable idle oMLX models; it does not acquire locks or unload anything.

## Waits and refusal surface

| Wait or refusal | What it waits for | Message / result |
|---|---|---|
| Cold-load lock acquisition | Another guard cold admission to finish; bounded by this request's `X-Portal-Load-Wait` or `LOAD_GUARD_WAIT_S` | `cold load of {model} would exceed its wait for another model load ({seconds}s)` |
| oMLX transition | `is_loading` / `models_loading` to clear; lock is released while polling | `Cannot load {model}: engine model transition still active after waiting {seconds}s` |
| Queued Ollama free | Model to disappear from `/api/ps` and, on the live-ceiling path, enough host headroom to appear | `Cannot load {model}: free of {names} did not settle within the {seconds}s load wait (projected …, host headroom …)` |
| Capacity wait | Pipeline request completion, foreign oMLX activity ending, a pending free/counter change, or the next 5-second recheck | `Cannot load {model}: projected memory … would exceed host headroom … (oMLX headroom … + idle Ollama … - margin …) after waiting {seconds}s` |
| Quiet capacity refusal | Nothing is in flight and no pending change can raise capacity | Same projected-memory message ending `with nothing in flight to wait for` |
| Native transport | Converts `LoadRefusedError` to HTTP 507; router capacity classifiers cascade it as an engine capacity rejection | JSON error body carries the refusal text |

The wait header is parsed as seconds and clamped to 0–3600; malformed or absent values use the configured default. oMLX's own capacity refusal is not made by this guard: oMLX's engine guard owns that decision.

## Findings, ranked

### High — fixed-ceiling admission did not subtract committed Ollama memory

At the audit base, the fixed headroom replaced the live ceiling but the formula still added idle Ollama bytes without subtracting Ollama residents. A fixed 8 GiB ceiling, one idle 4 GiB resident, a 6 GiB tag (7.5 GiB projected), and a 2 GiB margin yielded 10 GiB available and admitted a model that cannot fit the fixed budget. A busy Ollama resident was also invisible to this fixed headroom. This is separate from the live-ceiling behavior described by `P5-OMLX-CEILING-001`.

**Fixed:** `_ollama_available()` subtracts observed resident Ollama bytes under the fixed ceiling and adds back only idle bytes that can be reclaimed. Ollama admission and `plan()` use this accounting. `host_free_bytes()` retains its existing best-case reclaimable-memory estimate (`fixed headroom + idle residents`), as required by its current memory-gate contract test; the native load admission remains the final capacity decision. Tests cover an idle-resident over-admission and a busy resident across independent guards.

### High — independent Pipeline workers could admit cold loads from the same snapshot

At the audit base, two worker-local locks did not serialize cold Ollama/Ollama or Ollama/oMLX admissions. Their in-memory busy counters also could not see a request already running in another worker. I reproduced the cold-load race with two independent guards over the existing fake engines: the second admission completed while the first cold load was still waiting to become resident.

**Fixed:** cold admissions coordinate through a shared `flock` file under `/tmp/portal-5-load-guard`; per-engine/model shared locks expose active request leases to other guards. The same mechanism covers Ollama and oMLX. Regression tests exercise two Ollama guards and an Ollama/oMLX pair.

### Medium — rejected Ollama unload responses were recorded as pending frees

`_free_ollama()` ignored the HTTP response status. A 500 response left the model resident but was added to pending frees, so an idle host waited out the whole load budget and reported an unsettled free. The new fake-backed test failed at the audit base after 0.3 seconds with that delay.

**Fixed:** only successful 2xx unload responses create pending-free records; unsuccessful responses are logged and lead to the normal quiet capacity refusal.

### Medium — an immediate Ollama free could be used as its own baseline

Pending-free baselines were sampled after all unload requests. When an Ollama unload returned the model to `/api/ps` and raised the live headroom before that sample, the subsequent settle check required another rise of the same size. If the new headroom still could not fit the target, the guard waited to the deadline and falsely said that the completed free had not settled. A fake with an immediate 10 GiB headroom rise reproduced the full 0.3-second wait.

**Fixed:** each accepted Ollama unload stores the headroom observed immediately before its own POST. The admission remeasures actual capacity separately, so a completed-but-insufficient free now gets the quiet capacity refusal without spending the remaining wait.

### Maintainability — admission remains just over the 80-line guideline

`_admit_ollama` is 84 lines at both the audit base and after these changes, with eight `if` nodes. No helper left by prior rounds was found to be dead: the pending oMLX/Ollama bookkeeping, transition probes, cancellation cleanup, and wait accounting are all reachable. I kept the admission loop's size unchanged and did not move instrumentation sites from the planned metrics lane.

## Verification and evidence

The pre-fix tests failed on the audited code for the response-status, cross-guard cold-load, and immediate-headroom-baseline cases. An isolated archive of the audit base also failed the fixed-ceiling regression with `Failed: DID NOT RAISE LoadRefusedError`. The added regressions pass on the changed worktree. The complete contract gate and commit receipts are in the worker's final report.

## Open / risk

- The cross-worker lock assumes Pipeline workers share one writable `/tmp`, as the compose workers do. This does not coordinate separate hosts or independently isolated containers sharing remote engines.
- The preflight `host_free_bytes()` estimate can be higher than the fixed-ceiling admission capacity when idle Ollama models are present. This preserves the established memory-gate estimate; the native transport's load admission applies the stricter fixed-budget check before sending a model load.
- Activity locks make already-running requests visible, but a resident request can begin in another worker after an admission snapshots the idle list and while an Ollama unload POST is in flight. Closing that narrow start-versus-unload window needs a per-model operation reservation and a post-wait residency recheck; the current transport has already completed admission before `begin`. No live two-worker stack test was run from this worktree.
- The wiki fact-unit search/get/explain tools were unavailable in this session.
