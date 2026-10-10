# Review evaluation report `931f78ea19fa21c0`

- commit `212a9eb42d71f099d5d8e0e21893e845bbab5533`
- embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`; corpus `real:bots-answer-key:7405f881b56146de71fe2ea691b942a47b64d05c93dbd54cbdff18eaa3790fa5`
- config `894248fbccb6977e`; policy `D-T10-TRUTH-SPAN; truth derivation with the per_entry benign-pairing arm and the entity_days truth span`
- models: none
- rows `30` digest `4a110a63ae822ed9`

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
| usable_index_slice_yield | 0.666667 | 3 | 3 | fails when no pre-registered index yields a benign comparator under this arm |
