# RBP Benign Corpus and Alert-Fatigue Closeout — 2026-07-30

## Outcome

The strong V4 arm now has both axes populated: fair notify recall 5/5 (100.0%) on attacks, and notification precision 12/12 (100.0%) on the representative benign subset.

False-flag rate: 0/12 (0.0%). Confident wrong confirms: 0; honest anomaly flags: 0.

The 5/5 attack figure above is the retained V4 comparison axis, not a
post-tuning replay. A fresh five-cell grounding regression notified on 4/5;
the non-notify was T1557 evidence containing only EventCode 4624 counts, while
the old T1557 notification depended on an invented EventCode 4738. See
`reports/RBP_ATTACK_GROUNDING_REGRESSION_20260730.md`.

## Benign cells

| Cell | Sourcetype | Verdict | False flag | Runtime |
|---|---|---|---:|---:|
| `p5n001` | `windows:security` | RULED_OUT | no | 141.99s |
| `p5n002` | `windows:security` | RULED_OUT | no | 123.56s |
| `p5n003` | `web:access` | RULED_OUT | no | 75.67s |
| `p5n004` | `web:access` | RULED_OUT | no | 131.23s |
| `p5n005` | `linux:auditd` | RULED_OUT | no | 77.74s |
| `p5n006` | `linux:auditd` | RULED_OUT | no | 122.03s |
| `p5n007` | `windows:security` | RULED_OUT | no | 122.05s |
| `p5n008` | `windows:security` | RULED_OUT | no | 118.08s |
| `p5n009` | `web:access` | RULED_OUT | no | 68.26s |
| `p5n010` | `web:access` | RULED_OUT | no | 72.43s |
| `p5n011` | `linux:auditd` | RULED_OUT | no | 75.08s |
| `p5n012` | `linux:auditd` | RULED_OUT | no | 141.78s |

## Fairness and provenance

- Windows Security, web access, and Linux auditd each contribute four plausibly confusable routine-activity cells.
- Cells use the production `ship_batch` HEC primitive, `portal5_lab` index, attack-corpus sourcetypes, and the same `corpus:*` provenance field shape. No `episode_id` or ground-truth field is shipped.
- The blue arm receives raw telemetry only. The `ground_truth=benign` label exists solely in the evaluation checkpoint.
- Coverage is a twelve-cell representative subset, not an exhaustive estimate of all normal enterprise behavior; the measured precision must not be extrapolated beyond this corpus.
