---
id: unit-V2_SCENARIO_AUDIT_V1-8-jwt-three-endpoints-vs-uat-p-d05
kind: why
title: "V2_SCENARIO_AUDIT_V1 \u2014 8. `jwt-three-endpoints` vs UAT P-D05"
sources:
- type: design
  path: docs/V2_SCENARIO_AUDIT_V1.md
  section: 8. `jwt-three-endpoints` vs UAT P-D05
last_generated_commit: ''
confidence: high
tags:
- docs
- V2_SCENARIO_AUDIT_V1
created_at: 1783195000.924624
updated_at: 1783195000.924624
---


**UAT P-D05 status**: FAIL (2/5 with Laguna)
**V2 Laguna result**: PASS

**UAT prompt** (verbatim from line 3301):
> Implement a FastAPI JWT authentication flow: POST /auth/login returns access + refresh tokens, GET /protected requires valid access token, POST /auth/refresh exchanges a refresh token for a new access token. Show the complete implementation.

**V2 prompt** (verbatim from coding_scenarios.yaml):
> Implement three Flask endpoints in a single Python file:
>   - POST /auth/login — accepts {username, password}, returns JWT
>   - GET /protected — requires Authorization: Bearer <token>
>   - POST /auth/refresh — refreshes a near-expiring token
>
> Use python-jose for JWT, include an `exp` claim (1 hour), read the
> secret from os.environ (never hardcode). Provide the complete file
> in a single fenced code block.

**Axis scores**:
- Output-format prescription: **Y** — V2: "Provide the complete file in a single fenced code block." UAT: "Show the complete implementation" — open to prose+code mixed output.
- Required-element naming: **Y** — V2 names "os.environ" (assertion checks), "exp" claim (assertion checks), "/auth/login", "/protected", "/auth/refresh" (assertion checks all three). UAT names the three endpoints but does not specify environment-variable secret handling, token expiry, or the specific JWT library.
- Algorithm prescription: **Y** — V2: "Use python-jose for JWT" (library prescription), "include an `exp` claim (1 hour)" (token-format prescription), "read the secret from os.environ (never hardcode)" (secret-management prescription). UAT: none of these — model must choose library, token format, and secret strategy independently.

**Verdict**: EASIER

**Notes**: Together with async-http-retry-wrapper, this is one of the two scenarios scoring EASIER on all three axes. V2 not only mandates a fenced code block and names assertion-checked elements, but also prescribes the JWT library, token format, and secret-management approach — eliminating design d
