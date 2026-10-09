---
id: D-T4-DEFENSE
question: Do bounded searches of the configured detection library improve defense-state agreement with published answer-key truth over a constant INDETERMINATE control?
stage: raised
why_not_binding: "The latest ledger has no measured binding stage: T1 and T2 have no reconciled paired workload, and T3 excluded all paired slices before product execution."
arms:
  - constant_indeterminate
  - searched_detections
metric: False COVERED rate, agreement with answer-key expected_signal truth, and exact binomial test against chance agreement on answer-key activity in recorded windows.
adopt_if: At least 20 valid same-index routine-use/malicious pairs exist; self-test and report validation pass; the searched arm has zero false COVERED results and agreement with answer-key truth exceeds chance at binomial p < 0.05. If no detection maps to an answer-key technique, resolve INCONCLUSIVE with the mapping gap; with fewer than 20 pairs resolve INCONCLUSIVE without running either arm.
anti_goals:
  - Do not treat health, rule presence, HTTP status, or query submission as COVERED evidence.
  - Do not use engine output to label truth or relabel a near-miss.
  - Do not execute an attack, chain, target tool, emulation, or host operation.
status: PREREGISTERED
---
The searched arm runs only the already-configured SPL detections as bounded, read-only searches over recorded answer-key windows and entities. Expected detections come from the library's `expected_signal` field; returned rows must overlap the concern events to count as COVERED. No default state is promoted to COVERED.
