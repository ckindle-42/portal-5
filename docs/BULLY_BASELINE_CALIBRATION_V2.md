# Defensive Bully `BASELINE_CALIBRATION_V2` provenance (invalid as reference)

`BASELINE_CALIBRATION_V2` is retained unchanged for provenance, but it is
**invalid as a redesign reference**. The bench queried embeddings with SHA-256
fingerprints, wired only the semantic candidate axis, and stripped ATT&CK
mappings; it therefore measured broken retrieval rather than cousin-engine
discrimination. Its trustworthy-looking curve must not be used for acceptance,
tuning, or match-or-beat comparisons. The first valid replacement is
`BASELINE_CALIBRATION_V3`, documented in
`docs/BULLY_BASELINE_CALIBRATION_V3.md`.

## Frozen inputs and artifacts

| Item | Frozen value |
|---|---|
| Corpus schema | `SPECIMEN_CORPUS_V2` |
| Corpus snapshot | `eca338c1724d1b1bf8efa9704cbd0c74671a51dcdd28111e746df4c4a668eda6` |
| Corpus file SHA-256 | `f1420564fc1df30ddf73b4af181278a7486a30b9e4b4a0aa5a288d72fb2c5607` |
| Sealed-ledger snapshot | `c49075f95b8fc0517e258b320f33a1e4068b34c844c06fe073b8c7379d306ba7` |
| Baseline schema | `BASELINE_CALIBRATION_V2` |
| Baseline self-hash | `1b5d6511bc11acb93908c610bc784c57ce609c828071a2b828a16d33b67e0afc` |
| Baseline file SHA-256 | `7bf57d451810f99c8961e86eb1a6f4fcebd051042b9b1201fe24a2896e0e5504` |
| Curve CSV SHA-256 | `86d7ee87cf85da3787e8ac015e2b091015794f59096832ec6f261dba88fee237` |
| Parent snapshot rows before/after | `316 / 316` |
| Blind curve rows | `2,845` |

The corpus and sealed truth live at
`/Volumes/data01/portal5_hunt/artifacts/specimen_corpus_v2/`. The reference
report, compatibility copy, curve CSV, and read-only Organ snapshot live at
`/Volumes/data01/portal5_hunt/artifacts/calibration/BASELINE_CALIBRATION_V2/`.
The report self-hash is computed over canonical JSON with `snapshot_hash` set to
null; it was independently recomputed after the run. The corpus contains 316
attack-data parents, 2,528 replay mutations, and one live-lab cousin, all
live-indexed.

## Historical comparison table (void)

These values describe the invalid instrument reading only. They are not
acceptance bounds:

| Measure | Direction | Invalid P7.3 reading |
|---|---:|---:|
| Band-crossing accuracy | at least | `0.467487` |
| Monotonic-pair accuracy | at least | `0.750565` |
| Mid-distance blind-spot rate | at most | `0.259402` |
| Real-SAME overclaim rate | at most | `0.000000` |
| Wrong-parent rate | at most | `0.913009` |
| Response-axis failures | at most | `339` |
| Unresolved rows | at most | `0` |
| Snapshot children indexed | exactly | `0` |

The comparison must also retain a non-trivial real response reading rather than
collapsing to all-indeterminate. The reference distribution is 53 COVERED, 344
MISSED, and 2,448 INDETERMINATE from real observed detector outcomes. A new
sourcetype is an additional acceptance dimension; its rows cannot be pooled into
the denominator to hide a regression on Windows Security, Linux auditd, web
access, or Docker daemon.

No result may re-bless V2. V3 cites and supersedes it while retaining this file
and its hashes as provenance.
