---
id: D-T1-BASELINE
question: Does the new review pipeline recover more independently sourced truth than the legacy funnel at the same analyst workload, and where is truth lost?
stage: raised
arms: [legacy_funnel, review_d0]
metric: recall of truth items at the workload budget B (paired exact McNemar over truth items); false-raise per 1,000 benign units is reported alongside, never averaged with it
adopt_if: review_d0 is not significantly worse than legacy_funnel (two-sided exact McNemar p >= 0.10, or review_d0 ahead), its realized benign false-raise rate is within the calibrated alpha plus three binomial standard errors, and every known-answer self-test and report-validator gate passes; otherwise the pipeline is the finding, not the baseline
anti_goals:
  - tune no constant, weight, cutoff or prompt on this harness; review_d0 runs exactly as installed
  - modify no deprecated module; the legacy arm runs the old defaults as shipped
  - report nothing that did not pass the known-answer self-test for the same stamp
status: PREREGISTERED
---
Workload budget B: chosen on a validation split (disjoint from the test split by host and by day) as
the Youden point subject to a false-raise rate of at most 10 per 1,000 benign units. B is an
analyst-workload statement and is stamped with every report. The ledger (attribution) is part of
the report: its binding stage decides which experiments the next task may run.
