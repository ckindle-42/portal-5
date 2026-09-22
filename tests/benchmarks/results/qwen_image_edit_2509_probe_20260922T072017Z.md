# Qwen-Image-Edit-2509 probe

- Portal HEAD: `2553339ebbbe19e9b5b2ac2cf25f1c7f86aac25b`
- Invocation: alias-qwen-edit-2509; august baseline is HF Qwen/Qwen-Image-Edit because the seated tag qwen-image-edit already resolves to Qwen/Qwen-Image-Edit-2509 in mflux 0.19.1
- Baseline tag: `Qwen/Qwen-Image-Edit`
- 2509 tag: `qwen-edit-2509`
- Started: 2026-09-22T03:41:38.125087Z

0.19.1 seated qwen-image-edit -> Qwen/Qwen-Image-Edit-2509

No persistent config change. The seated `MFLUX_QWEN_EDIT_TAG` is untouched.

## Mechanical rates

- baseline: 6/6 (100.0%)
- 2509: 10/10 (100.0%)

## Pairs

| id | category | baseline | 2509 | baseline_s | 2509_s | operator score (1-5) |
|---|---|---|---|---|---|---|
| id01 | identity_preservation | `tests/benchmarks/results/qwen_edit_2509_outputs/baseline/id01.png` | `tests/benchmarks/results/qwen_edit_2509_outputs/2509/id01.png` | 726.65 | 730.32 |  |
| id02 | identity_preservation | `tests/benchmarks/results/qwen_edit_2509_outputs/baseline/id02.png` | `tests/benchmarks/results/qwen_edit_2509_outputs/2509/id02.png` | 730.8 | 730.71 |  |
| id03 | identity_preservation | `tests/benchmarks/results/qwen_edit_2509_outputs/baseline/id03.png` | `tests/benchmarks/results/qwen_edit_2509_outputs/2509/id03.png` | 717.19 | 717.37 |  |
| id04 | identity_preservation | `tests/benchmarks/results/qwen_edit_2509_outputs/baseline/id04.png` | `tests/benchmarks/results/qwen_edit_2509_outputs/2509/id04.png` | 731.68 | 731.56 |  |
| mi01 | multi_image | `` | `tests/benchmarks/results/qwen_edit_2509_outputs/2509/mi01.png` |  | 1214.81 |  |
| mi02 | multi_image | `` | `tests/benchmarks/results/qwen_edit_2509_outputs/2509/mi02.png` |  | 1215.96 |  |
| mi03 | multi_image | `` | `tests/benchmarks/results/qwen_edit_2509_outputs/2509/mi03.png` |  | 1215.56 |  |
| tx01 | text_editing | `tests/benchmarks/results/qwen_edit_2509_outputs/baseline/tx01.png` | `tests/benchmarks/results/qwen_edit_2509_outputs/2509/tx01.png` | 731.03 | 731.47 |  |
| tx02 | text_editing | `tests/benchmarks/results/qwen_edit_2509_outputs/baseline/tx02.png` | `tests/benchmarks/results/qwen_edit_2509_outputs/2509/tx02.png` | 731.32 | 731.29 |  |
| ct01 | controlnet_style_pose | `` | `tests/benchmarks/results/qwen_edit_2509_outputs/2509/ct01.png` |  | 731.62 |  |

## Operator gate (P2.G1)

Score identity preservation, multi-image faithfulness, text editing,
and pose accuracy from 1 to 5. Promotion is not applied by this task.
A follow-up that switches the seated tag is reasonable when 2509 beats
the August baseline on at least 3 of 4 identity items, at least 2 of 3
multi-image items score at least 3, and text editing does not regress.

Operator scores: PENDING
