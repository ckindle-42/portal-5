# oMLX vs Ollama — Multi-Model Sustained Bake-off (v4, final — thinking-matched + broader model set)

**Task:** TASK_OMLX_OLLAMA_MULTIMODEL_BAKEOFF_V1
**Supersedes:** v1, v2, v3 (all in `reports/`). v3's two open items — a thinking-matched comparison and a broader model set — are completed here; the core matched-load/push-sweep verdict from v3 is unchanged and carried forward.

## 1. Thinking-mode-matched comparison (coder/gemma/3B trio)

v3 flagged thinking mode as the one setting that couldn't be equalized via the endpoint production actually uses (`/v1/chat/completions` silently ignores `think`). Built proper support for this: Ollama routes through native `/api/chat` (the only endpoint that honors `think`) when forcing the variable; oMLX gets `enable_thinking`/`thinking_budget` injected. Both confirmed live before running anything.

**One real constraint found along the way:** Ollama HTTP 400s on `think:true` for models that don't support thinking (`think:false` is silently accepted for the same models). Only `gemma` in this trio supports thinking — `coder` and `3B` don't. So "think=on for the whole trio" isn't a valid test; the on/off comparison only makes sense isolated to `gemma`.

### think=OFF (full trio, all three models)

| metric | Ollama | oMLX |
|---|---|---|
| ok/total | 12/12 | 14/14 |
| failures | 0 | 0 |
| ttft p50/p99 (s) | 0.67 / 1.25 | 0.63 / 1.32 |
| tps_mean | 20.2 | 28.7 |
| tps_cv | 0.350 | 0.302 |
| truncated | **0** | 2 |

With thinking off, both engines are close and clean — no reasoning tokens burning the token budget, zero truncation on Ollama specifically (gemma's 4096-token budget goes entirely to the visible answer). oMLX still shows its consistent ~40% throughput edge.

### think=ON (gemma alone — the only valid comparison)

| metric | Ollama | oMLX |
|---|---|---|
| ok/total | 6/6 | 9/9 |
| failures | 0 | 0 |
| ttft p50/p99 (s) | 1.39 / **66.6** | 1.20 / **1.44** |
| tps_mean | 16.4 | 35.6 |
| tps_cv | 0.151 | 0.103 |

This is the cleanest, most isolated version of the finding from v2/v3: same model family, same task, thinking forced on for both — Ollama's p99 is **46x** oMLX's (66.6s vs 1.44s, on just 6 samples so one outlier dominates, but the pattern repeats across every test in this whole exercise). oMLX's throughput is also more than double (35.6 vs 16.4 tok/s) specifically in thinking mode. Both engines complete every request.

## 2. Broader model set — a second, independent trio

Selected two more real production models (not benchmark-only picks): `huihui_ai/qwen3.5-abliterated:9b` (used across several security workspaces) and `supergemma4-26b-uncensored` (used in `auto-security` variants). Verified parity before running:
- **qwen3.5-9b**: Ollama Q4_K_M (6.6GB) vs oMLX 4bit (5.3GB) — same quant class. Ollama bakes `temp=1/top_k=20/top_p=0.95`; oMLX has no `generation_config.json` for this checkpoint to verify against, so `temp=1.0/top_p=0.95` was pinned explicitly on both rather than trust an unverifiable default.
- **supergemma4-26b**: Ollama Q4_K_M (16GB) vs oMLX 4bit (16.4GB) — close match. Ollama's Modelfile has **no** sampling params baked at all; pinned to oMLX's known `generation_config.json` values (`temp=1.0/top_p=0.95`) on both.
- Context: real production tags used (`-ctx8k` / `-ctx64k`, matching each model's actual `config/portal.yaml` `context_limit`).

| metric | Ollama | oMLX |
|---|---|---|
| ok/total | 6/6 | 9/9 |
| failures | 0 | 0 |
| ttft p50/p99 (s) | 1.52 / **333.0** | 1.20 / **2.45** |
| tps_mean | 15.8 | 20.7 |
| tps_cv | 0.275 | 0.222 |

**The pattern generalizes.** A completely different pair of models (9B + 26B, both heavy reasoning-capable checkpoints) shows the same shape: both zero failures, oMLX's tail stays tight (p99=2.45s) while Ollama's explodes (p99=333s, ~136x). Root cause here is more precisely characterized than in earlier reports: with only 2 heavy, long-generating (near max_tokens, both models used extensive thinking — 7500-11500 avg reasoning chars) models under 5-way concurrency, requests queue behind Ollama's limited concurrent-serving capacity — total request durations of 3-7 minutes were observed directly in the Ollama server log, not a TTFT-measurement artifact this time. oMLX's engine pool absorbed the same load without queueing.

## Consolidated verdict (v1 → v4, what actually holds up)

Across four independent tests now — the original coder/gemma/3B trio (matched-load, push sweep 8/12/16), the thinking-isolated gemma comparison, and this independent 9B/26B pair — **the same qualitative result reproduces every time**: both engines complete every request (zero failures throughout this entire exercise, across every configuration tested), but oMLX's tail latency stays flat and predictable under concurrent multi-model pressure while Ollama's grows by one to two orders of magnitude past a certain concurrency/load threshold. This is no longer a single confounded data point — it reproduced across 2 different model pairs, both thinking states, and 3 concurrency levels.

**What this doesn't show**: a difference at low concurrency (both engines are close, oMLX ~30-50% ahead on throughput, comparable TTFT) or a fundamental reliability gap (zero failures on either side under every condition except deliberately overloading oMLX past its own ~50GB ceiling, where it also failed). The recommendation from v3 stands, now on firmer evidence: for workspaces that need headroom above their configured `max_concurrent` (default 5), oMLX is the more predictable choice; for normal single-digit concurrency, the two are close enough that this data point alone shouldn't be the deciding factor.

## Provenance

- Thinking off: `results/omlx_v3_shootout_think_off_{ollama,omlx}_*.json`
- Thinking on (gemma only): `results/omlx_v3_shootout_think_on_gemma_only_{ollama,omlx}_*.json`
- Broader model set: `results/omlx_v3_shootout_broad_set_b_{ollama,omlx}_*.json`
- Commits: `778def71` (settings-parity audit), `33055b4c` (think toggle + 2nd-pair sampling)
- HEAD at run time: `33055b4c`
