# Granite Switch compliance probe

- Checkpoint: `/Users/chris/.portal5/granite-switch/granite-switch-4.1-3b-preview`
- Device: `mps`
- Edges run: 183
- Wall time: 1764.6s
- Portal HEAD: `2553339ebbbe19e9b5b2ac2cf25f1c7f86aac25b`

factuality-detection emits yes/no JSON (yes = claim unsupported by the document). policy-guardrails emits Yes/No/Ambiguous JSON. Mapped onto the task's supported/unsupported and compliant/non-compliant tables.

## Factuality

- Boilerplate catch: 12/34 (35.3%)
- SUPPORTED false positives: 65/141 (46.1%)

## Policy guardrails

- Row-mismatch catch: 0/8. The task's keywords (traceability, row, different standard, wrong row) match 0 edges in this corpus. The 8 targets are the negative verdicts that are not the boilerplate pattern.
- SUPPORTED false positives: 3/141 (2.1%)

## Per standard

| standard | n | boilerplate caught | boilerplate missed | supported FP |
|---|---|---|---|---|
| CIP-003-8 | 3 | 0 | 0 | 0 |
| CIP-003-9 | 3 | 0 | 0 | 2 |
| CIP-004-7 | 42 | 0 | 7 | 18 |
| CIP-005-7 | 10 | 2 | 1 | 3 |
| CIP-006-6 | 23 | 2 | 2 | 5 |
| CIP-007-6 | 38 | 2 | 6 | 12 |
| CIP-008-6 | 18 | 2 | 2 | 5 |
| CIP-009-6 | 11 | 4 | 1 | 2 |
| CIP-010-4 | 19 | 0 | 1 | 9 |
| CIP-011-3 | 10 | 0 | 2 | 5 |
| CIP-013-2 | 2 | 0 | 0 | 0 |
| CIP-014-3 | 4 | 0 | 0 | 4 |

## Samples where Granite disagreed with a clean supported reading

- `rel-8eda7a76fa299bc465d7` gold=SUPPORTED fact=unsupported reply={"label": "yes"}
- `rel-a29c1ffd30b9adddc3a3` gold=SUPPORTED fact=unsupported reply={"label": "yes"}
- `rel-665cc4d153247e6e137f` gold=SUPPORTED fact=unsupported reply={"label": "yes"}

## Samples where Granite flagged a boilerplate-shaped overclaim

- `rel-603c36b2c4876026c4de` gold=UNSUPPORTED fact=unsupported reply={"label": "yes"}
- `rel-5f6a92fa7b38141ef0f5` gold=UNSUPPORTED fact=unsupported reply={"label": "yes"}

## Operator gate (P3.G1)

Ship as a compliance guard only if boilerplate catch is at least 50% and the
SUPPORTED false-positive rate is at most 20%. Retain for tuning if boilerplate
catch is at least 30%. Otherwise reject. This task does not wire the adapter.

Operator decision: PENDING
