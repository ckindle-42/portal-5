# SPLASH_PREFIX_FANOUT_BAKEOFF_V1 — decision record

**Date:** 2026-09-20 · **Task:** TASK_COMPLIANCE_DELIVER_AND_SETTLE_ENGINE_V1 §B · **Base:** `6ff98738` → `dd624404`
**Status:** evidence complete; **`[GATE]` is an operator decision — this record presents it and stops.** No workspace was created, `config/portal.yaml`'s engine tier is untouched, `config/backends.yaml` has no splash entry, `sweep.py`'s loop is unmodified (docstring text only).

---

## 1. Reachability — PASS, all four checks

splash 1.0 (the formula-pinned `splash-1.0-arm64-macos26` build — the only release; per the operator, the specific version and bits required for advertised speed) serves `incoai/Qwen3.8-27B-Splash` on `127.0.0.1:8000`, API key mandatory even on loopback:

1. direct `:8000` — 401 without key / 200 with.
2. forwarder `:8086` (socat `TCP-LISTEN:8086,fork,reuseaddr TCP:127.0.0.1:8000`, host) with Bearer key — 200.
3. **THE GATE**: `portal5-pipeline` → `host.docker.internal:8086` → splash — **200** (python3/urllib in-container; the minimal pipeline image ships no curl).
4. SSE survives the relay — 67 `data:` frames spread over 3.7 s (streaming, not one blob).

`scripts/splash-forwarder.sh` + `deploy/launchd/com.portal5.splash-forwarder.plist` (`StartInterval 120`) mirror `omlx-watchdog.sh`'s structure, logging, and two-consecutive-failure threshold; deliberately **not** wired into `launch.sh _ensure_native_services` — `./launch.sh up` does not start it. Port 8086 added to the Rule 7 roster (CLAUDE.md, `.env.example`) annotated *evaluation-only, splash forwarder, not started by `launch.sh`*.

## 2. Startup memory budget, verbatim (the batch-limit evidence)

From the serve log — splash's own memory plan on this box (Apple M4 Pro, 64 GB):

```json
memory_plan_json: {"device_name":"Apple M4 Pro","macos_version":"27.0.0","apple_gpu_family":9,"gpu_core_count":20,"physical_memory_bytes":68719476736,"recommended_max_working_set_bytes":60129542144,"max_buffer_length_bytes":41747087360,"max_threadgroup_memory_bytes":32768,"max_threadgroup_width":1024,"has_unified_memory":true,"supports_placement_sparse":true}
```

Load-time refusal (observed when Ollama held gemma4): *"model loading needs 17355931648 bytes plus 6871947673 bytes protected for macOS, but only 21695053824 bytes are currently available"* — the 27B package wants 17.36 GB weights + 6.87 GB macOS reserve before it will start; the 35B wants 20.92 GB + the same reserve. One-model-at-a-time is enforced twice: once by splash's own single-instance lock (*"Splash is already serving (PID …); stop it with Ctrl+C first"*), once by this memory floor.

## 3. Gate outputs, verbatim (State B)

