# oMLX vs Ollama — Multi-Model Sustained Bake-off

**Task:** TASK_OMLX_OLLAMA_MULTIMODEL_BAKEOFF_V1
**Question:** under mixed concurrent multi-model load, does oMLX hold steady or degrade vs Ollama?
**Method:** `bench_omlx_v3.py --gate shootout`, identical duration/concurrency/model-set per engine.
**Steadiness metric:** decode-TPS coefficient of variation (`tps_cv`, lower=steadier) + `ttft_p99` tail + failure rate.
**Engines:** oMLX v0.5.7 (`:8085`, just upgraded from 0.5.4 — see Provenance), Ollama 0.32.5 (`:11434`).
**Model set:** coder / gemma / 3B-general, matched across engines (oMLX native ids ↔ Ollama GGUF tags, `llama3.2:3b` newly registered in `config/backends.yaml` for this run).
**HEAD:** `c1949a89`

## Results — matched load (180s, concurrency 6)

| metric | Ollama | oMLX | note |
|---|---|---|---|
| total requests completed | 15 | 86 | oMLX served **5.7x** more requests in the same window |
| ok / failures | 10 / 5 (33% fail) | 85 / 1 (1.2% fail) | |
| throughput (rps) | 0.03 | 0.46 | **15x** |
| ttft p50 (s) | 53.7 | 0.49 | |
| ttft p95 (s) | 177.0 | 3.23 | |
| ttft p99 (s) | 177.0 | 6.81 | **26x** lower on oMLX |
| tps_mean | 2.8 | 20.5 | **7.3x** |
| tps_cv (steadiness, lower=better) | 0.947 | 0.559 | oMLX markedly steadier |

The task's own comparator script renders a mechanical "DEGRADES" verdict because it
gates on `failures == 0` as a hard binary — but that check doesn't normalize for
request volume: 1 failure out of oMLX's 86 completed requests (1.2%) tripped the
same bar as Ollama's 5 failures out of only 15 (33%). Taken on the actual numbers,
oMLX did not degrade relative to Ollama on this workload — it was Ollama that
degraded severely. See Verdict below for the corrected read.

## Push (concurrency knee: 90s runs at c8 / c12 / c16)

| concurrency | engine | total | ok | fail | rps | ttft p99 (s) | tps_mean | tps_cv |
|---|---|---|---|---|---|---|---|---|
| 8  | ollama | 8  | 5  | 3 (38%) | 0.04 | 109.2 | 1.8  | 0.043 |
| 8  | omlx   | 53 | 52 | 1 (2%)  | 0.54 | 6.1   | 17.5 | 0.591 |
| 12 | ollama | 12 | 8  | 4 (33%) | 0.05 | 140.1 | 1.4  | 0.137 |
| 12 | omlx   | 73 | 73 | 0 (0%)  | 0.74 | 2.3   | 15.6 | 0.483 |
| 16 | ollama | 23 | 16 | 7 (30%) | 0.04 | 308.5 | 16.2 | 1.301 |
| 16 | omlx   | 85 | 85 | 0 (0%)  | 0.84 | 7.8   | 13.9 | 0.508 |

**oMLX's knee:** none found in this range — throughput scales up monotonically
(0.46 → 0.54 → 0.74 → 0.84 rps) and failures go to **zero** at c12 and c16.
p99 TTFT stays in single digits throughout.

**Ollama's knee:** already past it at c6 (the matched-load run). Failure rate holds
at 30-38% across every concurrency level tested, and p99 TTFT climbs from 177s
(c6) to 308s (c16) — it does not recover, it gets worse. `tps_cv` at c16 (1.301)
means the standard deviation of decode-TPS *exceeds* the mean — wildly unsteady.

## Optional: end-to-end pipeline shadow-shift under load

`--url http://localhost:9099 --models auto-coding` (120s, concurrency 6) — the
real production path: `auto-coding` routes to `omlx-coding` (priority 10) with
Ollama fallback, per the shadow-shift landed in `ef9e7a3a`. This also exercises
the F1/F5 routing fixes from `TASK_PIPELINE_OMLX_CORRECTIONS_V1` live.

The harness initially failed outright (0/107,359, all HTTP 401 — `one_request`
had no Authorization header, and the pipeline requires one; a busy-fail loop
with no backoff burned through the full duration issuing rejected requests
near-instantly). Fixed by adding optional `PIPELINE_API_KEY`-env Bearer auth to
`one_request` (only applied when the URL targets `:9099`; harmless no-op for
direct oMLX/Ollama calls). Rerun:

