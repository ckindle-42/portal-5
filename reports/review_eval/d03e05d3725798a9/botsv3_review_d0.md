# Review evaluation report `d03e05d3725798a9`

- commit `d6145c276260cf0475abb6f014657614b9d3d27a`
- embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`; corpus `real:botsv3:25e5d654c29bc747ced0c52e759b22d4a9e82d1c06d29d1d2008801ff3949ac0`
- config `18fa5266ca207ac2`; policy `review_d0`
- models: none
- rows `1` digest `2c6dc34961d481a7`

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
