---
id: unit-PERSONA_PROMPT_AUDIT_V1-5-fullstacksoftwaredeveloper-uat-p-d05-scored-2-5-
kind: why
title: "PERSONA_PROMPT_AUDIT_V1 \u2014 5. `fullstacksoftwaredeveloper` \u2014 UAT\
  \ P-D05 (scored 2/5 FAIL)"
sources:
- type: design
  path: docs/PERSONA_PROMPT_AUDIT_V1.md
  section: "5. `fullstacksoftwaredeveloper` \u2014 UAT P-D05 (scored 2/5 FAIL)"
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_PROMPT_AUDIT_V1
created_at: 1783195000.8856032
updated_at: 1783195000.8856032
---


**UAT failure detail** (from tests/UAT_RESULTS.md):
> 2/5(40%). All 3 endpoints=✗(missing: ['/auth/login', '/protected', '/auth/refresh']); exp claim present=✗(none of: ['exp', 'expiry', 'expiration', 'expires', 'expire', 'ttl']); No hardcoded secret=✓(ok); Code block present=✗(no code block); Routed model: fullstacksoftwaredeveloper=✓

**UAT prompt** (from portal5_uat_driver.py `"P-D05"`):
> "Implement a FastAPI JWT authentication flow: POST /auth/login returns access + refresh tokens, GET /protected requires valid access token, POST /auth/refresh exchanges a refresh token for a new access token. Show the complete implementation."

**UAT assertions that failed**:
- All 3 endpoints: keywords ["/auth/login", "/protected", "/auth/refresh"] — missing "/protected" and "/auth/refresh"
- exp claim present: keywords ["exp", "expiry", "expiration", "expires", "expire", "ttl"] — not found
- Code block present: no code block found

**Persona system prompt** (from config/personas/fullstacksoftwaredeveloper.yaml `system_prompt` field):
> You are a senior fullstack software developer with expertise spanning frontend, backend, database design, API architecture, and security-first development practices.
>
> HARD CONSTRAINTS (never violate):
> - YOUR RESPONSE IS INCOMPLETE WITHOUT FENCED CODE BLOCKS for every implementation file requested. Architecture overview and component breakdown are scaffolding — drop them if you are running long. The user wants working code, not a design document.
> - Never produce authentication or authorization code without implementing it securely: JWT handling, token storage, refresh flows, and session invalidation all have common pitfalls — call them out.
> - Pin dependency versions in all generated package manifests. Floating versions are a maintenance and security liability.
> - Never hardcode secrets, API keys, or environment-specific values — always use environment variables.
> - Do not generate production-style code for a stack you have not confir
