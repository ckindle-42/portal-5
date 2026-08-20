# BULLY_UNKNOWN_COUSIN_RUN_M3_V1

> **Errata (2026-08-20, `TASK_BULLY_LOOP_REINTEGRATION_V1`):** beyond the
> single-schema intake gap noted below, this run's grader was ALSO never wired
> into the orchestrator -- a standalone-script pattern that recurred through
> every subsequent pass until this task. The organ is now wired in via
> `bully/loop_grader.py`, matching level-first on the pyramid axis
> (`bully/pyramid.py`) instead of flat distance. See
> `docs/DESIGN_BULLY_LOOP_REINTEGRATION_V1.md` and the live successor run
> `docs/BULLY_LOOP_MILESTONE_RUN_R6_V1.md`.

> **Errata (2026-08-19, `TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1`):** this
> run's intake was single-schema and effectively blind on 4 of 5 real sources.
> `artifact_graph._ENTITY_FIELDS`/`_TIME_FIELDS`/`_ACTION_FIELDS` were hardcoded
> CloudTrail field names; every dataset in this eval was attack_data
> (Sysmon/osquery), so entities went empty, timestamps went unparsed, and every
> action mapped to `other` on non-CloudTrail records. The `unknown_cousin_recall
> 0.973` headline below looked healthy because every published concern brief
> shares exactly one shape feature (`class_present=other`) and "resembles" an
> anchor only because both sides degraded to the same blindness -- see
> `docs/DESIGN_BULLY_UNIVERSAL_INTAKE_V1.md` (RC1) for the forensic proof. This
> run's benign-control failure (1.0) was **also misdiagnosed** below as evidence
> the invictus environment is compromised; RC3 in the same design doc proves the
> baseline's remarkability had a content-independent floor from a fit/score
> level mismatch (fit L1/L2, score L4) -- perfectly clean data failed
> identically, so the "compromised environment" conclusion was wrong. The unit
> model (U.1), shape/vocabulary split (U.2), three-way grading (V.1), outcome
> space (V.2), and leave-one-family-out (T.4) methodology below are all correct
> and carry forward unchanged; they were fed by a broken intake. Corrected
> intake, honest baseline, and re-run: `docs/BULLY_UNIVERSAL_INTAKE_RUN_M6_V1.md`.
> This document stays in the repo as the honest record of what this pass
> actually measured.

M.3 verification run for `TASK_BULLY_UNKNOWN_COUSIN_V1`. COLD: no network,
no model calls, no training. Real local data throughout -- no synthetic
corpus was substituted anywhere a real one was available; where one was not
available, that is stated rather than hidden. Raw output:
`docs/BULLY_UNKNOWN_COUSIN_RUN_M3_V1.json`. Reproduce with
`uv run python3 scripts/bully_unknown_cousin_run.py`.

## Data

- **Type library / evaluation split (T.2):** 1,286 attack_data manifests
  with declared MITRE techniques, split 50/50 by dataset path
  (`unit_measurement.split_datasets`, seed 0) into 643 type-library datasets
  and 643 evaluation datasets. `assert_no_contamination` ran clean -- no
  evaluation dataset also contributed a type.
- **Type library:** 141 `attack_episode` anchors were actually buildable
  from the type-half datasets (many real event files did not parse into a
  connected `L4_WINDOW` unit from the first 200 sampled records -- the same
  sparsity that drives the coverage-gap number below).
- **Normal baseline (N.2):** fit from 2,265 `L1_ARTIFACT`/`L2_ENTITY` units
  drawn from 44 of 55 CloudTrail export files in the
  `invictus_ir_aws_dataset` corpus; the remaining 11 files were held out,
  untouched by `fit`, and used only as the T.4 benign control.
  **This corpus is a real incident-response case study, not clean
  traffic** -- it contains genuine `stratus-red-team`-simulated intrusion
  activity throughout. That is the honest normal-baseline source available
  locally; see the benign-control result below for what it costs.

## M.1 -- falsification instrument: VALID

Ladder built from real verbs harvested from the actual type library
(grouped by classified action class, not hand-picked per rung):

| rung | level | combined distance | relation |
|---|---|---|---|
| L0_IDENTITY | 0 | 0.125 | EXACT |
| L1_SUBSTITUTION | 1 | 0.300 | EXACT |
| L2_REORDERED | 2 | 0.411 | SIMILAR |
| L3_CROSS_VOCABULARY | 3 | 0.500 | EXACT |
| L4_UNRELATED | 4 | 1.000 | NOT_AT_ALL |

`rho = 0.9999...` (>= 0.9 floor), shuffled-label control averaged
`0.404` over 50 trials (well below the true rho), negative control holds
(L4 is the farthest rung). **Verdict: VALID.**

**Individually-normal combination case:** a 6-step real escalation chain
(`AssumeRole -> GetSessionToken -> AttachUserPolicy -> PutBucketPolicy ->
DeleteBucket -> PutObject`) against a baseline that has separately seen
every one of those six verbs individually. Every `L1_ARTIFACT` unit graded
`NORMAL`; the `L4_WINDOW` combination graded `NOVEL` -- a concern. **This is
the flagship capability this task exists to create, and it holds.**

## T.4 -- leave-one-family-out: the headline number