State B = everything as `./launch.sh up` leaves it (Ollama 0.34.2 daemon, oMLX, pipeline), plus splash on :8086. Model ids: Ollama `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` (the tag `auto-compliance` declares), oMLX `Qwen3.8-27B-4bit` (present — no pull needed), splash `incoai/Qwen3.8-27B-Splash`. Real fixed body: `reading_material.fixed_body(repo, 'CIP-007-6')` — 57,906 chars (the task's `'CIP-007'` address does not parse; the revision id does).

**STATE A (dedicated) WAS NOT RUN.** Rationale, on the record: both rival engines' shortfalls replicated on the production box with ollama healthy — oMLX wedged with Ollama idle, splash deadlocked with Ollama idle — so the "is it the box?" question State A exists to answer was already answered negatively; State A could only have re-measured ollama, whose State-B numbers are already the strongest arm. Recorded `STATE_A_NOT_RUN`; nothing promotes on State A alone.

### fanout, state B (`summarize --state B --shape fanout`)

```
arm                            mode          n   wall_s  ttft_p50  per_tps  agg_tps  accept
ollama/direct/off              concurrent    1     34.8     0.389    11.60    11.49    1.00
ollama/direct/off              concurrent    2     70.8    18.086    11.47    11.30    1.00
ollama/direct/off              concurrent    4    141.3    53.211    11.53    11.33    1.00
ollama/direct/off              concurrent    8    281.5   123.727    11.63    11.37    1.00
ollama/direct/off              sequential    2     70.1     0.729    11.58    11.41    1.00
ollama/direct/off              sequential    4    140.2     0.707    11.67    11.41    1.00
ollama/direct/off              sequential    8    280.7     0.710    11.66    11.40    1.00
ollama/direct/on               concurrent    1     34.7     0.398    11.66    11.54    1.00
ollama/direct/on               concurrent    4    141.1    53.612    11.57    11.34    1.00
omlx/direct/off                concurrent    1      7.6     0.398    22.26    21.09    1.00
omlx/direct/off                concurrent    2    200.5    82.006    13.03     1.60    1.00
omlx/direct/off                concurrent    4    404.7   200.843    11.26     1.47    1.00
omlx/direct/off                sequential    2    198.8    76.197    11.21     1.50    1.00
omlx/direct/off                sequential    4    411.2    76.814    11.56     1.56    1.00
splash/direct/off              sequential    1    358.9   351.738    22.32     0.46    1.00

-- prefix reuse under load (warm TTFT / cold prefill TTFT) --
  ollama/direct/off concurrent n=1: x0.00 PREFIX_REUSED cached_tokens_reported=3
  ollama/direct/off concurrent n=2: x0.11 PREFIX_REUSED cached_tokens_reported=6
  ollama/direct/off concurrent n=4: x0.32 PREFIX_REUSED cached_tokens_reported=12
  ollama/direct/off concurrent n=8: x0.74 PREFIX_LOST cached_tokens_reported=24
  ollama/direct/off sequential n=2: x0.00 PREFIX_REUSED cached_tokens_reported=6
  ollama/direct/off sequential n=4: x0.00 PREFIX_REUSED cached_tokens_reported=12
  ollama/direct/off sequential n=8: x0.00 PREFIX_REUSED cached_tokens_reported=24
  ollama/direct/on concurrent n=1: x0.00 PREFIX_REUSED cached_tokens_reported=3
  ollama/direct/on concurrent n=4: x0.32 PREFIX_REUSED cached_tokens_reported=12
  omlx/direct/off concurrent n=1: x0.00 PREFIX_REUSED cached_tokens_reported=1
  omlx/direct/off concurrent n=2: x0.53 PARTIAL cached_tokens_reported=1
  omlx/direct/off concurrent n=4: x1.29 PREFIX_LOST cached_tokens_reported=2
  omlx/direct/off sequential n=2: x0.49 PARTIAL cached_tokens_reported=1
  omlx/direct/off sequential n=4: x0.49 PARTIAL cached_tokens_reported=2
  splash/direct/off sequential n=1: x0.95 PREFIX_LOST

-- fan-out vs sequential (same arm, same n, wall clock) --
  ollama/direct/off n=2: sequential 70.1s vs concurrent 70.8s = x0.99 FANOUT_NO_WIN
  ollama/direct/off n=4: sequential 140.2s vs concurrent 141.3s = x0.99 FANOUT_NO_WIN
  ollama/direct/off n=8: sequential 280.7s vs concurrent 281.5s = x1.00 FANOUT_NO_WIN
  ollama/direct/on: NEEDS_BOTH_MODES
  omlx/direct/off n=2: sequential 198.8s vs concurrent 200.5s = x0.99 FANOUT_NO_WIN
  omlx/direct/off n=4: sequential 411.2s vs concurrent 404.7s = x1.02 FANOUT_NO_WIN
  splash/direct/off: NEEDS_BOTH_MODES

-- engine margin, concurrent wall clock at n=4 --
  (no splash concurrent n=4 — the arm wedged; no margin computable)
```

Scope notes carried into every reading of the above: oMLX arms are REDUCED (rounds 1, `max_tokens` 160) — the full-size arms wedged twice (completions hang while `/v1/models` stays 200; one wave burned 240 s timeouts on every request); the splash full-size arm wedged at n=2 sequential ~50 min in (memory-plan suspend deadlock: splash's own log *"growth paused; waiting=1; suspended=1"*, then *"waiting for resident requests to finish"* with the resident request already finished); the splash n=1 line is the only completed splash fanout arm (rounds 2, `max_tokens` 160).

### append, state B (`summarize --state B --shape append`)

```
arm                            mode          n   wall_s  ttft_p50  per_tps  agg_tps  accept
ollama/direct/off              sequential    4    140.3     1.141    11.76    11.41    1.00
omlx/direct/off                sequential    4     34.5     1.084    20.39    18.15    1.00

-- prefix reuse under load (warm TTFT / cold prefill TTFT) --
  ollama/direct/off sequential n=4: x0.01 PREFIX_REUSED cached_tokens_reported=12
  omlx/direct/off sequential n=4: x2.71 PREFIX_LOST cached_tokens_reported=4
```

(omlx append ×2.71 is a warm-cold artifact — its append arm ran after its fanout arms in the same server session, so the "cold" reference was already warm; cached_tokens=4 says the cache held. Recorded, not hidden.)

## 4. The headline as a pair — and the append-vs-fanout contrast

**Gate 1 (does a prefill collapse exist and survive concurrency?):**

| arm | verdict |
|---|---|
| ollama sequential (all n) | **PREFIX_REUSED ×0.00** — cold 168 s → warm 0.7 s, flat to n=8 |
| ollama concurrent | REUSED to n=4 (×0.32), LOST at n=8 (×0.74) — concurrency thrashes the slot |
| omlx | PARTIAL at n=2 (×0.49-0.53), LOST at n=4 (×1.29) — re-prefills under load |
| splash | **PREFIX_LOST ×0.95 at n=1** — `cached_tokens=0` on identical back-to-back requests |

**Gate 2 (does fanning out finish sooner?):** **FANOUT_NO_WIN on every engine that completed** — ×0.99–1.02 everywhere. Neither ollama nor oMLX batches this workload; splash could not be measured (wedged). There is no fan-out to win.

**The pair, plainly:** on State B the prefill collapse exists on exactly one engine — Ollama, sequential — and fanning out wins on none. The sweep's sequential loop is not merely "correct": on today's daemon it holds the prefix cache, and every concurrent alternative either loses the cache (ollama concurrent n=8, omlx) or cannot finish (splash).

**Append-vs-fanout contrast:** ollama caches BOTH shapes now (append ×0.01, fanout-sequential ×0.00). §0.2's framing — "the conversation gets the cache; the sweep does not" — was true on Sep 17 (§P4.1 ×1.0) and is **falsified on Sep 19's daemon**: the sweep's independent sequential calls DO reuse (B2's replication: 16,708/16,730 tokens, ×118). What did not change: concurrent traffic over the shared body degrades or loses the cache everywhere it was measurable.

## 5. Projection (labelled a projection)

Scaled from fixed-body probes, not a sweep run. Register = 258 nodes; recorded baseline: 72 min/standard, ≈4.9 h full sweep (cacheless, gemma4, §P7).

* **Ollama sequential, today (Qwen3.8-27B, cached):** per node ≈ 0.7 s TTFT + 400-token decode at 11.6 tok/s ≈ **35 s/node** → per standard (20 nodes) ≈ 12 min → full sweep ≈ **2.5 h**. The cache the daemon now grants is worth ~2× the recorded baseline by itself.
* **oMLX sequential (reduced data):** 22.3 tok/s single-stream but PARTIAL reuse (×0.49) → per node ≈ 0.5 s + 76 s re-prefill-share + decode ≈ **45-50 s/node** → ≈ **3.5 h**, with two full-size wedges on record.
* **splash:** no completion of the workload at n≥2; at n=1, TTFT alone (352-370 s) exceeds the recorded per-node cost by ~7×. **Not projectable — the workload does not complete.**

## 6. Admission at n=8 and n=16 (splash, oMLX)

**Not run — wedging precluded it.** splash's admission log is nonetheless on record from the attempts: requests are *accepted* then *suspended* under KV pressure (*"growth paused; waiting=1; suspended=1"*), i.e. acceptance is not completion. Inco's 16-way/32 K acceptance claim could not be reproduced even at 2-way sequential over a 17 K body on this box. oMLX n=8/16 was not reached because n=4 full-size already hung. Both recorded honestly; no admission claim either way.

## 7. Chat verdict (second, with the aggregate-vs-per-stream distinction)

```
-- chat gate (n=4 vs n=1, same arm, concurrent) --
  ollama/direct/off: CHAT_CONCURRENCY_DEGRADES (ttft x86.80, per-stream decode x1.00)
  ollama/pipeline/off: CHAT_CONCURRENCY_DEGRADES (ttft x49.12, per-stream decode x0.99)
  splash/direct/off: CHAT_CONCURRENCY_DEGRADES (ttft x2.46, per-stream decode x0.45)
```

Absolute numbers first: splash 35B chat per-stream decode 56.5 → 25.2 tok/s from n=1→4 while walls grow sublinearly (4.8 → 11.0 s) and **aggregate rises 53.9 → 93.3 tok/s** — real concurrency. Ollama's per-stream is flat (46.9 → 46.9) but walls scale ×4 — no batching; the agent/sweep aggregate never grows. Pipeline cost is invisible at chat scale (direct vs pipeline within noise). By the stated thresholds all arms DEGRADE (ollama on TTFT, splash on per-stream); by aggregate, splash 35B chat is the only engine that gains throughput under load — good for the sweep lane in principle, and the record must also say: good chat aggregate on an engine that dies on long-prompt sequential traffic is a narrow win.

## 8. Tool-call verdict (B5, real dispatch path, `compliance_context` schema from the live MCP)

| engine | result |
|---|---|
| Ollama (Qwen3.8-27B) | **PASS** — well-formed `tool_calls`, args parse, serialized bytes clean (`'{"ref":"CIP-007-6 R2 Part 2.2","mode":"index"}'`), identical under streaming and non-streaming |
| oMLX (Qwen3.8-27B-4bit) | **PASS** — same, serialized style differs (`{"ref": "…"}` with spaces — still valid JSON) |
| splash (35B) | **TOOLCALL_INCOMPATIBLE in this environment** — non-streaming 503 `resource_timeout` ("memory did not become available within the resource wait limit"); on retry the server died mid-probe (`Server disconnected`). A model-card claim of tool support is not dispatch capability under memory pressure. |

## 9. B6 — per-cell reading comparison (Coupling 2), scorer named

Instrument: the §P1 six-case read-test (one call, no tools, `reading_material.render` material, judged by reading) — chosen over the generic scorer suite because the `coding` scorer is known to choke on reasoning-trace preamble and splash ships reasoning-on by default; these cells ran `reasoning_effort: "none"` and produce clean prose. Receipts: `reports/compliance/prove_then_scale/b6/cell_splash_*.json`.

| case | qwen38 ollama | qwen38 splash | qwen36 ollama | qwen36 splash |
|---|---|---|---|---|
| parent | PASS | PASS | PASS | PASS |
| choice | FAIL | **PASS** (finds the temporal-latitude narrowing) | FAIL | **PASS** (names the Change-Management/escalation narrowing) |
| interval | PASS | PASS (richer: reconciles note vs procedure) | PASS | PASS |
| read_check | PASS | PASS | PASS | PASS |
| either_or | PASS | PASS | PASS | PASS |
| no_operator_side | FAIL | FAIL (same policy-restatement answer) | FAIL | FAIL |
| both-sides citations | 5/6 (mechanical artifact on interval) | **6/6** | 5/6 | **6/6** |
| wall (mean) | ~301 s | ~134 s | ~56 s | ~25 s |

**The engine changed what the model says.** `choice` flipped FAIL→PASS on splash for both models — on Ollama both answered "yes, using all the latitude"; on splash both answered "no", each with different, specific, correct narrowings. `no_operator_side` stayed FAIL on both engines — that blindness is model-bound, not engine-bound. Broader scorer dimensions (instruction-following, long-context recall at window, refusal preservation) were **not run**: QUALITY_UNPROVEN for those dimensions specifically; the reading-lane comparison above is complete.

## 10. Soak verdict (B7)

**3 h bar: NOT MET at the real duty cycle.** The sweep-realistic shape (n≥2, 400-token outputs, 17 K shared body) wedged splash twice in separate attempts — first attempt ~50 min in, second on the second request — non-deterministically (the same 160-token shape that wedged at 00:38 survived a 40-round run at 07:18). Component: splash's memory-plan suspend path (*"growth paused; suspended=1"* → *"waiting for resident requests to finish"*), while `/v1/models` keeps answering 200. **The oMLX watchdog pattern would NOT have caught it** — the probe endpoint stays healthy; only completions hang (the same gap oMLX's own wedge exposes). Clean datapoint on record: 29 min at n=2/160 tokens, cache stable (16,992), TTFT 0.5-0.8 s, no drift — splash can run; it cannot yet be trusted to keep running.

