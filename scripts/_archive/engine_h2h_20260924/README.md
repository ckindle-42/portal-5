# Engine head-to-head + Bonsai probe tooling (archived 2026-09-24)

Frozen snapshot of the tooling behind the September 2026 engine and Bonsai
evaluations. Not maintained, not imported by live code, not collected by pytest.
Kept so its parts can be reused without being rebuilt.

**Verdicts it produced** are in `docs/MIMO_V26_DISTILL_9B_BRINGUP_V1.md`
("Bonsai verdict", "Deep-lane result", "Fit bench V3"). The raw receipts stay live in
`tests/benchmarks/results/engine_h2h/*.jsonl`.

**Removed from the host at archive time:** the engines MTPLX, Rapid-MLX,
vllm-mlx, mlx-serve, the PrismML llama.cpp fork and the PrismML MLX fork, and
every Bonsai/Ternary/MTPLX model, drafter and control tag. Ollama, oMLX,
Homebrew llama.cpp and mlx-lm stay; production uses them. Reviving an engine
means reinstalling it. The launch argv in `engine_h2h.yaml` is the recipe.

## What's here

| Path | What it is | Reusable bits |
|---|---|---|
| `bench_engine_h2h.py` | Harness: `doctor`, `switch`, `preflight`, `speed`, `security`, `quality`, `summarize` | single-flight lock; swap start-gate and growth guard; nonce-prefixed cold prefill; per-engine think-off dialects; template diff (local vs source vs GGUF-embedded); oMLX per-model spec settings via `model_settings.json` with backups |
| `engine_h2h.yaml` | Registry: engines (ports, exact plain/spec argv, stop signal) and models | argv that worked for each engine, including fairness pins (MTPLX: `--no-stats-footer`, `--ssd-session-cache off`, `--tool-prompt-mode native`; mlx-serve: `--no-pld --no-drafter --no-mtp`) |
| `prismml_mlx_server.py` | Minimal OpenAI-compatible server for PrismML's 1-bit/2-bit MLX fork | pattern for wrapping an MLX runtime with no server |
| `tests/` | Its unit tests (import paths assume the old `tests/benchmarks/` location) | |
| `fixtures/engine_h2h/security_prompts.json` | 5 CWE snippets + 1 clean control, with instruction | security-lane prompt set |
| `fixtures/engine_h2h/prefill_*.txt` | Byte-identical real-repo prefill text | cold-prefill measurement |
| `fixtures/bonsai_quality/quality.json` | 43-item synthetic quality fixture (arithmetic, factual, instruction, logic, long-context, python, summary) | |
| `wfe_plans/` | WFE engine-mode plans (Bonsai, MiMo coding lane) | |
| `deep_lane/` | Thinking-on reasoning runner (18 machine-checked prompts, answers verified in Python), plus its results | deep-lane A/B against any Ollama/`/v1` engine |

## To revive

Move the files back to `tests/benchmarks/` (harness, registry, adapter),
`tests/benchmarks/fixtures/` and `tests/unit/`. The harness resolves its
fixtures and registry relative to its own directory, and the tests import
`tests.benchmarks.bench_engine_h2h`. Reinstall whichever engine you need, then
run `doctor`.

## Lessons worth keeping (all fixed or recorded elsewhere)

- The WFE runner used to send only temperature/top_p/seed. Fixed 2026-09-24
  (`SAMPLING_KEYS` in `tests/wfe/runner.py`). Check each engine's per-request stats
  for what was actually applied.
- MTPLX defaults to its legacy `hybrid` tool contract and has no `repeat_penalty`.
- oMLX 0.6.4 cannot load PrismML/MTPLX Bonsai packs (`prism_hadamard_qwen35`).
- `pgrep -f <name>` wait loops match other wait loops that contain the same
  string, which deadlocks a chain. Wait on a PID or a sentinel file instead.
