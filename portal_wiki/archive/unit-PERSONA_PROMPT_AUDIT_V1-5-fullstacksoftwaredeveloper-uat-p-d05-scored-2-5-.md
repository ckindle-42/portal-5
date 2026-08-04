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
created_at: 1785348275.81886
updated_at: 1785348275.81886
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
> - Do not generate production-style code for a stack you have not confirmed: if framework versions, database choice, or deployment target are unspecified, ask.
> - If required context is missing, state: "Insufficient context — needed: [frontend framework, backend language/framework, database, auth requirements, deployment target]."
>
> OUTPUT FORMAT (priority order — ship the highest-priority sections first; drop lower-priority sections if response budget is tight):
> 1. Implementation (MANDATORY — full, working code in fenced blocks, one per file)
> 2. Security considerations (MANDATORY when auth or data handling is involved)
> 3. Architecture overview (one paragraph; skip if obvious from the code)
> 4. Component breakdown (skip if implementation is one or two files)
> 5. Testing approach (skip if not asked)

**Axis scores**:
- Output-format prescription: Y — "OUTPUT FORMAT (priority order): 1. Implementation (MANDATORY — full, working code in fenced blocks, one per file) 2. Security considerations (MANDATORY...) 3. Architecture overview 4. Component breakdown 5. Testing approach." Explicit section structure with mandatory/optional designations.
- Output-content constraints: Y — Must include fenced code blocks for every file. Must implement auth securely (JWT, refresh, session invalidation). Must pin dependency versions. No hardcoded secrets. Must confirm stack before generating code.
- Behavior boundary: Y — "Never produce authentication or authorization code without implementing it securely." "Do not generate production-style code for a stack you have not confirmed." "Push back on insecure patterns even if they are simpler." (from RESPONSE APPROACH section).

**Verdict**: CLEAR

**Notes**: Another crystal-clear contract. The first HARD CONSTRAINT literally says "YOUR RESPONSE IS INCOMPLETE WITHOUT FENCED CODE BLOCKS." Yet the model produced prose about the architecture without code blocks and only covered the /auth/login endpoint. The model correctly avoided hardcoded secrets (the one assertion it passed) but failed on code delivery and completeness. This is not a contract gap — the contract explicitly prioritizes code over prose.

---
