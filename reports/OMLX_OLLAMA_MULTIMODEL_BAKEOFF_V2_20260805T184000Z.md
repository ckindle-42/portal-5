# oMLX vs Ollama — Multi-Model Sustained Bake-off (v2, corrected)

**Task:** TASK_OMLX_OLLAMA_MULTIMODEL_BAKEOFF_V1
**Supersedes:** `OMLX_OLLAMA_MULTIMODEL_BAKEOFF_20260805T160244Z.md` — that run was methodologically confounded (see Postmortem below) and its verdict should not be relied on.
**Question:** under mixed multi-model load, matching the real settings and pressure Ollama is actually held to in production, does oMLX hold steady or degrade vs Ollama?

## Postmortem on v1 — why it was redone

The operator (correctly) challenged the first run: Ollama has been solid in production since the MLX retirement, so a result showing it collapsing didn't match lived experience. Investigation found **three independent, real problems**, not one:

1. **Cross-engine memory contention.** v1 never unloaded one engine before testing the other — oMLX had ~25-28GB of models resident (confirmed via its server log) throughout every "Ollama-only" run, both engines competing for the same unified-memory pool and the same system-wide `iogpu.wired_limit_mb` kernel cap. Fixed: both engines' model-unload APIs (`POST /v1/models/{id}/unload` for oMLX, `ollama stop <model>` for Ollama) are now used to verify **zero** models resident on the other side before every run.
2. **Toy prompts, tiny token budget.** v1 reused `SINGLE_PROMPTS` (a few hundred tokens each) capped at `max_tokens=200` — not representative of real usage. Fixed: added `SHOOTOUT_PROMPTS`, five genuinely multi-step tasks (an LRU cache implementation, a debugging task with a real bug to find, a constraint-satisfaction scheduling puzzle, a cache-strategy tradeoff analysis, plus the original debugging prompt), `max_tokens` raised to 4096.
3. **A real, unrelated production bug.** Chasing "are the settings actually equivalent" turned up that Ollama's `/v1/chat/completions` endpoint **silently ignores a runtime `options.num_ctx` override** (verified live with raw `curl`, no Portal code involved) — the model loads at its full trained context (131k-262k tokens) regardless. Portal 5's pipeline (`cluster_backends.py`'s `chat_url`) dispatches to Ollama exclusively through this endpoint, so `_inject_ollama_options`'s `num_ctx` injection has never actually taken effect for **any** workspace. The only mechanism that works is a Modelfile-baked `PARAMETER num_ctx` on a dedicated `-ctxNk` tagged model (already the pattern for most of the fleet). Scanning every workspace found exactly one real casualty: **`auto-security::pentest`** had been running at 262144 tokens of context instead of its configured 8192 since it was promoted 2026-07-16 — fixed by pointing its `model_hint` at the already-existing `...Q4-ctx8k` tag (commit `db75e444`). v1's bake-off itself was also affected: its Ollama-side context was never actually capped either.

Also corrected: concurrency dropped from an arbitrary 6 to **5**, matching `PORTAL5_DEFAULT_WORKSPACE_CONCURRENCY` — the real ceiling `auto-coding` (the production workspace for the coder model tested here) actually runs under.

## Method (v2)

- `bench_omlx_v3.py --gate shootout`, `SHOOTOUT_PROMPTS` (5 multi-step tasks), `max_tokens=4096`, `concurrency=5`, `duration=180s`.
- **Isolation enforced**: before each engine's run, the other engine's model-unload API was called for every resident model and re-checked to confirm zero loaded.
- **Ollama model ids use the `-ctxNk`-tagged variants** (`qwen3-coder:30b-a3b-q4_K_M-ctx16k`, `gemma4:e4b-it-qat-ctx8k`, `llama3.2:3b-ctx8k` — the last created for this bake-off, matching the project's existing convention) so context is genuinely capped at 16384/8192, matching what `auto-coding`/`bench-gemma4-e4b-qat` are configured for.
- oMLX gets no context override (matches production: `_inject_omlx_options` injects nothing either — its paged cache is managed server-side).
- oMLX v0.5.7 (`:8085`), Ollama 0.32.5 (`:11434`). HEAD `fccb3052`.

## Results — matched load (180s, concurrency 5)

| metric | Ollama | oMLX |
|---|---|---|
| total requests / ok / fail | 16 / 16 / **0** | 20 / 20 / **0** |
| throughput (rps) | 0.05 | 0.07 |
| ttft p50 (s) | 0.618 | 0.684 |
| ttft p95 (s) | 119.3 | 1.23 |
| ttft p99 (s) | 193.4 | 1.53 |
| tps_mean | 22.5 | 29.0 |
| tps_cv (steadiness, lower=better) | 0.454 | 0.307 |
| truncated (hit max_tokens) | 1/16 | 3/20 |
| avg response length (chars) | 3793 | 4893 |

**Both engines completed every request — zero failures on either side.** That alone is the headline correction from v1: with true isolation and a real context cap, Ollama's failure mode disappears entirely. The remaining, genuine difference is tail latency.

### Per-model breakdown (this is the real finding)

| model | engine | requests | ttft p50 (s) | ttft p95 (s) | tps_mean |
|---|---|---|---|---|---|
| qwen3-coder:30b-a3b-q4_K_M-ctx16k | Ollama | 6 | 0.58 | 1.09 | 15.8 |
| gemma4:e4b-it-qat-ctx8k | Ollama | 5 | **78.9** | **193.4** | 16.6 |
| llama3.2:3b-ctx8k | Ollama | 5 | 0.30 | 0.51 | 36.6 |
| Qwen3-Coder-30B-A3B-Instruct-4bit | oMLX | 7 | 0.97 | 1.53 | 21.1 |
| gemma-4-e4b-it-4bit | oMLX | 7 | 0.60 | 1.23 | 27.8 |
| Llama-3.2-3B-Instruct-8bit | oMLX | 6 | 0.49 | 0.81 | 39.5 |

Ollama's entire tail comes from **one model**: `gemma4:e4b-it-qat-ctx8k` (p50 TTFT 78.9s — nearly a minute and a half to first token). The other two Ollama models (coder, 3B) perform comparably to or faster than their oMLX counterparts on TTFT. This is not "Ollama degrades under multi-model load" in general — it's specific to this one model/tag having a slow cold-load or swap-back cost in the round-robin, worth its own investigation (candidates: it's the only `Q4_0`-quantized model in the set vs `Q4_K_M` elsewhere, or a vision-capable model paying extra initialization cost the others don't). oMLX shows no comparable per-model outlier — all three stay under 1.6s p95.

## Verdict

**oMLX holds a real, if narrower, edge — tighter tail latency and steadier decode-TPS (tps_cv 0.307 vs 0.454) — but the dramatic "Ollama collapses" story from v1 does not survive a fair test.** With true isolation and a working context cap, Ollama completed every request with no failures, and two of its three models matched or beat oMLX on TTFT. The gap that remains is concentrated in one specific Ollama model/tag, not a systemic multi-model weakness — worth a targeted follow-up (test `gemma4:e4b-it-qat-ctx8k` alone, cold vs warm, to isolate whether it's the quantization format, vision-model initialization, or something else) before drawing any fleet-wide conclusion from it.

**Recommendation:** the original F4 question (promote `omlx-local` to a real workspace route?) does not have strong support from this data — the evidence for "oMLX categorically outperforms" was largely an artifact of v1's flawed methodology. What *does* hold up: oMLX's tail-latency consistency across differently-sized models is a genuine, real advantage, and worth keeping on the roadmap, but not on the strength of a single "Ollama fails" data point that traced back to one specific model's cold-load cost.

## Two real bugs found and fixed along the way

1. **`auto-security::pentest` running at 30x its configured context** since 2026-07-16 (fixed, commit `db75e444`) — a materially different memory/behavior profile than what was validated at promotion time.
2. **Ollama's OpenAI-compat endpoint silently drops `options.num_ctx`** — documented in `_inject_ollama_options`'s docstring (same commit) so this isn't rediscovered the hard way again. Every other workspace already worked around it correctly via `-ctxNk` tagged models; only the one above had drifted off that pattern.

## Provenance

- Ollama (isolated, v2): `results/omlx_v3_shootout_v3_isolated_ollama_20260805T182957Z.json`
- oMLX (isolated, v2): `results/omlx_v3_shootout_v3_isolated_omlx_20260805T183617Z.json`
- v1 (confounded, superseded): `results/omlx_v3_shootout_multimodel_{ollama,omlx}_20260805T15*.json`, `results/omlx_v3_shootout_isolated_*_20260805T17*.json` (transitional runs during the debugging process — the *_isolated_multimodel_* files still used the broken uncapped-context bare model tags; only *_v3_isolated_* is the final, correct methodology)
- Commits: `db75e444` (context bug + pentest fix), `fccb3052` (harness fixes: prompts, concurrency, model tags)
- HEAD at run time: `fccb3052`
