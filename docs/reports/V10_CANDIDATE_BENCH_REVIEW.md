# V10 Candidate Bench Review — 6 models

**Date:** 2026-06-29
**Task:** TASK_MODEL_EVAL_V10_CANDIDATES
**PROMOTE_POLICY:** confirm-only — operator reads results and decides per candidate.
**Probe results:** `v10_candidates_20260629T202251Z.json` (P2 corrected: direct Ollama)
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

North-Mini-Code cohere2moe architecture smoke-loaded OK on this Ollama build (0.30.7+ MLX Metal).

## Probe results

Scoring is structural (regex + marker counts). P2 now calls Ollama directly (bypasses pipeline) so raw ``tool_calls`` arrays are observable. 5/5 = all signature markers present. P5 is binary per question (3 questions, max 3.0 total).

### `bench-agentworld` — Qwen-AgentWorld-35B-A3B (re-validate)

| Probe | Score | Markers | Latency |
|---|---|---|---|
| P1_envsim | 3.0/5.0 | 3/5 markers | 23.8s |
| P6_swe_handoff | 2.0/5.0 | 2/5 markers | 36.4s |

### `bench-ornith-9b` — Ornith-1.0-9B (DeepReinforce)

| Probe | Score | Markers | Latency |
|---|---|---|---|
| P2_toolchain | 4.0/5.0 | 4/5 markers | 6.8s |
| P4_uncensored | 3.0/5.0 | 3/5 markers | 29.0s |

### `bench-ornith-35b` — Ornith-1.0-35B (DeepReinforce)

| Probe | Score | Markers | Latency |
|---|---|---|---|
| P2_toolchain | 4.0/5.0 | 4/5 markers | 17.6s |
| P6_swe_handoff | 4.0/5.0 | 4/5 markers | 29.4s |

### `bench-north-mini-code` — North-Mini-Code-1.0-QAD (Cohere)

| Probe | Score | Markers | Latency |
|---|---|---|---|
| P2_toolchain | 4.0/5.0 | 4/5 markers | 37.6s |
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
| P2_toolchain | 4.0/5.0 | 4/5 markers | 8.4s |
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

> **PROMOTE_POLICY: confirm-only.** Operator decides per candidate.

### `bench-agentworld` — Qwen-AgentWorld-35B-A3B (re-validate)

- **Model hint:** `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL`
- **Size:** ~22 GB
- **TPS:** see table above
- **Probe pattern:** see per-workspace probe table
- **Possible lanes:** auto-agentic secondary, auto-agentic-lite primary (both unchanged)
- **Operator verdict:** [ ] Promote  [x] Hold for re-bench  [ ] Drop — production status unchanged. Model card's env-simulation/tool-coherence training claims are well above what P1_envsim (3/5) and P6_swe_handoff (2/5) showed here; operator flagged this as a probable harness mismatch rather than a real regression. Re-bench with a methodology that better targets its trained strengths before drawing any conclusion either way.

- **Model hint:** `hf.co/deepreinforce-ai/Ornith-1.0-9B-GGUF:Q4_K_M`
- **Size:** ~5.6 GB
- **TPS:** see table above
- **Probe pattern:** see per-workspace probe table
- **Possible lanes:** N/A — dropped
- **Operator verdict:** [ ] Promote  [ ] Hold for re-bench  [x] Drop — modest gain over baseline didn't justify a new lane; the 35B sibling is the keeper. Workspace and backends.yaml entry removed 2026-06-30.

- **Model hint:** `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M`
- **Size:** ~21 GB
- **TPS:** see table above
- **Probe pattern:** see per-workspace probe table
- **Possible lanes:** new `auto-agentic-ornith` workspace (additional opencode/Claude Code IDE option alongside auto-agentic, auto-agentic-lite — not a replacement)
- **Operator verdict:** [x] Promote  [ ] Hold for re-bench  [ ] Drop — strong tool-chain (4/5) and SWE-handoff (4/5) probe markers. Promoted 2026-06-30 to `auto-agentic-ornith`, selectable via `opencode . --model portal/auto-agentic-ornith` and `cc-local.sh --model auto-agentic-ornith`.

- **Model hint:** `hf.co/coder543/North-Mini-Code-1.0-QAD-GGUF:NVFP4`
- **Size:** ~19.3 GB
- **TPS:** see table above
- **Probe pattern:** see per-workspace probe table
- **Possible lanes:** new `auto-coding-northmini` workspace (diversity option alongside auto-coding — NOT a replacement; Qwen3-Coder-30B stays primary)
- **Operator verdict:** [x] Promote  [ ] Hold for re-bench  [ ] Drop — 4/5 tool-chain + 4/5 SWE-handoff, cohere2moe architecture confirmed smoke-loads cleanly on this Ollama build (the Phase-4 compatibility gate flagged in this review is resolved). Promoted 2026-06-30 to `auto-coding-northmini`.

- **Model hint:** `hf.co/empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF:Q4_K_M`
- **Size:** ~5.6 GB
- **TPS:** see table above
- **Probe pattern:** see per-workspace probe table
- **Possible lanes:** N/A — dropped
- **Operator verdict:** [ ] Promote  [ ] Hold for re-bench  [x] Drop — worst performer in the set (0/5 needle-in-haystack despite the 1M-context headline, 2/5 uncensored-depth). Workspace and backends.yaml entry removed 2026-06-30.

- **Model hint:** `hf.co/TeichAI/GLM-4.7-Flash-Claude-Opus-4.5-High-Reasoning-Distill-GGUF:Q4_K_M`
- **Size:** ~18.1 GB
- **TPS:** see table above
- **Probe pattern:** see per-workspace probe table
- **Possible lanes:** N/A — dropped
- **Operator verdict:** [ ] Promote  [ ] Hold for re-bench  [x] Drop — beat its own base (2.0/3.0 vs bench-glm's 1.0/3.0) but not enough to justify a new lane. Workspace and backends.yaml entry removed 2026-06-30.

- **`AEON-7/Ornith-1.0-35B-AEON-Ultimate-Uncensored-NVFP4`** — Blackwell-only; await community GGUF abliteration.
