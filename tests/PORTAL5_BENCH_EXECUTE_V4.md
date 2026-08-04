# PORTAL5_BENCH_EXECUTE_V4 — opencode Bench Execution Prompt

<!-- WIKI:GENERATED unit=unit-portal5-bench-execute-v4-portal5-bench-execute-v4-opencode-bench-execution-prompt -->
> **Supersedes** `PORTAL5_BENCH_EXECUTE_V3.md` (archived under
> `docs/_archive_execdocs/`). V4 is the current opencode bench execution
> prompt for the post-collapse / post-alias-retirement codebase: corrected
> scale, `PORTAL_ENABLE_EVAL` gating, preflight-driven counts (no baked
> numbers), and served-model verification tie-in.

Run the Portal 5 comprehensive TPS benchmark suite (Ollama-only). The live
stack is expected running when you begin. At the end, update the Grafana
benchmarks dashboard and commit results.

**Scale is config-driven and drifts — never trust a number in this doc. Run
the preflight first:**

```bash
python3 scripts/execute_preflight.py
```

`bench_tps.py` is the sole TPS instrument. The acceptance and UAT suites
assert no performance numbers — they delegate routing/TPS coverage to the
bench.

## Why

V4 exists because the pre-collapse docs baked in counts that went stale after
alias retirement and the eval-module gating changed how the bench surface is
loaded. The execution prompt now points at `scripts/execute_preflight.py` for
ground truth and at `bench_tps.py --dry-run` for the plan, so an execution
agent derives numbers from live config instead of a paragraph. `bench_tps.py`
is a re-export shim over `tests/benchmarks/bench/`, keeping the operator
entry point stable while the implementation was modularized.
<!-- /WIKI:GENERATED -->

---

## Your Role

<!-- WIKI:GENERATED unit=unit-portal5-bench-execute-v4-your-role -->
You are the **benchmark execution agent**, not the implementation agent. You
execute the suite, diagnose failures, adjust the run, retry intelligently, and
produce a Grafana dashboard update. Results go to `tests/benchmarks/results/`
as a timestamped JSON (`RESULTS_DIR` / `RESULTS_FILE` in
`tests/benchmarks/bench/config.py`); the dashboard at
`config/grafana/dashboards/portal5_benchmarks.json` updates from that file via
`scripts/update_grafana_benchmarks.py`.

**No shortcuts. No prior-run bias.** Do not assume models from a previous run
are still loaded or producing similar TPS. Every run is fresh.

**Do NOT modify product code.** `portal/**` is protected. If a bench failure
traces to a product bug, report it — don't patch it here.

## Why

The role is deliberately separated from implementation so the bench stays a
measurement instrument: the execution agent adjusts run scope, diagnoses
failures, and reports product bugs without editing routing code, which keeps
results trustworthy. The read-only rule and fresh-run rule protect against the
two ways a bench corrupts itself — patching the code under test, or
over-trusting cached resident models — so the dashboard update reflects what
actually ran.
<!-- /WIKI:GENERATED -->

---

## Phase 0 — Preflight (required before any run)

<!-- WIKI:GENERATED unit=unit-portal5-bench-execute-v4-phase-0-preflight-required-before-any-run -->
```bash
python3 scripts/execute_preflight.py
```

Phase 0 is a hard requirement: run the preflight before anything else. It
prints the current production and eval workspace counts, the persona count,
the MCP fleet size, and the `model_pin` personas, and it exits nonzero with a
"STOP" banner if a retired alias id reappears in `config/portal.yaml`. Only
proceed to `--dry-run` and the real run once it reports "OK to run."

## Why

Preflight exists so the bench never starts from a stale or non-canonical
surface. Counts and vocabularies drift as workspaces and personas are added,
so an execution agent needs the current ground truth, not a doc's baked
numbers. The retired-alias check catches a regression where a retired id like
`auto-redteam` silently reappears; benching that surface would waste hours and
produce results that mislead, which is why the nonzero exit is a stop signal.
<!-- /WIKI:GENERATED -->

---

# 1. Ground truth — counts + no retired-alias leak

