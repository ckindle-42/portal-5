# PORTAL5_BENCH_SEC_EXECUTE_V3 — Security Bench Execution Prompt

Supersedes the V2 execute prompt, archived at
`docs/_archive_execdocs/PORTAL5_BENCH_SEC_EXECUTE_V2.md`. V3 reflects the
post-alias-retirement codebase: the pre-collapse security workspace ids
(`auto-redteam`, `auto-blueteam`, `auto-pentest`, `auto-purpleteam*`) are
retired, and security variants are addressed canonically as
`auto-security::<variant>`. `scripts/execute_preflight.py` enumerates the live
variant set from `config/portal.yaml` and fails loudly if any retired alias
leaks back into the workspace table.

The suite is `tests/benchmarks/bench_security.py`, a thin re-export shim whose
implementation lives under `portal/modules/security/core/`; the real entry
point is `python3 -m portal.modules.security.core` (`__main__.py` dispatches to
`cli.main`). It evaluates security workspaces on offensive/defensive prompts
(the tool-free theory pass) and, for the execution workspaces, on multi-turn
attack-chain tool-call sequences. This is capability measurement and is
distinct from `tests/benchmarks/bench_tps.py`, which measures throughput:
will the model engage offensive tasks, follow structured output, call tools in
order, and complete the chain?

## Why

The collapse folded nine discipline workspaces into one `auto-security` base
with config-driven variants, so every example command in the earlier prompt
was stale and a bare `auto-pentest` target would fail. Grounding the runbook to
`cli.py` and `scripts/execute_preflight.py` keeps the invocation aligned with
the code that actually executes the bench, instead of a snapshot from a dated
document.

---

---

## What changed in the security surface (read before running)

The collapse (commit a7d9dcc8) folded nine security workspaces into one
`auto-security` base with `variants:` blocks, and the alias shim that let old
ids keep working was removed. `scripts/execute_preflight.py` hard-codes the 23
retired aliases in `RETIRED_ALIASES` and its `check_no_retired_aliases` gate
fails the preflight if any leaks back into `config/portal.yaml`. The current
variant set — `redteam`, `redteam-deep`, `blueteam`, `purpleteam`,
`purpleteam-deep`, `purpleteam-exec`, `pentest`, `uncensored` — resolves to the
canonical `auto-security::<variant>` form.

The bench's internal vocabulary is already canonical: `_data.py`'s
`PER_WORKSPACE_TIMEOUT` and `EXECUTION_WORKSPACES` are keyed on the literal
`::` strings (the edcaa8b fix). Because `call_pipeline` forwards the workspace
string as the pipeline `model` field, a retired id such as `auto-pentest` is
not a registered workspace and the request fails rather than silently running;
use `auto-security::pentest`. The exact set of live variants is printed by the
preflight — use that list, not this table, since variants are config-driven.

## Why

The alias shim was removed deliberately so a stale runbook id fails loudly
instead of silently routing to a wrong workspace. Re-grounding to the
preflight's retired-alias list and to `_data.py`'s canonical keys makes the
"trust the preflight's live list" rule mechanically verifiable, because the
variant set is config-driven and the harness must never trust a table typed
from memory.

---

---

### 0a. Ground truth

Run `python3 scripts/execute_preflight.py` before every session.
`scripts/execute_preflight.py` reads `config/portal.yaml` at runtime, collects
every `variants:` sub-key of the `auto-security` workspace into a
`security_variants` list, and prints them under "Security canonical variants
(sec-bench --workspaces targets)". It returns exit 0 with the line "No retired
aliases present. Surface is canonical. OK to run." when `check_no_retired_aliases`
finds none of `RETIRED_ALIASES` in the workspace table, and exit 1 otherwise.
Use the printed list, verbatim, as the `--workspaces` targets for the security
bench. If a variant you expect is missing, confirm against `config/portal.yaml`
`workspaces.auto-security.variants` before assuming a bug — the variant set is
config-driven and the preflight is its ground truth.

## Why

The doc's table drifted because variants are defined in exactly one place —
`config/portal.yaml` — and echoed everywhere else. The preflight exists to
print reality at run time: workspace counts, the canonical variant list, the
model-pin personas, and any retired-alias leak, so an execute agent benches
against live config rather than a baked table that has already gone stale.

---

### 0b. Lab readiness gate — do not bench a cold or unreachable lab

