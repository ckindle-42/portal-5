# Review evaluation report `725bebcc8911ba4b`

- commit `fcce4bf3dc9b24d5cc8b28f9db2aba75760a5908`
- embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`; corpus `real:t6-proof:d2bbad0d80f3ce74a465f6626be714e0560496a5124fe4317eab7861cfec692f`
- config `7aafe77da36fe734`; policy `D-T6-PROOF; review_d0/no_reader vs legacy_funnel`
- models: none
- rows `161` digest `a101b841ecfec214`

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
| claim_proven_fraction | 0.25 | 4 | 4 | fails when any standing claim is not PROVEN under the task rule |
| processed_corpus_fraction | 1.27305e-05 | 9 | 9 | fails when the processed real-event fraction is omitted or recomputes differently |
| drill_pass_fraction | 1 | 3 | 3 | fails when any required phase-C drill does not pass |
