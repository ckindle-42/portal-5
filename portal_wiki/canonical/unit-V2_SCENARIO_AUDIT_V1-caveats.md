---
id: unit-V2_SCENARIO_AUDIT_V1-caveats
kind: why
title: "V2_SCENARIO_AUDIT_V1 \u2014 Caveats"
sources:
- type: design
  path: docs/V2_SCENARIO_AUDIT_V1.md
  section: Caveats
last_generated_commit: ''
confidence: high
tags:
- docs
- V2_SCENARIO_AUDIT_V1
created_at: 1783195000.9275572
updated_at: 1783195000.9275572
---


- **System prompt vs user prompt**: UAT tests use persona system prompts to set REPL/role context. V2 scenarios bake some of that context into the user prompt text. Where V2 says "You are a SQL terminal" and UAT relies on the sqlterminal persona's system prompt, the prompts are structurally different — but the V2 approach is more explicit. This audit scores the explicit V2 instructions against the UAT user prompt, which may overstate the bias for REPL-role scenarios (items 2, 5, 6). A more precise comparison would incorporate UAT persona system prompts.

- **Task content changes**: Several V2 scenarios introduce different task content (e.g., different SQL statements, different Python code, ClamAV in qa-test-enumeration). These content changes may independently affect difficulty. The audit focuses on prompt framing (format, element naming, algorithm) rather than task-content difficulty.

- **UAT P-B04 (e2e-debugger-root-cause) is the cleanest comparison** — it's the only FAIL-predecessor scenario where V2 does NOT add output-format prescription. V2 adds only required-element naming (explicitly listing investigation categories). This scenario passed for Laguna. It's the closest to a "FAITHFUL" comparison but the required-element naming still biases it.

- **Two FAIL cases under V2**: `code-review-with-confidence` and `e2e-playwright-login-test` both failed despite V2 prompt enhancements. These failures are the strongest evidence that Laguna genuinely struggles on Audit and Composite shape tasks, regardless of prompt clarity. They act as a partial negative control: if V2 were purely prompt-engineering, these would pass too.
