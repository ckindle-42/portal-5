# Review evaluation report `90890b3c9418457c`

- commit `83ddaa0bd53a382f3880bb902adb6ce8b2507ef4`
- embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`; corpus `real:bots_truth_manifest:4bf90b1a9ab892a8b7ae80f7c55707605f478bc5861d4a04d0958fe2e37ac9b5`
- config `fec89e8ce2825a92`; policy `T2-truth-stratification`
- models: none
- rows `7` digest `d52a2f40d9abcfa7`

## Known-answer self-test

- oracle: PASS
- inverted: PASS
- constant: PASS
- random: PASS
- planted: PASS
- benign_quiet: PASS

## Metrics

| metric | value | n | denominator | reads as failure when |
|---|---|---|---|---|
| exact_parent_reconciliation_rate | 0 | 5 | 5 | fails when any completed current source replay differs from the T1 product event-id set |
