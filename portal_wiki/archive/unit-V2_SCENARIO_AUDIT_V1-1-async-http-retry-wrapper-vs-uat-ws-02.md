---
id: unit-V2_SCENARIO_AUDIT_V1-1-async-http-retry-wrapper-vs-uat-ws-02
kind: why
title: "V2_SCENARIO_AUDIT_V1 \u2014 1. `async-http-retry-wrapper` vs UAT WS-02"
sources:
- type: design
  path: docs/V2_SCENARIO_AUDIT_V1.md
  section: 1. `async-http-retry-wrapper` vs UAT WS-02
last_generated_commit: ''
confidence: high
tags:
- docs
- V2_SCENARIO_AUDIT_V1
created_at: 1783195000.922687
updated_at: 1783195000.922687
---


**UAT WS-02 status**: FAIL (1/6 with Laguna)
**V2 Laguna result**: PASS

**UAT prompt** (verbatim from line 3041-3046):
> Write a Python async HTTP retry wrapper using httpx.AsyncClient. Requirements: exponential backoff with jitter, max 3 retries, retry only on 429/500/502/503/504 status codes, configurable timeout. Include type hints, docstring, and a usage example.

**V2 prompt** (verbatim from coding_scenarios.yaml):
> Write an async Python function `fetch_with_retry(url, max_attempts=3)` that uses httpx.AsyncClient. It must:
>   - retry on HTTP 429, 500, 502, 503, 504
>   - use exponential backoff with asyncio.sleep (start 1s, double each retry)
>   - return the response body on success, raise on exhaustion
>   - use full type hints
>
> Provide the function in a single fenced code block. No prose outside the code block.

**Axis scores**:
- Output-format prescription: **Y** — V2: "Provide the function in a single fenced code block. No prose outside the code block." UAT: no format constraint; model was free to mix prose and code.
- Required-element naming: **Y** — V2 names `asyncio.sleep` which the V2 assertion checks for. UAT says "exponential backoff with jitter" (no specific sleep primitive). V2 names `httpx.AsyncClient` (assertion checks). UAT also names `httpx.AsyncClient` — overlap, but V2 adds `asyncio.sleep`.
- Algorithm prescription: **Y** — V2: "exponential backoff with asyncio.sleep (start 1s, double each retry)." UAT: "exponential backoff with jitter" — model must determine schedule and whether to add jitter (V2 drops jitter entirely).

**Verdict**: EASIER

**Notes**: This is the canonical example from the task brief. V2 removes the jitter requirement, prescribes exact backoff schedule, mandates a fenced code block, and forbids prose. The UAT's open format is precisely why Laguna scored 1/6 (prose, no code block).

---