## 11. Model-swap downtime (B4)

27B → 35B ready-to-ready: **42 s** after a clean kill (splash loads in ~25-30 s; the memory wait dominates when free RAM is short). Failure mode on record: a swap attempted while the previous serve lives produces a single-instance refusal, and the operator-visible model list then lies (old model still listed until the new one binds). One-model-at-a-time is an operational cost every workspace that binds splash pays on every seat change.

## 12. Recommendation on `sweep.py` — recorded finding only; loop NOT modified

**Keep the sequential loop; the evidence does not support changing it.** Gates 1 and 2 did not both clear on any engine: ollama sequential is the only arm with both prefix reuse (×0.00) and completion; concurrent arms lose the cache (ollama n=8), re-prefill (omlx), or wedge (splash). Concrete recorded finding for a future task: on State B, ollama's sequential loop already holds the fixed body in cache (this is new since §P4.1 — see §13), so **the cheapest speed win for the sweep is not an engine swap at all: it is a daemon-config pin** — the §B2 forensics show the reuse appeared with the daemon environment/state changes of Sep 18-19 and is not yet pinned by configuration the repo controls. A `sweep.py` change would be justified only by a future instrument run in which some engine completes the workload with reuse AND beats ×1.15 of sequential wall.

## 13. What changed under §0.2 — the §P4.1 premise is time-stamped, not eternal

