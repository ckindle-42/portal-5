# Pending model verdicts — decision-support sheet (2026-08-11 05:43 UTC)

62 pending entries, 783.9 GB total reclaim potential.

## ⚠ Stack boundary in effect

**Boundary date: 2026-08-08** (`--stack-boundary-days=3`).

The Ollama + oMLX inference stack has changed materially. Evidence
captured before the boundary was measured under a prior stack and
**does not reflect current behavior**. All TPS/quality averages in
this sheet are computed over post-boundary rows only; pre-boundary
rows are counted but excluded from decision math. Numeric-driven
decline suggestions require ≥1 post-boundary row — otherwise the
suggestion downgrades to `investigate-refresh` (re-bench first).

Models with NO post-boundary evidence: **59 / 62** (of which 11 have only pre-boundary data)

If most pending models fall into that bucket, a fleet-wide bench
sweep is the real prerequisite — this task will otherwise mostly
emit `investigate-refresh` suggestions.

## How to use

For each row, review the mined evidence + suggested verdict, then
record the decision inline in `config/PENDING_MODEL_VERDICTS.md` as:

```
- [x] `tag` — X.X GB
  - verdict: decline (superseded by <incumbent>; quality Δ ≤ 0)
  - evidence: `...` (regenerated each audit run)
```

Verdict vocabulary: `decline` | `promote` | `keep-open` | `investigate` | `investigate-refresh`.
`investigate-refresh` = evidence is missing, pre-boundary only, or >60 days old — re-bench first.
The verdict/reason line survives audit reruns (Part A of this task).

Sorted biggest-reclaim-first.

## `portal5/qwen3.6-27b-mtp:q8_0-drafted` — 43.6 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-qwen36-27b-mtp
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-28** (44d old) — ⚠ **all pre-boundary**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `qwen3.6:27b-q8_0` — 27.9 GB

