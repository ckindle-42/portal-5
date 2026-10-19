# Decision: auto-reasoning seats K2-Horizon-MoVA-36B-A4B (2026-10-19)

**Operator:** seat K2 now on the screen evidence, then a K2-only stability run; math is not
the lane's use case, so the run was cut to one shot per science and puzzle task.

| Run | Arm | Result | Median |
|---|---|---|---|
| Screen `wfe_reasoning_hard_20261019b` (12 tasks) | K2-Horizon | 12/12 | 28 s |
| | DeepSeek-R1-0528-Qwen3-8B (incumbent) | 8/12 | 383 s |
| | glm-4.7-flash | 10/12 | 248 s |
| Stability `wfe_reasoning_k2_stability_20261019` | K2: grad science | 13/13 | 12 s (science + puzzle) |
| | K2: puzzle | 12/12 | |
| | K2: competition math (stopped, operator) | 20/21 | |

The 16 original science and puzzle items (written for the suite, so not in any training data)
all pass. The one math miss is `competition-math-05` (271 vs 279). Remaining math rows and all
repeats were marked `SKIPPED_DECIDED` with the operator's reason in the manifest.

Settings: card temperature 1.0, top_p 0.95; the template defaults `reasoning_effort` to high.
About 21 GB loaded vs DeepSeek's 6 GB, only while the lane is in use. DeepSeek stays seated in
the compliance council.