- **`unknown_cousin_recall = 0.973`** (108/111 held-out malicious eval
  units across 45 held-out technique families raised a concern with their
  own family's types excluded from the library).
- **`full_library_recall = 0.991`** -- close to the leave-one-out number.
  `matcher_warning: false`: full-library is *not* dramatically higher than
  leave-one-out, so this run does not show the "matcher wearing a cousin's
  clothes" pathology T.4 exists to catch.
- **Shuffled-label control: `0.937`.** This is the run's honest weak
  point: with 83 of 111 outcomes landing on `NOVEL` (see the distribution
  below), which never consults the type library at all, shuffling library
  content barely moves the aggregate recall -- the control mostly measures
  the baseline's novelty signal, not the type-matching signal it was
  designed to isolate. The ratio (0.937 / 0.973 ≈ 0.96) does not clearly
  demonstrate collapse the way the M.1 ladder's shuffle (0.40 / 1.00) does.
  **Reported plainly rather than smoothed:** at this outcome mix, T.4's
  shuffle control needs to be computed over the `COUSIN`/`UNKNOWN_SAME`
  subset specifically to isolate matching from novelty; that refinement is
  not yet implemented.
- **Benign control: `1.0` concern rate -- FAILS the `<= 0.3` bound.**
  Not a grading bug: the only local "benign" corpus available
  (`invictus_ir_aws_dataset`) is itself a compromised environment. This is
  residual risk "the baseline can be poisoned by an adversary present
  throughout the fitting window" (D.0) actually manifesting against real
  data, not a synthetic edge case.
- **`verdict: INVALID`** -- driven by the benign-control failure above.
  The `unknown_cousin_recall` number is still published as the headline,
  per the task's own instruction to publish plainly rather than withhold;
  its INVALID gate is the honest signal that this run's controls do not
  yet certify it.

## T.3 -- precision/recall (floor metric separated)

Over all 111 scored `L4_WINDOW` rows: precision `1.0`, recall `0.991`.
Outcome distribution: `NOVEL` 83, `UNKNOWN_SAME` 17, `COUSIN` 10, `NORMAL`
1. **`KNOWN_INSTANCE` count: 0** (floor metric, not computed as headline --
   the type library here is exclusively `attack_episode` anchors, which
   never resolve to `KNOWN_INSTANCE` by construction; a live deployment
   with `detection_coverage`/`confirmed_finding` anchors would populate
   this row).

## Confidence calibration

| confidence bucket | n | empirical accuracy |
|---|---|---|
| 20-30% | 7 | 1.00 |
| 30-40% | 1 | 1.00 |
| 40-50% | 2 | 1.00 |
| 50-60% | 9 | 1.00 |
| 60-70% | 1 | 1.00 |
| 70-80% | 10 | 1.00 |
| 90-100% | 80 | 1.00 |

Every bucket reads 1.0 empirical accuracy because T.1's `correct` is a
binary "raised a concern for a known-malicious arrival" check, and nearly
every arrival did. This calibration table is honest but not yet
discriminating -- it will only become informative once benign held-out
arrivals are included in the same scored population (today's benign
control feeds T.4 only, not T.3/calibration).

## Suppression evidence (L.1)

A synthetic repeat (real production code path, deliberately simple input
for a clean demonstration): first sighting of
`AssumeRole -> ListBuckets -> AttachUserPolicy` graded `NORMAL` (empty
library, unremarkable baseline); analyst closes it `BENIGN_CLOSE`, written
back as a `benign_pattern` anchor; the identical shape/vocabulary on a
second entity graded `RECOGNIZED_NORMAL` on its next sighting.
**`suppression_fired: true`.**

## Coverage gap

**`unconnected_artifact_rate = 0.827`** (532 of 643 evaluation datasets
produced no `L4_WINDOW` unit from their first 200 sampled records). This is
the honest bound on structural grouping over real, sparse attack_data
files: many datasets ship too few parseable events, or events that share no
entity/causal link within the 300s adjacency window, for the graph to
connect them into a combination-level unit at all. It is reported as a
limitation, not silently absorbed into `NORMAL`.

## Concern briefs (10 published, flagship first)

The flagship individually-normal-combination brief and 9 further real
concern briefs (from held-out `UNKNOWN_SAME`/`COUSIN`/`NOVEL` outcomes) are
published in full, per-row, in the JSON (`concern_briefs`) -- not
summarized only. Sample (flagship):

```json
{
  "outcome": "NOVEL",
  "level": "L4_WINDOW",
  "flagship_individually_unremarkable_combo": true,
  "remarkability": 0.9,
  "confidence": 0.9,
  "what_could_not_be_seen": ["shape", "vocabulary"]
}
```

## What this run does not certify

- T.4's `verdict` is `INVALID` (benign control failure, explained above) --
  the `unknown_cousin_recall` headline is real and published, but not yet
  backed by a passing control suite on this data.
- The shuffled-label control is diluted by `NOVEL`'s library-independence;
  a follow-up should compute it over the type-matching subset only.
- `KNOWN_INSTANCE` was never exercised (no `detection_coverage` /
  `confirmed_finding` anchors in this run's library).
- The normal baseline is fit from incident-response data, not clean
  traffic -- every number that depends on it inherits that assumption.

These are carried openly per D.0's residual risks, not smoothed into a
passing headline.
