# Review evaluation report `41eaed5720a9844f`

- commit `4a6eeb9ccd019d6cbc3b00795d3f68e1549450ca`
- embedder `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`; corpus `real:reader-prerequisites:f56783be88f2f963a32f3f8a52701da15e8a705fe18f73257116328410f35500`
- config `ab8750b4530f4783`; policy `T3-prerequisite-gate`
- models: auto-security::security-council-granite41-30b@f1882d96fca8, auto-security::security-council-mistral-small32-24b@c3c35d409533, auto-security::security-council-qwen36-27b@48213e5bcdf8, auto-security::security-expert-foundation-sec-8b@d9df9289cf2a, hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx96k@24ba2fea389d, hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k@442c0e498f93
- rows `14` digest `398c59b8175da7d2`

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
| core_reasoning_candidate_rate | 0.5 | 4 | 4 | fails when no configured single-reader candidate produces a reasoning channel |
| panel_reasoning_seat_rate | 0.333333 | 3 | 3 | fails when the configured panel has no reasoning-capable seat |
| paired_truth_slice_yield | 0 | 3 | 3 | fails when no registered index has an eligible paired truth slice |
| alpha_open_available | 0 | 1 | 1 | fails when T2 has no candidate-recall-versus-alpha curve from which to derive alpha_open |
| workload_B_available | 0 | 1 | 1 | fails when T1 did not establish workload budget B |
| reader_depth_R_available | 0 | 1 | 1 | fails when evaluation window duration and measured concern p95 latency are unavailable |
