# Review evaluation report `cf5bfa97e417c12a`

- commit `d6145c276260cf0475abb6f014657614b9d3d27a`
- embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`; corpus `real:botsv1:64b8b2f6043fa9373a8bc6356081ae8efebd6da065a4e90350da691b0d568abb`
- config `06884308c9979df9`; policy `review_d0`
- models: none
- rows `1` digest `0ddfc0b7c9bd1ee4`

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
| slice_eligibility | 0 | 1 | 1 | fails when the pre-registered index has no usable attack and benign pair |
