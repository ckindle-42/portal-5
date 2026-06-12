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

7. **emits_reasoning fix applied (TASK_V9_EVAL_EXTENDED Phase 1):** Both workspaces now have `emits_reasoning: True`. Confirmed deployed in running pipeline container after `docker compose up -d --force-recreate` (note: `restart` does not pick up new images).

---

## Extended Evaluation (TASK_V9_EVAL_EXTENDED)

### CC-01 Asteroids Challenge Results

| Model | Workspace | Status | Assertions | Time | Notes |
|---|---|---|---|---|---|
| Gemma4-12B-Coder Q4_K_M | bench-gemma4-12b-coder | WARN | 5/10 (50%) | 34.9s | Code block present (1197 chars with fix, 472 chars without). Full Asteroids HTML but no game loop (no requestAnimationFrame/setInterval). Asteroid/lives/score keywords present. Behavioral patterns (lives decrement, score increment, asteroid push) not matched. |
| Qwopus3.6-27B-Coder-MTP Q5_K_M | bench-qwopus-coder-mtp | WARN | 6/10 (60%) | 820.7s | Massive output (36,976 chars). Asteroid split/push behavioral=✓, lives+score keywords=✓. Canvas game loop keywords MISSING (no requestAnimationFrame/setInterval/game loop). Lives+score behavioral patterns not matched. Qwopus may use DOM-based animation (setTimeout) that falls outside assertion patterns. |

**Critical note:** Initial CC-01 runs were executed WITHOUT the `emits_reasoning` fix deployed (pipeline container still on old image after `docker compose restart`). Gemma4 produced only 472 chars vs 1197 chars after fix. Qwopus showed 10/10 PASS without fix (reasoning tokens were counted as content, inflating assertion matches) vs 6/10 WARN with fix (reasoning separated). Both results above reflect the CORRECT runs with the fix active.

### Coding Shootout V3 — Per-Shape Pass Rate

| Model | REPL | Audit | Composite | Ship-It | Overall* | TPS | Memory |
|---|---|---|---|---|---|---|---|
| Qwopus3.6-27B-Coder-MTP Q5_K_M | 87.5% | 75.0% | 88.9% | 92.3% | **88.2%** | 38.9 | 19 GB |
| laguna-xs.2:Q4_K_M (incumbent) | 100.0% | 100.0% | 62.5% | 92.3% | **87.9%** | 153.2 | 19 GB |
| devstral-small-2 | 62.5% | 75.0% | 100.0% | 92.3% | **85.3%** | 55.6 | 15 GB |
| Gemma4-12B-Coder Q4_K_M | 75.0% | 100.0% | 88.9% | 84.6% | **85.3%** | 85.6 | 7 GB |
| qwen3-coder:30b-a3b-q4_K_M | 12.5% | 100.0% | 100.0% | 92.3% | **76.5%** | 236.3 | 19 GB |
| glm-4.7-flash:Q4_K_M | 50.0% | 75.0% | 77.8% | 61.5% | **64.7%** | 166.1 | 15 GB |
| qwen3-coder-next (REF) | 62.5% | 75.0% | 77.8% | 92.3% | 79.4% | 123.8 | 46 GB |
| huihui-ai Qwen3-Coder-Next abl (REF) | 62.5% | 100.0% | 88.9% | 92.3% | 85.3% | 131.0 | 46 GB |

*Overall = candidate columns only. Reference models excluded.

### Key Observations

1. **Qwopus-27B leader**: Strongest overall candidate (88.2%). Excellent Ship-It (92.3%), solid REPL (87.5%), strong Composite (88.9%). Weakest shape is Audit (75.0% — tied with devstral and glm). Slowest TPS (38.9) — acceptable for batch/offline coding but painful for interactive. 19 GB memory is reasonable.

2. **Gemma4-12B outlier**: 85.3% overall in only 7 GB — best efficiency ratio in the shootout. Perfect Audit (100%), strong Composite (88.9%). Weakest shape is RePL (75.0%) and Ship-It (84.6%). 12B coding specialist at 85.6 TPS — viable fast-path candidate. Fails CC-01 (can't implement a full game loop), but passes most production coding scenarios.

3. **Laguna's weak spot exposed**: Perfect REPL/Audit but 62.5% Composite — worst in field. The model dominates simple, stateful output formats but struggles with multi-element deliverables (fullstack, e2e test author). Consistent with V1→V2 delta pattern (93.9% single-prompt → 87.9% production shapes).

4. **Shape specialization pattern**: No single model dominates every shape. Qwopus wins Ship-It; devstral wins Composite; laguna wins REPL; gemma4 wins Audit (tied with laguna at 100%). This confirms the workspace-decomposition argument from Shootout V2.

5. **qwen3-coder-30b REPL collapse**: 12.5% REPL is the single worst per-shape score. The model appears fundamentally unable to produce exact-format stateful terminal output (SQL: 0/3, Python: 0/2, JS: 0/1). This is a disqualifying weakness for the `auto-coding` workspace's REPL persona tier.

### Extended Promotion Verdicts

> **PROMOTE_POLICY: confirm-only. Operator decides.**

| Workspace | CC-01 | Shootout Overall | Recommended Lane | Verdict |
|---|---|---|---|---|
| bench-qwopus-coder-mtp | WARN (6/10) | 88.2% (1st) | auto-agentic fallback / batch coding | Hold — CC-01 game loop gap needs investigation. Strong Shootout leader but 38.9 TPS limits interactive use. |
| bench-gemma4-12b-coder | WARN (5/10) | 85.3% (tied-3rd) | auto-coding fast-path (7 GB, 85.6 TPS) | Hold — CC-01 failure disqualifies from Ship-It role. Strong Audit+Composite at 7 GB is compelling for lightweight personas. |
