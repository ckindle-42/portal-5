# Review evaluation report `ea8a1330837e2913`

- commit `d6145c276260cf0475abb6f014657614b9d3d27a`
- embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`; corpus `real:botsv2:8c4fea104572cf48e00b1f73c001e1edfb6c8f9e3cb2475980cf7c7fc157aebc`
- config `6afc23ed24d3b789`; policy `review_d0`
- models: none
- rows `1` digest `f3998ea88fe9520b`

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
