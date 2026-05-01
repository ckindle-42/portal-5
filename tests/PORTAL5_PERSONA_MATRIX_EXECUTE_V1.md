# PORTAL5_PERSONA_MATRIX_EXECUTE_V1 — Claude Code Execution Prompt

Clone `https://github.com/ckindle-42/portal-5/`. The live system is already
running. `tests/portal5_persona_matrix.py` is implemented and stable.

The persona matrix is a per-(persona, model) coverage sweep. For each
registered workspace, every model in the workspace's full routing chain
is exercised against every applicable scenario from the workspace's
fixture. Behavioral assertions (not signal-string matching) determine
pass/warn/fail per cell. Output is a JSON matrix plus a console summary.

This is V1. Companion to:
- `PORTAL5_ACCEPTANCE_EXECUTE_V6.md` (pipeline-routed acceptance)
- `PORTAL5_UAT_EXECUTE_V2.md` (OWUI-visible conversations)

---

## Your Role

You are the **persona matrix execution agent**. You do not modify the
driver, the fixture, the assertion library, or the personas themselves.
You run sweeps, monitor, diagnose regressions, and produce a clean
result JSON plus a regression triage report.

**The matrix tests methodology, not memorization.** Models that fail
behavioral assertions are not necessarily "bad" — they may be excellent
at the underlying task but produce output in a shape the persona's
methodology doesn't permit. Your job is to diagnose whether a regression
indicates: (a) genuine model degradation, (b) persona-prompt drift,
(c) assertion-library tuning, or (d) Ollama digest update.

**Sequential only.** Single-user M4 Mac. The matrix loads one model
per cell; never parallel. The driver enforces this — do not attempt
concurrent runs.

**Direct-backend.** The matrix bypasses the pipeline at `:9099`. It
posts to Ollama (`:11434/v1/chat/completions`) and MLX (`:8081/v1/chat/completions`)
directly with `model: <id>` pinned. Pipeline state — workspace routing
descriptors, intent classifier, admission control — does not affect
matrix outcomes. This is by design: the matrix isolates model behavior
from pipeline behavior.

---

## What the Matrix Tests

For each `(persona, model)` cell, the matrix runs every applicable scenario
from the workspace's fixture and records assertion outcomes:

```
                       deepseek-r1  gpt-oss  dolphin  granite4.1:30b  Qwopus  ...
complianceanalyst        P12/W1/F0   P9/W2/F2   P5/W4/F4   P12/W1/F0   ...
nerccipcompliance        ...
gdprdpoadvisor           ...
hipaaprivacyofficer      ...
```

`P/W/F` = PASS / WARN / FAIL counts of scenarios run against that cell.

Behavioral assertions (subset, by workspace):

**`auto-compliance`** (`tests/lib/compliance_assertions.py`):
- `structural.table_columns` — gap-analysis output produces the 6 mandated columns
- `classification.exact_token` — uses `Full / Partial / None / Ambiguous`
- `anti_fabrication.refusal_pattern` — refuses to invent verbatim requirement text
- `refuse_to_certify` — does not give binary "yes/no compliant"
- `insufficient_context.exact_phrase` — uses the mandated `Insufficient context — needed:` token
- `policy.modal_verbs` — uses SHALL/SHOULD/MAY, no aspirational hedges
- `citation.format[FRAMEWORK]` — produces a recognizable citation in the framework's standard shape

**`auto-coding`** (`tests/lib/coding_assertions.py`, after TASK 006):
- `structural.code_block_present`
- `structural.no_truncation_or_placeholders`
- `language.<python|javascript|html|rust|go|sql|bash>` — language fingerprint
- `constraint.<python_no_external|js_no_framework|html_single_file>`
- `behavioral.no_clarification_stall`

The fixture (`tests/fixtures/<workspace>_scenarios.yaml`) defines the
prompts and which assertions apply. Adding a scenario: one YAML row.
Adding a workspace: one entry in `WORKSPACE_REGISTRY` plus a fixture +
assertion library — see TASK 006 for the template.

---

## Phase 0 — Pre-flight (run once, ~3 min)

