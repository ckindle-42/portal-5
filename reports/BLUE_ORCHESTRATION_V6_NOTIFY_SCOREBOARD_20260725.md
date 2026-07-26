# Blue Orchestration V6 Hunt-and-Notify Scoreboard — 2026-07-25

## Outcome

RBP's headline objective is notification: a correct confirmation and an honest `ANOMALOUS_UNCLASSIFIED` escalation both count as catches. Exact mapping remains visible as a conditional quality measure, not the recall gate.

## Three-axis scoreboard

| Run | Arm | Raw notify | Fair notify | Real misses | Correct confirms | Honest anomalies | Wrong confirms | Axis 3 exact / parent / tactic / unclassified / incorrect |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| v2 | `v2_exact_pre_v3` | 5/17 (29.4%) | 4/6 (66.7%) | 2 | 4 | 1 | 0 | 4 / 0 / 0 / 1 / 0 |
| v3 | `council_strong` | 3/17 (17.6%) | 3/7 (42.9%) | 4 | 2 | 1 | 0 | 2 / 0 / 0 / 1 / 0 |
| v3 | `strong_full_v3` | 7/17 (41.2%) | 4/10 (40.0%) | 6 | 3 | 4 | 0 | 3 / 0 / 0 / 4 / 0 |
| v3 | `weak_mentor_validation` | 9/17 (52.9%) | 6/9 (66.7%) | 3 | 0 | 7 | 2 | 0 / 1 / 0 / 7 / 1 |
| v4 | `council_strong` | 8/17 (47.1%) | 2/6 (33.3%) | 4 | 1 | 7 | 0 | 1 / 0 / 0 / 7 / 0 |
| v4 | `strong_full_v3` | 11/17 (64.7%) | 5/5 (100.0%) | 0 | 3 | 8 | 0 | 3 / 0 / 0 / 8 / 0 |
| v4 | `weak_mentor_validation` | 8/17 (47.1%) | 3/8 (37.5%) | 4 | 0 | 7 | 1 | 0 / 1 / 0 / 7 / 0 |
| v4_v5a_snapshot | `council_strong` | 8/17 (47.1%) | 6/11 (54.5%) | 4 | 1 | 7 | 0 | 1 / 0 / 0 / 7 / 0 |
| v4_v5a_snapshot | `strong_full_v3` | 11/17 (64.7%) | 7/9 (77.8%) | 0 | 3 | 8 | 0 | 3 / 0 / 0 / 8 / 0 |
| v4_v5a_snapshot | `weak_mentor_validation` | 8/17 (47.1%) | 4/11 (36.4%) | 1 | 0 | 7 | 1 | 0 / 1 / 0 / 7 / 0 |

Fair recall includes only PRESENT or INDETERMINATE oracle cells; provably ABSENT evidence is excluded from both its numerator and denominator.

## Strong-arm V2 → V3 → V4 reading

| Generation | Raw notify | Fair notify | Real misses | Exact maps / catches |
|---|---:|---:|---:|---:|
| V2 | 5/17 (29.4%) | 4/6 (66.7%) | 2 | 4/5 |
| V3 | 7/17 (41.2%) | 4/10 (40.0%) | 6 | 3/7 |
| V4 | 11/17 (64.7%) | 5/5 (100.0%) | 0 | 3/11 |

## Real misses by technique

- v2 / `v2_exact_pre_v3`: `T1552` (RULED_OUT), `T1557` (RULED_OUT)
- v3 / `council_strong`: `T1189` (RULED_OUT), `T1550.002` (RULED_OUT), `T1552.005` (UNRESOLVED), `T1595` (RULED_OUT)
- v3 / `strong_full_v3`: `T1047` (RULED_OUT), `T1053.005` (UNRESOLVED), `T1190` (RULED_OUT), `T1552.005` (RULED_OUT), `T1557` (RULED_OUT), `T1557.001` (UNRESOLVED)
- v3 / `weak_mentor_validation`: `T1047` (UNRESOLVED), `T1550.002` (RULED_OUT), `T1558.003` (RULED_OUT)
- v4 / `council_strong`: `T1047` (RULED_OUT), `T1550.002` (RULED_OUT), `T1557` (RULED_OUT), `T1595` (RULED_OUT)
- v4 / `weak_mentor_validation`: `T1552` (RULED_OUT), `T1552.005` (RULED_OUT), `T1557.001` (RULED_OUT), `T1611` (RULED_OUT)
- v4_v5a_snapshot / `council_strong`: `T1047` (RULED_OUT), `T1550.002` (RULED_OUT), `T1557` (RULED_OUT), `T1595` (RULED_OUT)
- v4_v5a_snapshot / `weak_mentor_validation`: `T1557.001` (RULED_OUT)

## Interpretation

On the strong solo arm, raw notification rose from 5/17 in V2 to 7/17 in V3 and 11/17 in V4. V3 did make "I see something" first-class (honest anomalies rose from 1 to 4), but its fair result fell from 4/6 to 4/10 and it was silent on six PRESENT cells: V3 was therefore a mixed change, not an unqualified improvement. V4 is the clear RBP-native improvement: 11 raw catches, 5/5 fair catches, zero real misses, and zero confirmed-wrong notifications on the strong arm.

Mapping quality tells the complementary story. Exact maps stayed at 3 while total catches rose from 7 in V3 to 11 in V4, so exact-map share fell as honest anomaly notifications increased. That is a quality-of-catch tradeoff, not a recall failure. Confirm-only recall remains reported under Axis 3.

## Measurement gaps and grounded discrepancies

- **Notification precision / alert fatigue on benign activity is unmeasurable.** Every curated cell is a real injected attack; the corpus has no benign cells and this instrument emits no fabricated precision number.
- The committed V5A attribution JSON does not retain `match_grade`, despite the task's grounded-facts section saying it does. The raw V3 and V4 checkpoints retain it; V2 predates the field and is reported as `UNKNOWN` rather than inferred.
- Re-attributing all stored checkpoints through the current oracle changes the old V5A evidence buckets because later V5B discriminator coverage is now present at HEAD. The committed V5A snapshot scores the V4 strong arm at 7/9 fair; the current oracle scores the same checkpoint at 5/5. Raw notification remains 11/17 and real misses remain zero under both oracle snapshots.

## Reproducibility

- v2: `portal/modules/security/core/results/checkpoints/corpus_replay_bench_v2_exact.json` — SHA-256 `6fc90f95e694b162b00d20aa06a27bc35d8b81c4e9f76b47ef1c381705a7ab89`
- v3: `portal/modules/security/core/results/checkpoints/corpus_replay_bench.json` — SHA-256 `8be8468867a64c1643d5181fa1d6e3cc238392d52b3d10755e50329772dc6265`
- v4: `portal/modules/security/core/results/checkpoints/corpus_replay_bench_v4_closeout.json` — SHA-256 `8bfb406544a903f11def43ecb3c65e4ac66149671ef032e6b8fb507eb1bcbad0`
- v4_v5a_snapshot: `reports/BLUE_ORCHESTRATION_V5A_ATTRIBUTION_20260725.json` — SHA-256 `dbaffc5d4238b1b9c4342841c55e195437ac8bf4c1269cf29adf81e54e945ee8`

The three local run artifacts match the SHA-256 values documented by the V5D close-out. No model or corpus rerun was needed. The scoreboard joined the V2/V3/V4 comparison through the same current V5A oracle; the separately labeled V5A snapshot preserves its committed oracle results. No production verdict-path changes were made.