`./launch.sh lab-up` starts the core lab stack (Incalmo C2 + Talon SOC
analyst) via `_launch_lab_up` in `scripts/lib/lab.sh`; `./launch.sh lab-up-wazuh`
adds the Wazuh/OpenSearch telemetry stack via `_launch_lab_up_wazuh` (requires
`LAB_OPENSEARCH_PASSWORD`), which blue-detection scoring needs. The readiness
gate itself is `python3 scripts/lab_ready.py` — note that `launch.sh` has no
`lab-ready` case, so the bare `./launch.sh lab-ready` form falls through to the
usage message. `scripts/lab_ready.py` runs its `CHECKS` table — attack image
present in DinD, image manifest hash matching `config/attack_image_contract.json`,
vulhub clone, challenge dirs, DC/SRV/WEB reachable from the attack container,
sufficient disk — and exits non-zero whenever a required check is RED. Do not
bench a cold or unreachable lab. See `docs/LAB_SETUP.md` for the cold-start
runbook.

## Why

A green gate is a precondition, not a courtesy: a cold lab produces zero
live-success signals across an entire multi-hour run with nothing telling the
operator why. The gate is a standalone script precisely so it can run from
automation and CI, and its required-versus-best-effort split keeps optional
telemetry from blocking an otherwise ready bench.

---

---

## Your Role

The execute agent's role is to run the security bench, not to build it.
Concretely: run `scripts/execute_preflight.py` and the lab readiness gate,
invoke `python3 -m portal.modules.security.core` with the flags the run
requires, diagnose failures against the code that produces them (the `cli.py`
flag definitions, `_data.py` timeout keys, `scoring.py` dimensions), retry
intelligently after correcting the invocation, and deliver the candidate
qualification report. Product code under `portal/` is read-only: a capability
failure that traces to a product bug is reported with evidence, not patched in
place. `candidate_eval.py`'s `PROMOTE_POLICY=confirm` enforces the same boundary
at the promotion step.

## Why

Splitting the executor from the implementer keeps the bench an honest
measurement instrument. If the same agent wrote the harness and then judged its
own candidates, a failing score could be "fixed" by editing the rubric; keeping
product code read-only forces capability problems to surface as findings, which
is exactly what a qualification run is supposed to produce.

---

## Autonomous Monitoring Loop — required default

Security chains are slow by construction: thinking models plus tool
round-trips, with `_data.py`'s `PER_WORKSPACE_TIMEOUT` capping per-workspace
requests at up to 1500 seconds for the `auto-security::redteam`,
`auto-security::purpleteam`, and `auto-security::purpleteam-deep` keys, and
`CHAIN_MODEL_TURN_TIMEOUT_S` aborting a single model turn at 300 seconds. A
full multi-variant run therefore spans hours. The execute agent should
establish a periodic monitoring loop after launch — the same wakeup pattern the
TPS and acceptance execute prompts use — checking liveness and progress roughly
every 20 to 30 minutes, skipping and noting a hung workspace, and halting with
evidence if the whole run has stalled. This is operator process guidance, not a
harness feature: nothing in the bench code schedules wakeups on the operator's
behalf.

## Why

Idle-timeout caps and per-turn aborts make the harness fail-safe, but they do
not tell a long unattended run to keep going or when to give up. The monitoring
loop is the human-in-the-loop complement to those mechanical timeouts,
converting a silent multi-hour stall into an observed, recorded decision instead
of burned compute.

---

---

## Running

The bench entry point is `python3 -m portal.modules.security.core`, which
dispatches through `portal/modules/security/core/__main__.py` into `cli.main`.
With no arguments it benches `DEFAULT_WORKSPACES` — the eight canonical
`auto-security::*` strings defined in `_data.py` — across every prompt in
`PROMPTS`, running the tool-free theory pass (prose rubric scoring via
`score_response`). The expensive passes are opt-in: `--exec-eval` enables the
tool-calling execution pass for the two `EXECUTION_WORKSPACES` entries,
`--exec-chain-models` adds the multi-model handoff chain, and `--lab-exec`
switches tool results from synthetic to real sandbox execution. `--dry-run`
prints the plan without calling the pipeline, and `--output` overrides the
default `results/sec_bench_<timestamp>.json` path.

## Why

The earlier prompt's "Running" section was an empty code block, so this unit
replaces it with the invocation that actually exists. The default is
deliberately broad (all workspaces across all prompts) while the slow and
lab-touching passes stay opt-in, so a quick dry-run and a full multi-hour live
campaign are both one command away without risking unintended live execution.

---

# Single variant on the prompt set

```bash
python3 -m portal.modules.security.core --workspaces auto-security::pentest
```

This benches a single variant across the full prompt set. The `pentest`
variant is defined under `config/portal.yaml`'s `auto-security.variants`, and
`auto-security::pentest` is one of the two `EXECUTION_WORKSPACES` in `_data.py`
(alongside `auto-security::purpleteam-exec`). With only `--workspaces` given,
this runs the theory pass — `tool_choice=none`, prose rubric scoring — for every
prompt; the tool-enabled execution pass requires adding `--exec-eval`, and
`--dry-run` prints the plan without hitting the pipeline.