```bash
git clone https://github.com/ckindle-42/portal-5/ && cd portal-5
cat CLAUDE.md
cat docs/COMPLIANCE_FALLBACK_POLICY.md  # threshold policy
cat docs/PERSONA_MATRIX_CI.md           # CI / baseline lifecycle (if 007 landed)

# Driver present and parses
test -f tests/portal5_persona_matrix.py || exit 1
python3 -m py_compile tests/portal5_persona_matrix.py
python3 tests/portal5_persona_matrix.py --help

# Stack health (matrix bypasses the pipeline but still needs backends)
curl -sf http://localhost:11434/api/version > /dev/null && echo "Ollama OK"
curl -sf http://localhost:8081/health | python3 -m json.tool

# Plan a dry-run for each registered workspace
python3 tests/portal5_persona_matrix.py --workspace auto-compliance --dry-run
# After 006:
python3 tests/portal5_persona_matrix.py --workspace auto-coding --dry-run

# Identify which baseline JSONs already exist
ls -la tests/benchmarks/results/persona_matrix_baseline_*.json 2>/dev/null
```

If a workspace has no baseline JSON yet, you are establishing the first
one (see Phase 1 below). If baselines exist, you are producing a sweep
to compare against.

---

## Phase Plan — when to run which sweep

The matrix has three operational modes. Choose based on why you're running:

### Mode A — First baseline establishment

Run the FIRST sweep for a workspace. Inspect results manually. Decide
whether the numbers represent acceptable behavior. Commit the result as
the canonical baseline.

```bash
WS="auto-compliance"
python3 tests/portal5_persona_matrix.py \
    --workspace "$WS" \
    --backend ollama \
    --output "tests/benchmarks/results/persona_matrix_baseline_${WS}.json"
```

**Time budget**: 15–45 min for Ollama-only depending on chain size.
Add 30–90 min for an MLX sweep on top.

After the run completes, inspect:

```bash
python3 -c "
import json
r = json.load(open('tests/benchmarks/results/persona_matrix_baseline_auto-compliance.json'))
for c in r['cells']:
    s = c['summary']
    total = s['PASS'] + s['WARN'] + s['FAIL']
    pct = 100*s['PASS']/total if total else 0
    print(f'{c[\"persona\"]:30} {c[\"model\"]:50} {pct:5.1f}% PASS  FAIL={s[\"FAIL\"]}')
"
```

Apply the threshold policy from `docs/COMPLIANCE_FALLBACK_POLICY.md`:
- &ge;80% MUST-pass &rarr; keep current routing position
- 60&ndash;80% &rarr; demote within group, re-evaluate in 90 days
- <60% OR any fabrication failure &rarr; remove from compliance routing groups

If the baseline is acceptable, commit:

```bash
git add tests/benchmarks/results/persona_matrix_baseline_${WS}.json
git commit -m "test(matrix): establish $WS baseline — $(date -u +%Y-%m-%d)"
```

If the baseline reveals an unacceptable model, **do NOT commit it as
baseline**. Instead, decide:
- (a) The model belongs out of the routing chain &rarr; edit `config/backends.yaml`
  to remove or demote, re-run the sweep, baseline the better state.
- (b) The persona prompt is over-constraining &rarr; file an issue against
  the persona, do not baseline yet.
- (c) The assertion is too strict &rarr; file an issue against
  `tests/lib/<workspace>_assertions.py`, do not baseline yet.

### Mode B — Drift check vs. existing baseline

Run a sweep and diff against the committed baseline. This is the
day-to-day operational mode.

```bash
WS="auto-compliance"
TS=$(date -u +%Y%m%dT%H%M%SZ)
python3 tests/portal5_persona_matrix.py \
    --workspace "$WS" \
    --backend ollama \
    --baseline-compare "tests/benchmarks/results/persona_matrix_baseline_${WS}.json" \
    --regression-threshold 10 \
    --output "tests/benchmarks/results/persona_matrix_${WS}_${TS}.json"
```

(`--baseline-compare` and `--regression-threshold` require TASK 007.)

Exit codes (per TASK 007):
- 0 = clean
- 1 = either FAIL cells OR regressions (not both)
- 2 = both FAIL cells AND regressions

For exit-code triage see "Diagnosing FAILs and Regressions" below.

### Mode C — Granite-required guard

