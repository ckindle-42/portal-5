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
created_at: 1783195000.886365
updated_at: 1783195000.886365
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
> - Do not include personal opinions i
