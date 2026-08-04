# Persona Matrix CI Operations

<!-- WIKI:GENERATED unit=unit-persona-matrix-ci-persona-matrix-ci-operations -->
This unit is the operations surface of the persona-matrix CI: how a sweep is configured, triggered, and consumed by an operator. Configuration is registry-driven — `WORKSPACE_REGISTRY` in `_common.py` maps each sweepable workspace to its assertion module, fixture module, persona categories, and an optional `threshold_doc`. The `auto-compliance` entry binds to `tests.lib.compliance_assertions`, `tests.lib.compliance_fixtures`, the compliance category, and `docs/COMPLIANCE_FALLBACK_POLICY.md`; `auto-coding` binds to the coding assertion and fixture libraries and carries no `threshold_doc` (the coding fallback-policy doc it once named does not exist, so the dead reference was dropped). The workflow supports three operator flows: baseline creation (run locally, inspect, commit the workspace-scoped JSON), manual dispatch (pick a workspace and the `ollama` backend from the workflow inputs), and artifact retrieval (the `persona_matrix-*` upload with 30-day retention).

CI differs from the fallback-policy docs in an important way: the workflow is policy-free. It only compares a fresh run against the committed baseline through `--baseline-compare`; deciding what behavior is acceptable is delegated to the `threshold_doc` files the registry references, which the gate never reads. Operations are therefore split between the mechanical diff and the human-owned acceptability policy.

## Why

The original unit was pure cross-reference — it described a doc's relationship to another doc, which cannot be verified once the generated source is gone. What is real and checkable is the registry binding that names the compliance fallback policy as a workspace's threshold reference and the workflow triggers that define how an operator drives a run. Rewriting the unit around those concrete surfaces keeps it useful as an operations map instead of a memory of a file.
<!-- /WIKI:GENERATED -->

---

## Pipeline shape

<!-- WIKI:GENERATED unit=unit-persona-matrix-ci-pipeline-shape -->
The persona-matrix workflow has no scheduled cron trigger. `persona_matrix_nightly.yml` declares only workflow_dispatch (manual) and pull_request (path-scoped), and the file's own header comment explains why: no self-hosted runner is kept online for this repo, so a cron would queue forever and be auto-cancelled by GitHub. The PR path filter narrows runs to changes that plausibly alter matrix outcomes: `config/personas/**`, `config/backends.yaml`, `tests/lib/**`, `tests/fixtures/**`, and `tests/portal5_persona_matrix.py`.

```
[workflow_dispatch (workspace + backend inputs)] ──┐
[PR touching personas / backends / lib / fixtures] ┤── persona-matrix-nightly (self-hosted)
                                                   ┘          │
                                                              ▼
                                                     pre-flight: pipeline :9099 + Ollama :11434 health
                                                              │
                                                              ▼
                                                     tests/portal5_persona_matrix.py --baseline-compare --regression-threshold 10
                                                              │
                                                              ▼
                                                     tests/benchmarks/results/persona_matrix_<ws>_ci_<ts>.json   (uploaded artifact)
                                                              │
                                                              ▼
                                                     tests/persona_matrix_diff.py vs baseline   (run log, no PR comment)
                                                              │
                                                              ▼
                                                     exit 0 clean / 1 FAIL-or-regression / 2 both   (job status)
```

The `tests/portal5_persona_matrix.py` entrypoint is a thin shim that delegates to `portal.modules.eval.persona_matrix` (`cli.main`), so the sweep, loaders, and diff integration live in the module tree rather than in `tests/`.

## Why

The shape matters because the doc that produced this unit drew a `[scheduled cron]` input that the workflow explicitly forbids — a cron on this repo was empirically shown to queue forever across months of scheduled runs before it was removed. Restating the shape from the actual trigger and step structure makes the unit describe the real CI topology, and keeping the diagram fenced preserves it as a stable reference that does not drift the way prose would.
<!-- /WIKI:GENERATED -->

---

## Baseline lifecycle

<!-- WIKI:GENERATED unit=unit-persona-matrix-ci-baseline-lifecycle -->
The persona matrix treats a committed result file as the reference the CI gate diffs against. The workflow's `Determine sweep parameters` step expects that reference at `tests/benchmarks/results/persona_matrix_baseline_<workspace>.json` and, when present, hands it to the sweep via `--baseline-compare`. A first baseline is therefore an operator action: run the driver locally without `--baseline-compare`, inspect the rendered matrix, and commit the JSON under the workspace-scoped name. The workflow never writes this file — its own sweep output goes to a timestamped `persona_matrix_<workspace>_ci_<ts>.json` artifact — so the baseline can only change through an operator-authored commit.

