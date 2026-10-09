# Review evaluation report `6382ecb3d97f4cee`

- commit `d6145c276260cf0475abb6f014657614b9d3d27a`
- embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`; corpus `real:recorded-captures:5445bf316cfc1c065f6d61c69858a3464ff10892831113e2797a68dea1c772b0`
- config `67943f3b1d16ddc6`; policy `capture-admission-report`
- models: none
- rows `2` digest `1736d6a0eef27e90`

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
| capture_admission_rate | 0.000887311 | 1127 | 1127 | fails when the self-tested validator admits no recorded capture |