<!-- WIKI:GENERATED unit=unit-portal5-bench-execute-v4-1-ground-truth-counts-no-retired-alias-leak -->
```bash
python3 scripts/execute_preflight.py
```

The preflight is the ground-truth gate for every bench, security, and
acceptance session. It recomputes the production and eval workspace counts,
the persona count, the MCP fleet size, and the `model_pin` personas from live
YAML at run time, then returns zero only when no retired alias id reappears in
`config/portal.yaml`. A nonzero exit with the "STOP" banner means the surface
regressed and the suite must not run.

## Why

This suite's scale is config-driven and drifts, so baked workspace or persona
counts in an execution doc went stale and mis-planned runs. The preflight
recomputes reality from `config/portal.yaml` at run time and hard-fails on a
retired alias like `auto-redteam` or `auto-phi4` reappearing, which would
silently corrupt a whole bench. Trust its numbers, never the doc.
<!-- /WIKI:GENERATED -->

---

# 2. Bench plan — the real test count for THIS run

<!-- WIKI:GENERATED unit=unit-portal5-bench-execute-v4-2-bench-plan-the-real-test-count-for-this-run -->
```bash
PORTAL_ENABLE_EVAL=1 python3 tests/benchmarks/bench_tps.py --dry-run
```

`tests/benchmarks/bench_tps.py` is the operator-facing entry shim for the
modularized bench package; it re-exports `main` from `bench/cli.py`. The
`--dry-run` flag prints the configured Ollama model count, the workspace count
from `config/backends.yaml`, the persona count, and the "Total to test" figure
for the current `--mode` without executing any requests. That total is the
authoritative plan for this run.

## Why

The dry-run exists because every count the bench prints comes from live config
rather than a doc: `_config_ollama_models_unique`, `_config_workspaces`, and
`_discover_personas` in `bench/discovery.py` recompute the catalog at startup.
A plan written by hand goes stale the moment a workspace or persona is added.
The `PORTAL_ENABLE_EVAL=1` prefix mirrors the eval module opt-in so the plan
matches what a real run against the pipeline can actually route.
<!-- /WIKI:GENERATED -->

---

# 3. Backends up?

<!-- WIKI:GENERATED unit=unit-portal5-bench-execute-v4-3-backends-up -->
```bash
curl -s localhost:11434/api/tags  >/dev/null && echo "ollama ok"
curl -s localhost:9099/health     >/dev/null && echo "pipeline ok"
```

The bench hits Ollama at `http://localhost:11434` and the pipeline at
`http://localhost:9099` (constants `OLLAMA_URL` / `PIPELINE_URL` in
`tests/benchmarks/bench/config.py`). The pipeline registers a `/health`
handler in `portal/platform/inference/router/app.py`; Ollama serves
`/api/tags`. The bench itself probes the same backends via
`_check_backend` on startup and refuses to run if neither responds.

## Why

`PORTAL_ENABLE_EVAL=1` must be set before `portal.platform.inference` is
imported: `_eval_enabled` in `portal/platform/inference/config.py` gates the
eval-module workspaces at pipeline load, and a bench plan that lists eval
workspaces is incomplete if the pipeline cannot route them. The retired-alias
check is the other gate — a leak there means the surface is not canonical, so
bench a broken surface is pointless and the run must stop.
<!-- /WIKI:GENERATED -->

---

## Autonomous Monitoring Loop — required default

<!-- WIKI:GENERATED unit=unit-portal5-bench-execute-v4-autonomous-monitoring-loop-required-default -->
Full bench runs take hours: the default `--runs 5` multiplies every direct
model, pipeline workspace, and persona test, and each model swap is gated by a
cooldown and Metal-drain wait. Immediately after launching, establish a
periodic wakeup loop and keep it until the run finishes. Not optional —
long-running runs stall on OOM, hung backends, or a model that refuses to
load, and nobody notices until the wakeup checks.

## Why

