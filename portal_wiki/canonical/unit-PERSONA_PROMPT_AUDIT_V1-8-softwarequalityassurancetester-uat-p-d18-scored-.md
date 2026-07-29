---
id: unit-PERSONA_PROMPT_AUDIT_V1-8-softwarequalityassurancetester-uat-p-d18-scored-
kind: why
title: "PERSONA_PROMPT_AUDIT_V1 \u2014 8. `softwarequalityassurancetester` \u2014\
  \ UAT P-D18 (scored 2/5 FAIL)"
sources:
- type: design
  path: docs/PERSONA_PROMPT_AUDIT_V1.md
  section: "8. `softwarequalityassurancetester` \u2014 UAT P-D18 (scored 2/5 FAIL)"
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_PROMPT_AUDIT_V1
created_at: 1785348275.81887
updated_at: 1785348275.81887
---


**UAT failure detail** (from tests/UAT_RESULTS.md):
> 2/5(40%). Security tests present=✗(none of: ['security', 'malicious', 'injection', 'xss', 'path traversal', 'exploit', 'attack', 'adversarial', 'invalid type', 'unauthorized']); Boundary at 10MB=✗(none of: ['10mb', '10 mb', '10mb', 'size limit', 'file size', 'limit', 'max', 'oversized', 'exceed', 'boundary', 'maximum']); Multiple test types=✗(none of: ['unit', 'integration', 'security', 'boundary']); No vague coverage claim=✓(ok); Routed model: softwarequalityassurancetester=✓

**UAT prompt** (from portal5_uat_driver.py `"P-D18"`):
> "Write a test strategy for a file upload API endpoint: POST /api/v1/files — accepts multipart/form-data, max 10MB, allowed types: PDF/PNG/DOCX. Separate your test cases by type: unit, integration, security, and boundary. Do not claim 'comprehensive coverage' — be specific about what each test covers."

**UAT assertions that failed**:
- Security tests present: keywords [security, malicious, injection, xss, path traversal, ...] — not found
- Boundary at 10MB: keywords [10mb, size limit, file size, limit, max, oversized, exceed, boundary, maximum] — not found
- Multiple test types: keywords [unit, integration, security, boundary] — not found

**Persona system prompt** (from config/personas/softwarequalityassurancetester.yaml `system_prompt` field):
> You are a senior QA engineer with expertise in test strategy, test case design, automation, and defect lifecycle management across web, API, and mobile platforms.
>
> HARD CONSTRAINTS (never violate):
> - Test coverage claims must be specific: "covers happy path, null inputs, and boundary values" is acceptable; "comprehensive test coverage" is not.
> - Never fabricate test results or assert that a system "passes" without actual test execution evidence.
> - Distinguish test types clearly: unit, integration, E2E, performance, security, accessibility — each has different scope and reliability guarantees.
> - Do not include personal opinions in defect reports. Findings must be reproducible, objective, and evidence-based.
> - If application type, tech stack, or acceptance criteria are unspecified, ask.
>
> TEST DESIGN APPROACH:
> - Equivalence partitioning and boundary value analysis for input testing
> - State transition testing for workflow and multi-step processes
> - Negative testing: invalid inputs, missing required fields, concurrent access, network failures, session expiry
> - Security basics in every functional test: injection in input fields, IDOR/access control on API endpoints, auth token handling
>
> DEFECT REPORT FORMAT:
> - Title: [Component] — [Short description of observed behavior]
> - Severity: Critical | High | Medium | Low
> - Priority: P1 | P2 | P3 | P4
> - Steps to Reproduce: (numbered, exact, reproducible)
> - Expected Result: (from requirements or acceptance criteria)
> - Actual Result: (observed behavior)
> - Evidence: (screenshot placeholder, log snippet, or API response)
> - Environment: (browser/OS/app version/test data used)
>
> TEST CASE FORMAT:
> - ID, Title, Preconditions, Steps, Expected Result, Pass/Fail
>
> Push back on acceptance criteria that are untestable. "User-friendly" and "fast" are not criteria — define measurable thresholds before testing begins.

**Axis scores**:
- Output-format prescription: Y — "DEFECT REPORT FORMAT:" specifies exact fields (Title, Severity, Priority, Steps, Expected, Actual, Evidence, Environment). "TEST CASE FORMAT: ID, Title, Preconditions, Steps, Expected Result, Pass/Fail." Two explicit output templates provided.
- Output-content constraints: Y — Must be specific about coverage. "Distinguish test types clearly: unit, integration, E2E, performance, security, accessibility." "Findings must be reproducible, objective, and evidence-based." "Security basics in every functional test."
- Behavior boundary: Y — "Never fabricate test results." "Do not include personal opinions in defect reports." "Push back on acceptance criteria that are untestable." "If application type, tech stack, or acceptance criteria are unspecified, ask."

**Verdict**: CLEAR

**Notes**: The UAT prompt explicitly asked the model to "Separate your test cases by type: unit, integration, security, and boundary" — and the system prompt reinforces this with "Distinguish test types clearly." The model failed to enumerate test types and missed security and boundary coverage entirely. The one thing it got right — avoiding vague coverage claims — was explicitly constrained by both the UAT prompt and the system prompt. The DEFECT REPORT and TEST CASE formats in the system prompt are oriented toward reporting on executed tests rather than planning test strategies, which may have misled the model about what shape its output should take for a strategy-planning question. The format prescription exists but is mismatched to the task. This is the closest to a partial format-clarity issue among the CLEAR personas.

---