Use when the routing-chain composition matters. Fails immediately if a
required model is missing from the chain (e.g., someone removed
`granite4.1:30b` from `ollama-reasoning` in `backends.yaml`).

```bash
python3 tests/portal5_persona_matrix.py \
    --workspace auto-compliance \
    --backend ollama \
    --require granite4.1:8b,granite4.1:30b \
    --output /tmp/matrix_granite_required.json
```

Exit code 3 = required model missing. The driver does not run scenarios
in that case — fix the chain composition first.

---

## Phase 1 — Sweep execution (any mode)

The driver prints progress as it runs. Sample output shape:

```
=== PERSONA MATRIX SWEEP — workspace=auto-compliance ===
  personas:  7  (cippolicywriter, complianceanalyst, gdprdpoadvisor, ...)
  models:    9  (smallest-first)
  scenarios: 252
  cells:     63

  [1/9] model: ollama/hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF  (1.0GB)
    [1/7] cippolicywriter                       PASS=18 WARN=2 FAIL=2 ERR=0  (124.1s)
    [2/7] complianceanalyst                     PASS=22 WARN=0 FAIL=2 ERR=0  (138.9s)
    ...
  [2/9] model: ollama/granite4.1:8b  (5.5GB)
    [1/7] cippolicywriter                       PASS=21 WARN=1 FAIL=0 ERR=0  (89.4s)
    ...
```

Monitor for:

- **ERR > 0 on every cell for a model**: the model isn't loading or
  responding. Check Ollama: `curl -s http://localhost:11434/api/ps`.
  If the model isn't listed and pull was skipped, run `ollama pull <id>`.
- **Sudden swing in PASS rate between models**: expected for diverse
  models, but `>30%` swing within the same group warrants inspection
  (model variants in the same group should have similar methodology
  adherence).
- **Sweep completes faster than expected**: usually means many cells
  errored out. Inspect the JSON for `summary.ERROR > 0`.
- **Sweep completes much slower than expected**: an MLX cold-load may
  have hit during an Ollama-only run (impossible if `--backend ollama`
  was set; if not, MLX intervention can stretch each cell by 30–180s).

When the sweep completes, the driver prints the matrix table and writes
the JSON. If `--baseline-compare` was set, regressions print to stderr
between the matrix table and the exit.

---

## Phase 2 — MLX sweep (separate from Ollama sweep)

MLX cold-loads are expensive. Run MLX sweeps separately, ideally
overnight or unattended.

```bash
WS="auto-compliance"
TS=$(date -u +%Y%m%dT%H%M%SZ)

# Use --mlx-warmup so per-cell elapsed_s excludes cold-load time
# (TASK 007). Skips models that fail to warm within timeout.
python3 tests/portal5_persona_matrix.py \
    --workspace "$WS" \
    --backend mlx \
    --mlx-warmup \
    --output "tests/benchmarks/results/persona_matrix_${WS}_mlx_${TS}.json"
```

Big-model handling:

```bash
# By default the driver SKIPS models flagged big_model: true in
# backends.yaml. To include them (Qwen3-Coder-Next-4bit ~46GB,
# Llama-3.3-70B-Instruct-4bit ~40GB, Qwen3-VL-32B-Instruct-8bit ~36GB):
python3 tests/portal5_persona_matrix.py \
    --workspace "$WS" \
    --backend mlx \
    --include-big-models \
    --mlx-warmup \
    --max-scenarios 3 \
    --output "tests/benchmarks/results/persona_matrix_${WS}_bigmodels_${TS}.json"
```

`--max-scenarios 3` keeps big-model sweeps tractable: each cold-load is
1–3 min, so 7 personas × 3 big models × 8 scenarios per persona = ~12
hours uncapped. With `--max-scenarios 3` you get a representative
sample in 1–2 hours.

Big-model coverage is **not part of routine baselines**. Run it pre-
release or quarterly.

---

## Diagnosing FAILs and Regressions

When a cell shows FAIL, inspect:

```bash
python3 -c "
import json
r = json.load(open('tests/benchmarks/results/persona_matrix_auto-compliance_<TS>.json'))
for c in r['cells']:
    if c['summary']['FAIL'] > 0:
        print(f\"\\n=== {c['persona']} on {c['backend']}/{c['model']} ===\")
        for sc in c['scenarios']:
            if sc['status'] == 'FAIL':
                print(f\"  scenario={sc['id']}[{sc.get('framework','')}]\")
                for r in sc.get('results', []):
                    if not r['passed']:
                        print(f\"    {r['severity']:6} {r['name']}: {r['detail']}\")
"
```

