# Council bench 2026-10-19: dense roster vs one resident MoE

**Finding:** the auto-council can run about 9× faster (median 27 s vs 225 s per review)
at the old council's quality, by giving every role (Evidence, Challenger, Operator,
synthesizer) to the one MoE already loaded on oMLX: `gemma-4-26b-a4b-it-QAT-4bit`. Each role
keeps its own prompt and separate call. It adds no memory and no load time. Same 20 fixed
cases (`tests/fixtures/council/cases.json`) for every configuration; full rows in
`tests/benchmarks/results/council_bench_20261019.json`.

| Configuration | Correct | Key issue | Clear rejects | Median | 20 reviews |
|---|---|---|---|---|---|
| baseline: granite-30B / mistral-24B / DeepSeek-R1-8B, Qwen3.8 synth | 12/20 | 16/20 | 0/5 | 225 s | 76 min |
| baseline + early_quorum | 11/20 | 16/20 | 0/5 | 177 s | 67 min |
| Qwen3.8-27B in every seat (dense) | 16/20 | 18/20 | 3/5 | 279 s | 96 min |
| gemma4-26B-A4B in every role | 12/20 | 16/20 | 3/5 | 26 s | 8 min |
| gemma4 + early_quorum (run 1 / run 2) | 14/20, 11/20 | 14/20, 13/20 | 4/5, 3/5 | 27 s | 9 min |
| gemma4 + decompose | 12/20 | 14/20 | 2/5 | 28 s | 9 min |

**How to read it**

- *Noise:* the same configuration scored 14/20 and then 11/20, agreeing on 16 of 20
  decisions. Differences of ±3 on this set are noise.
- *Rubric confound:* the dense baseline rows ran before the review contract had a decision
  rubric (6ccfeb5d). The gemma rows ran after it, so part of the clear-reject gain is the rubric.
- *Qwen3.8 everywhere* is the most accurate single run (16/20), but it is too slow for the
  lane and within reach of the noise.
- *decompose* did not help with this model.

**Memory constraint, measured:** three separate ~20 GB MoE seats (Qwen3.6-35B-A3B,
gemma4-26B-A4B, glm-4.7-flash) cannot be resident together on the 64 GB host. oMLX refused
Qwen3.6 with 507 ("21.16GB does not fit under the dynamic memory ceiling 19.05GB"), and the
Ollama load_guard queued glm-4.7-flash (needs 22.1 GiB, 18.6 available). The council posts to
whichever backend declares the model id, so a seat's model must name the oMLX build
(e.g. `gemma-4-26b-a4b-it-QAT-4bit`) to reach the resident copy, not the Ollama GGUF tag.

---

## Generated report (scripts/council_bench.py)

# Council bench — moe1_gemma4_eq_r2

Configuration: `{"early_quorum": true, "members": {"challenger": {"model": "gemma-4-26b-a4b-it-QAT-4bit"}, "evidence": {"model": "gemma-4-26b-a4b-it-QAT-4bit"}, "operator": {"model": "gemma-4-26b-a4b-it-QAT-4bit"}}, "synthesizer_model": "gemma-4-26b-a4b-it-QAT-4bit"}`

- Cases: 20 · accuracy 0.550 · key-issue recall 0.650
- Time: median 27.48 s · p90 34.66 s
- Errors: 0 · per-stage timings captured: 20/20
- Override status: applied

## Configurations

| Configuration | Cases | Accuracy | Key-issue recall | Median s | p90 s |
|---|---:|---:|---:|---:|---:|
| `baseline` | 20 | 0.600 | 0.800 | 225.25 | 253.72 |
| `early_quorum` | 20 | 0.550 | 0.800 | 176.94 | 277.28 |
| `single_model_qwen38` | 20 | 0.800 | 0.900 | 279.16 | 364.48 |
| `moe1_gemma4` | 20 | 0.600 | 0.800 | 25.83 | 28.84 |
| `moe1_gemma4_eq` | 20 | 0.700 | 0.700 | 26.52 | 30.92 |
| `moe1_gemma4_decompose` | 20 | 0.600 | 0.700 | 28.18 | 37.50 |
| `moe1_gemma4_eq_r2` | 20 | 0.550 | 0.650 | 27.48 | 34.66 |

