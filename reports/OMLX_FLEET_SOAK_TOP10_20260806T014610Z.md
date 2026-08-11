# oMLX 10-Model Fleet Soak Test — Rip-and-Replace Capacity Verdict

**Task:** answer whether oMLX can replace Ollama as primary with Ollama demoted to fallback-only — the question the short bursts in `OMLX_OLLAMA_MULTIMODEL_BAKEOFF_V4` and the follow-up probes couldn't answer, because they only ever exercised 2-3 models at once for 90-120s.

**Method:** `tests/benchmarks/bench_omlx_soak.py`. 10 models — the highest-traffic production models by persona-count-weighted workspace routing (live Prometheus telemetry had too little history to trust; see prior session for the derivation) — round-robined with weighted-random selection matching that traffic proxy, concurrency=5 (production default), for 3 hours (10,800s) straight against oMLX directly (`:8085`). `/health` polled every 60s for `engine_pool` memory state; results checkpointed every 5 minutes.

7 of the 10 models had no MLX build on disk at session start and were pulled from HF this session (all located with exact or close quant matches; one substitution needed — see §4).

## 1. Headline result

**oMLX itself never went down. Zero outages, zero crashes, across the full 3 hours.** But **41.5% of all requests failed** (699/1685) — not randomly, and not from instability. Every failure was the engine's own admission control rejecting a request it couldn't safely serve:

- **HTTP 507** — can't load a new model because doing so would push total memory past the ceiling.
- **HTTP 400** — the "prefill memory guard" rejects a request outright when even that request's KV cache would tip memory over.

```
HTTP 507: Cannot load Qwen3-VL-32B-Instruct-4bit: projected memory 60.81GB
would exceed the metal_cap memory ceiling 47.00GB (current: 41.62GB, model: 19.19GB)
```

This is graceful degradation, not a crash — the engine protects itself by shedding load. But at your actual top-10 traffic mix and concurrency=5, the box doesn't have enough memory headroom to serve it without shedding ~40% of requests.

## 2. Failure rate over time: stable equilibrium, not a leak

Reconstructed from the 5-minute checkpoints across the full run:

| t (min) | cumulative requests | cumulative failures | fail rate |
|---|---|---|---|
| 5 | 39 | 25 | 64.1% (cold-start spike) |
| 15 | 102 | 49 | 48.0% |
| 30 | 244 | 98 | 40.2% |
| 60 | 507 | 211 | 41.6% |
| 90 | 791 | 346 | 43.7% |
| 120 | 1058 | 426 | 40.3% |
| 150 | 1309 | 550 | 42.0% |
| 180 (final) | 1685 | 699 | 41.5% |

The first 5 minutes ran hot (64% — several large models requested cold and simultaneously before the pool had any warm/evicted state to work with), then it **settled into a flat 40-44% band and stayed there for the remaining 2h55m** — no upward drift (no leak), no downward trend (no self-tuning or recovery). This is a genuine steady-state capacity ceiling for this model mix, not a transient or a bug that would resolve with a longer run.

## 3. Which models absorb the failures

| Model | Size class | ok | fail | fail rate | tps (when ok) |
|---|---|---|---|---|---|
| granite-30b | 30B | 21 | 92 | **81.4%** | 7.2 |
| hauhaucs-creative | 35B | 26 | 49 | 65.3% | 10.9 |
| gemma-daily | 26B-A4B | 24 | 43 | 64.2% | 13.2 |
| qwen-vl | 32B | 54 | 93 | 63.3% | 6.5 |
| granite-8b | 8B | 74 | 121 | 62.1% | 12.3 |
| tongyi-research | 30B-A3B | 47 | 75 | 61.5% | 15.5 |
| qwen35-9b | 9B | 32 | 19 | 37.3% | 16.1 |
| coder | 30B-A3B | 445 | 148 | 25.0% | 11.8 |
| vulnllm | 7B | 143 | 37 | 20.6% | 21.4 |
| deepseek-r1 | 8B | 120 | 22 | 15.5% | 16.7 |

Two things worth noting:
- **Size alone doesn't predict failure rate** — `coder` (30B) has one of the lowest fail rates because it's also the highest-weighted (34/98) so it's disproportionately likely to already be the resident/warm model when a request lands; low-weight large models (`granite-30b`, `hauhaucs-creative`) get evicted and have to cold-load into an already-crowded pool constantly.
- **granite-8b at 62.1% fail is the standout anomaly** — it's the smallest model in the set (8.87GB) yet has the third-worst fail rate. This isn't a capacity story for that one; see §4.

## 4. Model-availability note: the oQ4 Granite-8B conversion doesn't load on this oMLX version

