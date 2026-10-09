# F1 — cousin-v2 at unit mass (review follow-up to TASK_EG2_FOLLOWUPS_AND_BULLY_ENGINE_V1 B1)

2026-10-09. Same corpus (SPECIMEN_CORPUS_V3 final, 988 blind probes), same seeded arm-d-sim
projection, same one-retrieval-pass-per-probe design as `20261008T195439Z`. Harness fix first:
`base` now pins the cousin-v1 weights and re-implements the v1 action-sequence channel (after
1ee68f4b it silently read the engine's v2 `_WEIGHTS` and values-first `_decompose`). Both
reproduce exactly: base 154 related / 1 cross-source, adopted v2 241 / 16.

## Why

v2's weights sum to 1.15. `confidence` = present weight mass, documented in [0, 1]; the 0.6
classification gate was 15% looser than designed, and v2's "0 ANOMALOUS" rested on it.

## Unit-mass arms (paired exact McNemar vs adopted v2 `values_fallback_mass_preserving`)

| variant | related (graded) | cross-source | ANOMALOUS | vs v2 related | vs v2 cross |
|---|---|---|---|---|---|
| v2 adopted (mass 1.15) | 241 | 16 | 0 | — | — |
| **f1_v2_unit_scaled (v2 / 1.15) — ADOPTED as cousin-v3** | 240 | 16 | 90 | 1/0, p=1.0 | 0/0, p=1.0 |
| f1_unit_35_35_10_05 | 240 | 17 | 88 | 2/1, p=1.0 | 0/1, p=1.0 |
| f1_unit_35_35_05_10 | 240 | 16 | 109 | 9/8, p=1.0 | 0/0, p=1.0 |
| f1_unit_375_375_05_05 | 246 | 23 | 110 | 9/14, p=0.40 | 0/7, p=0.016 |

## Decision

Adopt v2 / 1.15 (cousin-v3): ranking is identical to v2 by construction (every composite scales
by 1/1.15), so the B1 ranking evidence carries over unchanged. In this blind lane, attack is always
truth-stripped; the 90 newly-ANOMALOUS probes are the ones whose chosen pair also lacks semantic
(present mass (0.40+0.10+0.10)/1.15 = 0.52). Under v2 they passed the gate at exactly 0.60 and
got SIMILAR/NEW claims, and 89 of 90 were not truth-related — abstention is the correct answer.
In production (attack present) the same pair carries 0.65 and stays classifiable.

`f1_unit_375_375_05_05` is better on cross-source (7/0, p=0.016), but it was chosen post hoc from
four arms (Bonferroni ~0.06), it changes the SAME-band share (100 vs 64) under thresholds fitted
on another weighting, and it would need its own B1.4 threshold re-fit. Recorded as a candidate,
not adopted.

Thresholds: composites are linear in the weights, so same_max rescales 0.063 -> 0.055 (measured
identity max 0.0621 / 1.15 = 0.0540); `THRESHOLDS_VERSION` -> v3, `ALGORITHM_VERSION` -> cousin-v3.
