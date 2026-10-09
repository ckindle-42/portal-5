# Review evaluation report `d000a7c8502c9e9c`

- commit `53ed4f0cce04721a196887b3c6db0e041ec3a2f1`
- embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`; corpus `real:botsv2/stream:dns/1501784416-1501784577`
- config `370e3cec52c92316`; policy `T3 default no_reader; live analyst-review surfaces; alpha_unusual=0.2`
- models: granite4.1:8b-ctx8k@2ee9becf2bbb
- rows `4` digest `733bbf88d826a000`

## Known-answer self-test

- benign_quiet: PASS
- constant: PASS
- inverted: PASS
- oracle: PASS
- planted: PASS
- random: PASS

## Metrics

| metric | value | n | denominator | reads as failure when |
|---|---|---|---|---|
| phase_d_e2e_case_success | 1 | 4 | 4 | value is below 1.0 when any required Phase D case is not evidenced as passing |
