# B1.4 — EG2+V3 reference distributions, clamp decision, re-derived thresholds

TASK_EG2_FOLLOWUPS_AND_BULLY_ENGINE_V1 B1.4, 2026-10-08. Its own commit, its own numbers.

## Measured reference distributions (EG2, `:8946/embed`, sentence-similarity, symmetric)

Deduplicated SPECIMEN_CORPUS_V3 parents (972), 64-text sample, `measure_distances`
(`eg2_v3_distributions.json`):

| band | p50 | p95 | retired harrier reference |
|---|---|---|---|
| self | 0.0 | 0.0 | 0.0 |
| near | 0.0448 | 0.1336 | 0.073 |
| far | 0.0905 | 0.1630 | 0.064 |

EG2+V3 sits at or above the retired harrier constants on every band: the upward-only clamp in
`derive_thresholds` never binds for the primary space (it shifts up, exactly as the derivation
intends). **Clamp decision: keep.** It stays as the anti-tuning guard for hypothetical tighter
future spaces — the evidence shows it is not hiding anything for EG2; dropping it would be a
policy change with no measured need.

## Identity composite under v2 weights (the same_max evidence)

100 real probes graded against their own indexed record on the seeded arm-d-sim projection
(`eg2_v3_identity_composites.json`): median 0.0387, p95 0.0497, max 0.0621. The offset over
pure embedder self-distance (0) is the truth-strip's context asymmetry — the probe's `family`
is stripped (`probe_signature`), the indexed record keeps it, so the context channel adds
~0.033 for every probe-vs-record pair. The frozen `same_max_distance` 0.05 failed 2/100 true
self-pairs (the fixture `test_all_p74_style_controls` failed the same way, composite 0.053–0.061).

## Adopted thresholds (cousin-v2 scale, `THRESHOLDS_VERSION bully-cousin-thresholds-v2`)

| threshold | old | new | evidence |
|---|---|---|---|
| same_max_distance | 0.05 | **0.063** | covers the measured identity maximum 0.0621 |
| similar_max_distance | 0.40 | 0.40 (frozen base) | band boundary is dominated by non-semantic channels; no measured case for moving it |
| new_max_distance | 0.85 | 0.85 (frozen base) | unchanged |

Effect on the adopted variant over the same 988 probes (paired, ranking untouched):
related_graded 241 → 241; SAME-band chosen pairs 61 → 65; the 4 movers flip
DISCOVERY → REGRESSION (SAME×MISSED) — the cost of the identity fix, recorded here.

`_INCUMBENT_*` reference constants re-pointed at the measured EG2+V3 values; the retired
harrier shape derives no downward shift (clamp) and inherits the frozen values (test added).

All six former `TRUTH_LEAK_XFAIL` SA2 fixture tests now run unmarked and pass
(1156 passed, 0 xfailed in tests/security/bully).
