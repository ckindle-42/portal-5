# Benchmark Results

Timestamped JSON files from `python3 tests/benchmarks/bench_tps.py`. Each run produces one file.

## Useful jq queries

```bash
LATEST=$(ls -t tests/benchmarks/results/bench_tps_*.json | head -1)

# How many models tested / succeeded?
jq '[.results[] | select(.runs_success > 0)] | length' "$LATEST"

# TPS leaderboard (successful runs, sorted by TPS×Q)
jq -r '.results[] | select(.runs_success > 0) | [.model[-50:], .avg_tps, .quality_score, .tps_quality, .prompt_category] | @tsv' "$LATEST" \
  | sort -t$'\t' -k4 -rn | column -t

# Coding models only
jq '[.results[] | select(.prompt_category == "coding" and .runs_success > 0)]
  | sort_by(-.tps_quality)
  | .[] | {model: .model[-50:], avg_tps, quality_score, tps_quality}' "$LATEST"

# Reasoning models only
jq '[.results[] | select(.prompt_category == "reasoning" and .runs_success > 0)]
  | sort_by(-.tps_quality)
  | .[] | {model: .model[-50:], avg_tps, quality_score, tps_quality}' "$LATEST"

# Failed / unavailable models
jq '[.results[] | select(.runs_success == 0)] | length' "$LATEST"
jq -r '.results[] | select(.runs_success == 0) | [.model[-50:], .est_memory_gb] | @tsv' "$LATEST"

# Hardware summary
jq '{hardware, timestamp, total_wall_time_s, mode}' "$LATEST"
```

## Benchmark decisions log

### 2026-04-25 — M4 Pro, 64GB, mlx-lm 0.31.1

**T-16: auto-spl primary model** (coding workspace)

| Model | TPS | Q-Score | TPS×Q | Decision |
|---|---|---|---|---|
| Qwen3-Coder-30B-A3B-Instruct-8bit | 38.9 | 0.67 | **26.1** | **Keep (current winner)** |
| Devstral-Small-2507-MLX-4bit | 9.5 | 1.00 | 9.5 | Good quality, 4× slower |
| Huihui-GLM-4.7-Flash-abliterated-mlx-4bit | 30.9 | 0.00 | 0.0 | **Broken** — empty output on Apple Silicon (P5-MLX-006) |

**Result:** No change. `auto-spl` stays on `mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit`.

**T-17: auto-data primary model** (reasoning/data workspace)

| Model | TPS | Q-Score | TPS×Q | Decision |
|---|---|---|---|---|
| DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit | 7.6 | 1.00 | **7.6** | **Switch to this** |
| DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit | — | — | — | Cannot load (~44GB needed; fails under normal conditions) |

**Result:** Switch `auto-data` to `mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit`. Saves 16GB RAM, same quality signals, 8bit never reliably loads alongside other services.

**GLM finding:** `Huihui-GLM-4.7-Flash-abliterated-mlx-4bit` loads and reports TPS but produces empty content on Apple Metal. Confirmed broken — see KNOWN_LIMITATIONS.md P5-MLX-006.