## By category

| Category | Cases | Accuracy | Key-issue recall | Median s |
|---|---:|---:|---:|---:|
| clear_reject | 5 | 0.600 | 1.000 | 26.61 |
| clear_support | 5 | 0.400 | 0.000 | 27.26 |
| hidden_flaw | 3 | 1.000 | 1.000 | 29.21 |
| missing_evidence | 2 | 0.500 | 1.000 | 21.57 |
| operational_risk | 2 | 0.000 | 1.000 | 32.54 |
| split | 1 | 1.000 | 1.000 | 27.70 |
| stale_claim | 2 | 0.500 | 0.000 | 27.42 |

## Seats

| Seat | Appearances | Participated | Rate | SUPPORT/REVISE/REJECT |
|---|---:|---:|---:|---|
| challenger | 20 | 20 | 1.000 | 1/8/11 |
| evidence | 20 | 18 | 0.900 | 3/10/5 |
| operator | 20 | 9 | 0.450 | 2/7/0 |

## Cases

| Case | Category | Expected | Decision | OK | Key issue | Votes SUPPORT/REVISE/REJECT | Wall s |
|---|---|---|---|---|---:|---|---:|
| `case-01` | clear_support | SUPPORT | ESCALATE | no | miss | 1/1/0 | 27.26 |
| `case-02` | clear_support | SUPPORT | REVISE | no | miss | 1/2/0 | 30.27 |
| `case-03` | clear_support | SUPPORT | REVISE | no | miss | 0/2/1 | 28.91 |
| `case-04` | clear_support | SUPPORT | SUPPORT | yes | miss | 2/0/0 | 16.80 |
| `case-05` | clear_support | SUPPORT | SUPPORT | yes | miss | 2/1/0 | 24.66 |
| `case-06` | clear_reject | REJECT | REVISE | no | hit (reviewers) | 0/2/1 | 34.66 |
| `case-07` | clear_reject | REJECT | REJECT | yes | hit (reviewers) | 0/0/2 | 23.81 |
| `case-08` | clear_reject | REJECT | REJECT | yes | hit (reviewers) | 0/0/2 | 26.61 |
| `case-09` | clear_reject | REJECT | REVISE | no | hit (reviewers) | 0/2/1 | 35.27 |
| `case-10` | clear_reject | REJECT | REJECT | yes | hit (reviewers) | 0/0/2 | 25.97 |
| `case-11` | hidden_flaw | REVISE | REVISE | yes | hit (reviewers) | 0/2/0 | 29.21 |
| `case-12` | hidden_flaw | REVISE | REVISE | yes | hit (reviewers) | 0/2/0 | 23.29 |
| `case-13` | hidden_flaw | REVISE | REVISE | yes | hit (reviewers) | 0/2/1 | 35.36 |
| `case-14` | missing_evidence | REVISE | REVISE | yes | hit (reviewers) | 0/2/0 | 21.60 |
| `case-15` | missing_evidence | REVISE | REJECT | no | hit (reviewers) | 0/0/2 | 21.53 |
| `case-16` | stale_claim | REVISE | REJECT | no | miss | 0/0/2 | 24.65 |
| `case-17` | stale_claim | REVISE | REVISE | yes | miss | 0/2/0 | 30.19 |
| `case-18` | operational_risk | REVISE | ESCALATE | no | hit (reviewers) | 0/1/1 | 32.99 |
| `case-19` | operational_risk | REJECT | REVISE | no | hit (reviewers) | 0/2/1 | 32.10 |
| `case-20` | split | REVISE | REVISE | yes | hit (reviewers) | 0/2/0 | 27.70 |
