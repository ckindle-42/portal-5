# Blue Orchestration V4 Close-out — 2026-07-25

## Outcome

All three V4 code defects are fixed and the 51-cell corpus replay completed
with no unresolved investigations. The result does **not** support changing
production routing: confirm-only recall did not improve for the strong solo
arm, and the council arm lost the one-voter confirmations that V4C correctly
identified as unsafe.

## Validation

- Checkpoint:
  `portal/modules/security/core/results/checkpoints/corpus_replay_bench_v4_closeout.json`
- Cells: 51/51 `done`
- Verdicts: 5 CONFIRMED, 22 ANOMALOUS_UNCLASSIFIED, 24 RULED_OUT
- UNRESOLVED: 0
- Correct-confirm false demotions: 0
- Quarantined aggregate claims: 1 (`T1552.005`, cite-or-drop failure; not a
  discriminator false demotion)
- Council non-participation traces: 16/17 cells
- Parent-collapse audit: the weak NTDS arm retained `T1003` and emitted
  `precision note: T1003 could be refined to T1003.003`

## Confirm-only recall

| Arm | V3 checkpoint | V4 close-out | Delta |
|---|---:|---:|---:|
| Strong solo (`strong_full_v3`) | 3/17 (17.6%) | 3/17 (17.6%) | 0.0 pp |
| Council (`council_strong`) | 2/17 (11.8%) | 1/17 (5.9%) | -5.9 pp |
| Weak Mentor validation | 1/17 (5.9%) | 1/17 (5.9%) | 0.0 pp |

The V3 values above were recomputed confirm-only from the stored verdict and
technique IDs. A RULED_OUT payload that happens to retain a technique ID is
not a detection and receives no recall credit.

The repository has no corpus-matched V2 checkpoint with these same 17
techniques and arms, so a literal V3+V4-vs-V2 delta cannot be computed without
running a new V2 baseline. The apples-to-apples stored comparison is V4 vs V3.

## Finding disposition

- `P5-SEC-BLUE-MITRE-001`: resolved by the label-blind, positive-contradiction
  sibling discriminator gate. No false demotions in the full sweep.
- `P5-SEC-BUDGET-STARVE-001`: resolved. The V3 checkpoint had 10 UNRESOLVED
  cells across the three arms; V4 has 0, and every solo trace reaches Expert.
- `P5-SEC-COUNCIL-001`: resolved mechanically and by policy. Quorum uses the
  full roster, non-voters are traced, and the live sweep demonstrated that a
  0.5 participation floor was too permissive for a two-member roster. The
  final default is 0.67, so one-of-two participation escalates/arbiter-routes
  rather than auto-confirming.

## Production decision

Do not promote V4 orchestration as a recall improvement. Merge the correctness
fixes, retain current production routing, and treat the high council non-voter
rate (16/17 cells, primarily `cogito:32b`) as roster-selection data before any
future council experiment.