## Why

A single-variant run is the cheapest way to smoke-test a new candidate model or
a changed prompt before committing hours to the full fleet. The variant still
resolves through the canonical `::` key, so routing, per-workspace timeouts, and
scoring all use the same vocabulary as a full multi-variant run.

---

# Several variants

```bash
python3 -m portal.modules.security.core --workspaces \
    auto-security::redteam auto-security::blueteam auto-security::purpleteam
```

This form benches three canonical variants — `redteam`, `blueteam`, and
`purpleteam` — each across the full prompt set. All three are defined as
`variants:` sub-blocks of `auto-security` in `config/portal.yaml`, so each
resolves to a distinct routed model configuration rather than the base
workspace. The `--workspaces` flag accepts any number of ids (nargs="+"),
defaults to `DEFAULT_WORKSPACES` when omitted, and `run_bench` cross-filters the
prompt categories: a blue-team workspace skips red-team prompts and vice versa.
Run with `--dry-run` first to confirm the resolved set before any live call.

## Why

Benching several variants in one invocation is the standard
candidate-comparison shape: identical prompts and scoring, only the served
model differs. The cross-category skip in `run_bench` matters because a blueteam
variant handed offensive prompts would score against the wrong rubric, so the
harness removes that mismatch deterministically before any model is called.

---

# Dry-run the full expanded plan first (each step no-ops if its module is absent)

```bash
python3 -m portal.modules.security.core --full-expanded --dry-run
```

`--full-expanded` (defined in `cli.py`) adds the security expansion steps on top
of the workspace bench: the named-oracle count, the CTF flag-oracle bench, the
OWASP LLM-redteam probes, the validation suite's Log4Shell
vulnerable-vs-hardened use-case, and a field-journal write. Each expansion step
wraps its module import in a try/except and prints "module absent — skipped"
when the module cannot be imported, so a partial install degrades gracefully.
`--dry-run` stops every step before live inference: workspace rows print
"DRY-RUN", the CTF and LLM-redteam steps short-circuit, and the journal write is
skipped. Note that `bench_integration.run_full_expanded_bench` is a separate
loader exercised by tests, not the code path `cli.py`'s flag invokes.

## Why

A full-expanded run is multi-hour and lab-touching, so dry-running first is the
only cheap way to confirm every step resolves before committing real time. The
per-step ImportError fallback is intentional: the suite must never crash on a
box that lacks one optional module, and it must say so explicitly when one is
missing.

---

# Full expanded with live lab execution (needs green lab-ready)

```bash
python3 -m portal.modules.security.core --full-expanded --lab-exec
```

This is the heavy full-suite run. `--full-expanded` adds the expansion steps
(oracles, CTF, LLM-redteam, validation, journal) to the default
`DEFAULT_WORKSPACES` bench; it does not by itself run tool-calling chains or
blue detection. The prompt-set theory pass always runs; the tool-enabled
execution pass for the two `EXECUTION_WORKSPACES` (`auto-security::pentest`,
`auto-security::purpleteam-exec`) needs `--exec-eval`; the multi-model
attack-chain sequencing needs `--exec-chain-models`; and blue-detection
correlation needs a blue model via `--blue-defender-model` or `--purple`.
`--lab-exec` switches tool results from synthetic to real MCP sandbox execution
and, when chain models are requested, triggers the mandatory
`verify_lab_targets_reachable` gate in `cli.py`, which aborts unless the DC/SRV
targets respond unless `--force-unreachable-lab` overrides deliberately. A green
`python3 scripts/lab_ready.py` is the standing precondition. Treat the earlier
doc's blanket phrasing as aspirational: the bench is flag-composed, not one
switch.

## Why

The original doc claimed `--full-expanded` alone executes chains, execution
workspaces, and blue correlation; re-grounding shows each of those is a separate
opt-in flag. Conflating them makes an operator believe a flag-composed suite is
monolithic, which either over-runs the lab or silently skips the passes they
intended to run.

---

## Served-model note (new in V3)

Persona-level model pins (`model_pin`) are consumed by the pipeline, not the
bench: `portal/platform/inference/router/handlers.py` Phase 4c applies a
persona's `model_pin` through `_resolve_model_override` (bounded to the
`config/backends.yaml` model catalog) so a persona is served the model its
identity claims. Because the bench forwards workspace strings as the pipeline
`model` field, a run that qualifies a *persona* rather than a bare workspace is
only meaningful when that persona is served its pinned model. `scripts/execute_preflight.py`
prints every persona with a `model_pin` (slug → pin) under its "model_pin
personas" header; cross-check any persona appearing in your run against that
live list before trusting its capability score. The currently pinned set is
coding/vision/reasoning personas (for example `glm_coder`, `gemma_vision`,
`magistralstrategist`); no security-specific persona currently carries a pin, so
the original doc's "two security-adjacent personas" phrasing is stale.

