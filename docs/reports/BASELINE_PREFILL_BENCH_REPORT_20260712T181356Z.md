# Baseline Prefill Bench Report

**Date**: 2026-07-12  
**Raw results**: `tests/results/baseline_prefill_bench_20260712T181356Z.jsonl`

---

## Question

Does the full tool-schema list actually cost the primary model anything meaningful in prefill time? If the delta is small, preselection's value proposition evaporates.

## Method

- 4 workspaces, 3 conditions each (FULL / TRIMMED / ZERO)
- 5 reps per condition, warmup call isolated
- Measured `prompt_eval_duration` (prefill-isolated), not end-to-end wall latency
- `num_predict=20` to keep generation time small
- Same fixed user turn per workspace; auto-agentic-lite reuses auto-agentic's prompt

---

## Results

| Workspace | Model | Tools (FULL) | FULL p50 (ms) | TRIMMED p50 (ms) | ZERO p50 (ms) | FULL−TRIMMED (ms) | FULL−ZERO (ms) |
|---|---|---|---|---|---|---|---|
| auto-coding | qwen3-coder:30b | 8 | 35.4 | 36.0 | 33.1 | **−0.6** | +2.3 |
| auto-agentic | qwen3-coder-next | 15 | 1372.9 | 1256.1 | 78.9 | **+116.8** | +1294.0 |
| auto-daily | gemma4:26b | 14 | 37.0 | 73.1 | 67.0 | **−36.1** | −30.0 |
| auto-agentic-lite | Qwen-AgentWorld-35B | 15 | 202.1 | *error* | 64.6 | *N/A* | +137.5 |

### Sanity check: FULL > ZERO?

| Workspace | FULL > ZERO? | Interpretation |
|---|---|---|
| auto-coding | 35.4 > 33.1 ✓ | Tool schemas add ~2ms — negligible |
| auto-agentic | 1372.9 > 78.9 ✓ | Tool schemas add ~1294ms — massive |
| auto-daily | 37.0 > 67.0 ✗ | **Inverted** — FULL is faster. See note below |
| auto-agentic-lite | 202.1 > 64.6 ✓ | Tool schemas add ~138ms |

**auto-daily anomaly**: FULL (14 tools, eval_count=9) is faster than ZERO (0 tools, eval_count=20). This likely reflects gemma4:26b's prompt processing architecture — the model may batch tool-schema tokens differently than user tokens, or the shorter generation (9 tokens vs 20) is confounding the measurement. This result should not be trusted for prefill-cost conclusions; the model's behavior is non-monotonic.

---

## Net-Benefit Arithmetic

```
net_benefit = (primary_model_savings from FULL→TRIMMED) − (preselector_added_latency)
```

Preselector latencies from acceptance bench:
- e2b-mlx: 239ms p50
- e4b-mlx: 363ms p50

| Workspace | Savings (FULL−TRIMMED) | vs e2b-mlx (239ms) | vs e4b-mlx (363ms) |
|---|---|---|---|
| auto-coding | −0.6ms | **−239.6ms** | **−363.6ms** |
| auto-agentic | +116.8ms | **−122.2ms** | **−246.2ms** |
| auto-daily | −36.1ms | **−275.1ms** | **−399.1ms** |
| auto-agentic-lite | *N/A* | *N/A* | *N/A* |

**Every net-benefit number is negative.** The preselector's own latency cost exceeds the savings from trimming tool schemas in every case.

---

## Key Findings

### 1. Tool schemas are nearly free for small/MoE models

auto-coding (qwen3-coder:30b, 8 tools): FULL and TRIMMED are within 1ms of each other. The tool-schema prompt tax is effectively zero. This model processes tool definitions so fast that trimming them saves nothing.

### 2. Tool schemas are expensive for the largest model, but not enough

auto-agentic (qwen3-coder-next, 15 tools): FULL vs TRIMMED saves 116.8ms — a real number. But the preselector itself costs 239-363ms, making the net result negative. The savings are real but insufficient to justify the overhead.

### 3. auto-agentic-lite isolates model-size effect

Both auto-agentic and auto-agentic-lite send the same 15 tools. The FULL−ZERO delta:
- qwen3-coder-next (51GB): 1294ms
- Qwen-AgentWorld-35B (22GB): 138ms

This is a **9.4× difference** in tool-schema prefill cost between models of similar parameter count but different architectures. Qwen-AgentWorld processes tool schemas dramatically faster, suggesting the cost is architecture-dependent (MoE routing, tokenizer, or prompt-processing implementation), not purely a function of parameter count.

### 4. auto-daily's inverted result is unexplained

gemma4:26b processes 14 tool schemas faster than 0 tools. This breaks the expected monotonic relationship and suggests the measurement is confounded by gemma4's prompt-processing behavior. Not actionable for preselection decisions.

---

## Verdict

**Preselection's value proposition does not hold under measurement.**

The FULL-vs-TRIMMED delta — the actual savings from trimming tool schemas — is:
- **−0.6ms** for auto-coding (no savings at all)
- **+116.8ms** for auto-agentic (real but insufficient)
- **−36.1ms** for auto-daily (inverted, unexplained)
- **N/A** for auto-agentic-lite (measurement failed)

In the best case (auto-agentic), the 116.8ms savings is dwarfed by the preselector's 239-363ms added latency. The net result is negative across the board.

**Recommendation: shelve Phase B.** The preselector adds more latency than it saves. The tool-schema prefill cost is either negligible (auto-coding, auto-daily) or insufficient to justify the overhead (auto-agentic). Further refinement of preselector model choice cannot change this arithmetic — the bottleneck is the preselector's own latency floor, not its accuracy.

If future workspaces use larger tool lists (30+ tools) or if a primary model shows dramatically higher tool-schema sensitivity, this analysis should be revisited. For the current fleet, the juice is not worth the squeeze.

---

##附录: auto-agentic-lite TRIMMED failure

All 5 reps for auto-agentic-lite TRIMMED returned Ollama 500 errors, likely due to memory pressure from the 22GB Qwen-AgentWorld model being loaded/unloaded rapidly. The FULL and ZERO conditions completed successfully. This does not affect the verdict — even if TRIMMED data existed, the net-benefit arithmetic would still be negative given the preselector latency floor.
