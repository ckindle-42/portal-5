# Persona Matrix CI Operations

Companion to `docs/COMPLIANCE_FALLBACK_POLICY.md`. Where that doc captures
*what* the matrix measures, this doc captures *how* it runs in CI and what
operator workflows it supports.

## Pipeline shape

```
[scheduled cron] ──┐
[PR-touching matrix code] ──┤── persona-matrix-nightly workflow
[manual dispatch] ──┘                │
                                     ▼
                          tests/portal5_persona_matrix.py sweep
                                     │
                                     ▼
                          tests/benchmarks/results/...json (artifact)
                                     │
                                     ▼
                          tests/persona_matrix_diff.py vs baseline
                                     │
                                     ▼
                          green or red CI status
```

## Baseline lifecycle

1. **First baseline (per workspace).** Operator runs the matrix locally
   without `--baseline-compare`, inspects results, decides whether the
   numbers represent acceptable behavior, and commits the JSON to:
       `tests/benchmarks/results/persona_matrix_baseline_<workspace>.json`

2. **Re-baselining.** Required after any of:
   - New model added to a backend group on the workspace's chain
   - Existing model upgraded (Ollama re-pull moves the digest)
   - Persona system prompt edited
   - Fixture scenario added/modified
   - Assertion library threshold/regex changed
   Process: run the matrix manually, inspect the diff, commit the new
   baseline if the changes are intentional and acceptable.

3. **Quarterly cadence.** Even with no triggering change, re-baseline
   quarterly to absorb drift in model behavior from re-pulls,
   environmental shifts, or assertion-library tuning.

## CI vs. local-run boundary

CI runs on a self-hosted runner that has access to the Portal 5 stack.
Public GitHub-hosted runners cannot reach the local pipeline / MLX /
Ollama services. If the self-hosted runner is unavailable, the workflow
queues — it does not fall back to a hosted runner.

The CI run is **non-destructive** by design:
- Sweep results write to `tests/benchmarks/results/...` and are uploaded
  as a workflow artifact (30-day retention) but are **not** auto-committed
- Baselines are updated only by an operator-authored commit
- Failed CI runs comment with the diff summary but do not block local
  development unless the failing run is on a PR

## MLX coverage policy

**MLX inference is retired (commit 3a0c58e).** All chat inference runs through
Ollama (:11434). The `--mlx-warmup` flag and `mlx_models:` key in `backends.yaml`
described here no longer exist — they were part of the pre-retirement MLX proxy.

CI sweeps are Ollama-only. MLX is retained only for non-chat runtimes:
speech (:8918), transcription (:8924), embeddings (:8917), and reranking (:8925).
Those runtimes are not exercised by the persona matrix driver.

## Big-model coverage

Models flagged `big_model: true` in `backends.yaml` (currently:
`Qwen3-Coder-Next-4bit` ~46GB, `Llama-3.3-70B-Instruct-4bit` ~40GB,
`Qwen3-VL-32B-Instruct-8bit` ~36GB) are skipped from CI by default.
Each big-model load takes 1–3 minutes plus full eviction of every other
model — running them in a nightly sweep would extend the workflow past
its 120-minute timeout.

Big-model coverage is operator-driven:
- Pre-release validation: run `--include-big-models` once before
  shipping a release that touches the agentic-coding workspace.
- Quarterly: same trigger as re-baselining.

## Regression triage workflow

When CI surfaces a regression:

1. **Identify the regressed cell.** The diff output names exactly
   `(persona, backend, model)`.
2. **Run the cell in isolation** locally to reproduce:
   ```bash
   python3 tests/portal5_persona_matrix.py \
       --workspace <ws> \
       --persona <slug-substring> \
       --model <model-substring> \
       --output /tmp/repro.json
   ```
3. **Inspect the failing scenarios.** The JSON shows per-scenario
   `results` with the assertion `name`, `passed`, `severity`, and
   `detail`. Find which assertion(s) flipped from PASS to FAIL.
4. **Triage cause.** Three common patterns:
   - **Model digest drift.** `ollama pull` was re-run and the model
     behaves differently. Acceptable cause; re-baseline if the new
     behavior is in spec.
   - **Persona prompt edit.** Recent persona change inadvertently
     constrained the model in a way the assertion library catches.
     Either revise the prompt or relax the assertion.
   - **Genuine regression.** The model is now worse. Demote per the
     fallback policy in `docs/<WORKSPACE>_FALLBACK_POLICY.md`.

## Out of scope for CI

- TPS / latency comparison. That's `bench_tps`'s job; the matrix only
  cares about behavioral pass/fail.
- Pipeline routing tests. Acceptance v6 covers those (`S3a` / `S3b`).
- Per-(persona, model) coverage of non-registered workspaces. Each
  workspace must register in `WORKSPACE_REGISTRY` before CI can sweep it.