Re-baselining is warranted when the same inputs that fire the workflow change behavior expectations. The PR path filter watches `config/personas/**` (persona system-prompt edits), `config/backends.yaml` (a model added to a workspace chain), `tests/lib/**` (assertion-library threshold or regex changes), and `tests/fixtures/**` (scenario edits). A model re-pull that moves the Ollama digest is not a file change; it surfaces as a regression in the next baseline diff and is the signal to re-baseline when the new behavior is in spec. The quarterly cadence is operator policy, not code — nothing enforces it; the mechanical backstop is the regression threshold (`--regression-threshold`, default 10pp) applied by `persona_matrix_diff.py`'s `compute_regressions`.

## Why

The lifecycle exists because the CI gate is a diff, not an absolute judge: the workflow can only decide clean or red against a previously committed reference, so an operator must own when that reference moves. Binding the trigger list to the workflow's PR paths makes "when do I re-baseline" mechanically checkable instead of a memory, while digest-drift and quarterly cases stay human judgment, which is why they are policy rather than enforced in code.
<!-- /WIKI:GENERATED -->

---

## CI vs. local-run boundary

<!-- WIKI:GENERATED unit=unit-persona-matrix-ci-ci-vs-local-run-boundary -->
CI runs on a self-hosted runner because the sweep and its pre-flight step need host access to the Portal 5 stack. The workflow's `runs-on: self-hosted` line and its Pre-flight step curl `localhost:9099` (pipeline health) and `localhost:11434` (Ollama version) before the sweep starts; a public GitHub-hosted runner has neither of those loopback services. If the self-hosted runner is offline the job queues — the workflow declares no fallback label, so GitHub has no hosted pool to spill onto.

The CI run is non-destructive by construction. Sweep output lands at `tests/benchmarks/results/persona_matrix_<workspace>_ci_<ts>.json`, is uploaded as a `persona_matrix-*` artifact with `retention-days: 30`, and is never committed by the workflow. The baseline file is only read (passed to `--baseline-compare`), so baseline updates require an operator-authored commit. The workflow does not post a PR comment: it prints the `persona_matrix_diff.py` summary to the run log and, when the sweep exited non-zero, fails the job with that same exit code — a failed PR check blocks merge, while a manual dispatch failure only marks that run red.

## Why

The boundary is a consequence of the local-first architecture: the matrix measures real local models, so the runner must be the machine that can reach them, and the results must not mutate the repo. Splitting measure from change keeps CI safe to run unattended — the workflow can fail loudly and upload evidence, but it can never overwrite a baseline or leak a result into version control, which is what allows the nightly gate to run with zero operator supervision.
<!-- /WIKI:GENERATED -->

---

## MLX coverage policy

<!-- WIKI:GENERATED unit=unit-persona-matrix-ci-mlx-coverage-policy -->
MLX chat inference was retired in commit `3a0c58e` (`feat: retire MLX proxy — migrate to Ollama-only inference stack`); the persona-matrix driver now talks only to Ollama at the `OLLAMA_URL` constant (`http://localhost:11434`) via `_chat_direct`, and the CLI restricts `--backend` to `ollama`. The workflow's `backend` input offers only `ollama` as a choice, so CI sweeps are Ollama-only by construction. The `--mlx-warmup` flag and a `mlx_models:` key in `backends.yaml` no longer exist anywhere in the current tree — the only `MLX_MODELS` reference left is a comment in `backends.yaml` about the embedding pull list.

MLX survives only outside chat inference as separate non-chat runtimes the matrix driver never calls: speech (`scripts/mlx-speech.py`, port 8918), diarized transcription (launch.sh, port 8924), embeddings (port 8917), and reranking (`.env.example` RERANKER, port 8925). Those runtimes are excluded from persona-matrix sweeps because `run_cell` only ever issues an OpenAI-compatible chat request to the Ollama URL; no MLX endpoint is consulted during a sweep.

## Why

This unit exists to keep a stale doc from resurrecting a retired stack: the MLX-proxy era had warmup flags and big-model handling that no longer compile against the driver's CLI. Grounding the boundary to commit `3a0c58e`, the `OLLAMA_URL` constant, and the `ollama`-only backend choice makes it checkable — if MLX ever re-enters chat inference, the cited source files change first, which is the only way this policy can stay honest.
<!-- /WIKI:GENERATED -->

---

## Big-model coverage

<!-- WIKI:GENERATED unit=unit-persona-matrix-ci-big-model-coverage -->
The `--include-big-models` flag and the `big_model` field still exist in the persona-matrix driver, but the policy's original claim — that specific models are flagged `big_model: true` in `config/backends.yaml` — is stale. No `big_model: true` marker exists anywhere in `backends.yaml` today, and the loader hardcodes `big_model` to `False` for every model it resolves (`models_in_group` in `loaders.py` and the explicit-models path in `sweep.py`). The pre-retirement MLX-era entries the policy named — `Qwen3-Coder-Next-4bit`, `Llama-3.3-70B-Instruct-4bit`, `Qwen3-VL-32B-Instruct-8bit` — are gone; the current catalog uses Ollama ids such as `qwen3-coder-next:latest`, and the only Qwen3-VL-32B entry is `Qwen3-VL-32B-Instruct-4bit` under the `omlx` holding group, which no workspace routing chain references.