The bench is deliberately slow: it unloads each Ollama model and waits for
Metal to drain before loading the next (`_wait_metal_drain` in
`tests/benchmarks/bench/lifecycle.py`) so TPS numbers are not skewed by
resident-model reuse. A multi-hour unattended run therefore cannot self-heal;
a wakeup loop is what turns a stalled overnight run into a diagnosed, resumed
one. This is why the V4 prompt made the loop a required default rather than a
suggestion.
<!-- /WIKI:GENERATED -->

---

### On launch

<!-- WIKI:GENERATED unit=unit-portal5-bench-execute-v4-on-launch -->
1. Start the run detached, logging to a timestamped file under
   `tests/benchmarks/results/`.
2. Record the PID and the expected test count (from `--dry-run`).
3. Set the first wakeup ~20 min out.

## Why

The bench writes results to a timestamped JSON under
`tests/benchmarks/results/` by default: `RESULTS_DIR` and the UTC-stamped
`RESULTS_FILE` are set in `tests/benchmarks/bench/config.py`. Because a full
run spans hours and the CLI appends as it goes, the output file doubles as the
run's log of progress, so recording where it lives and the planned count on
launch is what lets a later wakeup compare completed tests against the
`--dry-run` plan and decide between reschedule, filter, or halt.
<!-- /WIKI:GENERATED -->

---

### On each wakeup

<!-- WIKI:GENERATED unit=unit-portal5-bench-execute-v4-on-each-wakeup -->
1. Is the process alive? (`ps`), how far along? (tail the log, count completed
   tests vs planned).
2. If progressing: reschedule ~20–30 min out.
3. If stalled (no new completed test in roughly two cooldown intervals):
   diagnose — a model that won't load, an OOM, a hung backend. Note it, and
   either narrow the next run with `--model` / `--workspace` / `--persona`
   filters, or halt with evidence.
4. If finished: proceed to results + dashboard.

## Why

The bench CLI has no `--skip-model` flag; instead it supports filter args
(`--model` substring, `--workspace`, `--persona`) and a `--retry-failed`
resume that reloads the last results file and skips already-completed entries
via `_result_already_done` in `tests/benchmarks/bench/results_io.py`. A wakeup
check therefore judges progress from the log and the dry-run plan, and reacts
by scoping the run or stopping with evidence rather than waiting blindly for a
run that will never finish.
<!-- /WIKI:GENERATED -->

---

## Modes

<!-- WIKI:GENERATED unit=unit-portal5-bench-execute-v4-modes -->
`bench_tps.py` selects test tiers with `--mode` (choices in
`tests/benchmarks/bench/cli.py`: `direct`, `pipeline`, `personas`, `all`,
default `all`):
- **direct** — each Ollama model hit directly on Ollama (raw model TPS).
- **pipeline** — each workspace through the pipeline at `:9099` (routing +
  serving overhead).
- **personas** — each persona's `workspace_model` through the pipeline; the
  result is tagged with `persona_slug` but the request model is the
  workspace, so `model_pin` is not exercised by this mode.

## Why

The three tiers isolate different overheads: direct isolates raw model speed,
pipeline adds routing, and personas exercises the persona-to-workspace
mapping (`_resolve_persona_workspace` in `portal/platform/inference/router/
preinject.py`). `bench_personas` sends the persona's `workspace_model`, not
the persona slug, so a `model_pin` persona benches its workspace's pool
default — pin-serving correctness is verified separately by
`scripts/persona_intent_audit.py` and `routing_regression.py`, not by this
mode's TPS.
<!-- /WIKI:GENERATED -->

---

## Served-model sanity (new in V4)

<!-- WIKI:GENERATED unit=unit-portal5-bench-execute-v4-served-model-sanity-new-in-v4 -->
Persona served-model correctness was a recent bug class, so V4 adds a sanity
check. The bench records the model the API actually returned as `routed_model`
and a boolean `expected_model_match` per test (`tests/benchmarks/bench/measure.py`);
the expected keys come from `tests/expected_models.py`
(`expected_model_keys`, `model_matches_expected`). Grep the results JSON for
persona-mode entries and confirm `expected_model_match` is not false where the
requested workspace's model_hint should have been served.

