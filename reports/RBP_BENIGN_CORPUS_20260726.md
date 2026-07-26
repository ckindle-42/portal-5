# RBP Benign Corpus and Alert-Fatigue Closeout — 2026-07-26

## Outcome

The strong V4 arm now has both axes populated: fair notify recall 5/5 (100.0%) on attacks, and notification precision 2/6 (33.3%) on the representative benign subset.

False-flag rate: 4/6 (66.7%). Confident wrong confirms: 0; honest anomaly flags: 4.

## Benign cells

| Cell | Sourcetype | Verdict | False flag | Runtime |
|---|---|---|---:|---:|
| `p5n001` | `windows:security` | ANOMALOUS_UNCLASSIFIED | yes | 95.35s |
| `p5n002` | `windows:security` | RULED_OUT | no | 69.01s |
| `p5n003` | `web:access` | ANOMALOUS_UNCLASSIFIED | yes | 65.06s |
| `p5n004` | `web:access` | ANOMALOUS_UNCLASSIFIED | yes | 104.77s |
| `p5n005` | `linux:auditd` | ANOMALOUS_UNCLASSIFIED | yes | 69.36s |
| `p5n006` | `linux:auditd` | RULED_OUT | no | 150.44s |

## Fairness and provenance

- Windows Security, web access, and Linux auditd each contribute two plausibly confusable routine-activity cells.
- Cells use the production `ship_batch` HEC primitive, `portal5_lab` index, attack-corpus sourcetypes, and the same `corpus:*` provenance field shape. No `episode_id` or ground-truth field is shipped.
- The blue arm receives raw telemetry only. The `ground_truth=benign` label exists solely in the evaluation checkpoint.
- Coverage is a six-cell representative subset, not an exhaustive estimate of all normal enterprise behavior; the measured precision must not be extrapolated beyond this corpus.
