---
id: unit-p5-roadmap-p5-fut-013-omlx-evaluation-canceled
kind: what
title: "P5_ROADMAP \u2014 P5-FUT-013: OMLX Evaluation \u2014 PROCEED to Phase 1"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: docs/reports/OMLX_DECISION.md
- type: code
  path: tests/benchmarks/results/omlx_v3_reeval_20260802T221435Z.md
last_generated_commit: 10c7734f3f87df5a9d525bb5c1f3970c96a73a91
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.592072
updated_at: 1784946220.592072
---

P5-FUT-013 evaluated oMLX as a candidate inference engine and is superseded by
Phase 1 integration. `OMLX_DECISION.md` records the decision chain: the
2026-04-25 bake-off RETIRED oMLX because KV-cache persistence was not functional
(warm TTFT slower than cold); the 2026-05-28 re-evaluation (v0.3.12) kept it
retired but cleared MTP speedup past the 1.5x gate; and the 2026-08-02 six-gate
re-evaluation (v0.5.4) passed every gate — KV-cache warm TTFT speedup on
agentic-length prefixes, decode 1.32-1.46x over production GGUF (2.2-2.5x with
Lightning MTP), Qwen/Gemma tool calling, grammar with one reproducible gemma
livelock edge, and batching 1.6-3.1x with zero failures — producing the decision
PROCEED to Phase 1 dual-backend. Full results are in
`tests/benchmarks/results/omlx_v3_reeval_20260802T221435Z.md`. Phase 1 is visible
in `config/backends.yaml`, which registers the `omlx` backend type and two
backends: `omlx-local` (holding group, no routing reference) and `omlx-coding`
(the live `group: coding` candidate with `priority: 10` and aliases). Per the
decision doc, Ollama remains the sole production engine until Phase 1 lands.

## Why

The oMLX path flipped from RETIRE to PROCEED because part of the original verdict
was a methodology artifact: the paged KV cache works in 256-token blocks, so
short prefixes never show a warm-cache win. Re-measuring on agentic-length
prefixes cleared the cancel trigger, and the dual-backend decision registers
oMLX in `config/backends.yaml` without disturbing production routing —
evidence before promotion, the same rule the bench fleet follows.
