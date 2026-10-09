---
id: D-T2-TRUTH-STRATIFICATION
question: Does finer index, sourcetype, and UTC-day stratification recover independently identifiable truth cells from the existing BOTS answer-key scenarios?
stage: window
why_not_binding: T1 excluded all three paired product slices, so no product stage was measured; this record evaluates scorer-plane truth coverage only.
arms: [coarse_entry_windows, index_sourcetype_day_cells]
metric: count of retained cells with every declared entity located in the named source and day, and every product event id reconciled to its source interval
adopt_if: retain the expanded stratification only if it yields at least one additional entity-complete cell, all cell intervals are UTC-day bounded and disjoint by event id, and the truth known-answer self-test and report validator pass
anti_goals:
  - do not add entities, sourcetypes, labels, or time ranges that are not supported by the published answer key and indexed telemetry
  - do not treat an answer-key entry as product-stage evidence or fit a threshold on these cells
  - do not use proxy windows or any target-facing operation
status: PREREGISTERED
---
The control is T1's whole-entry interval derivation. The candidate subdivides those same answer-key
scenarios by source and UTC day; it may increase usable truth units without changing the published
labels. T1 derived 7 of 27 whole entries and found 0 of 3 usable attack/benign index pairs.
