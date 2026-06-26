# Archived MLX inference stack (retired 2026-06-09, commit 3a0c58e)

These 8 scripts powered the standalone MLX inference proxy that ran
alongside Ollama on the M4 Pro Mac Mini through commit `3a0c58e^`.
The MLX proxy tier was retired when Ollama 0.30.7 reached throughput
parity (and often a small lead) using its native MLX Metal backend —
eliminating the thread-patch maintenance burden, admission control
complexity, and dual-stack operational overhead that the proxy required.

| File | Lines | Purpose |
|---|---|---|
| `mlx-proxy.py` | 1,850 | Inference proxy on :8081, admission control, KV-cache mgmt, per-model memory ceiling, tool-call parsing |
| `mlx-watchdog.py` | 1,400 | Dual-mode watchdog (zombie detect + active recovery) |
| `mlx-model-laguna.py` | 395 | Laguna-XS MLX model loader/server |
| `mlx-readiness.py` | 308 | Health probe (wired-memory + model-loaded) |
| `mlx-switch-benchmark.py` | 843 | Model-switch benchmark harness |
| `patch-mlx-templates.py` | 189 | Qwen 3.5/3.6 chat template vendor + patch |
| `patch-mlx-threads.py` | 245 | Forced single-thread MLX patch |
| `smoke_test_mlx.py` | 109 | MLX-proxy smoke test |

## Status: archive-only

These scripts are not runnable as-is at HEAD. They depend on surfaces
removed in `3a0c58e`:

- `mlx-apple-silicon` backend type in `cluster_backends.py`
- `Backend.mlx_metadata` field
- `_inject_mlx_options` in the router
- `mlx_model_hint`, `mlx_only`, `mlx_chat_template_kwargs` in `WORKSPACES`
- `mlx_models:` block in `config/backends.yaml`

Two regression-guard tests in `tests/unit/test_pipeline.py`
(`test_no_duplicate_mlx_proxy_url`,
`TestModelSupportsToolsRealBackend.test_backend_has_no_mlx_metadata_field`)
explicitly assert the absence of those surfaces.

## When to consult these

- A successor MLX (or future Ollama feature) needs admission-control
  reference: read `mlx-proxy.py` for the working model.
- KV-cache hot/cold tiering design comes up: `mlx-proxy.py` plus
  `OMLX_DECISION.md` give the prior art.
- Thread-management on Apple Silicon for inference: `patch-mlx-threads.py`.
- Watchdog patterns for inference processes: `mlx-watchdog.py`.

## How to revive (rough sketch — no commitment)

1. Decide on a successor target: a re-introduced standalone MLX, OMLX,
   or something else.
2. Restore `mlx-apple-silicon` backend type to `cluster_backends.py`.
3. Reintroduce `_inject_mlx_options` and re-add MLX selection branches
   to the router (`portal_pipeline/router/handlers.py`, `routing.py`).
4. Add `mlx_model_hint` / `mlx_only` fields back to the unified
   `Preset` schema (`portal_pipeline/config.py`).
5. Update or remove the regression-guard tests in
   `tests/unit/test_pipeline.py`.
6. Copy and adapt the scripts from this directory back into `scripts/`.

## Tests retained only in git history

The two unit-test files
(`tests/unit/test_mlx_proxy.py`, `tests/unit/test_proxy_unload.py`) were
also deleted in `3a0c58e`. They are intentionally NOT archived here
because they would not import against HEAD. Recover via
`git show 3a0c58e^:tests/unit/test_mlx_proxy.py` if needed.

## See also

- `OMLX_DECISION.md` — CANCELED P5-FUT-013 OMLX bake-off (parallel
  retirement context)
- `deploy/omlx/config.yaml` — OMLX evaluation config (also retired)
- `scripts/_archive/README.md` and `scripts/_archive/bench_v5_ladders.sh` —
  parallel V5 bench retirement from the same migration era
