# oMLX vs Ollama — Multi-Model Sustained Bake-off (v3, final)

**Task:** TASK_OMLX_OLLAMA_MULTIMODEL_BAKEOFF_V1
**Supersedes:** v1 (`OMLX_OLLAMA_MULTIMODEL_BAKEOFF_20260805T160244Z.md`, confounded by cross-engine memory contention) and v2 (`OMLX_OLLAMA_MULTIMODEL_BAKEOFF_V2_20260805T184000Z.md`, still carrying an undiscovered TTFT-measurement bug and an unverified quantization mismatch).
**Question:** under mixed multi-model load, with every setting actually verified matched, does oMLX hold a real edge over Ollama?

## Why there's a v3 — two more real bugs found after v2 shipped

The operator pushed back twice more on v2, and both times the pushback found something real:

1. *"Doesn't Ollama's tail latency contradict our production experience — what exactly differed?"* → Found a **measurement bug**: `one_request`'s TTFT only counted `content` stream deltas. `gemma4:e4b-it-qat` streams extended "thinking" tokens via a separate `reasoning` field with `content` empty until thinking finishes. The harness was measuring "time until thinking ends," not "time until the model starts working" — an actively-computing model was being reported as silently stalled for up to 193s. **This fully explains v2's entire "Ollama tail latency" finding.**
2. *"Are quant/sampling/concurrency actually matched — verify before running, don't discover after."* → A full settings audit (not spot-checks) found: coder and gemma already matched exactly (traced to byte-identical upstream `generation_config.json` on both engines) — but **`llama3.2:3b` did not**: Ollama's default pull is Q4_K_M (2.0GB) while oMLX's `Llama-3.2-3B-Instruct-8bit` runs at 8-bit (3.6GB), an unmatched ~2x precision gap. Also confirmed live that Ollama's `/v1/chat/completions` endpoint silently ignores **`top_k`** in addition to the already-known `num_ctx`/`think` — three separate parameters that appear to work (no error, no rejection) but have zero effect.

Both are now fixed (commit `778def71`): TTFT counts the first token of any kind (content or reasoning); a new `llama3.2:3b-instruct-q8_0-ctx8k` Ollama tag matches oMLX's 8-bit precision; `temperature`/`top_p` (confirmed-functional standard OpenAI fields) are pinned identically for the 3B model on both engines; `top_k` is deliberately left unset on both since it can't be forced on Ollama's side anyway.

## What is and isn't matched — full accounting

| dimension | status | detail |
|---|---|---|
| Isolation | ✅ matched | Both engines' model-unload APIs verified zero-loaded on the other side before every run |
| Context window | ✅ matched | 16384 (coder) / 8192 (gemma, 3B) both engines — Ollama via Modelfile-baked `-ctxNk` tags (the only mechanism that works), oMLX via its paged cache (no pre-allocation needed) |
| Quantization | ✅ matched | coder: both ~4-bit/Q4_K_M (18GB both). gemma: Q4_0 (Ollama, QAT-trained checkpoint) vs 4bit (oMLX) — same size class (6.1GB/5.4GB), different method names but same upstream QAT checkpoint. 3B: Q8_0 (Ollama, 3.4GB) vs 8bit (oMLX, 3.6GB) — fixed this run |
| Sampling (coder, gemma) | ✅ matched | Byte-identical `temperature`/`top_p`/`top_k`, verified via the shared upstream `generation_config.json` |
| Sampling (3B) | ✅ matched (partial) | `temperature=0.7`/`top_p=0.9` pinned explicitly on both. `top_k` **cannot** be matched — confirmed non-functional on Ollama's `/v1/chat/completions` (temp=1.5 + top_k=1 still produced non-deterministic output) |
| Concurrency | ✅ matched | 5, matching `PORTAL5_DEFAULT_WORKSPACE_CONCURRENCY` — the real ceiling `auto-coding` runs under in production |
| max_tokens | ✅ matched | 4096 both — a practical subset of `auto-coding`'s real 16384 `predict_limit`, chosen to keep the sweep's wall-clock bounded |
| Thinking mode (gemma) | ⚠️ **not matched, by necessity** | Ollama's Modelfile has it on; oMLX's `thinking_default` is `false`. Confirmed live that Ollama's `/v1/chat/completions` silently ignores a `think:false` override (only native `/api/chat` honors it) — **cannot be forced to match from the endpoint production actually uses.** No `config/portal.yaml` workspace sets `think` explicitly anywhere, so each engine's real, unconfigured default is what's tested — which is itself the honest representation of current production behavior, just not a controlled variable. |

**One dimension genuinely cannot be equalized without switching Ollama off the endpoint production uses.** Everything else is now verified matched or explicitly, transparently pinned.

## Results — matched load (180s, concurrency 5)

| metric | Ollama | oMLX |
|---|---|---|
| ok / total | 13/13 | 22/22 |
| failures | **0** | **0** |
| throughput (rps) | 0.04 | 0.08 |
| ttft p50 (s) | 0.668 | 0.621 |
| ttft p99 (s) | 1.353 | 1.249 |
| tps_mean | 19.3 | 28.9 |
| tps_cv (steadiness) | 0.342 | 0.319 |

Both zero failures, both tight tails (under 1.4s p99), comparable steadiness. oMLX completed ~70% more requests in the same window and shows ~50% higher decode throughput — a real, moderate edge, not a rout.

## Results — concurrency-push sweep (90s each)

