# Defensive Bully `BASELINE_CALIBRATION_V3` reference

`BASELINE_CALIBRATION_V3` is the first trustworthy cold redesign reference.
It uses semantic behavior queries, all four candidate axes, complete corpus
ATT&CK mappings, and index/grade-symmetric signature records. Identity,
retrieval-health, and fixed near/far controls passed before the curve was
released. No training, threshold tuning, weight change, or calibration proposal
was applied.

`passed: false` characterizes remaining engine errors; `status: VALID` means the
instrument and reference are valid. These are deliberately separate concepts.

## Frozen inputs and artifacts

| Item | Frozen value |
|---|---|
| Corpus schema | `SPECIMEN_CORPUS_V2` |
| Corpus snapshot | `eca338c1724d1b1bf8efa9704cbd0c74671a51dcdd28111e746df4c4a668eda6` |
| Corpus file SHA-256 | `f1420564fc1df30ddf73b4af181278a7486a30b9e4b4a0aa5a288d72fb2c5607` |
| Sealed-ledger snapshot | `c49075f95b8fc0517e258b320f33a1e4068b34c844c06fe073b8c7379d306ba7` |
| Baseline schema/status | `BASELINE_CALIBRATION_V3` / `VALID` |
| Baseline self-hash | `24177395f0adce7b89cea56f76090b44b1528db986fc53b81a532fe295078109` |
| Baseline file SHA-256 | `d849fc20bdbf5fb4d89d51ad4435f5f5931a08d8a8513580a07becaed5fd630f` |
| Curve CSV SHA-256 | `1fdd5c8a5dc61893fd6966a842f8f5f67487d64489ff82eb5748490e81a063eb` |
| Parent snapshot rows before/after | `316 / 316` |
| Blind curve rows | `2,845` |

Artifacts are frozen at
`/Volumes/data01/portal5_hunt/artifacts/calibration/BASELINE_CALIBRATION_V3/`.
The report self-hash was independently recomputed over canonical JSON with
`snapshot_hash` set to null.

## Measurement-validity controls

| Control | Result |
|---|---:|
| Parent identity | `316 / 316` SAME, zero failures |
| Parent-or-family candidate retrieval | `2,845 / 2,845` (`100%`) |
| Degenerate candidate sets | `0 / 2,845` (`0%`) |
| Fixed known-near | `SIMILAR`, distance `0.25` |
| Fixed known-far | `NEW`, distance `0.60` |
| Measurement-valid curve rows | `2,845 / 2,845` |
| Construction proxy ↔ feature-edit Pearson correlation | `0.931253` |

The response oracle reads raw shipped evidence for token corroboration, but
ground truth requires the separately observed live detector outcome. The 397
rows with that independent signal resolve to 53 COVERED and 344 NEAR_MISS;
the other 2,448 rows are honestly INDETERMINATE rather than token-only labels.

## Cold characterization

| Measure | V3 reference |
|---|---:|
| Band-crossing accuracy | `0.554657` (`1,578 / 2,845`) |
| Monotonic-pair accuracy | `0.985088` (`33` violations / `2,213` pairs) |
| Mid-distance blind-spot rate | `0.000351` (`1 / 2,845`) |
| Real-SAME overclaim rate | `0.000000` |
| Exact wrong-parent rate | `0.419533` (`1,061 / 2,529`) |
| Correct-family accuracy | `1.000000` (`2,529 / 2,529`) |
| Unresolved rows | `0` |
| Snapshot children indexed | `0` |

Per-lane band accuracy is `0.990506` for 316 attack-data parents,
`0.500396` for 2,528 replay mutations, and `0.0` for the single live-lab row.
The one-row live-lab result remains directional evidence, not a population
estimate.

## Match-or-beat contract

A redesign comparison must use the unchanged corpus and sealed ledger, remain
cold, pass all measurement-validity controls, keep measurement-invalid rows out
of engine-error denominators, and report exact-parent and correct-family metrics
side by side. Added sourcetypes must be reported separately so they cannot
dilute regressions on Windows Security, Linux auditd, web access, or Docker
daemon. V2 is provenance only and is not an acceptance bound.
