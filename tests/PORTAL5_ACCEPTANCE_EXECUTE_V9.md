# PORTAL5_ACCEPTANCE_EXECUTE_V9 — Claude Code Prompt

The current acceptance entry point is `tests/portal5_acceptance_v6.py`, a thin
script that re-exports the routing signal dicts and delegates to
`acceptance.cli.main`; confirm it is still the newest runner by listing the
`portal5_acceptance_*` shims under `tests/` before running.

Two changes mark the current surface. First, the retired standalone security
workspace ids no longer exist as workspace ids: S6 tests the `auto-security`
workspace with variant awareness, and `scripts/execute_preflight.py` maintains
the `RETIRED_ALIASES` guard list that fails the run if such an id reappears.
Second, routing integrity is now assertable: `scripts/routing_regression.py
--assert-baseline` checks the served-model tuple against
`tests/routing/baseline.json`, and the `model_pin` persona field is enumerated
by the preflight so S10 can verify the served model. S3 and S21 perform
expected-model matching per request through `tests/expected_models.py`.

Bench workspaces are out of acceptance scope by design: `s03_routing.py`
excludes `bench-*` ids, the runner registers no bench sections in
`ALL_SECTIONS`, and full-catalog routing plus TPS measurement belongs to
`tests/benchmarks/bench_tps.py`. The acceptance suite is not a benchmark and
asserts no TPS or performance figures. Scale is config-driven — run the
preflight and read the live numbers rather than trusting a figure written into
a document.

## Why

This unit exists to stop an operator from running the acceptance suite against
stale assumptions: the old execution doc baked a workspace count and referenced
retired security ids, both already wrong at the codebase state the doc
described. The corrected surface derives everything from the preflight and the
section code, so the suite's target is whatever `config/portal.yaml` says today,
and the retired-id guard turns a regression back into an immediate failure.

---

## Your Role

The acceptance operator acts as the execution agent for the suite: launch the
section runner against a live stack, watch the live progress log for stalls,
diagnose failures using the recorded detail and evidence, retry sections
intelligently, and produce a pass/fail report. Each check is recorded through
`record` in `tests/lib/results.py` into the in-memory `_log` with a section, id,
name, status, detail, and duration, and the CLI prints a summary plus a routing
summary via `_print_routing_summary` from the accumulated routing log when the
run finishes.

The role explicitly does not modify product code: `portal/**` is treated as
read-only during acceptance. A regression found by a section is reported with
evidence — its FAIL or WARN row, the routing tuple when applicable, and the
relevant detail — rather than fixed in the moment or hidden by editing
expectations.

## Why

The separation between execution agent and product owner is what makes the
acceptance signal trustworthy. If the same agent could edit routing or
expectation code mid-run, every red result could be quietly turned green and
the suite would measure nothing. Recording a fixed schema of status, detail,
and evidence per check, and summarizing routing intent versus actual model,
gives the owner everything needed to reproduce a failure without changing
product code.

---

## Phase 0 — Preflight (required)

Before any run, verify the environment in order. First run
`scripts/execute_preflight.py`: it prints the live production, eval, and total
workspace counts plus the persona and MCP-fleet counts from `config/portal.yaml`
and must end with "OK to run". It exits non-zero and prints a STOP banner if a
retired alias has reappeared as a workspace id, via `check_no_retired_aliases`
in the same script.

Then confirm no suite instance is already running by grepping the process table
for the entry script `tests/portal5_acceptance_v6.py`. Finally probe the
pipeline: the unauthenticated `/health` endpoint on `localhost:9099`
(registered in `portal/platform/inference/router/app.py`) returns quickly and is
the liveness gate. `PORTAL_ENABLE_EVAL` must be unset so the eval/bench
workspace set stays out of the served catalog; if the preflight flags a
retired-alias leak, stop rather than proceeding.

## Why

Acceptance runs are long and expensive, so the cheap checks happen up front. A
retired-alias leak or a second concurrent run invalidates every result that
follows, and the pipeline health probe confirms the routing surface is actually
serving before the first request. Preflight is the difference between a wasted
multi-hour run and a clean one, which is why the script prints live counts
instead of trusting a number baked into a document.

---

## Autonomous Monitoring Loop — required default

The acceptance suite runs many Ollama-routed sections back to back against a
live stack, so a full run is long and the machine is unattended for extended
windows. The S10c compliance section is the most expensive phase: it drives
every compliance persona through every applicable scenario expanded from the
compliance fixture, issuing one pipeline chat request per scenario. Because a
run can stall silently on cold model loads, ComfyUI memory pressure, or an
Ollama crash, the operator must monitor rather than fire-and-forget.