§0.2 corrected the sweep docstring on the strength of §P4.1 (collapse ×1.0, no cross-request reuse). B2's self-test then found **§P4.1 no longer reproduces**: the same shape through the module's own transport reuses 16,708/16,730 tokens (×118). Forensics: same binary (0.34.2 installed Sep 17 22:57), same daemon env (FLASH_ATTENTION/q8_0/NUM_PARALLEL=4 verified in ollama.log across the Sep 17/18 restarts), NUM_PARALLEL=1 A/B negative — the flip is daemon *state*, not configuration; attribution open. Consequences carried: the B2 docstring states the three-layer history; the A4.3 conversation-cache proof stands (append shape, ×157); §0.2's "correct by accident" framing is retired — the loop is correct *by measurement* on today's daemon, and B8's recommendation rests on today's measurement.

## 14. Scope-only: if the `[GATE]` ever promotes a splash tier

Mirroring `unit-design-omlx-dual-backend-plumbing`'s B1 plumbing — **scope, not implementation**:

* `Backend.type = "splash"`, `health_path: /v1/models`.
* `_inject_splash_options` peer to `_inject_omlx_options`: no `options` sub-dict, no `keep_alive`, no `num_ctx`; `think: false` → `reasoning_effort: "none"`; `repeat_penalty` has no splash equivalent and **must be dropped explicitly**, not passed through.
* `aliases:` mapping the GGUF `model_hint` to the package id (`hf.co/unsloth/Qwen3.8-27B-GGUF:…` → `incoai/Qwen3.8-27B-Splash`; `…Qwen3.6-35B…` → `incoai/Qwen3.6-35B-A3B-Splash`).
* `priority:` for a shadow-then-shift rollout.
* The one-model-at-a-time constraint is the real architectural cost: per §0.6, the council gives each seat its own model and iterates serially — a fan-out *across* models splash cannot serve at all; the bench/UAT/persona-matrix/WFE harnesses sweep a diverse fleet, which a single-model engine buys nothing; **and per A3, the conversation's seat is gemma4 — splash ships no gemma4 package, so the conversation and the sweep would run different models.** That cost is stated, not hidden.
* Pre-conditions any promotion must clear first (from this record): the suspend deadlock (§10), tool dispatch under memory pressure (§8), and a stability soak at the real duty cycle (§10's 3 h bar).

## 15. §0.3, recorded

The barrier is not CLAUDE.md Rule 8. Rule 8's heading says "Single Inference Tier: Ollama"; its enforced body is *"Never add `transformers` or `torch` to `portal/platform/inference/`"* — an HTTP-speaking engine violates nothing, and oMLX is already a second tier in production at `:8085`. The real barriers are the ones this record prices: one-model-at-a-time, a proprietary package format, a v1.0 track record (§10), and a loopback bind requiring the forwarder (§1).

---

## `[GATE]` — operator decision. Evidence presented; this task stops here.

The three options, priced by this record:

1. **Sanctioned evaluation tier with a dedicated compliance seat** — blocked today by §10 (non-deterministic suspend deadlock at the duty cycle) and §8 (tool dispatch fails under memory pressure). Both are splash-side defects; re-run this bake-off after a splash release fixes them. The 35B MoE is the interesting package: it reads (B6, 6/6 both-sides, ~2.5× faster than Ollama on the same cells), batches chat aggregate (×2), and holds its cache within a run.
2. **Standalone side-channel for the sweep** — the sweep's own verdict (§12) is that ollama sequential already wins on today's daemon; a side-channel buys nothing until splash completes the workload at all. Not recommended on this record.
3. **Drop** — the forwarder scripts and roster line are inert without a serve process; nothing to unwind beyond deleting them.

Materials for the decision: this record, `B2_SELFTEST_VERDICT.md`, the `tests/benchmarks/results/engconc_*` receipts, `reports/compliance/prove_then_scale/{b5,b6}/`, and the splash serve log at `~/.portal5/logs/splash-serve.log`.