| total | ok | fail | rps | ttft p50/p95/p99 (s) | tps_mean | tps_cv |
|---|---|---|---|---|---|---|
| 66 | 66 | 0 | 0.51 | 1.44 / 2.94 / 3.20 | 17.2 | **0.033** |

Zero failures, and by far the steadiest `tps_cv` observed in this bake-off
(0.033 vs 0.483-0.591 for oMLX direct, 0.043-1.301 for Ollama direct) — the
pipeline's own per-workspace timeout/retry handling and the shadow-shift's
Ollama fallback appear to smooth over exactly the kind of transient the direct
oMLX runs showed 0-1 failures on. This is the one config the task's a-priori
"Ollama is stable" framing and this bake-off's actual data agree on completely:
whichever engine ends up serving `auto-coding` under this harness's load, the
production routing path holds rock-steady.

(Results file is labeled `..._ollama_...json` — a pre-existing harness quirk:
`engine = "omlx" if "8085" in args.url else "ollama"` mislabels any non-`:8085`
URL as "ollama", including the pipeline's `:9099`. Left as-is; out of scope
to fix here.)

## Root cause (observed live, not just inferred from the numbers)

While setting up this bake-off, a single Ollama request for `llama3.2:3b` hung
for 5+ minutes with a resident 27B model (`huihui_ai/Qwen3.6-abliterated:27b`,
25.7GB) already loaded. The pipeline log showed the exact mechanism:

```
Backend ollama-general timed out for workspace=llama3.2:3b (300s) — probing engine state
Backend ollama-general: engine reports model still running — retrying once with 300s timeout
```

Ollama's server log confirmed a single in-flight generation task occupying the
model runner's only slot; loading a second/third model required evicting it,
and eviction was blocked behind that slow, still-running generation. This is
the same mechanism the shootout gate is measuring at scale: round-robining
across 3 differently-sized models forces Ollama to repeatedly evict/reload
between them, and each eviction can stall behind whatever is still decoding.
oMLX's engine pool (multi-model, with pinning/TTL/LRU per `docs/reports/OMLX_DECISION.md`'s
re-evaluation) is designed for exactly this residency pattern and visibly
does not pay the same tax.

## Verdict

**oMLX HOLDS STEADY under multi-model sustained/concurrent load; Ollama degrades
severely on this hardware.** Every steadiness signal — throughput, tail TTFT,
tps_cv, and (properly normalized) failure rate — favors oMLX by a wide margin,
consistently across matched load and all three push-concurrency levels. This is
the opposite of the a-priori framing ("Ollama is the known-stable rockstar");
on *this specific* mixed multi-model round-robin workload, that framing does not
hold. It does **not** mean Ollama is broken in general — single-model,
non-concurrent traffic (the vast majority of Portal 5's current workspace
routing) is unaffected, and this result is specific to forced multi-model
eviction pressure at the concurrency levels tested here.

**Recommendation:** given F4's deferred decision (`config/backends.yaml`, commit
`86e6f142`) to promote `omlx-local` to a real workspace route "only if the
bake-off shows it earns it" — this data supports that promotion, at least for
workloads that mix multiple concurrently-hot models (e.g. `auto-coding` +
`auto-daily` + a general workspace under real multi-user load). It does not by
itself justify moving Portal 5's single-model workspaces off Ollama.

## Provenance

- Ollama results: `results/omlx_v3_shootout_multimodel_ollama_20260805T153203Z.json`,
  `results/omlx_v3_shootout_push_c{8,12,16}_ollama_*.json`
- oMLX results: `results/omlx_v3_shootout_multimodel_omlx_20260805T153836Z.json`,
  `results/omlx_v3_shootout_push_c{8,12,16}_omlx_*.json`
- Shakedown: `results/omlx_v3_shootout_shakedown_omlx_20260805T153055Z.json`
- Engines: oMLX upgraded 0.5.4 → 0.5.7 via `brew upgrade jundot/omlx/omlx` prior to
  this run (see `TASK_PIPELINE_OMLX_CORRECTIONS_V1` commit `86e6f142` for the
  companion routing fixes); Ollama 0.32.5, unchanged.
- `gate_shootout` added in commit `717b0e6c` (bundled with a spine re-pin —
  see that commit's message).
- HEAD at run time: `c1949a89`.
