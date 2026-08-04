# Compliance Fallback Policy

<!-- WIKI:GENERATED unit=unit-compliance-fallback-policy-compliance-fallback-policy -->
The compliance fallback policy governs which models may serve requests behind the `auto-compliance` workspace and what happens when a fallback falls below expectations. Its operational shape is fixed by three config surfaces. `config/portal.yaml` declares the workspace: `module: compliance`, `model_hint: granite4.1:8b-ctx16k`, the temperature and context knobs, the tool list, and the owui system prompt. `config/backends.yaml` declares the routing chain in `workspace_routing` (`auto-compliance` routes through the reasoning group and then the general group) and lists the model pools those groups draw from. The registry entry in `WORKSPACE_REGISTRY` binds the workspace to its assertion library `tests.lib.compliance_assertions`, its fixture loader `tests.lib.compliance_fixtures`, and its per-workspace `threshold_doc`. The compliance module surface (`portal.modules.compliance.config`) exposes exactly one workspace id, `auto-compliance`, via `COMPLIANCE_WORKSPACE_IDS`.

## Why

The source document's status and last-reviewed lines were hand-edited stamps that no tooling writes, which is exactly the kind of unverifiable claim re-grounding removes. The policy itself is real, but its truth lives in the files the router and the sweep actually read: the workspace entry, the routing chain, and the registry binding are each machine-checkable, so this unit can be verified against HEAD instead of trusted from a dated stamp.
<!-- /WIKI:GENERATED -->

---

## What "compliance fallback" means

<!-- WIKI:GENERATED unit=unit-compliance-fallback-policy-what-compliance-fallback-means -->
Compliance fallback means the `auto-compliance` workspace's routing chain in `config/backends.yaml`: `workspace_routing` routes the workspace through the reasoning group and then the general group, in that priority order. `config/portal.yaml` sets the workspace `model_hint` to `granite4.1:8b-ctx16k`, the 16K-context derived tag of Granite 4.1 8B, which is registered in both the reasoning and general groups with `supports_tools: true`. In the request path, `_prioritize_hinted_backend` moves the backend able to serve the hint to the front of the candidates; if the hint cannot be resolved, the handler falls back to that backend's first model and records the event on the `_hint_fallback_total` metric. The candidate set is ordered by `workspace_routing` group priority, and `get_backend_candidates` appends the `fallback_group` and any remaining healthy backends as degrade-don't-fail tiers, so any Ollama model in `ollama-reasoning` or `ollama-general` can become the served handler when the hint is unavailable. The former MLX proxy priority, a chain that began with an mlx group, was retired in commit 3a0c58e and no mlx entry remains in the chain.

## Why

The source document named the primary hint `granite4.1:8b`, but the live workspace config selects the context-capped `granite4.1:8b-ctx16k` tag, and the "falls through" behavior lives in the request handler, not in policy prose. Re-grounding fixes the tag and pins the fallback to its actual mechanism — hint prioritization, first-model fallback and the metric that counts it — so the claim is testable against the router code rather than trusted from a sentence.
<!-- /WIKI:GENERATED -->

---

## Threshold policy

<!-- WIKI:GENERATED unit=unit-compliance-fallback-policy-threshold-policy -->
The matrix driver grades each scenario through assertion severities rather than an absolute pass band. Every assertion in `tests/lib/compliance_assertions.py` carries a `severity` of `MUST` (default), `SHOULD` or `INFO`, and `ScenarioOutcome.status` derives from it: a response fails when any `MUST` assertion fails, warns when all `MUST` pass but a `SHOULD` fails, and passes otherwise. The anti-fabrication assertion `assert_no_fabrication_when_asked` is the case that can override percentage: a response quoting a long verbatim-looking block without a refusal phrase fails at `MUST` severity, so a single fabrication-pattern failure fails the cell regardless of how many other scenarios passed. `run_sweep` aggregates scenario outcomes into per-cell counts, and `compute_regressions` in `tests/persona_matrix_diff.py` defines PASS-rate as PASS over PASS plus WARN plus FAIL with a default regression threshold of 10 percentage points. The eighty-percent and sixty-percent accept, borderline and reject bands and the ninety-day re-evaluation cadence from the source document are operator routing policy; the registry records the policy document in its `threshold_doc` field, but no code enforces those bands.

## Why

The source document presented the accept, borderline and reject thresholds as though the driver enforced them; it does not. What the code actually decides is severity-graded — fabrication-style failures are `MUST` so they dominate the outcome — and every percentage band is a human judgment on the published matrix. Splitting the enforced mechanics from the advisory bands keeps this unit true to what the harness will actually fail on.
<!-- /WIKI:GENERATED -->