After launching the suite, establish a scheduled wakeup loop that periodically:

- probes pipeline liveness via the unauthenticated `/health` endpoint on
  `localhost:9099` (registered in `portal/platform/inference/router/app.py`);
- tails the live progress log written by the runner at
  `/tmp/portal5_progress.log` — `_emit` in `tests/lib/results.py` appends one
  line per check carrying the section, id, name, detail, and running
  PASS/WARN/FAIL counts, so progress is observable without polling the stack;
- diagnoses a stall from the last recorded section and its detail before
  acting, then halts with evidence if the run is genuinely hung rather than
  merely slow.

## Why

An unattended acceptance run that hangs wastes hours and produces a useless
results file. The runner writes a live progress log and the pipeline exposes a
health endpoint precisely so an operator can distinguish a slow-but-alive run
from a wedged one, and can point at recorded evidence when stopping. Nothing in
the code stops a hung section for you, so the monitoring cadence is an operator
discipline the preflight and the progress log exist to support.

---

## Running

The runner entry point is `tests/portal5_acceptance_v6.py`, which is a thin
wrapper: it re-exports `WORKSPACE_PROMPTS` and the related signal dicts and
calls `acceptance.cli.main`, with all real behavior in
`tests/acceptance/{cli,runner,results,_common}.py`. Before launching, confirm no
newer runner exists by listing the `portal5_acceptance_*` shims under `tests/`.

Section selection is handled by the `--section` argument in
`tests/acceptance/cli.py` and by `_parse_sections` in
`tests/acceptance/runner.py`, which accepts a single id, a comma-separated list,
an inclusive numeric range such as `--section S0-S5`, or `ALL`. The
authoritative section list is the `s*` module set under `tests/acceptance/`,
each wrapped by a function in the runner's `ALL_SECTIONS` map. Key sections for
the current surface: S3/S3a routes the production catalog; S6 covers the
`auto-security` workspace and its variants; S10 and S10c exercise personas (S10
via Ollama chats with expected-model checks, S10c via the compliance fixture);
S17 covers CAD render; S21 exercises the LLM intent router; S23 checks model
diversity in the Ollama catalog.

## Why

The runner is deliberately a thin entry point so the section files stay the
authoritative catalog and the CLI stays stable across runner versions. Section
selection supports ids, comma lists, and ranges because operators frequently
re-run just the sections relevant to a change rather than the whole suite,
which takes a long wall-clock time. Confirming the newest runner up front
prevents executing an outdated suite.

---

## Coverage (current)

Section S3 (a wrapper that runs S3a) covers production-workspace routing. Its
catalog is the hand-maintained `PRODUCTION_WORKSPACES` list in
`tests/acceptance/s03_routing.py`, paired with the prompt-and-signal entries in
`WORKSPACE_PROMPTS` in `tests/acceptance/_common.py`. `WORKSPACE_PROMPTS` is a
static dictionary, not derived live from `WORKSPACES`; the runtime workspace id
set is loaded separately by `_load_workspaces`, which pulls ids from the
routing layer's `WORKSPACES` mapping. The authoritative production count is
printed by `scripts/execute_preflight.py`, which reads `config/portal.yaml` and
counts workspaces whose module is not the eval module.

Section S6 covers the `auto-security` workspace and its variants, each
exercised by sending a `variant` query parameter alongside the base workspace
call. Section S17 covers `auto-cad` through its S17-10 pipeline request. The
intent is that every production workspace has routing coverage across the
sections, so run the preflight list against the section coverage and report any
production workspace that no section exercises rather than silently accepting
the gap.

## Why

Workspace coverage exists to catch routing regressions on the production
catalog, so the section set must stay aligned with `config/portal.yaml` as the
workspace list evolves. Baked counts drift exactly the way the acceptance doc's
older workspace count did, which is why the preflight prints the live
production set and the operator reconciles section coverage against it instead
of trusting a number written into prose.

---

## New in V9 — routing + served-model verification

Routing integrity is verified in two layers. Before the suite, run
`scripts/routing_regression.py --assert-baseline`: it resolves the fixed corpus
in `tests/routing/corpus.json` through the keyword routing layer and asserts
the full `(base, variant, served_model)` tuple per prompt against
`tests/routing/baseline.json`, exiting non-zero on any drift. A failure means
routing has moved from its proven baseline — a product regression to report,
not to mask by adjusting acceptance expectations.

