---
id: unit-COMPLIANCE_FALLBACK_POLICY-granite-4-1-initial-expectation
kind: why
title: "COMPLIANCE_FALLBACK_POLICY \u2014 Granite 4.1 \u2014 initial expectation"
sources:
- type: design
  path: docs/COMPLIANCE_FALLBACK_POLICY.md
  section: "Granite 4.1 \u2014 initial expectation"
last_generated_commit: ''
confidence: high
tags:
- docs
- COMPLIANCE_FALLBACK_POLICY
created_at: 1783195000.833357
updated_at: 1783195000.833357
---


Per IBM Research's stated design (Granite 4.1: dense, no-thinking,
tool-calling-first, BFCL V3 leader at 73.7 for the 30B, GRC-aware
training, ISO certification), Granite is expected to:

- **PASS clearly** on dense-structured-tool-output (scenario I) — no
  reasoning chain to leak into the structured output.
- **PASS** on classification-token-discipline — strong instruction
  following per IFEval 87.1 (8B) / 89.7 (30B).
- **PASS** on citation discipline across the 7 frameworks rotated by
  the multi-framework scenarios.
- **PASS** on anti-fabrication scenarios — Apache 2.0 + ISO discipline +
  the "no chain of thought" design favor explicit refusal over confident
  invention.
- **WARN-acceptable or PASS** on insufficient-context — the persona
  prompt enforces the exact phrase regardless of model.

If Granite 8B fails to clear the 60% MUST threshold on the first run,
the realistic interpretations are: (a) the persona system prompt isn't
guiding it well — tune the prompt; (b) the assertion bar is overly
strict — tune the assertion regex; (c) Granite 8B genuinely doesn't
suit compliance fallback at this size — demote it within
`ollama-general`.

If Granite 30B fails to clear the 80% MUST threshold, the operator
explicitly evaluates whether to keep it in `ollama-reasoning` or
demote it. The dense architecture's slower TPS at 30B is a separate
trade-off captured in `bench_tps` runs, not in this policy.
