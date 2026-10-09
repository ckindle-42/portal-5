# Review evaluation report `6a29bc97d0fd3b97`

- commit `d6145c276260cf0475abb6f014657614b9d3d27a`
- embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`; corpus `real:botsv1,botsv2,botsv3:4bf90b1a9ab892a8b7ae80f7c55707605f478bc5861d4a04d0958fe2e37ac9b5`
- config `ee0facde61b221d7`; policy `independent-truth-derivation`
- models: none
- rows `30` digest `1ab05cf3987d355b`

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
| answer_key_entry_yield | 0.259259 | 27 | 27 | fails when declared entities cannot be independently located and reconciled |
| usable_index_slice_yield | 0 | 3 | 3 | fails when none of the three pre-registered indexes has a paired real slice |