This prints, for every FAIL cell, which assertions tripped and why.

### Three diagnosis paths

**(1) Genuine model degradation.** Most common after Ollama re-pulls
that move the digest. Reproduce manually:

```bash
PERSONA=complianceanalyst
MODEL=granite4.1:30b

# Get the persona system prompt
SYSTEM=$(python3 -c "import yaml; d=yaml.safe_load(open(f'config/personas/{\"$PERSONA\"}.yaml')); print(d['system_prompt'])")

# Pick a failing scenario from the JSON inspection above
PROMPT="..."  # paste the scenario.prompt from the JSON

# Send manually
curl -s -X POST http://localhost:11434/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d "{
      \"model\": \"$MODEL\",
      \"messages\": [
        {\"role\":\"system\",\"content\":$(echo "$SYSTEM" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')},
        {\"role\":\"user\",\"content\":$(echo "$PROMPT" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')}
      ],
      \"max_tokens\": 700
    }" | python3 -m json.tool
```

If the model genuinely produced bad output (fabricated citation, wrong
classification token, certified compliance), apply the threshold
policy: keep / demote / remove from chain.

**(2) Persona-prompt drift.** Recent persona edit may have inadvertently
constrained the model. Check `git log -- config/personas/<slug>.yaml`
for recent changes. If a recent edit caused the regression, revert or
refine the persona — do NOT loosen the assertion to accommodate.

**(3) Assertion-library tuning.** The assertion regex may not handle a
legitimate variant the model produces. Inspect the assertion in
`tests/lib/<workspace>_assertions.py`, decide whether the model's
phrasing should pass, and if so, broaden the assertion. Re-run the
matrix to confirm the change resolved the FAIL without unrelated
regressions.

### Regression triage (Mode B output)

When `--baseline-compare` reports regressions:

```
--- REGRESSIONS vs baseline (threshold 10.0pp) ---
  REGRESSION  complianceanalyst             on ollama/granite4.1:30b               92.0% -> 78.0% (Delta -14.0pp)
```

For each regression line:
1. **Confirm via the JSON.** Inspect both baseline and current cell
   summary. The percentage delta should match.
2. **Check Ollama digest history** (if Ollama re-pulled recently):
   `ollama show <model>` shows the current digest.
3. **Apply diagnosis path 1, 2, or 3 above.**
4. **Decide**: re-baseline (if change is intentional and acceptable),
   demote/remove (if change is unacceptable per threshold policy), or
   tune assertion/persona (if root cause is methodology misalignment).

**Do NOT silently re-baseline a regression.** Each re-baseline is a
commit with a clear message explaining what changed.

---

## Diff against any prior run (TASK 007)

Beyond `--baseline-compare`, the standalone diff tool produces detailed
reports:

```bash
python3 tests/persona_matrix_diff.py \
    tests/benchmarks/results/persona_matrix_baseline_auto-compliance.json \
    tests/benchmarks/results/persona_matrix_auto-compliance_<NEW>.json \
    --threshold 10

# JSON output for tooling
python3 tests/persona_matrix_diff.py \
    tests/benchmarks/results/persona_matrix_baseline_auto-compliance.json \
    tests/benchmarks/results/persona_matrix_auto-compliance_<NEW>.json \
    --json > /tmp/diff.json
```

The text output sections:
- **Regressions**: PASS-rate dropped > threshold
- **Improvements**: PASS-rate rose > threshold (informational only)
- **New cells**: cells in NEW not in BASELINE (model added to chain)
- **Removed cells**: cells in BASELINE not in NEW (model removed)

Improvements never affect exit code. Treat them as "model got better"
or "Ollama re-pull included a fix" — interesting but not actionable.

---

## CI Integration (TASK 007)

If `.github/workflows/persona_matrix_nightly.yml` is in place, the
matrix runs nightly on a self-hosted runner. Manual operator runs are
still useful for:
- Pre-PR validation when a persona/fixture/assertion change is unsafe
  to roll out without local confirmation.
