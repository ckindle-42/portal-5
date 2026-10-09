---
id: D-T4-MATURE
question: Does scripted cycle-one analyst closure reduce cycle-two concerns and benign false raises while preserving truth recall on identical telemetry?
stage: raised
why_not_binding: "The latest ledger has no measured binding stage: T1 and T2 have no reconciled paired workload, and T3 excluded all paired slices before product execution."
arms:
  - cycle_one
  - cycle_two_after_scripted_closure
metric: Concerns and false raises per 1,000 units in cycle two versus cycle one, with truth recall compared on identical telemetry.
adopt_if: At least 20 valid same-index routine-use/malicious pairs exist; cycle-one closures use actor `scripted:truth` and are labelled scripted everywhere; cycle two uses identical telemetry; all self-test and report validation gates pass; adopt only if the paired p < 0.05 and raised-stage p < 0.10 gates pass with truth recall unchanged and fewer cycle-two concerns and false raises. With fewer than 20 pairs resolve INCONCLUSIVE without running either cycle.
anti_goals:
  - Do not present the scripted analyst as a human or use analyst output as truth.
  - Do not invent truth labels, use engine output as truth, or relabel a near-miss.
  - Do not run an attack, chain, target tool, emulation, or other operation to create a pair.
status: PREREGISTERED
---
The cycle-one scripted actor is exactly `scripted:truth`, labelled as scripted in the records and report. The candidate cycle reuses the cycle-one telemetry byte-for-byte so only learned knowledge changes. A run is not eligible unless the same-index routine-use and answer-key pair gate reaches 20.
