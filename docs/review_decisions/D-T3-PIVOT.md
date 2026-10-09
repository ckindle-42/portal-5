---
id: D-T3-PIVOT
question: Does one bounded pull pivot preserve reader truth recall while reducing concern latency versus three pivot rounds?
stage: raised
why_not_binding: "the reader is the workload lever: it moves the budget-limited frontier rather than one stage's loss"
arms:
  - max_rounds_3
  - max_rounds_1
metric: recall of truth items at workload B by paired exact McNemar, with pivot completeness, dropped claims, and p95 concern latency reported.
adopt_if: paired exact McNemar p < 0.05 in favour at B, no control-favouring regression at raised for p < 0.10, all known-answer and report-validator gates pass, every kept claim resolves, and measured R times p95 concern latency fits the window duration.
anti_goals:
  - tune no threshold, weight, cutoff, or prompt against the headline metric
  - run no attack, chain, target tool, or emulation operation
  - treat an incomplete or truncated pivot as a complete evidence set
status: INCONCLUSIVE
report: reports/review_eval/41eaed5720a9844f/t3_prerequisites.json
result: T1 had 0/3 eligible paired slices and no workload B, while per-concern p95 latency and window duration are unavailable, so no pivot arm ran.
---
The control permits three pull pivots per concern; the candidate permits one. Both use the same reasoning-capable single reader, alpha_open, truth slices, and workload B. No pivot arm runs without those shared inputs.
