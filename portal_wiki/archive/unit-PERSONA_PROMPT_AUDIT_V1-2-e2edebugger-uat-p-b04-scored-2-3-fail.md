---
id: unit-PERSONA_PROMPT_AUDIT_V1-2-e2edebugger-uat-p-b04-scored-2-3-fail
kind: why
title: "PERSONA_PROMPT_AUDIT_V1 \u2014 2. `e2edebugger` \u2014 UAT P-B04 (scored 2/3\
  \ FAIL)"
sources:
- type: design
  path: docs/PERSONA_PROMPT_AUDIT_V1.md
  section: "2. `e2edebugger` \u2014 UAT P-B04 (scored 2/3 FAIL)"
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_PROMPT_AUDIT_V1
created_at: 1785348275.818849
updated_at: 1785348275.818849
---


**UAT failure detail** (from tests/UAT_RESULTS.md):
> 2/3(66%). Timing issue suspected=✓(found: ['timeout']); Browser inspection suggested=✗(none of: ['snapshot', 'browser', 'inspect', 'navigate', 'reproduce', 'accessibility']); Routed model: e2edebugger=✓

**UAT prompt** (from portal5_uat_driver.py `"P-B04"`):
> "My Playwright test `test_login_redirect` fails intermittently. The error is: 'TimeoutError: locator.click: Timeout 30000ms exceeded.' The test clicks a 'Sign In' button that should redirect to /dashboard. It works locally but fails in CI. What's your diagnosis approach?"

**UAT assertions that failed**:
- Browser inspection suggested: keywords ["snapshot", "browser", "inspect", "navigate", "reproduce", "accessibility"] — not found

**Persona system prompt** (from config/personas/e2edebugger.yaml `system_prompt` field):
> You debug failing end-to-end tests by reproducing the failure in a live browser. You combine code analysis with live browser inspection.
>
> When given a failing test:
> 1. Read the test code and the error message
> 2. Navigate to the page being tested
> 3. Reproduce the steps manually using browser tools
> 4. Identify the root cause (selector changed, timing issue, data dependency, flaky assertion)
> 5. Propose a fix with the specific code change
>
> You are especially good at:
> - Timing issues (race conditions, animations, lazy loading)
> - Selector brittleness (CSS selectors that break on UI changes)
> - Data state issues (test depends on specific DB state)
> - Cross-browser differences (test passes in Chrome, fails in Firefox)
>
> You always explain WHY the test failed, not just HOW to fix it.

**Axis scores**:
- Output-format prescription: N — The numbered steps describe a debugging process, not how the model should format its reply. No requirement for code blocks, section headers, bullet format, or any structural output contract.
- Output-content constraints: Y — "You always explain WHY the test failed, not just HOW to fix it." "Propose a fix with the specific code change." These mandate specific content in every response.
- Behavior boundary: N — The numbered steps are a procedural description of the task approach, not a guardrail. The closest thing to a boundary ("You debug failing end-to-end tests by reproducing the failure in a live browser") is a task identity statement, not a "do not X" or restrictively-bounded rule.

**Verdict**: WEAK

**Notes**: This persona has the weakest format contract of all 9, yet paradoxically achieved the highest UAT score (66%). The one failed assertion — "browser inspection suggested" — is a content gap, not a format failure. The system prompt does tell the model to "Navigate to the page" and "Reproduce the steps manually using browser tools" but the model didn't translate those procedural steps into response content mentioning browser inspection. This is the only case where the format-clarity hypothesis partially holds: a stronger format contract (e.g., "structure your response as: Diagnosis → Root Cause → Fix, with explicit mention of browser tools used") might have forced the browser inspection keywords into the output.

---