## Why

A security persona benched on the wrong model produces a capability number that
means nothing, so the pin check is not cosmetic. Re-grounding replaces the
doc's unverifiable "two security-adjacent personas" claim with the preflight's
live enumeration, which is the only ground truth that stays correct as pins move
between personas over time.

---

## Candidate qualification report

The qualification report summarizes the scored rows `run_bench` returns. Per
variant, the theory pass yields `score_response` metrics — `header_score`
(structured-output adherence to the prompt's `required_headers`), MITRE
coverage, and disclaimer penalties — and the execution pass yields
`score_execution` metrics: `step_coverage` and `proven_coverage` (chain
completion), `sequence_adherence` (tool-call ordering via longest increasing
subsequence), and `tool_diversity`. Chain runs add `chain_models_with_calls`
versus `chain_total_models` (engagement), handoff quality, and, under live
execution, `lab_success` plus blue `steps_detected` when telemetry is up. For
execution workspaces the report records whether the live-lab steps actually
executed and were detected. Promotion follows `PROMOTE_POLICY=confirm` (see
`candidate_eval.py`): the report recommends operator action and records a gate
clearance but never swaps fleet config automatically. Finally, the operator
commits the output JSON — default `results/sec_bench_<timestamp>.json` — and
any scoreboard update.

## Why

The report is the deliverable that turns raw JSON into a promotion decision,
and its rules exist to keep that decision conservative. Zero auto-promotion is
the load-bearing guarantee: a passing candidate is a recommendation and a
clearance record, so a bench artifact can never silently change which model the
fleet serves.

---

## Failure playbook

- `--workspaces auto-pentest` errors — `auto-pentest` is a retired alias (it is
  in `RETIRED_ALIASES` in `scripts/execute_preflight.py`) and is not registered
  in `config/portal.yaml`, so `call_pipeline` forwards it as the pipeline
  `model` and the request fails. Switch to `auto-security::pentest`.
- Variant resolves to base with no variant behavior — the `::` key must name a
  real `variants:` sub-block on `auto-security` in `config/portal.yaml`;
  `_resolve_workspace_variant` in the router only fabricates a synthetic
  workspace when the named variant is defined.
- Lab RED — resolve per `docs/LAB_SETUP.md` and re-run `scripts/lab_ready.py`;
  do not bench a cold lab.
- Chain times out — confirm `_data.py`'s `PER_WORKSPACE_TIMEOUT` has a literal
  `::`-keyed entry for the workspace (for example `auto-security::redteam`); a
  folded variant that lost its cap falls back to `REQUEST_TIMEOUT` and may be
  killed mid-chain. The edcaa8b fix keyed that dict on the literal `::` string
  precisely to stop this, so verify the key survived any later fold.

## Why

Each entry is a previously-hit failure with a specific mechanical cause. The
retired-alias and timeout entries both trace to one design decision: the
harness addresses variants by their literal `::` string, so aliases and
uncapped folds fail in ways that look like model faults but are vocabulary
faults. The playbook names the code that decides each outcome.

---

## Non-negotiables

- Run `scripts/execute_preflight.py` first and use its live `security_variants`
  list, never a baked table — the variant set is config-driven in
  `config/portal.yaml`.
- Address workspaces canonically as `auto-security::<variant>`; the
  pre-collapse aliases (`auto-redteam`, `auto-blueteam`, `auto-pentest`,
  `auto-purpleteam*`) are retired and the alias shim is gone, enforced by the
  `RETIRED_ALIASES` gate in the preflight.
- Confirm green `python3 scripts/lab_ready.py` before any `--lab-exec` run; the
  bench's own `verify_lab_targets_reachable` gate also aborts live chain runs on
  unreachable DC/SRV targets unless `--force-unreachable-lab` is passed.
- Product code under `portal/` is read-only for the execute agent, and promotion
  policy is `PROMOTE_POLICY=confirm` — zero auto-promotions; a passing candidate
  is a recommendation for operator action, never an automatic primary swap.

## Why

These four are the load-bearing rules the execution model rests on. Preflight
is the only current source of variant names, the canonical key is the only
vocabulary both harness and router accept, the lab gates exist because a cold
lab yields hours of meaningless zeros, and confirm-only promotion keeps a
benchmark artifact from ever editing fleet config on its own.

---
