---
id: unit-PERSONA_PROMPT_AUDIT_V1-3-e2etestauthor-uat-p-b01-scored-2-5-fail
kind: why
title: "PERSONA_PROMPT_AUDIT_V1 \u2014 3. `e2etestauthor` \u2014 UAT P-B01 (scored\
  \ 2/5 FAIL)"
sources:
- type: design
  path: docs/PERSONA_PROMPT_AUDIT_V1.md
  section: "3. `e2etestauthor` \u2014 UAT P-B01 (scored 2/5 FAIL)"
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_PROMPT_AUDIT_V1
created_at: 1785348275.8188531
updated_at: 1785348275.8188531
---


**UAT failure detail** (from tests/UAT_RESULTS.md):
> 2/5(40%). Playwright selectors=✗(none of: ['getbyrole', 'getbylabel', 'getbytext', 'locator', 'page.goto']); Happy path present=✗(none of: ['success', 'dashboard', 'redirect', 'expect', 'visible']); Error path present=✓(found: ['error']); Code block present=✗(no code block); Routed model: e2etestauthor=✓

**UAT prompt** (from portal5_uat_driver.py `"P-B01"`):
> "Write a Playwright test for a login page: POST /login accepts email+password, redirects to /dashboard on success, shows error toast on failure. Include both happy-path and error-path tests."

**UAT assertions that failed**:
- Playwright selectors: keywords ["getbyrole", "getbylabel", "getbytext", "locator", "page.goto"] — not found
- Happy path present: keywords ["success", "dashboard", "redirect", "expect", "visible"] — not found
- Code block present: no code block found

**Persona system prompt** (from config/personas/e2etestauthor.yaml `system_prompt` field):
> You generate Playwright end-to-end tests from natural-language descriptions. You think in terms of user journeys, not individual clicks.
>
> When given a feature description:
> 1. Identify the user journey to test (signup flow, form submission, navigation path, etc.)
> 2. Break it into testable steps with assertions
> 3. Generate a complete Playwright test file (TypeScript) with:
>    - Proper page object patterns
>    - Explicit waits (not arbitrary timeouts)
>    - Accessibility-based selectors — ALWAYS use these, never CSS selectors or XPath:
>      * page.getByRole('button', { name: 'Submit' })
>      * page.getByLabel('Email address')
>      * page.getByText('Dashboard')
>      * page.getByPlaceholder('Enter password')
>      * locator.locator('form').getByRole('textbox')
>    - Descriptive test names that document expected behavior
>    - Both happy-path and edge-case tests
>
> You use the browser tools to explore live pages and inspect their accessibility trees. This helps you write accurate selectors and understand the real DOM structure.
>
> Your test code should be production-ready: no TODOs, no placeholders, no "add your selector here."

**Axis scores**:
- Output-format prescription: N — The prompt says "Generate a complete Playwright test file (TypeScript) with: [list of characteristics]" but never specifies that the response must be ONLY a fenced code block, or that code must precede prose, or any explicit format instruction. The characteristics describe what the code should contain, not how the reply should be structured.
- Output-content constraints: Y — Must include Playwright selectors (specifically accessibility-based: getByRole, getByLabel, getByText, getByPlaceholder), explicit waits, descriptive test names, both happy-path and edge-case tests. "Production-ready: no TODOs, no placeholders."
- Behavior boundary: Y — "ALWAYS use these [accessibility-based selectors], never CSS selectors or XPath" is an explicit restrictively-bounded behavioral rule. "Your test code should be production-ready: no TODOs, no placeholders, no 'add your selector here'" is a clear output boundary.

**Verdict**: PARTIAL

**Notes**: The prompt knows WHAT the output should contain (Playwright code with specific selector types, both test paths) but never says HOW to format the reply (fenced code block, no prose, etc.). The model produced prose that mentioned error paths but didn't generate a code block or include Playwright primitives. The format gap here is plausible as a contributing factor: if the prompt had said "Reply ONLY with the test file in a fenced TypeScript code block, no prose," the model might have been forced to output code that would have triggered the selector and code-block assertions.

---
