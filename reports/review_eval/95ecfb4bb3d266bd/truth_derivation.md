# Review evaluation report `95ecfb4bb3d266bd`

- commit `dcb901fc7d54539ed32fc7e14343f46d5085832d`
- embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`; corpus `real:bots-answer-key:82bae32d62afd64a490ac86d6fa5da5973505fa7a58f2e731cc64e78394ca7fc`
- config `ff7de6980b7681f1`; policy `D-T9-BENIGN-POPULATION; truth derivation with the cross_index benign-pairing arm`
- models: none
- rows `30` digest `705772548a281a6d`

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
