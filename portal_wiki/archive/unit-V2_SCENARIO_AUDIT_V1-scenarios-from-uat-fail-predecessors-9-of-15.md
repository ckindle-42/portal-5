---
id: unit-V2_SCENARIO_AUDIT_V1-scenarios-from-uat-fail-predecessors-9-of-15
kind: why
title: "V2_SCENARIO_AUDIT_V1 \u2014 Scenarios from UAT-FAIL predecessors (9 of 15)"
sources:
- type: design
  path: docs/V2_SCENARIO_AUDIT_V1.md
  section: Scenarios from UAT-FAIL predecessors (9 of 15)
last_generated_commit: ''
confidence: high
tags:
- docs
- V2_SCENARIO_AUDIT_V1
created_at: 1783195000.926773
updated_at: 1783195000.926773
---


Of the 9 scenarios that test Laguna's response to tasks it previously failed:

- **0 FAITHFUL** — None of the 9 V2 prompts match UAT difficulty. Every scenario introduces at least one axis of prompt-clarity enhancement.
- **7 MIXED** — The majority add output-format prescription (fenced code block, "no prose") with occasional element naming. These help the model produce the right output shape but don't fully engineer around the failure mode.
- **2 EASIER** — `async-http-retry-wrapper` and `jwt-three-endpoints` introduce all three bias types, effectively prompt-engineering around the original failure modes.

**Implication**: V2's 94.1% Laguna aggregate is not a clean measurement of whether the "system prompt was the hidden variable" — because V2's prompts are systematically clearer than UAT's. The V2 prompts tell the model what format to use, what elements to include, and (in two cases) what algorithm to follow. The UAT prompts left these decisions to the model. The fact that Laguna scored higher under V2 is at least partially attributable to V2's prompt clarity, not to the system-prompt framing change.

The two scenarios that FAILED under V2 despite prompt help (`code-review-with-confidence`, `e2e-playwright-login-test`) are notable: these are the Audit and Composite shape scenarios where Laguna may genuinely lack depth regardless of prompt clarity.
