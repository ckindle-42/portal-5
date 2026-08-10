# Daily-Work Fleet Soak — 1:1 + Pipeline (tool-driven)

**Task:** TASK_DAILY_WORK_FLEET_SOAK_V1
**Method:** bench_daily_soak.py. 10 real daily categories, deep tool-provoking banks,
~3h each, concurrency 3. Direct legs (omlx/ollama) = true 1:1; pipeline leg = full-system shape.
**HEAD:** `33559917` (built on top of `TASK_OMLX_FULL_PIPELINE_COVERAGE_V1`, commits `50b73876`/`33559917`)

## 1:1 engine comparison (direct, same day of real work)

| | oMLX (direct) | Ollama (direct) |
|---|---|---|
| Total requests | 808 | 552 |
| Completed OK | **696** | 552 |
| Failed | 112 (13.9%) | 0 (0.0%) |
| Elapsed | 3.01h | 3.02h |
| TPS p50 / p90 | 16.6 / 33.5 t/s | 15.6 / 30.2 t/s |
| TTFT p50 / p90 | **4.2s** / 64.3s | 26.7s / 68.8s |

**Completed-work ratio: oMLX 1.26x Ollama** (696 vs 552 successful requests in the same 3 hours). oMLX wins on total throughput *despite* a 13.9% failure rate, because it fails fast (milliseconds) and moves to the next request, while Ollama never fails but queues — Ollama's much higher p50 TTFT (26.7s vs oMLX's 4.2s) is the queuing cost showing up as latency instead of a hard reject. This confirms the hypothesis both prior soaks flagged: completed-work-per-hour and fast-explicit-reject vs slow-silent-queue, not raw failure count, is the right lens.

**Per-workspace failure breakdown (oMLX only — Ollama had zero):**

```
auto-data        37.8% fail  (largest resident model — granite-30B dense, most cross-group thrashing)
auto-research    25.0% fail
auto-creative    22.7% fail
auto-daily       22.2% fail
auto-coding      13.9% fail
auto-spl          7.7% fail
auto-compliance   7.5% fail
auto-documents    5.6% fail
auto-reasoning    2.9% fail
auto-security     0.0% fail  (small model, low contention)
```

Failure rate tracks model size and cross-category switching frequency, not randomness — `auto-security`'s 0% and `auto-data`'s 37.8% bookend it cleanly.

**Failure mechanism (both are admission-control rejections, not crashes or bad output):**
- 69× HTTP 400 — oMLX's "prefill memory guard": request to an *already-loaded* model, but this specific prompt's predicted peak memory would exceed 90% of the Metal ceiling (`iogpu.wired_limit_mb` = 56GB of 68.7GB total system RAM).
- 43× HTTP 507 — "cannot load": request needed a *different* model not currently resident, and loading it would blow the ceiling. This is the cross-group thrashing `TASK_OMLX_FULL_PIPELINE_COVERAGE_V1` predicted, now measured under a real 10-category daily mix instead of coding-only.

## Tool-path behavior

Shakedown (Phase 2) independently verified real tool execution before committing to the 3h legs: a direct `auto-documents` request through the pipeline produced a genuine downloadable `.docx` (confirmed HTTP 200 on the generated file URL), not just prose claiming success. Default container log verbosity doesn't surface per-tool-call detail, so tool-firing was verified by response content/artifact, not log-grepping — worth noting for future soaks that want log-level tool telemetry.

No systematic difference in failure concentration between tool-heavy categories (documents/security/spl/data/research/compliance) and chat-heavy ones (daily/creative/reasoning) was visible on oMLX — `auto-data` (tool-heavy) and `auto-daily` (mostly chat) both landed in the 20-38% range, while `auto-documents` (tool-heavy) stayed at 5.6%, driven by model size/contention rather than tool usage.

## Pipeline production shape

689/689 requests succeeded (**0% failure**) over the full 3h — the production path never surfaced a client-visible error, including during the same kind of memory pressure that caused direct-oMLX failures. `by_served_backend`:

```
omlx-reasoning   224 ok   (auto-reasoning/research/compliance/data — 4-model multi-alias backend)
omlx-coding      150 ok
omlx-general      99 ok
omlx-security     67 ok
omlx-creative     40 ok
ollama-coding     42 ok   (fallback when omlx-coding was memory-constrained)
ollama-general    67 ok   (fallback when omlx-general was memory-constrained)
```

Every daily group served from `omlx-*` as its majority backend, with honest Ollama fallback for a meaningful minority (109/689 ≈ 15.8%) of coding/general requests — this is the pipeline's `get_backend_candidates` fallback chain doing exactly what it's designed to do, converting oMLX's 400/507 rejections (visible as client failures on the direct leg) into a silent, slightly-slower Ollama-served response instead. TTFT p50 (10.7s) and TPS p50 (12.3 t/s) sit between the two direct legs, consistent with a blended real-world mix plus routing/persona overhead on top.

