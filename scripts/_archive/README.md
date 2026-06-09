# Archived scripts

## V5 quantization-ladder bench tooling (archived after MLX-proxy retirement)

`bench_v5_ladders.sh` and `analyze_bench_v5.py` orchestrated the V5 quant-ladder
bench (TASK_MODEL_REFRESH_V5) against the MLX inference proxy. They are inoperable
after commit 3a0c58e:

- probe `http://localhost:8081/health/wired` (proxy retired)
- require `scripts/smoke_test_mlx.py` (deleted in 3a0c58e)
- look up the `mlx-apple-silicon` backend and its `mlx_models` key (both removed
  from config/backends.yaml)

Kept for recoverability only. The current Ollama bench path is
`tests/benchmarks/bench_tps.py`. Historical bench *results* remain under
`tests/benchmarks/results/`; the oMLX bake-off harnesses (`bench_omlx.py`,
`bench_mlx_vs_ollama.py`) remain in `tests/benchmarks/` as evidence for the
CANCELED P5-FUT-013 decision (see OMLX_DECISION.md).
