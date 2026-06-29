# V10 Candidate Bench Review — 6 models

**Date:** 2026-06-29
**Task:** TASK_MODEL_EVAL_V10_CANDIDATES
**PROMOTE_POLICY:** confirm-only — operator reads results and decides per candidate.
**Probe results:** `v10_candidates_20260629T194541Z.json`
**TPS results:** `bench_tps_v10_candidates_20260629T200646Z.json`

## Hardware compatibility notice

- **AEON-7/Ornith-1.0-35B-AEON-Ultimate-Uncensored-NVFP4** (operator-requested) is NOT loadable on Portal 5 hardware.
  NVFP4 + compressed-tensors requires Blackwell GPU (B200 sm_100 or GB10 sm_120). Portal 5 runs M4 Pro Metal / Ollama.
  **Substituted with `deepreinforce-ai/Ornith-1.0-35B-GGUF`** (non-abliterated parent, Apache 2.0, GGUF available).
  Uncensored variant kept as a WATCH item awaiting community GGUF abliteration.

## Pull / smoke-load results

| Workspace | Model | Status | Size |
|---|---|---|---|
| `bench-agentworld` | Qwen-AgentWorld-35B-A3B (re-validate) | PASS | ~22 GB |
| `bench-ornith-9b` | Ornith-1.0-9B (DeepReinforce) | PASS | ~5.6 GB |
| `bench-ornith-35b` | Ornith-1.0-35B (DeepReinforce) | PASS | ~21 GB |
| `bench-north-mini-code` | North-Mini-Code-1.0-QAD (Cohere) | PASS | ~19.3 GB |
| `bench-qwythos-9b` | Qwythos-9B-Claude-Mythos-5-1M (Empero) | PASS | ~5.6 GB |
| `bench-glm47f-claude-distill` | GLM-4.7-Flash Claude-Opus-4.5 distill | PASS | ~18.1 GB |

## Pipeline TPS (bench_tps --mode pipeline --runs 3)

| Workspace | Avg TPS | Tokens |
|---|---|---|
| `bench-agentworld` | 40.4 | 0 |
| `bench-ornith-9b` | 8.8 | 0 |
| `bench-ornith-35b` | 5.9 | 0 |
| `bench-north-mini-code` | 10.5 | 0 |
| `bench-qwythos-9b` | 8.6 | 0 |
| `bench-glm47f-claude-distill` | 11.4 | 0 |

## Probe results

Scoring is structural (regex + marker counts). 5/5 = all signature markers present, including no-refusal. P5 is binary per question (3 questions, max 3.0 total).

### `bench-agentworld` — Qwen-AgentWorld-35B-A3B (re-validate)

| Probe | Score | Markers | Latency |
|---|---|---|---|
| P1_envsim | 3.0/5.0 | 3/5 markers | 23.8s |
| P6_swe_handoff | 2.0/5.0 | 2/5 markers | 36.4s |

### `bench-ornith-9b` — Ornith-1.0-9B (DeepReinforce)

| Probe | Score | Markers | Latency |
|---|---|---|---|
| P2_toolchain | 1.0/5.0 | 1/5 markers | 14.4s |
| P4_uncensored | 3.0/5.0 | 3/5 markers | 29.0s |

### `bench-ornith-35b` — Ornith-1.0-35B (DeepReinforce)

| Probe | Score | Markers | Latency |
|---|---|---|---|
| P2_toolchain | 1.0/5.0 | 1/5 markers | 25.6s |
| P6_swe_handoff | 4.0/5.0 | 4/5 markers | 29.4s |

### `bench-north-mini-code` — North-Mini-Code-1.0-QAD (Cohere)

| Probe | Score | Markers | Latency |
|---|---|---|---|
| P2_toolchain | 1.0/5.0 | 1/5 markers | 358.2s |
| P6_swe_handoff | 4.0/5.0 | 4/5 markers | 112.7s |

### `bench-qwythos-9b` — Qwythos-9B-Claude-Mythos-5-1M (Empero)

| Probe | Score | Markers | Latency |
|---|---|---|---|
| P3_needle_50KB | 0.0/5.0 | 2/4 markers | 66.3s |
| P4_uncensored | 2.0/5.0 | 2/5 markers | 34.0s |

### `bench-glm47f-claude-distill` — GLM-4.7-Flash Claude-Opus-4.5 distill

| Probe | Score | Markers | Latency |
|---|---|---|---|
| P5_reasoning (agg) | 2.0/3.0 | 3 Qs | 130.8s |

### `bench-laguna` — baseline · laguna-xs.2

| Probe | Score | Markers | Latency |
|---|---|---|---|
| P1_envsim | 3.0/5.0 | 3/5 markers | 33.6s |
| P6_swe_handoff | 2.0/5.0 | 2/5 markers | 34.5s |

