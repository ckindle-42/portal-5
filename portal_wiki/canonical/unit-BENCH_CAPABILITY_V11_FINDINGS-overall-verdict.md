---
id: unit-BENCH_CAPABILITY_V11_FINDINGS-overall-verdict
kind: why
title: "BENCH_CAPABILITY_V11_FINDINGS \u2014 Overall verdict"
sources:
- type: design
  path: docs/BENCH_CAPABILITY_V11_FINDINGS.md
  section: Overall verdict
last_generated_commit: ''
confidence: high
tags:
- docs
- BENCH_CAPABILITY_V11_FINDINGS
created_at: 1783195000.827682
updated_at: 1783195000.827682
---


**AgentWorld's production status is NOT vindicated by the V11 re-test.** The V10 scores weren't purely format-bias — AgentWorld shows real capability weaknesses:

- C3 envsim: 0.33 vs laguna 1.00 (significant gap on its signature capability)
- C4 SWE: competitive (0.56 vs qwen3-coder 0.67) but inconsistent

**Recommendation:** Keep AgentWorld's current production status unchanged (auto-agentic secondary, auto-agentic-lite primary) pending further investigation. The V11 harness confirms that format-bias was PART of the V10 story but not the whole story — the capability gap is real and warrants a separate operator decision task with more probes run.