The mechanism is retained for future use: `sweep.py` and `ollama_client.py` both filter the resolved chain with `if not args.include_big_models` before running, so a model actually flagged `big_model` today would be excluded from default sweeps and included only when an operator passes `--include-big-models`. Because the loader never sets the flag, that filter is currently inert. Operator-driven big-model coverage therefore means deliberately passing `--include-big-models`; the workflow's own chains (`auto-compliance`, `auto-coding`) run within the job's `timeout-minutes: 120` cap without any exclusion logic firing.

## Why

The original doc asserted model identities and sizes that date to the pre-retirement MLX proxy and no longer exist in the catalog, so re-grounding must state what the code actually does rather than preserve a nostalgic policy. The structural truth worth keeping is that the exclusion switch survives but is a no-op until a model is flagged — operators should read the field as a reserved capability, not a policy currently in force, and the flag's help text is the only place the intended semantics are documented.
<!-- /WIKI:GENERATED -->

---

## Regression triage workflow

<!-- WIKI:GENERATED unit=unit-persona-matrix-ci-regression-triage-workflow -->
When a CI sweep surfaces a regression, the diff names the exact cell: `persona_matrix_diff.py` indexes cells by `(persona, backend, model)` and prints regressions as `persona on backend/model` with the PASS-rate delta in percentage points. To reproduce the cell in isolation, run the driver locally with the substring filters the CLI supports — `--workspace`, `--persona`, `--model`, `--output` (an output path such as one under `/tmp`) — so the sweep executes only that one cell. The JSON report's per-scenario entries carry the assertion `name`, `passed`, `severity`, and `detail` (built by `run_cell` in `sweep.py`), so you can see which assertion flipped from PASS to FAIL.

The three common causes map to real mechanisms. Model digest drift follows an `ollama pull` that changed model behavior; it surfaces as a regression in the next baseline diff, and re-baselining is the remedy when the new behavior is in spec. A persona system-prompt edit is tracked by the workflow's `config/personas/**` PR path; the fix is either revising the prompt or relaxing the assertion in `tests/lib/`. A genuine regression means the model got worse, and the demotion target is the workspace's `threshold_doc` from `WORKSPACE_REGISTRY` — `docs/COMPLIANCE_FALLBACK_POLICY.md` for `auto-compliance`.

## Why

Triage is the operator-facing complement to the mechanical diff: the diff can only say a cell dropped, never why, so the workflow exists to narrow a whole-matrix failure down to one assertion on one model. Grounding each cause to a concrete mechanism — the diff's cell key, the CLI substring filters, the JSON assertion payload, and the registry's `threshold_doc` — keeps the triage steps runnable against HEAD instead of relying on the doc's prose.
<!-- /WIKI:GENERATED -->

---

## Out of scope for CI

<!-- WIKI:GENERATED unit=unit-persona-matrix-ci-out-of-scope-for-ci -->
Three workloads are deliberately outside the persona-matrix CI gate. First, throughput comparisons: `bench_tps` (in `tests/benchmarks/`) owns TPS and latency, while the matrix driver records a `tps` field per scenario only as context — its pass/fail decision and the baseline diff use assertion outcomes exclusively, since `persona_matrix_diff.py` computes PASS-rate as PASS over PASS+WARN+FAIL and never reads throughput. Second, pipeline routing: `portal5_acceptance_v6.py` owns routing validation through section `S3a` (Ollama workspace routing, delegating to `tests/acceptance/runner.py`), whereas the matrix pins a model directly in the chat request via `_chat_direct` to measure raw model behavior. The former `S3b` MLX routing section was retired with the MLX proxy in `3a0c58e`.

Third, unregistered workspaces: the CLI derives its `--workspace` choices from the keys of `WORKSPACE_REGISTRY`, and `_load_workspace_modules` raises a hard exit if a requested workspace is not registered, so a workspace must be added to the registry before CI can sweep it. Nothing in the driver discovers workspaces dynamically.

## Why

The scope line exists because each instrument measures something different and mixing them produces misleading signals: routing belongs to acceptance because it exercises the intent classifier and routing chain, throughput belongs to bench because it needs controlled warm and cold load, and the matrix measures only behavioral compliance of a pinned model. Keeping the division explicit in the registry and driver makes what CI does not check as checkable as what it does.
<!-- /WIKI:GENERATED -->

---