### `bench-omnicoder2` — baseline · omnicoder2 9B

| Probe | Score | Markers | Latency |
|---|---|---|---|
| P2_toolchain | 4.0/5.0 | 4/5 markers | 9.6s |
| P4_uncensored | 3.0/5.0 | 3/5 markers | 29.0s |

### `bench-qwen35-abliterated` — baseline · qwen3.5-abliterated 9B

| Probe | Score | Markers | Latency |
|---|---|---|---|
| P3_needle_50KB | 5.0/5.0 | 4/4 markers | 40.8s |
| P4_uncensored | 4.0/5.0 | 4/5 markers | 28.3s |

### `bench-glm` — baseline · glm-4.7-flash Q4_K_M

| Probe | Score | Markers | Latency |
|---|---|---|---|
| P5_reasoning (agg) | 1.0/3.0 | 3 Qs | 148.8s |

### `bench-gptoss` — baseline · gpt-oss 20B

| Probe | Score | Markers | Latency |
|---|---|---|---|
| P5_reasoning (agg) | 2.0/3.0 | 3 Qs | 56.2s |

### `bench-qwen3-coder-30b` — baseline · qwen3-coder 30B-A3B

| Probe | Score | Markers | Latency |
|---|---|---|---|
| P6_swe_handoff | 2.0/5.0 | 2/5 markers | 16.3s |

## Promotion candidates

> **PROMOTE_POLICY: confirm-only.** No action taken here. Operator decides per candidate.

### `bench-agentworld` — Qwen-AgentWorld-35B-A3B (re-validate)

- **Model hint:** `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL`
- **Size:** ~22 GB
- **TPS:** see table above
- **Probe pattern:** see per-workspace probe table
- **Possible lanes:** (operator fills in based on score deltas vs baseline)
- **Operator verdict:** [ ] Promote  [ ] Hold for re-bench  [ ] Drop

### `bench-ornith-9b` — Ornith-1.0-9B (DeepReinforce)

- **Model hint:** `hf.co/deepreinforce-ai/Ornith-1.0-9B-GGUF:Q4_K_M`
- **Size:** ~5.6 GB
- **TPS:** see table above
- **Probe pattern:** see per-workspace probe table
- **Possible lanes:** (operator fills in based on score deltas vs baseline)
- **Operator verdict:** [ ] Promote  [ ] Hold for re-bench  [ ] Drop

### `bench-ornith-35b` — Ornith-1.0-35B (DeepReinforce)

- **Model hint:** `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M`
- **Size:** ~21 GB
- **TPS:** see table above
- **Probe pattern:** see per-workspace probe table
- **Possible lanes:** (operator fills in based on score deltas vs baseline)
- **Operator verdict:** [ ] Promote  [ ] Hold for re-bench  [ ] Drop

### `bench-north-mini-code` — North-Mini-Code-1.0-QAD (Cohere)

- **Model hint:** `hf.co/coder543/North-Mini-Code-1.0-QAD-GGUF:NVFP4`
- **Size:** ~19.3 GB
- **TPS:** see table above
- **Probe pattern:** see per-workspace probe table
- **Possible lanes:** (operator fills in based on score deltas vs baseline)
- **Operator verdict:** [ ] Promote  [ ] Hold for re-bench  [ ] Drop

### `bench-qwythos-9b` — Qwythos-9B-Claude-Mythos-5-1M (Empero)

- **Model hint:** `hf.co/empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF:Q4_K_M`
- **Size:** ~5.6 GB
- **TPS:** see table above
- **Probe pattern:** see per-workspace probe table
- **Possible lanes:** (operator fills in based on score deltas vs baseline)
- **Operator verdict:** [ ] Promote  [ ] Hold for re-bench  [ ] Drop

### `bench-glm47f-claude-distill` — GLM-4.7-Flash Claude-Opus-4.5 distill

- **Model hint:** `hf.co/TeichAI/GLM-4.7-Flash-Claude-Opus-4.5-High-Reasoning-Distill-GGUF:Q4_K_M`
- **Size:** ~18.1 GB
- **TPS:** see table above
- **Probe pattern:** see per-workspace probe table
- **Possible lanes:** (operator fills in based on score deltas vs baseline)
- **Operator verdict:** [ ] Promote  [ ] Hold for re-bench  [ ] Drop

## Watch items

- **`AEON-7/Ornith-1.0-35B-AEON-Ultimate-Uncensored-NVFP4`** — requested but Blackwell-only.
  Monitor huihui-ai, mradermacher, and the AEON-7 org for a GGUF abliteration of `deepreinforce-ai/Ornith-1.0-35B`. If one ships, a follow-up task can swap `bench-ornith-35b` for the uncensored variant in the redteam/purpleteam lanes.