| concurrency | engine | ok/total | fail | ttft p50 (s) | ttft p99 (s) | tps_mean |
|---|---|---|---|---|---|---|
| 8  | Ollama | 13/13 | 0 | 0.94 | 2.16 | 15.5 |
| 8  | oMLX   | 16/16 | 0 | 0.90 | 2.53 | 22.8 |
| 12 | Ollama | 18/18 | 0 | 1.31 | **141.5** | 11.2 |
| 12 | oMLX   | 21/21 | 0 | 1.05 | 3.10 | 19.0 |
| 16 | Ollama | 22/22 | 0 | 2.58 | **181.0** | 9.5 |
| 16 | oMLX   | 27/27 | 0 | 1.27 | 3.99 | 16.0 |

**This is the real, load-bearing finding of the whole exercise.** Both engines complete every request at every concurrency level — zero failures throughout. But oMLX's tail latency scales smoothly and predictably (2.5s → 3.1s → 4.0s), while Ollama's explodes past concurrency 8 (2.2s → 141.5s → 181.0s), even with quant/context/sampling fully matched and the TTFT bug fixed. Per-model breakdown at c12 shows this isn't one bad model — individual outlier requests across different models in the round-robin (gemma p95=141s on 6 requests, coder p95=31.6s on 6 requests) — small per-model sample sizes make single slow requests swing the tail hard, but the pattern repeats and worsens at c16, so it's a real trend, not noise from one unlucky draw.

## oMLX's own breaking point (the flip side)

oMLX is not infinitely elastic either — pushed past its comfortable range:

| models | combined size | ok/total | fail | ttft p50 (s) | ttft p99 (s) |
|---|---|---|---|---|---|
| 3 (baseline) | ~27GB | 22/22 | 0 | 0.62 | 1.25 |
| 5 | ~38GB | 7/7 | 0 | 2.57 | 2.73 |
| 6 (heavy) | ~92GB | 8/10 | **2** | **14.9** | **25.5** |

At 6 models with a combined working set (~92GB) far exceeding oMLX's ~42-47GB admission target, the server log shows continuous eviction churn — reloading a different model for nearly every request, since only 2-3 of the 6 fit resident at once:

```
Evicting 'Qwen3-Coder-30B-A3B-Instruct-4bit' to fit 'Qwen3-VL-32B-Instruct-4bit' under the admission soft target (57.35GB > 42.30GB)
Evicting 'gemma-4-e4b-it-4bit' to fit 'Qwen3-VL-32B-Instruct-4bit' ...
Evicting 'Llama-3.2-3B-Instruct-8bit' to fit 'Qwen3-Coder-30B-A3B-Instruct-4bit' ...
```

This is oMLX's real limit: not a hard failure boundary, but the same class of thrashing Ollama shows — just at a different threshold (**total resident working set** for oMLX vs **concurrent request pressure on a matched set** for Ollama). Neither engine is magic; both degrade when pushed past their design envelope, just via different mechanisms.

## Verdict

**oMLX holds a real, verified, but moderate advantage — mainly in tail-latency stability under concurrent pressure, not in raw failure rate or basic responsiveness.** At matched, realistic settings and normal production-level concurrency (5, matching `auto-coding`'s actual ceiling), the two engines are close: comparable TTFT, oMLX ~50% higher decode throughput. The gap that's actually large and reproducible is what happens **above** that normal ceiling (concurrency 12-16): Ollama's tail latency degrades by two orders of magnitude while still completing every request; oMLX's stays flat. Whether that matters depends entirely on whether Portal 5 workspaces are ever expected to run above their configured `max_concurrent` — today, nothing is (the default is 5, `auto-coding` doesn't override it).

**This does not repeat v1's "Ollama collapses" framing, and it doesn't fully vindicate a switch either.** It's a specific, bounded finding: *if* a workspace needs headroom above concurrency 5, oMLX is the more predictable choice for that specific workspace; for normal single-digit concurrency, the two are close enough that other factors (operational maturity, the one unmatched thinking-mode variable, oMLX's own thrash point) should weigh more than this data alone.

## What's still open (deferred, not done)

- **Broader model set**: only one trio was tested (coder/gemma/3B). Whether the tail-latency pattern generalizes to other production model combinations is untested — worth doing before making this the basis of a fleet-wide decision.
- **Thinking-mode-matched comparison**: a controlled variant with thinking forced off (or on) symmetrically on both engines, using Ollama's native `/api/chat` specifically for that leg, was identified as feasible (both `enable_thinking`/`thinking_budget` on oMLX and `think` on `/api/chat` for Ollama were confirmed to work) but not run.
- **oMLX's exact thrash threshold**: bracketed between 5 models (fine) and 6 models/~92GB (thrashing) — the precise boundary wasn't pinned down.

## Provenance

- Matched load: `results/omlx_v3_shootout_v4_final_{ollama,omlx}_*.json`
- Push sweep: `results/omlx_v3_shootout_v4_push_c{8,12,16}_{ollama,omlx}_*.json`
- oMLX model-count stress: `results/omlx_v3_shootout_v4_5model_omlx_*.json`, `results/omlx_v3_shootout_v4_6model_heavy_omlx_*.json`
- Commits: `db75e444` (Ollama context bug + pentest fix), `fccb3052` (harness: prompts/concurrency/context tags), `778def71` (settings-parity audit: TTFT metric, quant match, sampling match)
- HEAD at run time: `778def71`