Because `model_pin` is applied by the pipeline only when the request model is a
persona slug (not in bench persona mode), pin-serving correctness is verified
by `scripts/persona_intent_audit.py` (Check 2/3/5) and by
`scripts/routing_regression.py --assert-baseline`.

## Why

Served-model bugs were invisible to TPS alone: a persona can bench fine while
the pipeline silently serves its workspace's pool default instead of the
intended model. The bench therefore records `routed_model` and
`expected_model_match` so a mismatch is visible in the JSON, and the intent
audit plus the routing-regression baseline assert the full
`(base, variant, served_model)` tuple against a versioned corpus — the two
checks cover the paths the bench's own request shape cannot reach.
<!-- /WIKI:GENERATED -->

---

## Results + dashboard

<!-- WIKI:GENERATED unit=unit-portal5-bench-execute-v4-results-dashboard -->
1. Confirm the run completed the planned test count (allow documented skips).
2. Update `config/grafana/dashboards/portal5_benchmarks.json` from the results
   JSON via the updater:
   ```bash
   python3 scripts/update_grafana_benchmarks.py --input tests/benchmarks/results/<file>.json
   ```
3. Commit:
   ```bash
   git add tests/benchmarks/results/<file>.json config/grafana/dashboards/portal5_benchmarks.json
   git commit -m "bench(tps): run <date> — <N> tests, <notable findings>"
   ```

## Why

`scripts/update_grafana_benchmarks.py` reads a bench_tps results JSON and
rewrites `config/grafana/dashboards/portal5_benchmarks.json` (its
`DASHBOARD_PATH` constant), rendering the direct/pipeline/persona tables from
the JSON's `avg_tps` fields. The updater and the results file must be committed
together so the dashboard and its source stay in sync; results live under
`tests/benchmarks/results/` per `RESULTS_DIR` in
`tests/benchmarks/bench/config.py`. Confirming the count first prevents a
partial run from being blessed as a baseline.
<!-- /WIKI:GENERATED -->

---

## Failure playbook

<!-- WIKI:GENERATED unit=unit-portal5-bench-execute-v4-failure-playbook -->
- **A model won't load / OOMs** — a very large quantized model plus a long
  context window can exceed unified memory. Skip it and note it; don't force.
- **Persona benches at pool-default TPS not its pin** — served-model
  regression; report it, don't patch it.
- **Pipeline mode much slower than direct for the same model** — expected
  routing overhead, but a large gap on a simple prompt may indicate a
  mis-route; cross-check with `python3 scripts/routing_regression.py
  --assert-baseline`.
- **Preflight retired-alias leak** — surface regression; halt.

## Why

Each failure branch maps to a distinct code surface so the operator knows what
is safe to work around and what is a product bug. OOM is workload-dependent
and skippable; served-model and mis-route issues come from the pipeline
handlers, so `scripts/routing_regression.py --assert-baseline` exists as a
deterministic gate on the resolved `(base, variant, served_model)` tuple. The
retired-alias leak is a hard stop because a non-canonical surface invalidates
every number the run would produce.
<!-- /WIKI:GENERATED -->

---

## Non-negotiables

<!-- WIKI:GENERATED unit=unit-portal5-bench-execute-v4-non-negotiables -->
- Preflight + `--dry-run` before every run; counts come from there, not this
  doc.
- `PORTAL_ENABLE_EVAL=1` for full coverage of the eval-module workspaces.
- Product code is read-only; bench failures that are product bugs get
  reported.
- Every run fresh; no prior-run assumptions.

## Why

These rules exist because the bench's inputs are config-driven and its results
are only trustworthy if the surface being tested is canonical and complete.
The preflight and `--dry-run` recompute scale from `config/portal.yaml` and
`config/backends.yaml` at run time, so trusting them instead of a doc prevents
stale-plan errors. `PORTAL_ENABLE_EVAL=1` mirrors the eval-module opt-in that
the pipeline enforces at boot, and the read-only rule keeps the bench a
measurement instrument rather than a place to patch routing bugs.
<!-- /WIKI:GENERATED -->

---
