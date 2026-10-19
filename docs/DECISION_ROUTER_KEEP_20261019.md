# Decision: keep the auto-router classifier (2026-10-19)

The auto-router stays on `hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M-ctx2k`
(LLM_ROUTER_MODEL). Operator requirement: the router must be uncensored. This model is
uncensored and the best measured.

## How it was measured

`scripts/router_bench.py` calls the production classifier path directly: the real prompt
(`routing._build_router_prompt`) and payload (temperature 0, grammar-enforced JSON, 64-token
cap, num_ctx 2048), changing only the model. Each candidate classified all 45 prompts in
`tests/wfe/suites/routing_production.jsonl`: 14 security, 9 coding, 9 compliance, 9 SPL,
2 creative, 2 research. The router's model is a pipeline env, so a WFE campaign cannot swap
it. A reply after the 2000 ms deadline falls back to keyword routing in production, so it
counts as a miss. Rows: `tests/benchmarks/results/router_bench_20261019.json`.

| Classifier | Correct | Within 2 s | Median | Uncensored |
|---|---|---|---|---|
| gemma-4-E4B-OBLITERATED (current) | 44/45 | 44/45 | 675 ms | yes |
| MiniCPM5-2B (stock) | 44/45 | 44/45 | 329 ms | no |
| MiniCPM5-2B-heretic | 42/45 | 42/45 | 319 ms | yes |
| granite-4.2-8b-heretic | 44/45 | 44/45 | 1253 ms | yes |

All four produced valid JSON on every prompt. The current router got all 14 security prompts
right. MiniCPM5-2B is about 350 ms faster but censored; its heretic build loses accuracy
(missed a coding and a security prompt).

## The shared miss

Every model routed `route-research-00` to auto-daily. The prompt asks for "a fact-based
public-health brief with harm-reduction facts on recognizing opioid overdose…". It carries no
research or web signal, and auto-daily's description covers writing and summarization, so
the route is defensible. This is a debatable suite label, not a router defect.
