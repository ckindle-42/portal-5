---
id: D-T4-SUPPRESS
question: Does similarity-based suppression reduce benign cycle-two false raises without reducing recall of malicious cousins of benign-closed patterns?
stage: raised
why_not_binding: "The latest ledger has no measured binding stage: T1 and T2 have no reconciled paired workload, and T3 excluded all paired slices before product execution."
arms:
  - exact_only
  - never
  - similar_or_exact
metric: False raises per 1,000 benign units in cycle two and recall of malicious cousins of benign-closed patterns, compared by paired exact McNemar at workload B.
adopt_if: At least 20 valid same-index routine-use/malicious pairs exist; self-test and report validation pass; reject any arm whose malicious-cousin recall is below never at paired p < 0.10; among passing arms adopt the quietest only if the standard paired p < 0.05 and raised-stage p < 0.10 gates pass. With fewer than 20 pairs resolve INCONCLUSIVE without running any arm.
anti_goals:
  - Do not invent truth labels, use engine output as truth, or relabel a near-miss.
  - Do not run an attack, chain, target tool, emulation, or other operation to create a pair.
  - Do not tune thresholds, weights, cutoffs, or prompts against the result.
status: INCONCLUSIVE
report: reports/review_eval/4de03bca93e183d8/t4_pair_gate.json
result: "0/20 valid same-index pairs were available: the 24-hour-expanded answer-key intervals cover the indexed time in both retained BOTSv indexes, and all 12/12 benign benchmark cells are in portal5_lab, so no suppression arm ran."
---
The control suppresses only an exact benign anchor. The `never` arm suppresses nothing; the `similar_or_exact` arm also suppresses units similar to a benign anchor. Cycle two reuses identical recorded telemetry. The malicious-cousin gate protects against quieting a known malicious pattern merely because it resembles benign knowledge.