## Failure-rate over time (oMLX direct, 30-min buckets)

```
  0- 30min   9.5%
 30- 60min  18.0%
 60- 90min   9.9%
 90-120min   9.2%
120-150min  19.6%
150-180min  14.5%
```

Oscillating steady-state noise (9-20%), not a monotonic drift — consistent with cross-category thrashing (which model combination happens to be resident when a request lands) rather than a leak or progressive degradation.

## Incident during this soak: kernel panic between legs 2 and 3

The system experienced a full kernel panic and reboot at `2026-08-10 01:11:46 CDT`, roughly 10 minutes into the originally-launched pipeline leg. Root cause confirmed from `/Library/Logs/DiagnosticReports/panic-full-*.panic`:

```
panic(cpu 0): userspace watchdog timeout: no successful checkins from
WindowServer (1 induced crashes) in 122 seconds
```

**Root cause chain:**
1. `iogpu.wired_limit_mb` = 56GB caps oMLX's own Metal allocation — enforced (that's the 400/507s above).
2. **Ollama has no memory limit configured at all** (`OLLAMA_MEMORY_LIMIT` unset in its launchd environment — a previously-known, deferred risk that materialized here). It held a 54GB model (`granite4.1:30b-ctx64k`) resident at the end of the direct-Ollama leg.
3. The pipeline does have a real, code-level cross-engine memory gate — `MEMORY_GATE_PCT` (default 90%) in `portal/platform/inference/router/concurrency.py:187`, checking total system `vm_stat` before admitting new pipeline requests. But it only guards the pipeline path (`:9099`); the direct-engine legs bypass it by design (that's the point of the 1:1 comparison).
4. **Operational gap, not a code gap:** the task's "unload between legs" discipline was followed between the two *direct* legs (oMLX unloaded before the Ollama leg started) but not extended to the leg-2→leg-3 transition — Ollama's 54GB was still resident when the pipeline leg began loading oMLX models on top of it. Combined footprint (~54GB stale Ollama + up to 56GB fresh oMLX against 68.7GB physical) likely spiked faster than the gate's health-cycle polling could react, causing severe swap/compression pressure that starved WindowServer past its 122s watchdog window.

**Recovery:** confirmed clean 0GB/0GB state on both engines, relaunched the pipeline leg via `launchctl submit` (fully detached from the Claude Code session's process tree, so it survives that layer being torn down — though not a second full OS panic) for a clean, complete 3h run. The reported pipeline-leg numbers above are from that clean restart.

**Recommendations (not yet applied — would require a leg restart, deferred until after this run):**
1. Set `OLLAMA_MEMORY_LIMIT` (e.g. ~40GB) in Ollama's launchd plist so oMLX (56GB) + Ollama (40GB) can't jointly exceed physical RAM even in the worst case.
2. Extend the "unload between legs" discipline to *every* leg transition, not just direct-to-direct — unload both engines' resident models before starting any new leg, including into the pipeline leg.
3. Consider lowering `MEMORY_GATE_PCT` below 90% or tightening the health-cycle poll interval, since 90% + polling latency was not sufficient headroom against a fast combined-engine memory spike in this incident.
4. Optionally raise `iogpu.wired_limit_mb` closer to the 68.7GB physical ceiling (or lower it further) as a separate lever if oMLX's rejection rate needs tuning — see the failure-rate section above for the tradeoff this trades against.

## Caveats

- Concurrency 3 (daily overlap, not the prior soak's 5-way stress).
- Deep but finite banks — expand for even longer runs.
- `served_backend` from `x-portal-route` on the pipeline leg; direct legs are engine-pinned.
- The pipeline leg's 0% failure rate should be read alongside the oMLX direct leg's 13.9% — the pipeline isn't "better at not failing," it's absorbing the same rejections via fallback, which is by design but means the pipeline number alone doesn't show the underlying engine behavior.
- A kernel panic occurred mid-soak (see Incident section); the reported pipeline numbers are from a clean post-incident restart, not the original interrupted attempt.

## Provenance

- `results/daily_soak_direct_omlx_day_1to1_20260810T025817Z.json`
- `results/daily_soak_direct_ollama_day_1to1_20260810T055938Z.json`
- `results/daily_soak_pipeline_day_pipeline_20260810T150729Z.json` (+ checkpoints, shakedowns in the same directory)
- Harness: `tests/benchmarks/bench_daily_soak.py`
- HEAD: `33559917`
