# DESIGN_BULLY_TRUTH_ACCEPTANCE_V1

TASK_BULLY_TRUTH_ACCEPTANCE_V1 (Y). Every acceptance number becomes a join
against sealed truth; two grader defects that produced a 100% false-positive
run get fixed; the run is re-executed live. This note records what X.6
actually measured, the four defects with their code evidence, and why the
criterion that passed (`both_classes_notified`) could not have caught any of
it.

## What X.6 actually measured

X.6 (`docs/BULLY_ANALYST_LOOP_RUN_X6_V1.json`) carried
`implant_class_ground_truth` on every `per_row` entry -- sealed truth was in
the file the whole time. Cross-tabulated against what the grader said:

| ground truth | SAME | SIMILAR | ANOMALOUS_UNCLASSIFIED |
|---|---|---|---|
| **background** (cycle 1) | 161 | 139 | 0 |
| **background** (cycle 2) | 196 | 102 | 2 |

Every graded entity was `background`. Not one implant appeared in either
cycle. False-positive rate 100%, true-positive rate 0% -- and the grader
called 161 pieces of benign noise exact matches to known attack techniques.
`DIFFERENT` and `NEW` were zero in both cycles: out of 300 entity timelines
drawn from 2,000 records of mostly-benign live telemetry across 8 schemas,
not one graded as unrelated.

The run passed every acceptance criterion anyway.

## D1 -- acceptance compared the system against itself

`both_classes_notified` (`scripts/bully_analyst_loop_run.py`) checked that
the grader's own labels (`concern_class` derived from `relationship`) split
into `known_bad` and `unknown_cousin`. That is satisfiable by a run that
detects nothing, because it never consults `implant_class_ground_truth` --
the column sat in the same `per_row` dict, unread by any check. Splitting
background into "SAME" and "SIMILAR" buckets satisfies the criterion exactly
as well as splitting real detections would. This is the un-falsifiable
metric reflex, reproduced inside a criterion written to prevent it.

## D2 -- selection excluded every implant

`hec_ship` reported 182 implant events shipped across 20 sources,
`all_ok: true`. Zero were graded, because
`correlation.assemble_timelines` sorted richest-first:

```python
timelines.sort(key=lambda t: (t.n_sources, len(t.artifact_ids)), reverse=True)
```

then the run took the top 300 of 1,584 resolved entities. A ~1% needle never
wins a richest-first sort against a sea of background entities with many
sources and long artifact lists. The R.6 addendum flagged exactly this and
proposed fingerprint-targeted selection; it was never implemented, and it
silently invalidated the whole run -- richest-first is the right default for
an operator's queue and the wrong sampler for a measurement run.

## D3 -- the grader matches noise

Reproduced against the shipped `series_cousin.decide_cousin`: a benign
14-step timeline that is 71% unrelated noise, but happens to contain a known
technique's classes somewhere in order, graded `COUSIN` at distance 0.317
with aligned spine `('auth', 'execute', 'execute')`. Gap penalty is only
`-0.5` and nothing penalised how much unmatched noise surrounds the match:
`salience_fraction` scored the alignment only against the KNOWN side, so any
sufficiently long benign timeline could "contain" a short technique. The
`distinct_aligned >= 2` gate was absolute, so `auth + 13x execute` cleared it
trivially (2 distinct classes, however diluted).

Fixed in Y.2 by requiring the alignment to explain the OBSERVED series
(`MIN_OBSERVED_COVERAGE`) and by making distinctness a ratio of the aligned
length, not an absolute count (`MIN_DISTINCT_RATIO`).

## D4 -- scripted verdicts poisoned the library

`scripted_verdicts` in X.6 shows `concern_class: known_bad -> CONFIRMED ->
anchor_outcome: ESCALATE -> tier: ANALYST_CONFIRMED` on entities whose
ground truth was `background`. Benign patterns were written into the anchor
library as analyst-confirmed malicious knowledge at the highest trust tier,
which is why cycle 2 matched MORE background as SAME (161 -> 196) while
SIMILAR fell (139 -> 102): the flywheel ran backwards, and
`noise_reduction: 0.0533` reported that as maturation. Fixed in Y.4 by
refusing (and reporting) any scripted verdict that contradicts sealed truth
before it reaches write-back, and by quarantining anchors X.6 already
poisoned.

Two supporting facts worth carrying: `r5a_generate` was
`{"plane": "skipped", "reason": "--dry-run-generate"}` -- the real-tooling
half never ran; and `conformance_self_check` PASSed with
`trust_axis_fed_nulls` as a WARN, so `candidate_state` was still `None` on
every record despite W.2.

## Why `both_classes_notified` is vacuous, and what replaces it

`both_classes_notified` asked "did the grader's own two label buckets both
fire at least once?" That question has no dependency on truth: it is
satisfiable by mislabelling 100% of background as `known_bad`/
`unknown_cousin` in any ratio that touches both buckets. It cannot fail on a
run that detects nothing, which is exactly the run it was supposed to catch.

It is replaced, not demoted, by `truth_acceptance.acceptance_report`
(Y.1): `detection_report` (TP/FP/FN joined to
`implant_class_ground_truth`, `INVALID` when zero implants were graded),
`selection_report` (did truth-bearing entities reach the grader at all), and
`poisoning_report` (did any verdict write knowledge that contradicts sealed
truth). All three read the sealed-truth column directly; none can pass by
comparing the system to its own output.

## Standing principles (adds Y)

- Y1 -- every acceptance number is a join against sealed truth.
- Y2 -- a run whose graded population contains no implants is INVALID, not a
  pass.
- Y3 -- selection must be truth-aware; an excluded-implant run fails on
  selection before anything else is read.
- Y4 -- an alignment must explain the OBSERVED series, not merely be
  findable inside it.
- Y5 -- no verdict may write knowledge that contradicts sealed truth in a
  test run.

See `docs/BULLY_TRUTH_ACCEPTANCE_RUN_Y6_V1.md` for the live re-run and
`portal/modules/security/core/bully/truth_acceptance.py` for the acceptance
module.