During S10, `s10_personas_ollama.py` passes each persona slug to
`_assert_routing`, which resolves the expected model through
`tests/expected_models.py` (`expected_model_keys_for_persona` via the runtime
`_PERSONA_MAP`) and compares it against the model the pipeline actually served.
`scripts/execute_preflight.py` enumerates the `model_pin` personas so the
operator knows which slugs must be served their pinned model. A persona that
resolves to the right workspace but is served the wrong model records a routing
mismatch and is flagged as a WARN — exactly the bug class the model-pin work
fixed, so a regression here is actionable.

## Why

Routing integrity was the source of a real production bug: a request could land
on the right workspace yet be served a model that is not the one its persona
pins, and id-only comparison would not catch it. The baseline gate and the S10
expected-model check therefore compare the served model, not just the
destination, so the suite fails loudly on the exact regression that previously
slipped through as a green routing result.

---

## Results + dashboard

After a run completes, the results file is written to the repository root as
`ACCEPTANCE_RESULTS.md` by `_write_results` in `tests/lib/results.py`, carrying
the date, git SHA, section list, runtime, summary counts, and one row per
check. To publish it, run `scripts/update_grafana_acceptance.py --input
ACCEPTANCE_RESULTS.md`. The explicit `--input` path matters because the script's
default (the `RESULTS_FILE` constant) points at a `tests/`-tree location for the
results file while the runner writes the file to the repo root. The
script parses the markdown table, rewrites the dashboard JSON at
`config/grafana/dashboards/portal5_acceptance.json`, and archives a JSONL
snapshot into `tests/acceptance_corpus/` for the run-trend panel.

Then stage and commit the results and the dashboard together, with a message
that records the run date, the section count, and the pass/total figures, so
the commit history itself shows the outcome of each acceptance run.

## Why

The dashboard and the results file are the durable record of an acceptance run,
and keeping them in sync matters because the Grafana panels are rendered from
the markdown, not authored by hand. The corpus archive additionally preserves a
time series so a section's pass rate can be compared across runs. Wiring the
runner's output path and the updater's input path explicitly prevents the two
sides from silently pointing at different files.

---

## Failure playbook

The runner catches any exception a section module raises and records it as a
`{sec}-ERR` row with status FAIL; see the exception handler in `run_sections`
in `tests/acceptance/runner.py`. A NameError in such a row classifies as a
CODE-DEFECT via the error patterns in `tests/lib/results.py` and usually means
the checkout is stale — the section files were decomposed and import-clean — so
re-sync to HEAD before debugging further.

- **S6 asserts on a retired id** — you are on stale section files or a stale
  execution doc. `tests/acceptance/s06_security_workspaces.py` calls the
  `auto-security` workspace with `variant` query parameters; it does not assert
  the retired standalone security ids.
- **Routing-baseline assertion fails** — `scripts/routing_regression.py
  --assert-baseline` hard-fails on drift; that is a product routing regression
  to report, never to mask by loosening acceptance expectations.
- **A production workspace has no covering section** — a coverage gap to
  report, not an invitation to write tests into protected product code.
- **A persona is served the wrong model** — a served-model regression; report
  the persona slug, the expected pin, and the actual served model together.

## Why

Every failure mode here has a deliberate response because the suite's value is
a truthful pass/fail signal, not a green wall. Stale-checkout and stale-doc
failures are self-inflicted and cheap to rule out, while routing and
served-model failures are product regressions that loosening acceptance
expectations would hide. The classification in `tests/lib/results.py` and the
hard-fail behavior in the regression script keep the suite honest about what it
protects.

---

## Non-negotiables

Run the preflight first: `scripts/execute_preflight.py` prints the live
production workspace count from `config/portal.yaml` and the persona catalog
size, so acceptance targets the current surface rather than a baked number.
`PORTAL_ENABLE_EVAL` must be unset for acceptance runs: when it is unset, the
eval module's workspaces are excluded by `get_workspace_dict` via
`_eval_enabled` in `portal/platform/inference/config.py`, and the runner's
`ALL_SECTIONS` registers no bench sections, keeping the suite on production
workspaces.

Product code under `portal/` is read-only during acceptance: a regression is
reported with evidence, never hidden by loosening acceptance expectations. The
routing-baseline check and the served-model checks are pass/fail signal, not
advisory — a baseline drift in `scripts/routing_regression.py` or a served-model
mismatch in S10 is a failure to act on, per the mismatch-to-WARN handling in
`s10_personas_ollama.py`.

## Why

These rules keep the acceptance suite measuring the product instead of
defending it. A config-driven preflight prevents tests from targeting a stale
catalog after a collapse or expansion; keeping eval workspaces and bench
sections out bounds the run to what production actually serves; and refusing to
loosen expectations means a routing regression surfaces immediately rather than
as silent drift behind green results.

---
