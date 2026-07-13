# Bench Capability V11 Findings — AgentWorld Re-Test

**Date:** 2026-06-30  
**Task:** TASK_BENCH_METHODOLOGY_V11  
**Harness:** `tests/benchmarks/bench_capability.py` (capability-oriented, reasoning-stripping, execution-verified)

## Methodology fixes applied

| V10 Problem | V11 Fix |
|---|---|
| `_strip_think()` missed bare-prose reasoning ("Thinking Process:", "The user wants...") | `extract_final_answer()` strips tagged AND bare-prose reasons preambles, finds first answer boundary |
| `max_tokens=512` truncated reasoning models before answer | Reasoning-aware budgets: 8192 for `emits_reasoning` workspaces, 4096 otherwise |
| Probes scored format, not capability | `format_score` and `capability_score` reported separately |
| Single-shot probes blind to multi-turn agentic loop | Multi-turn agentic loop (C1) with planted error for recovery observation |
| Keyword bingo ("merge_intervals", "bottleneck") | Execution-based: code runs against unit tests; tcpdump parsed structurally; numeric answers checked |
| One prompt per category | 3 prompts per capability + held-out variants |

## Per-probe results

### C3 — Environment Simulation (3 prompts: seq, ls, df)

| Workspace | format_score | capability_score |
|---|---|---|
| bench-laguna (production IDE default) | 1.00 | **1.00** |
| bench-qwen3-coder-30b (production coder) | 1.00 | 0.67 |
| bench-agentworld | 1.00 | 0.33 |

**Call: REAL capability gap.** AgentWorld trails both baseline models on envsim. With reasoning preambles stripped and fair token budgets, AgentWorld correctly formatted its answers (format=1.00) but the actual simulated outputs were less accurate than laguna's (cap=1.00) and qwen3-coder's (cap=0.67). The V10 hypothesis that "reasoning preamble caused the low score" is NOT the full story — even with the fixed harness, AgentWorld underperforms on this capability.

### C4 — SWE Diagnosis (3 prompts: tcpdump filter construction)

| Workspace | format_score | capability_score |
|---|---|---|
| bench-laguna (production IDE default) | 1.00 | 0.22 |
| bench-qwen3-coder-30b (production coder) | 1.00 | 0.67 |
| bench-agentworld | 0.67 | 0.56 |

**Call: harness helped but capability gap still present.** AgentWorld's format_score of 0.67 (vs 1.00 for baselines) suggests it occasionally fails to produce the requested plan/fence structure even after preamble stripping. Its capability_score of 0.56 beats laguna (0.22) but trails qwen3-coder (0.67). The V10 score of 2.0/5.0 was partly format-bias (now fixed) but the capability signal is real and mixed — AgentWorld is competitive on tcpdump filter quality but inconsistent on answer structure.

## quality_signals verifier upgrade

The coding and reasoning categories now have optional verifier callables:

| Category | Verifier method | Old approach |
|---|---|---|
| coding | Execute `merge_intervals` against unit tests | Keyword match on `def merge_intervals`, `list`, `tuple`, `intervals.sort`, `merged`, `overlap` |
| reasoning | Check numeric answer (bottleneck value ~2.29/hr, mention of beds) | Keyword match on `(bottleneck, capacity)`, `doctor`, `nurse`, `bed`, `(wait, arrival)`, `(minute, hour)` |

**Contrast test result:** A correct-but-differently-worded merge_intervals implementation now scores 1.0 (was 0.0 in keyword-only mode). A keyword-stuffed-but-wrong implementation now scores 0.0 (was 1.0 before). The fix is working.

## Overall verdict

**AgentWorld's production status is NOT vindicated by the V11 re-test.** The V10 scores weren't purely format-bias — AgentWorld shows real capability weaknesses:

- C3 envsim: 0.33 vs laguna 1.00 (significant gap on its signature capability)
- C4 SWE: competitive (0.56 vs qwen3-coder 0.67) but inconsistent

**Recommendation:** Keep AgentWorld's current production status unchanged (auto-agentic secondary, auto-agentic-lite primary) pending further investigation. The V11 harness confirms that format-bias was PART of the V10 story but not the whole story — the capability gap is real and warrants a separate operator decision task with more probes run.

## Harness quality

All 16 capability_lib unit tests pass (including V10 AgentWorld excerpt regression fixtures). All 9 quality_signals verifier tests pass. The V11 harness itself is trustworthy — the scores it produces measure actual model capability, not format compliance against regex patterns.
