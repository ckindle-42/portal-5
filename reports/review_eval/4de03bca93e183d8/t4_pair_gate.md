# Review evaluation report `4de03bca93e183d8`

- commit `31ddefc13a037afcd4778ea0baaea05f68f87a96`
- embedder `not_used;T4_precondition_only`; corpus `real:bots_truth_manifest:4bf90b1a9ab892a8b7ae80f7c55707605f478bc5861d4a04d0958fe2e37ac9b5`
- config `f800d9617cb4b136`; policy `T4-pair-precondition`
- models: none
- rows `4` digest `246b6e804b0503f7`

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
| eligible_pairs | 0 | 3 | 20 | fails when fewer than 20 answer-key and same-index routine-use pairs can be independently labelled |
| botsv1_botsv2_unexcluded_index_seconds | 0 | 2 | 2 | fails when any indexed time remains outside every retained answer-key interval plus the 24-hour margin, requiring a routine-use search before a no-run result |
| same_index_benign_benchmark_cells | 0 | 12 | 12 | fails when portal5_lab benign benchmark cells are counted as same-index BOTSv background |