Before the soak started, `mlx-community/unsloth-granite-4.1-8b-mlx-oQ4` (the quant-matched pick to Ollama's `granite4.1:8b` Q4_K_M) failed to load at all:

```
HTTP 409: Model 'granite-4.1-8b-oQ4' failed to load: Received 2 parameters
not in model: lm_head.biases, lm_head.scales. Reload models after fixing
the files to retry.
```

Live-verified this is a real format incompatibility (unsloth's "optimized quant" packaging), not a fluke — `granite-4.1-30b-4bit` (a different uploader's native MLX conversion) loaded fine on the same oMLX version. Substituted `nightmedia/granite-4.1-8b-mxfp8-mlx`, which loads and answers correctly. **Its persistently high fail rate during the soak is therefore capacity contention, same as the other models, not a residual loading bug** — but it's a second, independent data point that not every "matched" MLX conversion for your fleet will actually work out of the box; each one needs a live load-and-answer check before being trusted, which is more or less what this whole exercise already does.

## 5. A ceiling discrepancy worth reconciling

`/health` reports `final_ceiling: 50,465,865,728` (50.5GB) throughout the run. The actual load-time enforcement in the 507 errors consistently cites **47.00GB**. Both numbers come from the same running process — this is either a stale/cached value in one code path or two different ceiling concepts (e.g. a soft display ceiling vs. a hard `metal_cap`) that aren't documented as distinct. Worth a quick look at the oMLX source/config before trusting `/health`'s number for capacity planning.

## 6. Verdict on the rip-and-replace question

**Not supported at the current ceiling and model mix.** oMLX's reliability story holds — it degrades gracefully rather than crashing, matching every prior test in this whole evaluation arc. But "gracefully" here means **shedding 4 in 10 requests**, and that's not a viable "daily go-to for everything" state as-is. Three real levers exist before this verdict changes, in rough order of effort:

1. **Raise `iogpu.wired_limit_mb`** (the 507 errors explicitly suggest this) — if there's real headroom on the 64GB box above the current ~47-50GB ceiling, this could be a config change, not an architecture change. Worth trying first.
2. **Reduce the concurrent model-diversity pressure** — this test forced all 10 models into rotation under 5-way concurrency; production traffic may not actually demand 4-5 distinct 20-35GB models resident simultaneously as often as the weighted-random selection did here. A trace of *actual* concurrent-model-diversity in production (once there's enough real telemetry — the original gap that started this whole exercise) would sharpen this.
3. **Segment the fleet** — keep the largest, lowest-traffic models (`granite-30b`, `hauhaucs-creative`, `tongyi-research`) on Ollama fallback permanently, and promote only the smaller/higher-traffic ones (`coder`, `vulnllm`, `deepseek-r1`, `qwen35-9b`) to oMLX-primary. That's a middle path between today's single-workspace shadow-shift and a full rip-and-replace.

## 7. Rerun with raised ceiling (2026-08-07/08)

**Change:** `iogpu.wired_limit_mb` raised 48128→57344 (47.0GB→56.0GB, 73%→87% of 64GB total), applied live via `sudo sysctl` and persisted in `/Library/LaunchDaemons/com.portal.vram.plist` for reboot survival. oMLX restarted to pick up the new ceiling. Identical soak parameters (3h, concurrency=5, same 10-model weighted mix) rerun for a clean A/B, tag `fleet_top10_raised_ceiling`.

| | Run 1 (47GB enforced) | Run 2 (56-60GB enforced) |
|---|---|---|
| Total requests | 1685 | 1150 |
| Failures | 699 (41.5%) | 341 (29.7%) |
| Outages | 0 | 0 |
| Peak memory | 50.4GB | 59.9GB |
| Failure-rate shape | hot start (64%) → flat 40-44% band | hot start (46%) → flat ~29-31% band |

**Raising the ceiling helped — failure rate dropped ~12 points (41.5%→29.7%, a ~28% relative reduction) — but did not come close to eliminating the failures.** Same qualitative shape as run 1: a cold-start spike, then a flat steady-state band for the rest of the 3 hours, no drift, no outages. The models that failed hardest in run 1 (`granite-30b`, `hauhaucs-creative`, `qwen-vl`, `tongyi-research` — the large, low-traffic-weight ones) are still the hardest hit in run 2. More headroom moved the ceiling but didn't change which models get squeezed out under this load pattern.

**Important correction to how run 1's result should be read**, identified after the fact: the RBP (security) engine — the heaviest real subsystem this soak was meant to stand in for — does not generate this load pattern in practice. Checked directly against the code:
- `exec_chain.py`'s core execution chain runs on `ThreadPoolExecutor(max_workers=1)` — single-threaded.
- `matrix.py`'s `run_matrix` iterates sequentially; its `max_concurrent` parameter is unused.
- The one real concurrent-multi-model path, `blueteam-council` (`config/portal.yaml`), dispatches at most 3 `council_models` concurrently (plus an optional tie-breaker), and is **not auto-routed and not exposed to OWUI** — a manually-triggered CLI-only confirm operation, not continuous production traffic.

So this soak test (5-way concurrency, continuous random selection across all 10 models for 3 hours) is a genuine stress-test upper bound, not a simulation of RBP's actual worst case, which tops out around 3-4 concurrent models fired on-demand. **The 30-42% failure rates above should be read as "here's what happens under deliberately harder load than the heaviest real subsystem generates today," not as a production failure-rate prediction.** Also worth flagging: production doesn't exist yet for this fleet — the backend is still being built — so there's no real traffic to validate either reading against yet; this soak (and its interpretation) is pre-production capacity planning, not a measurement of an existing failure mode.

## Provenance

- Soak harness: `tests/benchmarks/bench_omlx_soak.py`
- Result: `tests/benchmarks/results/omlx_fleet_soak_fleet_top10_20260806T014610Z.json`
- 7 pulled MLX models: `granite-4.1-8b-mxfp8`, `granite-4.1-30b-4bit`, `VulnLLM-R-7B-4bit`, `DeepSeek-R1-0528-Qwen3-8B-4bit`, `Tongyi-DeepResearch-30B-A3B-abliterated-4bit`, `gemma-4-26b-a4b-it-QAT-4bit`, `Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit` (symlinked into `/Volumes/data01/omlx-models/`)
- Notification: `tests/benchmarks/notify_soak_complete.py` (Slack/Telegram/Pushover via `NotificationDispatcher`, requires `uv run --env-file .env`)
- HEAD at run time: `33055b4c` + uncommitted `bench_omlx_v3.py`/`bench_omlx_stress_extras.py`/`bench_omlx_soak.py`/`notify_soak_complete.py`
