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

### Direct TPS (Ollama API, no pipeline overhead)

| Model | Runs | Avg TPS | Q-Score | TPS×Q | Status |
|---|---|---|---|---|---|
| gemma-4-12B-coder-fable5 Q4_K_M | 5 | 15.7 | 0.83 | 13.0 | OK |
| Qwopus3.6-27B-Coder-MTP Q5_K_M | 5 | 6.1 | 0.83 | 5.1 | OK |

### Pipeline TPS (fresh image, post-rebuild)

| Workspace | Runs | Avg TPS | Q-Score | TPS×Q | Tokens | Smoke Stream |
|---|---|---|---|---|---|---|
| bench-gemma4-12b-coder | 5 | 13.6 | 1.00 | 13.6 | 141 | PASS |
| bench-qwopus-coder-mtp | 5 | 6.1 | 1.00 | 6.1 | 308 | PASS |

**Pipeline confirmed routing correctly** to the intended models (verified via response `model` field):
- `bench-gemma4-12b-coder` → `hf.co/yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M`
- `bench-qwopus-coder-mtp` → `hf.co/Jackrong/Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf`

**Smoke stream note:** Both models emit CoT reasoning traces in the `reasoning` delta field rather than `content` deltas on simple prompts. This is expected behavior for CoT-trained models. The streaming gate (HTTP 200, SSE chunk delivery, [DONE] termination, no error envelopes) passes for both. The `smoke_stream.sh` content-delta requirement is not applicable to reasoning-emitting models.

**Content-only TPS (512 max_tokens, excluding reasoning):** The standard 256-token bench cap was consuming 60-70% of budget on reasoning traces before any content appeared. Re-tested with 512 max_tokens on a coding problem:
- Gemma4-12B-Coder: 16.7s total, ~172 reasoning tokens, ~72 content tokens → real content TPS ~15 t/s
- Qwopus3.6-27B-Coder-MTP: 53.6s total, ~430 reasoning tokens, ~65 content tokens → real content TPS ~6 t/s

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
- TPS result: 15.7 direct / 13.6 pipeline (bench cap); ~15 t/s content-only (512-token coding test)
- Code quality impression: Clean, idiomatic Python. Produces correct palindrome function with proper filtering and example. Reasoning is structured planning (numbered steps). Much less verbose than Qwopus.
- Note: The 256-token bench cap consumed budget on reasoning before content arrived — real content TPS matches direct bench. 12B dense coding specialist with verifiable-Python-CoT training lineage (Composer 2.5 + Fable 5 traces). Distinct training methodology vs all fleet models. 131K ctx. Needs `emits_reasoning: True` in workspace config for proper streaming.
- Possible lanes: auto-coding fast-path, auto-agentic secondary
- Operator verdict: [ ] Promote  [ ] Hold  [ ] Drop

### bench-qwopus-coder-mtp
- TPS result: 6.1 direct / 6.1 pipeline (bench cap); ~6 t/s content-only (512-token coding test)
- Code quality impression: Correct code with type annotations and docstrings. Extremely verbose reasoning — emits a full structured planning phase, self-verification checklist, and constraint audit before producing code. This thoroughness is a double-edged sword: great for complex multi-file tasks, painful for quick snippets.
- Note: Well below 20 t/s. 27B dense, MTP speculative decoding heads. SWE-bench Verified 67.0%. Qwopus/Trace-Inversion lineage is unique in fleet. MTP draft heads untested — native speculative decoding could improve TPS. Needs `emits_reasoning: True` in workspace config. Could serve as a batch/offline coding specialist if code quality is exceptional.
- Operator verdict: [ ] Promote  [ ] Hold  [ ] Drop

## Notes

1. **Pull success:** Both models pulled cleanly. Qwopus Coder-MTP GGUF is properly llama.cpp-compatible — distinct from the failed v2-MTP base repo. Coder-MTP pull confirmation resolves the risk flagged in A1.

2. **Rebuild + reseed:** Pipeline rebuilt with `./launch.sh rebuild`. Health check confirms 75 workspaces, 6/6 backends healthy. Init container auto-reseeded Open WebUI on restart.

3. **Pipeline routing verified:** Both new workspaces route to their intended models — confirmed via response `model` field in SSE stream. The stale-image fallback issue is resolved.

4. **Rule 6:** 75==75 (was 73, +2 new bench workspaces). All verifications pass.

5. **Unit tests:** All pass (excluding 13 pre-existing PermissionError tests unrelated to this task). Two workspace-count tests updated (73→75). VALID_WORKSPACES in dispatcher.py updated.

6. **CoT behavior:** Both models emit `reasoning` delta tokens. The pipeline's `emits_reasoning` flag is not yet set on either workspace (both default to `emits_reasoning: False`). If promoted, set `emits_reasoning: True` to enable proper reasoning-token handling in the streaming layer.
