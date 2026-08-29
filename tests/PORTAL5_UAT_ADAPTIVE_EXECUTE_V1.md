# PORTAL5_UAT_ADAPTIVE_EXECUTE_V1 — Claude Code Execution Prompt

> This is a **User Acceptance Test of Portal's capabilities**, run by you — an
> independent Claude Code agent — on the operator's behalf, exercising every
> OWUI-addressable workspace and persona through OWUI the way it is meant to be
> used, with deep multi-part challenges. It is the v9 acceptance gate before the
> repo is frozen and migrated to a clean-slate v9 repo, so the goal is holistic
> coverage of what Portal can actually do, not a keyword smoke test.
>
> **You are the independent author and first-pass judge.** Because you are not
> part of the Portal 5 fleet under test, this is a real external acceptance test
> rather than the system grading itself. You stand in for the operator: author
> each capability challenge, run it through OWUI, and propose a rubric
> assessment. The operator then accepts Portal capability by capability. You
> never set the acceptance `[GATE]`.

## What this is (and is not)

The static UAT (`portal5_uat_driver.py`, keyword-graded catalog) stays as the
fast regression layer. **Adaptive UAT sits above it**: deep, intended-use
challenges per space, run **through OWUI** on the exact same browser runner,
with full-response capture and per-challenge operator rubrics. Machine
assertions still run where they can (refusal posture, mandated output sections,
tool invocation, code delivery); everything else is judgment — first yours, then
the operator's.

Execution reuses the production OWUI path completely: `--adaptive` only swaps the
test catalog in `_select_tests`. Cascade ordering, model eviction, corpus
emission, and chat archival are unchanged.

## Step 1 — Author the challenges (you, independently)

Author challenges via worksheets so the author of record is you, not a fleet
model:

```bash
python3 tests/portal5_uat_adaptive.py --emit-worksheets
# writes tests/uat_adaptive/worksheets/<space>.json — one entry per challenge,
# each with an authoring_brief and an empty "prompt".
```

For each worksheet entry:

1. **Review design intent.** Read the `authoring_brief` and open the
   `design_refs` it lists (design docs / wiki units for that space). Confirm you
   understand what this workspace or persona was *designed to do*.
2. **Author the prompt.** Write ONE concrete, multi-sentence, intended-use
   request into `"prompt"` — name real artifacts, quantities, constraints — that
   exercises the space's core purpose for that dimension. For `continuity`
   entries, also set `"followup"`. Do not weaken a challenge to make it pass; if
   the intended use is demanding, the prompt should be demanding.
3. Leave `machine_assertions`, `rubric_id`, `dimension` as generated.

Then freeze:

```bash
python3 tests/portal5_uat_adaptive.py --ingest-worksheets
# validates every prompt is authored and freezes suites to tests/uat_adaptive/frozen/
```

(For non-sign-off dev runs only, the driver can auto-author with
`--adaptive-regenerate` (templates) or `--adaptive-author-model <slug>` (a local
model — NOT independent, not for sign-off).)

## Step 2 — Execute through OWUI (phased, sequential)

Sequential only — single-user M4 Pro. Run by module section so each model loads
once. Sections are `adaptive-<module>`. The run loads your frozen suites.

```bash
# Smoke one small space first, headed, to confirm OWUI drives correctly:
python3 tests/portal5_uat_driver.py --adaptive --adaptive-space auto --headed

# Then phase by module (--append accumulates across phases):
python3 tests/portal5_uat_driver.py --adaptive --section adaptive-general --append
python3 tests/portal5_uat_driver.py --adaptive --section adaptive-coding --append
python3 tests/portal5_uat_driver.py --adaptive --section adaptive-security --append
python3 tests/portal5_uat_driver.py --adaptive --section adaptive-research --append
python3 tests/portal5_uat_driver.py --adaptive --section adaptive-compliance --append
python3 tests/portal5_uat_driver.py --adaptive --section adaptive-cad --append
python3 tests/portal5_uat_driver.py --adaptive --section adaptive-documents --append
# media / image / video sections last (heaviest):
python3 tests/portal5_uat_driver.py --adaptive --section adaptive-media --append
python3 tests/portal5_uat_driver.py --adaptive --section adaptive-image --append
```

Run the same inter-phase memory/health gate the static UAT uses. Each challenge
writes a rubric-enriched row to `tests/uat_corpus/uat_<run>.jsonl` automatically.

`--adaptive` never touches the static keyword-UAT report (`tests/UAT_RESULTS.md`);
the driver's own row/summary writer is redirected to `tests/UAT_RESULTS_ADAPTIVE.md`
(machine-assertion view only). The operator scorecard is `tests/ADAPTIVE_UAT_RESULTS.md`,
built from the corpus by `--packet` in Step 4. Both are gitignored run artifacts.
`--append` accumulates the adaptive file across phases; a bare `--adaptive` run with
no `--section`/`--test` starts it fresh.

## Step 3 — Assess (you, first pass)

Read each captured response and propose a rubric assessment:

```bash
python3 tests/portal5_uat_adaptive.py --assess-pending > pending.json
# pending.json = [{test_id, space_id, dimension, prompt, response_text, chat_url,
#                  machine_status, rubric, auto_scores}, ...]
```

For each item, reason over whether the space did what it was designed to do,
then write `agent_verdicts.json`:

```json
[{"test_id": "...", "scores": {"correctness": 4, "depth": 5, "...": 3},
  "verdict": "PASS", "rationale": "one or two sentences on what it did/missed"}]
```

Score each rubric criterion 1-5, set PASS/PARTIAL/FAIL, and give a short honest
rationale. Then:

```bash
python3 tests/portal5_uat_adaptive.py --assess-apply agent_verdicts.json
```

## Step 4 — Operator review + capability acceptance

Build the packet (your proposals pre-filled, per-criterion, with rationale):

```bash
python3 tests/portal5_uat_adaptive.py --packet
# -> tests/uat_adaptive/review/review_<run>.html   (operator opens in a browser)
# -> tests/ADAPTIVE_UAT_RESULTS.md                 (capability-acceptance scorecard,
#                                                   then per-space evidence)
```

The results doc leads with a **capability acceptance** table (one row per Portal
capability area) so the operator accepts v9 capability by capability, with the
per-space challenges as the evidence beneath.

The operator confirms or overrides each verdict, clicks **Export verdicts JSON**,
and ingests:

```bash
python3 tests/portal5_uat_adaptive.py --ingest verdicts_<run>.json
```

## Step 5 — Exposure-gap finding

`--emit-worksheets` and the catalog exclude spaces with no OWUI exposure signal
and record them in `tests/uat_adaptive/designed_unreachable.json`; the rollup
surfaces them. Present this list to the operator: each is a designed space not
reachable in OWUI — before the clean-slate migration, decide per space to expose
it, retire it, or accept it as internal-only.

## Sign-off `[GATE]`

`[GATE]` The operator confirms every verdict (you proposed them), accepts Portal
capability by capability from the top table, resolves or accepts each
exposure-gap entry, then records the outcome at the bottom of
`ADAPTIVE_UAT_RESULTS.md`. Only then is v9 accepted for the clean-slate
migration. You never set this gate; PROMOTE_POLICY=confirm.

## Portability to the new repo

The whole subsystem is self-contained under `tests/uat/adaptive/` plus the
frozen suites. It moves to the v9 repo unchanged; re-emit worksheets there once
to re-anchor challenges against the new config source-of-truth.