- Re-baselining after intentional changes (CI never auto-re-baselines).
- MLX sweeps (default CI runs Ollama-only).
- Big-model sweeps (CI excludes big_models by default).

Watch the GitHub Actions / equivalent CI for the workflow run status.
Failures post a diff summary in the job log; 30-day artifact retention
preserves the result JSON for inspection.

---

## When NOT to run the matrix

- **You're testing pipeline routing.** Use acceptance v6 instead — the
  matrix bypasses the pipeline.
- **You're testing OWUI-visible behavior.** Use UAT V2 — the matrix
  has no OWUI integration.
- **You're testing TPS.** Use `bench_tps.py` — the matrix only cares
  about behavioral pass/fail.
- **A backend is unhealthy.** The matrix will produce ERROR cells which
  obscure the actual signal. Fix the backend first.

---

## Resume Protocol

The matrix is not designed for partial resume — sweeps are short enough
(15–90 min) that a clean re-run on interruption is preferred. If a
sweep is interrupted:

```bash
# Just re-run the same command. The driver writes the result JSON only
# at completion, so there's no half-written file to clean up.
python3 tests/portal5_persona_matrix.py --workspace "$WS" ...
```

If the sweep is consistently failing partway through, narrow the scope
to bisect:

```bash
# By persona:
python3 tests/portal5_persona_matrix.py --persona complianceanalyst ...

# By model substring:
python3 tests/portal5_persona_matrix.py --model granite4.1 ...

# By scenario count:
python3 tests/portal5_persona_matrix.py --max-scenarios 1 ...

# All combined for fastest single-cell smoke:
python3 tests/portal5_persona_matrix.py \
    --workspace auto-compliance \
    --persona complianceanalyst \
    --model granite4.1:8b \
    --max-scenarios 1 \
    --output /tmp/single_cell.json
```

---

## Completion Checklist

After a successful matrix sweep:

- [ ] Result JSON exists at the expected path under
      `tests/benchmarks/results/`
- [ ] Matrix console table printed without error
- [ ] In Mode B: regression count is 0 (or each regression triaged
      and dispositioned per "Diagnosing FAILs and Regressions")
- [ ] In Mode A: baseline reviewed against threshold policy and
      either committed or held back pending fixes
- [ ] If routing change resulted from inspection: `backends.yaml`
      committed with the change, threshold doc updated
- [ ] No FAIL cell whose root cause is "I didn't investigate"

---

## Section Coverage Audit

```bash
# Verify the matrix understands the registered workspaces
python3 -c "
from tests.portal5_persona_matrix import WORKSPACE_REGISTRY
for ws, cfg in WORKSPACE_REGISTRY.items():
    print(f'  {ws:25}  fixtures={cfg[\"fixtures_module\"]}  threshold_doc={cfg[\"threshold_doc\"]}')
"

# Cross-check: every threshold_doc referenced exists
python3 -c "
import os
from tests.portal5_persona_matrix import WORKSPACE_REGISTRY
for ws, cfg in WORKSPACE_REGISTRY.items():
    doc = cfg['threshold_doc']
    if not os.path.isfile(doc):
        print(f'WARN: {ws} threshold doc missing: {doc}')
    else:
        print(f'OK:   {ws} → {doc}')
"
```

---

## Expected Agent Behavior

You are operating as a **Matrix Sweep Operator**.

Responsibilities:
- Pick the correct mode (A / B / C) for the operator's intent
- Run sweeps with appropriate `--backend`, `--workspace`, `--max-scenarios`,
  `--mlx-warmup` flags
- Triage every FAIL cell to a diagnosis path (1, 2, or 3)
- Triage every regression to a disposition (re-baseline, demote,
  remove, tune)
- Update `backends.yaml` only when threshold policy says so
- Commit baseline JSONs only after operator review
- Produce a clean run log with regression counts and dispositions

**The task is complete when**: the requested mode's sweep finished,
every non-clean cell has a documented disposition, and any chain or
prompt or assertion changes informed by the sweep have been committed
with clear messages.

---

*Last updated: 2026-04-30 (V1 — companion to TASK_PERSONA_MATRIX_004
through TASK_PERSONA_MATRIX_OPS_007)*
