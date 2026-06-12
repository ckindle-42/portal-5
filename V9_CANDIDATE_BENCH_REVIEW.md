# V9 Candidate Bench Review — Qwopus3.6-27B-Coder-MTP + Gemma4-12B-Coder-Fable5

**Date:** 2026-06-12
**Task:** TASK_MODEL_EVAL_V9_CANDIDATES
**Version:** 7.5.1

## Pull Results

| Model | Pull Status | Size on Disk |
|---|---|---|
| Qwopus3.6-27B-Coder-MTP Q5_K_M | PASS | 20 GB |
| gemma-4-12B-coder-fable5 Q4_K_M | PASS | 7.4 GB |

Both pulls completed cleanly. The Qwopus Coder-MTP GGUF repo is properly llama.cpp-compatible (unlike the failed v2-MTP base reasoning repo from 2026-06-09).

## Bench Results

### Direct TPS

| Model | Runs | Avg TPS | Min TPS | Max TPS | >=20 TPS? |
|---|---|---|---|---|---|
| gemma-4-12B-coder-fable5 Q4_K_M | 5 | 15.7 | — | — | N |
| Qwopus3.6-27B-Coder-MTP Q5_K_M | 5 | 6.1 | — | — | N |

### Pipeline TPS

| Workspace | Runs | Avg TPS | Smoke Stream |
|---|---|---|---|
| bench-gemma4-12b-coder | 5 | 3.0* | PASS (HTTP 200, routed through old image) |
| bench-qwopus-coder-mtp | 5 | 7.0* | PASS (HTTP 200, routed through old image) |

**\* Stale image caveat:** Pipeline-mode benches ran against the pre-commit Docker image
(31m behind HEAD). The pipeline fell back to `huihui_ai/Qwen3.6-abliterated:27b` for both
new workspaces — the correct `model_hint` entries require a `./launch.sh rebuild` for the
pipeline container to see the new `config/backends.yaml` entries. Direct-mode TPS numbers
above are authoritative (Ollama directly, correct model IDs).

### Comparable fleet models (for context)

| Model | Avg TPS (V8) | SWE-bench | Size |
|---|---|---|---|
| portal5/gemma4-12b:q4_K_M-ctx8k | — | — | ~7.6GB |
| qwen3.6:27b-q4_K_M | — | 77.2% | ~16GB |
| laguna-xs.2:Q4_K_M | — | 68.2% | ~19GB |
| omnicoder2:9b-q4_k_m | — | — | ~5.7GB |

## Promotion Candidates

> **PROMOTE_POLICY: confirm-only. No action taken here. Operator decides.**

### bench-gemma4-12b-coder
- TPS result: 15.7 t/s direct
- Code quality impression: [fill after eval]
- Note: Below the 20 t/s preference, but quality/intent outweighs speed. 12B dense coding specialist with verifiable-Python-CoT training lineage (Composer 2.5 + Fable 5 traces). Distinct training methodology vs all fleet models. 131K ctx.
- Possible lanes: auto-coding fast-path, auto-agentic secondary
- Operator verdict: [ ] Promote  [ ] Hold  [ ] Drop

### bench-qwopus-coder-mtp
- TPS result: 6.1 t/s direct
- Code quality impression: [fill after eval]
- Note: Well below 20 t/s. 27B dense, MTP speculative decoding heads. SWE-bench Verified 67.0%. Qwopus/Trace-Inversion lineage is unique in fleet. However, TPS makes it impractical for interactive lanes. Could serve as a batch/offline coding specialist if code quality is exceptional.
- Possible lanes: auto-coding, auto-agentic
- Operator verdict: [ ] Promote  [ ] Hold  [ ] Drop

## Notes

1. **Pull success:** Both models pulled cleanly. Qwopus Coder-MTP GGUF is properly llama.cpp-compatible — distinct from the failed v2-MTP base repo. Coder-MTP pull confirmation resolves the risk flagged in A1.

2. **Stale Docker image:** The pipeline container must be rebuilt (`./launch.sh rebuild`) before trusting pipeline-mode TPS numbers or running smoke stream against the new workspaces accurately. Direct-mode TPS numbers (Ollama API directly) are authoritative.

3. **Smoke stream:** Both workspaces return HTTP 200 from the pipeline. The stale image routes both to `huihui_ai/Qwen3.6-abliterated:27b` (fallback) rather than the intended models. After rebuild, re-run smoke stream to verify correct model routing.

4. **Rule 6:** 75==75 (was 73, +2 new bench workspaces). All verifications pass.

5. **Unit tests:** All pass (excluding 13 pre-existing PermissionError tests unrelated to this task). Two workspace-count tests updated (73->75). VALID_WORKSPACES in dispatcher.py updated.
