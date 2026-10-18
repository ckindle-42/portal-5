# WFE decision — auto-math (2026-10-18)

Informational. **The seat is not changed by this document.** The seat change is an operator call
(P5-B2 practice), with the options below.

## Cells, builds, instrument

| | |
|---|---|
| Campaign | `wfe_math_20261018d` (screen + confirm). a halted (no_tools auto-halt, fixed 86e63133), b 12-task suite below the decision floor, c trace redaction HARNESS_ERROR (fixed 1747794a) |
| Plan | `tests/wfe/plans/reasoning_math_decision_v1.yaml` |
| Suite | `reasoning_math_production` — 36 tasks (arithmetic, combinatorics, logic-grid), all `no_tools`, 12 screen |
| Deployed build | `ad6e1342`, `build_dirty` 0, 12/12 backends |
| Engine path | `WFE_ENGINE=pipeline` (:9099); 432 rows; `--verify-complete` 0 problems |
| Incumbent | `phi4-mini-reasoning:latest-ctx24k` (ollama-reasoning) |

Served: phi4 and DeepSeek-R1-0528-Qwen3-8B on ollama-reasoning, glm-4.7-flash on ollama-general,
Qwen3.8-27B as `Qwen3.8-27B-oQ4e-mtp` on omlx-reasoning (the same MTP build as the other Qwen3.8 seats).

## Verdicts (confirm, 36 tasks × 3 repeats)

| Candidate vs phi4 | n | wins | losses | ties | p (sign) | Verdict |
|---|---|---|---|---|---|---|
| Qwen3.8-27B Q4_K_M-ctx32k | 36 | 11 | 1 | 24 | 0.0063 | **BETTER** |
| glm-4.7-flash Q4_K_M-ctx64k | 36 | 10 | 2 | 24 | 0.0386 | **BETTER** |
| DeepSeek-R1-0528-Qwen3-8B Q4_K_XL-ctx64k | 36 | 10 | 2 | 24 | 0.0386 | **BETTER** |

Recorded in `tests/wfe/fitness_ledger.yaml` (+3 cells). The challengers were each compared with the
incumbent, not with each other: Qwen3.8 over glm is not established by this campaign.

## Accuracy and speed (all 108 rows per arm)

| Arm | PASS | Decode tok/s med | TTFT s med | Total s med (p90) | Median output tokens | Lineage seats today |
|---|---|---:|---:|---:|---:|---|
| Qwen3.8-27B | 107/108 (99%) | 33.0 | 0.31 | **8.3** (13.9) | 495 | Qwen3.8: several (reasoning-deep, compliance, compliance-council; auto-documents G1 pending) |
| DeepSeek-R1-0528-Qwen3-8B | 105/108 (97%) | 49.4 | 0.53 | 51.9 (98.2) | 2814 | auto-reasoning, compliance council |
| glm-4.7-flash | 104/108 (96%) | 42.6 | 0.09 | 24.2 (71.0) | 1317 | **none** (bench only) — new lineage |
| phi4-mini-reasoning (incumbent) | 93/108 (86%) | 52.5 | 0.09 | 23.2 (62.1) | 1446 | auto-math only |

Qwen3.8 has the slowest decode, but it is fastest end to end because it reasons briefly (median 495
output tokens against 1.3k–2.8k). Answer tok/s is **not reported**: these rows predate T4
(b3e9443e), and their answer/reasoning split is wrong (phi4 p90 10,343 tok/s, glm 2,280 on a 33-char
answer). Decode tok/s does not depend on the split.

## Findings

- **Incumbent quality.** phi4's 15 non-PASS rows are mostly runs that hit the 8192 output cap with no
  visible answer (pipeline placeholder), on arithmetic and logic-grid tasks. A live production turn
  ("What is 17*23?") answered with an unrelated story (`p5-18e5c0416718`).
- **Receipt defect, fixed de1e657e.** `options_applied` read only top-level sampling, and Ollama seat
  sampling is injected into `options`, so every Ollama incumbent showed temperature null. That covers
  phi4 here and granite on auto-documents (that doc's "incumbent temperature null" finding was this
  defect, not the seat). Delivery was correct the whole time (`ollama_native.to_native_request`).
  It also kept the repeats policy from ever choosing 1 repeat for an Ollama seat.
- **Report crash, fixed in this batch.** T5 made `tests/wfe/report.py` import
  `router.metrics`, which opens Prometheus multiprocess files at import time. Under the campaign env
  (`PROMETHEUS_MULTIPROC_DIR=/dev/shm/...`) that crashed `--record`. The constant now lives in
  `router.trace`.

## Options for the operator

1. **Qwen3.8-27B**: the best measured accuracy and the fastest total time. It reuses the already-served
   oMLX build, so no new memory. Cost: one more seat for an already heavy lineage.
2. **glm-4.7-flash**: BETTER at p=0.039 and a lineage with no production seat today (diversity).
   Total time is about the same as the incumbent's.
3. **DeepSeek-R1-0528-Qwen3-8B**: BETTER, smallest of the three, but slowest (52 s median) and
   already seated twice.

Recommendation: **glm-4.7-flash** if diversity carries weight at this margin (107 vs 104 PASS, not
compared directly). Otherwise Qwen3.8. A glm-vs-Qwen3.8 head-to-head (36 × 3, about 2 h with
curtailment) would settle the order.
