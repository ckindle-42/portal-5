# Engine head-to-head tooling — restored 2026-11-05

The harness, registry, PrismML adapter, fixtures, and unit tests moved back to
the paths the September README named:

- `tests/benchmarks/bench_engine_h2h.py`
- `tests/benchmarks/engine_h2h.yaml`
- `tests/benchmarks/prismml_mlx_server.py`
- `tests/benchmarks/fixtures/engine_h2h/`
- `tests/benchmarks/fixtures/bonsai_quality/`
- `tests/unit/test_bench_engine_h2h.py`
- `tests/unit/test_prismml_mlx_server.py`

`deep_lane/` and `wfe_plans/` stay here. They are the September receipts and
plans, not the November screen. The November run plan is
`coding_task/proposals/ENGINE_H2H_202611.md`. Raw speed receipts still append
under `tests/benchmarks/results/engine_h2h/`.