---

## Canonical baseline

<!-- WIKI:GENERATED unit=unit-compliance-fallback-policy-canonical-baseline -->
The accepted baseline for the compliance matrix is stored at `tests/benchmarks/results/persona_matrix_baseline_auto-compliance.json`, a `portal5.persona_matrix.v1` report produced by `tests/portal5_persona_matrix.py`. Without an explicit `--output`, the driver writes to `RESULTS_DIR` using the workspace-scoped name `persona_matrix_<workspace>_<utc-stamp>.json`; the baseline file keeps the same shape so `persona_matrix_diff` and `--baseline-compare` can diff against it. Re-baselining is warranted whenever any sweep input changes: a model added or upgraded in the `ollama-reasoning` or `ollama-general` groups (`config/backends.yaml`), a compliance persona system prompt edit (`config/personas/*.yaml`), a fixture scenario change (`tests/fixtures/compliance_scenarios.yaml`), or an assertion library change (`tests/lib/compliance_assertions.py`). The quarterly cadence is operator policy and is not enforced by any code.

## Why

The baseline is a machine artifact, not a document: it is the output of the same driver the regression diff consumes, so its location and schema must match what `persona_matrix_diff` reads. Naming it with the workspace id keeps one chain's baseline from colliding with another in the shared results directory, and the trigger list simply names the inputs the sweep loads, so a stale baseline is attributable to a specific change rather than to unknown drift.
<!-- /WIKI:GENERATED -->

---

## Granite 4.1 — initial expectation

<!-- WIKI:GENERATED unit=unit-compliance-fallback-policy-granite-4-1-initial-expectation -->
Granite 4.1's model-card claims are recorded in the `bench-granite41-8b` and `bench-granite41-30b` workspace descriptions in `config/portal.yaml`. The 8B is described as a dense no-think model at roughly 5.3GB Q4_K_M, Apache 2.0 licensed and ISO-certified, with BFCL V3 68.3, IFEval 87.1 and GSM8K 92.5; the 30B as dense no-think at roughly 17GB Q4_K_M, Apache 2.0 and ISO-certified with cryptographic signatures, BFCL V3 73.7 (first on the IBM chart), IFEval 89.7, GSM8K 94.2 and EvalPlus 82.7, trained with GRC data curation for compliance and audit workflows.

The expectations the sweep will test are encoded in `tests/fixtures/compliance_scenarios.yaml`: the `dense-structured-tool-output` scenario description states dense no-think models should pass it cleanly while reasoning models typically warn on emitted think blocks, and the classification, citation-format, anti-fabrication and insufficient-context scenarios carry assertion specs dispatched by `run_assertions` to `tests/lib/compliance_assertions.py`. If the first run disappoints, the operator's knobs are the persona system prompt (`config/personas/*.yaml`), the assertion regexes in `tests/lib/compliance_assertions.py`, and model group membership in `config/backends.yaml`.

## Why

The source document's expectation prose is a prediction, so the only verifiable half is the model-card data recorded in the bench workspace descriptions and the fixture comments stating the intended outcome. Rewording the failure guidance to name the three configuration surfaces the operator can actually touch turns a speculative paragraph into a grounded decision checklist.
<!-- /WIKI:GENERATED -->

---

## Re-running the matrix

<!-- WIKI:GENERATED unit=unit-compliance-fallback-policy-re-running-the-matrix -->
Re-running the compliance matrix means invoking the persona-matrix driver against `auto-compliance` with the same inputs that produced the stored baseline. The driver is `tests/portal5_persona_matrix.py`, a compat shim for `portal.modules.eval.persona_matrix`. The flags in `cli.py` shape the run: `--workspace` (default `auto-compliance`), `--persona` and `--model` (substring filters on slugs and model ids), `--backend ollama` (backend-type filter), `--require` (hard model-presence gate that exits 3), `--dry-run` (print the plan without calling Ollama), `--include-big-models` (admit models otherwise skipped), and `--baseline-compare` with `--regression-threshold` (inline regression diff against a stored baseline). A re-run should reuse the same flags as the original sweep, because the regression diff only compares cells with matching persona, backend and model keys and silently ignores cells absent from either report.

## Why

Re-running a benchmark correctly is the same discipline as running it the first time: every filter changes which cells the report contains, and the diff tool ignores cells missing from either side, so a mismatched flag set produces a comparison that is quietly incomplete. Naming the flags that shape the chain turns "re-run the matrix" from a remembered command into a reproducible contract the operator can verify cell by cell.
<!-- /WIKI:GENERATED -->

---

# Full sweep

