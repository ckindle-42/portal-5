# Review evaluation report `fb80197354f28435`

- commit `0c8d97e77a4eadf4216fb8c78da4b787cb97cf64`
- embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`; corpus `real:bots-answer-key:82bae32d62afd64a490ac86d6fa5da5973505fa7a58f2e731cc64e78394ca7fc`
- config `381f635c4e5cf0ff`; policy `D-T8-PAIRING; truth derivation with the per_entry benign-pairing arm`
- models: none
- rows `30` digest `337acc2137a102bb`

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
