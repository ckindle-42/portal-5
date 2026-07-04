---
id: unit-V2_SCENARIO_AUDIT_V1-4-e2e-playwright-login-test-vs-uat-p-b01
kind: why
title: "V2_SCENARIO_AUDIT_V1 \u2014 4. `e2e-playwright-login-test` vs UAT P-B01"
sources:
- type: design
  path: docs/V2_SCENARIO_AUDIT_V1.md
  section: 4. `e2e-playwright-login-test` vs UAT P-B01
last_generated_commit: ''
confidence: high
tags:
- docs
- V2_SCENARIO_AUDIT_V1
created_at: 1783195000.9235158
updated_at: 1783195000.9235158
---


**UAT P-B01 status**: FAIL (2/5 with Laguna)
**V2 Laguna result**: FAIL

**UAT prompt** (verbatim from line 7090):
> Write a Playwright test for a login page: POST /login accepts email+password, redirects to /dashboard on success, shows error toast on failure. Include both happy-path and error-path tests.

**V2 prompt** (verbatim from coding_scenarios.yaml):
> Write a Playwright test in JavaScript (NOT TypeScript) that tests
> a login form at https://example.com/login. The test must:
>   - use getByRole/getByLabel selectors (NOT CSS or XPath)
>   - cover one happy path (correct credentials → redirect to /dashboard)
>   - cover one error path (wrong password → error message visible)
>   - use page.goto, expect, and async/await
>
> Provide the complete .spec.js file in a single fenced code block.

**Axis scores**:
- Output-format prescription: **Y** — V2: "Provide the complete .spec.js file in a single fenced code block." UAT: no format constraint (the assertion `has_code` is non-critical).
- Required-element naming: **Y** — V2 names "getByRole/getByLabel selectors", "page.goto", "expect" — all checked by V2 assertions. UAT does not name specific Playwright selectors; UAT assertion checks for ANY Playwright selector keyword in a broader set.
- Algorithm prescription: **N** — Both describe task content (happy path, error path); neither specifies algorithmic approach.

**Verdict**: MIXED

**Notes**: Same pattern — V2 adds fenced-code-block directive and names specific Playwright APIs. This scenario also FAILED under V2 for Laguna (despite the prompt help), mirroring code-review-with-confidence. Both failures are in the Composite and Audit shapes, where Laguna may genuinely struggle regardless of prompt clarity.

---