- **Suggested verdict:** `investigate-refresh` — only pre-boundary evidence (1 rows before 2026-08-08); re-bench required
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 1 tps rows total (**0 valid** post-boundary, 1 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-28** (44d old) — ⚠ **all pre-boundary**
  - avg TPS (pre-boundary, INVALID for decisions): 5.0 t/s
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k` — 24.2 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 2 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `qwen3.6:35b-a3b-q4_K_M` — 22.3 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-qwen36-35b-a3b
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-21** (51d old) — ⚠ **all pre-boundary**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` — 21.7 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-qwen36-35b-a3b-ud
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-28** (44d old) — ⚠ **all pre-boundary**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M` — 21.4 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-nex-n2-mini
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-21** (51d old) — ⚠ **all pre-boundary**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K` — 20.6 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-bugtrace-ultra-27b
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:Q4_K_M` — 20.3 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-huihui-qwen36-35b-a3b
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-28** (44d old) — ⚠ **all pre-boundary**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `portal5/xyz-aquila-mini:Q4_K_M` — 19.9 GB

- **Suggested verdict:** `investigate` — post-boundary evidence (tps=49.3, q=0.67, n=1) but no incumbent to compare
- **Bench workspaces routing to this tag:** bench-aquila-mini-35b-a3b
- **Mined evidence:** 1 tps rows total (**1 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
  - avg TPS (post-boundary only): **49.3** t/s   (PASS)
  - avg quality_score (post-boundary only): **0.67**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `portal5/xyz-aquila-mini:q4_k_m-ctx16k` — 19.9 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-aquila-research
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `muse-glimmer:30b-mlx` — 19.8 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-muse-glimmer-30b
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M` — 19.7 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-superqwen-agentworld-ablit
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `portal5/deepwen-3.6:q4.5-moq-ctx32k` — 19.7 GB

- **Suggested verdict:** `investigate` — post-boundary evidence (tps=40.4, q=0.0, n=1) but no incumbent to compare
- **Bench workspaces routing to this tag:** bench-deepwen-cad
- **Mined evidence:** 1 tps rows total (**1 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
  - avg TPS (post-boundary only): **40.4** t/s   (PASS)
  - avg quality_score (post-boundary only): **0.0**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `portal5/deepwen-3.6:q4.5-moq` — 19.7 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf` — 19.7 GB

- **Suggested verdict:** `investigate-refresh` — only pre-boundary evidence (1 rows before 2026-08-08); re-bench required
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 1 tps rows total (**0 valid** post-boundary, 1 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-23** (49d old) — ⚠ **all pre-boundary**
  - avg TPS (pre-boundary, INVALID for decisions): 29.7 t/s
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M` — 19.7 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-agents-a1
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf-ctx64k` — 18.7 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `deepseek-r1:32b-q4_k_m` — 18.5 GB

- **Suggested verdict:** `investigate-refresh` — only pre-boundary evidence (2 rows before 2026-08-08); re-bench required
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 2 tps rows total (**0 valid** post-boundary, 2 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-28** (44d old) — ⚠ **all pre-boundary**
  - avg TPS (pre-boundary, INVALID for decisions): 7.3 t/s
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.gguf` — 18.2 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-qwopus-coder-mtp-v2
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `glm-4.7-flash:Q4_K_M` — 17.7 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-glm
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-12** (60d old) — ⚠ **all pre-boundary**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `gemma4:31b-it-qat-ctx8k` — 17.6 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-21** (51d old) — ⚠ **all pre-boundary**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `gemma4:31b-it-qat` — 17.6 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-gemma4-31b-qat
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-21** (51d old) — ⚠ **all pre-boundary**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf` — 17.4 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-gemma4-31b-crack
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `gemma4:26b-a4b-it-q4_K_M` — 16.8 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-gemma4-26b-optiq
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-28** (44d old) — ⚠ **all pre-boundary**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M` — 16.7 GB

- **Suggested verdict:** `investigate-refresh` — only pre-boundary evidence (1 rows before 2026-08-08); re-bench required
- **Bench workspaces routing to this tag:** bench-qwen36-27b-optiq
- **Mined evidence:** 1 tps rows total (**0 valid** post-boundary, 1 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-21** (51d old) — ⚠ **all pre-boundary**
  - avg TPS (pre-boundary, INVALID for decisions): 14.4 t/s
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `qwen3.6:27b-mtp-q4_K_M` — 16.5 GB

- **Suggested verdict:** `investigate-refresh` — only pre-boundary evidence (2 rows before 2026-08-08); re-bench required
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 2 tps rows total (**0 valid** post-boundary, 2 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-28** (44d old) — ⚠ **all pre-boundary**
  - avg TPS (pre-boundary, INVALID for decisions): 4.3 t/s
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/mradermacher/gemma-4-26B-A4B-it-uncensored-heretic-GGUF:gemma-4-26B-A4B-it-uncensored-heretic.Q4_K_M.gguf` — 16.4 GB

- **Suggested verdict:** `investigate-refresh` — only pre-boundary evidence (2 rows before 2026-08-08); re-bench required
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 2 tps rows total (**0 valid** post-boundary, 2 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-28** (44d old) — ⚠ **all pre-boundary**
  - avg TPS (pre-boundary, INVALID for decisions): 22.8 t/s
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `sylink/sylink:8b` — 15.3 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-sylink-8b, bench-sylink
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `sylink/sylink:8b-ctx8k` — 15.3 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `phi4:14b-q8_0` — 14.5 GB

- **Suggested verdict:** `investigate-refresh` — only pre-boundary evidence (2 rows before 2026-08-08); re-bench required
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 2 tps rows total (**0 valid** post-boundary, 2 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-28** (44d old) — ⚠ **all pre-boundary**
  - avg TPS (pre-boundary, INVALID for decisions): 8.3 t/s
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `mistral-small3.2:24b` — 14.1 GB

- **Suggested verdict:** `investigate-refresh` — only pre-boundary evidence (2 rows before 2026-08-08); re-bench required
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 2 tps rows total (**0 valid** post-boundary, 2 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-28** (44d old) — ⚠ **all pre-boundary**
  - avg TPS (pre-boundary, INVALID for decisions): 8.45 t/s
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `devstral-small-2:latest-ctx8k` — 14.1 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-21** (51d old) — ⚠ **all pre-boundary**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `devstral-small-2:latest` — 14.1 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-devstral-small-2
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-21** (51d old) — ⚠ **all pre-boundary**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `devstral:24b` — 13.3 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-devstral
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-11** (61d old) — ⚠ **all pre-boundary**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k` — 13.3 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `gpt-oss:20b` — 12.8 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-gptoss
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-28** (44d old) — ⚠ **all pre-boundary**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `huihui_ai/qwen3-abliterated:14b-v2` — 8.4 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-qwen3-14b-abliterated
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0` — 8.0 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-foundation-sec-8b-reasoning
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-28** (44d old) — ⚠ **all pre-boundary**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M` — 7.1 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-jackrong-dsv4-9b
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `portal5/gemma4-12b:q4_K_M-ctx8k` — 7.0 GB

- **Suggested verdict:** `investigate-refresh` — only pre-boundary evidence (2 rows before 2026-08-08); re-bench required
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 2 tps rows total (**0 valid** post-boundary, 2 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-28** (44d old) — ⚠ **all pre-boundary**
  - avg TPS (pre-boundary, INVALID for decisions): 11.35 t/s
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M` — 6.9 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-gemma4-12b-agentic
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF:Q4_K_M` — 5.8 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-qwen35-9b-heretic-vision
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `gemma4:e4b-it-qat-ctx8k` — 5.7 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-21** (51d old) — ⚠ **all pre-boundary**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `gemma4:e4b-it-qat` — 5.7 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-gemma4-e4b-qat
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-21** (51d old) — ⚠ **all pre-boundary**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `meta-secalign-8b-q4_k_m:latest` — 4.6 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-meta-secalign-8b
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `dolphin-llama3:8b` — 4.3 GB

- **Suggested verdict:** `investigate-refresh` — only pre-boundary evidence (1 rows before 2026-08-08); re-bench required; pre-boundary closeout signal 'follow-on' in tests/benchmarks/results/omlx_v3_reeval_20260802T221435Z.md — captured under prior stack, re-affirm before treating as authoritative
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 1 tps rows total (**0 valid** post-boundary, 1 invalid pre-boundary) across 3 files
  - newest evidence: **2026-08-02** (9d old) — ⚠ **all pre-boundary**
  - pre-boundary closeout signals (re-affirm before trusting): follow-on
    - `follow-on` in `tests/benchmarks/results/omlx_v3_reeval_20260802T221435Z.md`
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hermes3:8b` — 4.3 GB

- **Suggested verdict:** `investigate-refresh` — only pre-boundary evidence (3 rows before 2026-08-08); re-bench required
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 3 tps rows total (**0 valid** post-boundary, 3 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-10** (62d old) — ⚠ **all pre-boundary**
  - avg TPS (pre-boundary, INVALID for decisions): 35.33 t/s
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `huihui_ai/gemma-4-abliterated:E2b-qat-ctx8k` — 4.1 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `huihui_ai/gemma-4-abliterated:E2b-qat` — 4.1 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-e2b-pentest, bench-exec-reasoning
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/Andycurrent/Mistral-7B-Uncensored-GGUF:Q4_K_M` — 4.1 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-mistral7b-uncensored
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `gemma4:e2b-it-qat-ctx8k` — 4.0 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-21** (51d old) — ⚠ **all pre-boundary**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `gemma4:e2b-it-qat` — 4.0 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-gemma4-e2b
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest evidence: **2026-06-21** (51d old) — ⚠ **all pre-boundary**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M` — 3.8 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-jackrong-dsv4-4b
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `llama3.2:3b-instruct-q8_0-ctx8k` — 3.2 GB

- **Suggested verdict:** `investigate` — post-boundary evidence (tps=31.7, q=1.0, n=1) but no incumbent to compare
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 1 tps rows total (**1 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-09**
  - avg TPS (post-boundary only): **31.7** t/s   (PASS)
  - avg quality_score (post-boundary only): **1.0**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M` — 2.3 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-fastcontext
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `cybersecqwen-4b-toolfix:latest` — 2.3 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-cybersecqwen-4b-toolfix
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `llama3.2:3b` — 1.9 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest evidence: **2026-08-05** (6d old) — ⚠ **all pre-boundary**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF:latest` — 1.3 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** (none — bench-orphaned)
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/Nguuma/security-slm-unsloth-1.5b:latest` — 1.0 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-security-slm-1p5b
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q4_K_M` — 0.7 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-lfm-micro-1p2b
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/LiquidAI/LFM2.5-350M-GGUF:Q4_K_M` — 0.2 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-lfm-micro-350m
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)

## `hf.co/LiquidAI/LFM2.5-230M-GGUF:Q4_K_M` — 0.1 GB

- **Suggested verdict:** `investigate-refresh` — no numeric evidence at all; manual review or re-bench
- **Bench workspaces routing to this tag:** bench-lfm-micro-230m
- **Mined evidence:** 0 tps rows total (**0 valid** post-boundary, 0 invalid pre-boundary) across 3 files
  - newest post-boundary evidence: **2026-08-11**
- **Same-lane incumbent:** (none identified — no matching production module tag)
