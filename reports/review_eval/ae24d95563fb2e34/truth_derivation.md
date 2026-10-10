# Review evaluation report `ae24d95563fb2e34`

- commit `212a9eb42d71f099d5d8e0e21893e845bbab5533`
- embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`; corpus `real:bots-answer-key:82bae32d62afd64a490ac86d6fa5da5973505fa7a58f2e731cc64e78394ca7fc`
- config `1c69a8dd9f261bdb`; policy `D-T10-TRUTH-SPAN; truth derivation with the hull benign-pairing arm and the index truth span`
- models: none
- rows `30` digest `709cce5e54456519`

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
| usable_index_slice_yield | 0 | 3 | 3 | fails when no pre-registered index yields a benign comparator under this arm |
