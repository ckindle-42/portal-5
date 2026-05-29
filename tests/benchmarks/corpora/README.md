# Positional Recall Corpora

Real Portal 5 source files chosen to span the catalog's `max_kv_size` ceilings.
Zero external/vendored code — representative of served code (A3).

## Corpus → Ceiling Mapping

| corpus file | ~tokens | exercises ceilings up to |
|---|---|---|
| `portal_pipeline/cluster_backends.py` (~31KB) | ~8K | 32K lanes (R1-Distill) |
| `scripts/mlx-proxy.py` (~78KB) | ~20K | 64K lanes (Qwen3-Coder-Next, Qwopus) |
| `tests/benchmarks/bench_tps.py` (~131KB) | ~33K | 131K lanes (gemma-4-31b, GLM-4.7-Flash, granite-4.1-30b) |

For 131K-ceiling lanes the assembler pads by concatenating the corpus multiple
times with unique `# === copyN/path ===` headers and samples functions from the
deepest copy, so the recall target genuinely sits near the ceiling, not at 33K.