<!-- WIKI:GENERATED unit=unit-compliance-fallback-policy-full-sweep -->
A full sweep runs every model in the auto-compliance chain against every applicable compliance scenario. The entrypoint is `tests/portal5_persona_matrix.py`, a thin shim for `portal.modules.eval.persona_matrix`. Without `--output`, the driver writes to `RESULTS_DIR` as `persona_matrix_<workspace>_<utc-stamp>.json`; an explicit `--output` path overrides the default. A complete run against the current chain:

```bash
python3 tests/portal5_persona_matrix.py \
    --output "tests/benchmarks/results/persona_matrix_$(date -u +%Y%m%dT%H%M%SZ).json"
```

Internally `run_sweep` resolves the chain with `chain_models_for_workspace`, loads the compliance personas, evicts Ollama models between cells, and returns a `portal5.persona_matrix.v1` report. `cli.py` returns exit code 1 when any cell has a FAIL (exit 2 when a baseline comparison also reports regressions), so a dirty sweep is visible to a shell.

## Why

The default filename embeds the workspace id because `RESULTS_DIR` is shared across every chain's sweeps; without the id an auto-compliance run and an auto-coding run would collide on the same timestamp. An explicit `--output` exists for operator-labelled runs, which is why the documented full-sweep command passes one, and the exit-code contract makes the sweep scriptable rather than eyeballed.
<!-- /WIKI:GENERATED -->

---

# Granite-required sweep (fails if Granite has been removed from chain)

<!-- WIKI:GENERATED unit=unit-compliance-fallback-policy-granite-required-sweep-fails-if-granite-has-been-removed-from-chain -->
The `--require` flag makes a sweep fail fast when a named model is absent from the resolved chain. In `run_sweep`, after backend, model and big-model filters, every required substring must appear in some chain model id; otherwise the driver prints the missing list and exits 3 before any cell runs. The documented granite-required sweep:

```bash
python3 tests/portal5_persona_matrix.py \
    --backend ollama \
    --require granite4.1:8b,granite4.1:30b \
    --output "tests/benchmarks/results/persona_matrix_granite_$(date -u +%Y%m%dT%H%M%SZ).json"
```

Both granite models are currently registered in the reasoning and general groups of `config/backends.yaml`, so the auto-compliance chain contains them; the sweep fails only if no remaining chain id contains the required substring. Comparison against baseline uses the real diff tool rather than a hand-rolled snippet:

```bash
python3 tests/persona_matrix_diff.py \
    tests/benchmarks/results/persona_matrix_baseline_auto-compliance.json \
    tests/benchmarks/results/persona_matrix_<NEW>.json --threshold 10
```

`compute_regressions` treats PASS-rate as PASS over PASS plus WARN plus FAIL per cell and flags a drop beyond the threshold in percentage points, default 10.0. The driver's `--baseline-compare` runs the same comparison inline and exits non-zero on regressions.

## Why

The source doc shipped an inline diff snippet with a hardcoded five-point flag that never matched the driver's real regression machinery. The code paths that actually enforce a granite-required sweep are the substring check in `run_sweep` (exit 3) and the per-cell PASS-rate comparison in `persona_matrix_diff` (10pp default), and grounding the unit to those two entry points keeps the failure mode and comparison semantics exact.
<!-- /WIKI:GENERATED -->

---

## Out of scope

<!-- WIKI:GENERATED unit=unit-compliance-fallback-policy-out-of-scope -->
The compliance fallback policy is scoped to `auto-compliance` only, and the mechanical boundary is the registry. In `WORKSPACE_REGISTRY`, `auto-compliance` is the single entry bound to `tests.lib.compliance_assertions` and `tests.lib.compliance_fixtures`; `auto-coding` binds to its own assertion and fixture modules, and the bench workspaces bind to a shootout harness. On the config side, `portal.modules.compliance.config` exposes exactly one id, `auto-compliance`, through `COMPLIANCE_WORKSPACE_IDS`, and `config/portal.yaml` maps the compliance module to that one workspace. The driver itself is workspace-parameterizable — `--workspace` accepts any registry key — but the fixture YAML, assertion library and threshold document are per-workspace, so extending the policy to `auto-coding`, `auto-research`, `auto-data` or `auto-security` means authoring those inputs, not changing the driver.

## Why

"Out of scope" is an architectural property, not a preference: the registry couples each workspace to its own assertion and fixture modules, so a compliance policy written for one chain cannot silently govern another. Stating which surfaces would need to be authored — fixtures, assertions, threshold document — converts the source document's future-work note into a concrete extension path grounded in the registry structure and the module's workspace list.
<!-- /WIKI:GENERATED -->

---
