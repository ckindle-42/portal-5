# V2 Scenario Audit — Bias Check vs UAT Prompts

**Source V2 task**: TASK_CODING_SHOOTOUT_V2.md (commit 4063dfc)
**Source V2 results**: tests/benchmarks/results/coding_shootout_v2_20260513T180038Z.json
**Audit date**: 2026-05-13
**Auditor**: Claude session (portal-5 coding task executor)

## Summary

This audit pairs each V2 scenario with its UAT predecessor (or notes "no UAT predecessor" for regression-guard scenarios) and scores the V2 prompt on three bias axes:

- **Output-format prescription** — Does V2 explicitly demand code block / format that UAT left open?
- **Required-element naming** — Does V2 name elements that V2's assertions then check for, where UAT did not?
- **Algorithm prescription** — Does V2 specify approach where UAT left model latitude?

A scenario hitting 3/3 axes is EASIER than its UAT predecessor. 0/3 is FAITHFUL. 1-2/3 is MIXED. Regression-guard scenarios (UAT-PASS predecessor) are NO COMPARISON.

| Verdict | Count |
|---|---|
| FAITHFUL | 0 |
| MIXED | 7 |
| EASIER | 2 |
| NO COMPARISON | 6 |

**Finding**: None of the 9 V2 scenarios derived from UAT-FAIL predecessors scored FAITHFUL. Every scenario introduces at least one axis of prompt-clarity enhancement over the UAT prompt. Two scenarios (async-http-retry-wrapper, jwt-three-endpoints) score EASIER on all three axes. The dominant bias is output-format prescription (8/9 scenarios), directly addressing Laguna's primary UAT failure mode — producing prose instead of code blocks.

---

## Per-Scenario Audit

### 1. `async-http-retry-wrapper` vs UAT WS-02

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

### 2. `sql-stateful-multi-statement` vs UAT P-D14

**UAT P-D14 status**: FAIL (1/4 with Laguna)
**V2 Laguna result**: PASS

**UAT prompt** (verbatim from line 3614-3616):
> SELECT TOP 3 Username, Role FROM Users ORDER BY CreatedAt DESC;
> INSERT INTO Users (Username, Email, Role) VALUES ('newuser', 'new@lab.local', 'analyst');
> SELECT Username, Role FROM Users WHERE Username = 'newuser';

**V2 prompt** (verbatim from coding_scenarios.yaml):
> You are a SQL terminal. I will give you statements one block at a time.
> Respond as a real PostgreSQL REPL would — show the result of each
> statement (row count, returned rows, or INSERT/UPDATE acks).
>
> Block 1:
>   CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT NOT NULL, role TEXT);
>   INSERT INTO users (username, role) VALUES ('alice', 'analyst'), ('bob', 'admin'), ('carol', 'analyst');
>   SELECT username, role FROM users WHERE role = 'analyst';
>   INSERT INTO users (username, role) VALUES ('newuser', 'analyst');
>   SELECT username FROM users WHERE username = 'newuser';
>
> Show the output of each statement in order, in the format a psql
> terminal would print.

**Axis scores**:
- Output-format prescription: **Y** — V2: "Respond as a real PostgreSQL REPL would — show the result of each statement (row count, returned rows, or INSERT/UPDATE acks)." and "in the format a psql terminal would print." UAT: raw SQL only, no format guidance.
- Required-element naming: **N** — V2 provides different SQL content (CREATE TABLE preamble, different INSERT values) but does not explicitly name assertion-checked strings in a directive manner. The assertion elements ("hello portal"-style equivalents) emerge from the SQL content, not from V2 naming them.
- Algorithm prescription: **N** — No algorithm prescribed. Both are SQL execution tasks.

**Verdict**: MIXED

**Notes**: V2 adds explicit REPL format instructions that UAT omitted. UAT P-D14's `model_slug: "sqlterminal"` likely carried a system prompt setting REPL context, but the user-facing prompt had no format guidance. V2 compensates by moving that context into the prompt text. The UAT failure reason was prose output without row counts — V2's "show the result of each statement" addresses this directly.

---

### 3. `code-review-with-confidence` vs UAT P-D04

**UAT P-D04 status**: FAIL (1/4 with Laguna)
**V2 Laguna result**: FAIL

**UAT prompt** (verbatim from line 3264-3273):
> Audit this Python function completely. Assign confidence level (High/Medium/Low) to each finding:
>
> def merge_configs(base: dict, override: dict) -> dict:
>     result = base
>     for key, val in override.items():
>         if isinstance(val, dict):
>             result[key] = merge_configs(result.get(key, {}), val)
>         else:
>             result[key] = val
>     return result

**V2 prompt** (verbatim from coding_scenarios.yaml):
> Audit this Python function for correctness and security. For each
> issue, label it [HIGH], [MEDIUM], or [LOW] confidence:
>
> ```python
> def merge_configs(base: dict, override: dict) -> dict:
>     result = base
>     for k, v in override.items():
>         if isinstance(v, dict) and k in result:
>             result[k] = merge_configs(result[k], v)
>         else:
>             result[k] = v
>     return result
> ```
>
> List every issue you find. Required elements in your audit:
>   - flag the aliasing/mutation bug (result = base mutates the caller)
>   - flag the unbounded recursion risk
>   - assign a confidence label to each finding
>   - propose a fix for the highest-confidence issue

**Axis scores**:
- Output-format prescription: **Y** — V2: "List every issue you find. Required elements in your audit:" with enumerated bullet points. UAT: "Audit this Python function completely" — open-ended.
- Required-element naming: **Y** — V2 explicitly names "aliasing/mutation bug (result = base mutates the caller)" and "unbounded recursion risk." V2 assertions check for "mutation", "alias", "recursion", "[HIGH]", "fix". V2 tells the model what bugs to flag; UAT requires the model to discover them.
- Algorithm prescription: **N** — Code audit task; no algorithm to prescribe.

**Verdict**: MIXED

**Notes**: V2 names the exact bugs the model must flag. UAT says "Audit completely" without hinting at specific issues. Notably, this scenario still FAILED for Laguna under V2 despite the prompt help — suggesting the model's audit depth is genuinely limited. But the prompt bias is clear: V2's "required elements" section is a checklist that eliminates the discovery burden.

---

### 4. `e2e-playwright-login-test` vs UAT P-B01

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

### 5. `linux-terminal-stateful` vs UAT P-D12

**UAT P-D12 status**: FAIL (2/4 with Laguna)
**V2 Laguna result**: PASS

**UAT prompt** (verbatim from line 3561-3566):
> $ mkdir -p /tmp/portal_test && cd /tmp/portal_test
> $ echo "hello portal" > greet.txt
> $ cat greet.txt
> $ pwd

**V2 prompt** (verbatim from coding_scenarios.yaml):
> You are a Linux terminal. Execute these commands in sequence,
> preserving working-directory and file-system state between them.
> Show only the terminal output for each command — no prose, no code
> blocks, just what the terminal would print.
>
> $ mkdir -p /tmp/portal_test
> $ cd /tmp/portal_test
> $ echo "hello portal" > greeting.txt
> $ cat greeting.txt
> $ pwd
> $ ls -la

**Axis scores**:
- Output-format prescription: **Y** — V2: "Show only the terminal output for each command — no prose, no code blocks, just what the terminal would print." and "preserving working-directory and file-system state between them." UAT: chained shell commands with no format guidance; the `$` prefix is implicit terminal framing.
- Required-element naming: **N** — V2 assertion elements ("hello portal", "/tmp/portal_test", "greeting.txt") are natural outputs of the provided commands. V2 does not name them as explicit requirements separate from the commands themselves.
- Algorithm prescription: **N** — No algorithm prescribed. The commands differ slightly (greet.txt vs greeting.txt, added ls -la) but these are task-content differences, not approach prescriptions.

**Verdict**: MIXED

**Notes**: V2's "preserving working-directory and file-system state" explicitly instructs the model to maintain state — exactly what Laguna failed at in UAT (lost cwd between commands). The UAT placed this burden on the persona's system prompt. V2's "no prose, no code blocks" also addresses the prose-output failure mode.

---

### 6. `python-repl-traceback` vs UAT P-D13

**UAT P-D13 status**: FAIL (1/3 with Laguna)
**V2 Laguna result**: PASS

**UAT prompt** (verbatim from line 3589-3592):
> data = {"name": "Portal", "version": 6}
> items = list(data.items())
> print(f"System: {data['name']} v{data['version']}")
> print(items[5])  # this should fail

**V2 prompt** (verbatim from coding_scenarios.yaml):
> You are a Python 3.11 REPL. Execute these statements one by one,
> printing exactly what the REPL would print after each. No prose,
> no commentary — just the REPL output.
>
> >>> system = "portal v6"
> >>> print(f"System: {system}")
> >>> data = [1, 2, 3]
> >>> print(data[10])

**Axis scores**:
- Output-format prescription: **Y** — V2: "No prose, no commentary — just the REPL output." UAT: raw Python code only; the model must infer REPL behavior from persona context.
- Required-element naming: **N** — V2 assertion elements ("System: portal v6", "IndexError", "Traceback") are natural execution outputs. V2's code is simpler than UAT's (direct string assignment vs dict parsing) — this is a task-simplification difference, not element naming. The model must still execute and produce the REPL output; V2 does not tell the model "include 'IndexError'".
- Algorithm prescription: **N** — Both provide Python code to execute; neither prescribes how.

**Verdict**: MIXED

**Notes**: V2 simplifies the UAT task content (replacing dict + list conversion with simple variable assignment + array access) and adds explicit REPL format instructions. UAT's original code required parsing a dict, converting to list, and formatting a string from dict fields. V2's code requires only string echo and array access. The "no prose" directive directly addresses Laguna's UAT failure (prose explanation instead of REPL output).

---

### 7. `qa-test-enumeration` vs UAT P-D18

**UAT P-D18 status**: FAIL (2/5 with Laguna)
**V2 Laguna result**: PASS

**UAT prompt** (verbatim from line 3704-3707):
> Write a test strategy for a file upload API endpoint: POST /api/v1/files — accepts multipart/form-data, max 10MB, allowed types: PDF/PNG/DOCX. Separate your test cases by type: unit, integration, security, and boundary. Do not claim 'comprehensive coverage' — be specific about what each test covers.

**V2 prompt** (verbatim from coding_scenarios.yaml):
> Design a test plan for a file-upload endpoint with these constraints:
>   - accepts only .pdf, .docx, .xlsx
>   - max file size 10MB
>   - virus-scans via ClamAV before storage
>   - returns 400 on rejection, 201 on success
>
> Enumerate at least 8 distinct test cases, each tagged by category:
>   [SECURITY], [BOUNDARY], [INTEGRATION], [HAPPY-PATH], [ERROR-PATH]
> For each test, specify input, expected output, and rationale.

**Axis scores**:
- Output-format prescription: **Y** — V2: "Enumerate at least 8 distinct test cases, each tagged by category: [SECURITY], [BOUNDARY], [INTEGRATION], [HAPPY-PATH], [ERROR-PATH]. For each test, specify input, expected output, and rationale." UAT: "Separate your test cases by type: unit, integration, security, and boundary." V2's format is far more structured — count minimum, bracket-tag format, per-test field specification.
- Required-element naming: **Y** — V2 introduces bracket-tag notation `[SECURITY]`, `[BOUNDARY]` which assertions check for as literal strings. UAT uses lowercase "security", "boundary" without bracket format. V2 also adds "ClamAV" (assertion-checked) as a concrete element absent from UAT.
- Algorithm prescription: **N** — Task specifications differ (ClamAV, response codes, file types) but these are scenario content differences, not approach prescriptions.

**Verdict**: MIXED

**Notes**: V2 adds a count floor ("at least 8"), bracket-format tagging that exactly matches assertion checks, and per-test field specification. V2 also introduces ClamAV as a concrete security target, making the security test dimension easier to enumerate than UAT's abstract prompt.

---

### 8. `jwt-three-endpoints` vs UAT P-D05

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

**Notes**: Together with async-http-retry-wrapper, this is one of the two scenarios scoring EASIER on all three axes. V2 not only mandates a fenced code block and names assertion-checked elements, but also prescribes the JWT library, token format, and secret-management approach — eliminating design decisions that UAT required the model to make. UAT's FastAPI vs V2's Flask is a framework difference but does not affect the bias analysis (both name a framework).

---

### 9. `e2e-debugger-root-cause` vs UAT P-B04

**UAT P-B04 status**: FAIL (2/3 with Laguna)
**V2 Laguna result**: PASS

**UAT prompt** (verbatim from line 7236):
> My Playwright test `test_login_redirect` fails intermittently. The error is: 'TimeoutError: locator.click: Timeout 30000ms exceeded.' The test clicks a 'Sign In' button that should redirect to /dashboard. It works locally but fails in CI. What's your diagnosis approach?

**V2 prompt** (verbatim from coding_scenarios.yaml):
> A Playwright test fails 10% of runs with "TimeoutError: page.goto
> timeout 30000ms". Logs show the test sometimes hangs on a JS modal,
> sometimes the page loads slowly under CI load. Propose root-cause
> analysis covering BOTH timing-side investigation (timeouts, retries,
> waits) AND browser-side investigation (DOM inspection, console
> errors, network panel).

**Axis scores**:
- Output-format prescription: **N** — Both ask for analysis/diagnosis approach. Neither specifies a structured output format.
- Required-element naming: **Y** — V2 explicitly names "timing-side investigation (timeouts, retries, waits)" and "browser-side investigation (DOM inspection, console errors, network panel)." V2 assertions check for "timeout", "retry", "console", "network", "browser" — all named in the prompt. UAT's "What's your diagnosis approach?" is completely open; the model must devise both investigation dimensions without prompting.
- Algorithm prescription: **N** — V2 names investigation categories but does not prescribe a specific diagnostic algorithm.

**Verdict**: MIXED

**Notes**: The UAT failure was that Laguna identified timing issues but omitted browser inspection. V2's prompt explicitly names both investigation sides and their sub-elements, directly addressing the failure mode. The "10% failure rate" and "JS modal" hints in V2 also narrow the diagnostic space compared to UAT's open-ended scenario.

---

### 10. `js-console-strict-output` (UAT P-D11 — PASS regression guard)

**UAT P-D11 status**: PASS with Laguna
**V2 Laguna result**: PASS

**UAT prompt** (verbatim from line 3521-3524):
> > typeof null
> > [].foo.bar
> > [1,2,3].map(x => x * 2)
> > new Map([["a",1],["b",2]]).get("c")

**V2 prompt** (verbatim from coding_scenarios.yaml):
> You are a strict V8 JavaScript console. Output exactly what each
> statement prints. No prose. No code fences.
>
> > typeof null
> > [].foo
> > [1,2,3].map(x => x * 2)
> > new Map().get('nothing')

**Verdict**: NO COMPARISON

**Notes**: UAT PASS regression guard. Both prompts are structurally very similar — JS console expressions with `>` prefix and explicit "no prose" instructions. The expression content differs (V2 uses `[].foo` and `new Map().get('nothing')` instead of `[].foo.bar` and `new Map([["a",1],["b",2]]).get("c")`), simplifying the Map expression but this is a task-content variation, not a biased rescue. The persona context (javascriptconsole) provides the REPL framing in both cases.

---

### 11. `github-destructive-warning` (UAT P-D09 — PASS regression guard)

**UAT P-D09 status**: PASS with Laguna
**V2 Laguna result**: PASS

**UAT prompt** (verbatim from line 3419):
> I need to undo the last 3 commits on main branch and remove them completely from git history so nobody can ever see them. What is the git command?

**V2 prompt** (verbatim from coding_scenarios.yaml):
> I pushed 3 commits to a shared feature branch but realized they contain a leaked API key. Two teammates have already pulled. What do I do?

**Verdict**: NO COMPARISON

**Notes**: UAT PASS regression guard. Both prompts ask about destructive git operations requiring safety guidance. UAT asks more directly for a destructive command; V2 adds context (leaked API key, teammates pulled) that broadens the response scope beyond a single command. V2 assertions check for "rotate", "force", "teammates", "warning" — the added context (API key leak, teammates) makes these responses more natural. V2's version is arguably a different (more realistic) scenario, not a biased simplification.

---

### 12. `bug-classification-by-type` (UAT P-D02 — PASS regression guard)

**UAT P-D02 status**: PASS with Laguna
**V2 Laguna result**: PASS

**UAT prompt** (verbatim from line 3117):
> Find all issues in this function and classify each by type (Logic Error, Runtime Error, Security Vulnerability, or Performance Issue):
>
> def get_config(env):
>     config = {"dev": {"db": "sqlite"}, "prod": {"db": "postgres"}}
>     cmd = f"load_config --env {env}"
>     os.system(cmd)
>     return config[env]["db"]

**V2 prompt** (verbatim from coding_scenarios.yaml):
> Find every issue in this function. For each, label the type:
>   [SECURITY], [LOGIC], [RUNTIME], [STYLE]
>
> ```python
> def get_user(username):
>     import os
>     result = os.system(f"grep {username} /etc/passwd")
>     users = result.split(",")
>     return users[5]
> ```

**Verdict**: NO COMPARISON

**Notes**: UAT PASS regression guard. Both are bug-classification tasks with category labels. UAT uses prose labels ("Logic Error", "Runtime Error", "Security Vulnerability", "Performance Issue"); V2 uses bracket tags ("[SECURITY]", "[LOGIC]", "[RUNTIME]", "[STYLE]"). V2's code is different (command injection via f-string into os.system). The bracket-tag convention matches the audit document's pattern across multiple V2 scenarios. Both prompts have similar structure — the key difference is task content (different buggy function) rather than prompt-engineering bias.

---

### 13. `code-review-pr-scope` (UAT P-D03 — PASS regression guard)

**UAT P-D03 status**: PASS with Laguna
**V2 Laguna result**: PASS

**UAT prompt** (verbatim from line 3206):
> PR Diff (review only the changed lines marked with +):
>
> def authenticate(username, password):
> - return check_db(username, password)
> + token = jwt.encode({"user": username}, SECRET_KEY, algorithm="HS256")
> + return {"token": token, "expires": 3600}
>
> def check_db(username, password):
>   # unchanged — no modification
>   return db.query(username, password)

**V2 prompt** (verbatim from coding_scenarios.yaml):
> Review only the lines marked CHANGED in this diff. Do not critique unchanged context lines.
>
> ```python
> def login(req):
> -     token = jwt.encode({"user": req.user}, "secret")
> +     token = jwt.encode(  # CHANGED
> +         {"user": req.user, "exp": time.time() + 3600},  # CHANGED
> +         SECRET_KEY,  # CHANGED
> +         algorithm="HS256",  # CHANGED
> +     )
>         check_db()  # unchanged context
>         return token
> ```

**Verdict**: NO COMPARISON

**Notes**: UAT PASS regression guard. Both prompts present a unified diff with "+" markers and explicit scope instructions ("review only the changed lines"). UAT uses "-"/"+" line prefixes; V2 uses inline "# CHANGED" comments and "# unchanged context" annotations. The scope-discipline instruction is equivalent in both. V2's diff adds the `exp` claim and `SECRET_KEY` changes — richer review material but conceptually the same task shape.

---

### 14. `k8s-manifest-complete` (UAT P-D07 — PASS regression guard)

**UAT P-D07 status**: PASS with Laguna
**V2 Laguna result**: PASS

**UAT prompt** (verbatim from line 3377):
> Generate a Kubernetes Deployment manifest for a Python FastAPI app. Image: ghcr.io/myorg/api:v1.2.3, port 8000, 2 replicas, readiness probe on /health, resource limits 512Mi/0.5CPU.

**V2 prompt** (verbatim from coding_scenarios.yaml):
> Provide a complete Kubernetes manifest (Deployment + Service) for
> a Python web service with these requirements:
>   - image: myorg/webapp pinned to tag v1.2.3
>   - readiness probe on /health
>   - resource limits: 512Mi memory, 0.5 CPU
>   - 3 replicas
>   - rolling update strategy
>   - includes a `kubectl rollout undo` command in a comment for
>     rollback reference
>
> Single fenced code block. Complete YAML, no placeholders.

**Verdict**: NO COMPARISON

**Notes**: UAT PASS regression guard. UAT asks for a Deployment; V2 asks for Deployment + Service (broader scope). UAT specifies 2 replicas, V2 specifies 3. V2 adds rolling update and rollback comment requirements. V2's "Single fenced code block" directive is an output-format prescription that UAT lacks, but since this is a PASS regression guard (the original test passed), the format prescription doesn't rescue a failure — it's a different task framing. The core requirements (image pin, readiness probe, resource limits) are present in both.

---

### 15. `creative-particle-system` (UAT P-D20 — PASS regression guard)

**UAT P-D20 status**: PASS with Laguna
**V2 Laguna result**: PASS

**UAT prompt** (verbatim from line 3827):
> Make me a particle system visualizer. Particles should emit from wherever I click, fan outward with randomized velocity and color, fade out over their lifetime, and respect gravity. Keyboard: [Space] to toggle gravity on/off, [C] to clear all particles.

**V2 prompt** (verbatim from coding_scenarios.yaml):
> Build a self-contained HTML file with a canvas particle system:
> particles emit on space-bar, fall with gravity, fade out over 2
> seconds. Vanilla JS, no libraries. Ship it as one file, ready to
> open in a browser. Don't ask clarifying questions.

**Verdict**: NO COMPARISON

**Notes**: UAT PASS regression guard. Both are creative-coding particle system tasks. Key differences: UAT says "emit from wherever I click" with "[Space] to toggle gravity on/off, [C] to clear" — more interactive specification. V2 says "emit on space-bar, fall with gravity, fade out over 2 seconds" — simpler interaction model (emit on keypress vs click position). V2 adds "Don't ask clarifying questions" and "Ship it as one file" — both present in UAT assertions implicitly. UAT's "has_code" assertion is non-critical, recognizing creative personas may narrate. V2 simplifies the interaction model but both are PASS cases for Laguna.

---

## What This Tells Us

### Scenarios from UAT-FAIL predecessors (9 of 15)

Of the 9 scenarios that test Laguna's response to tasks it previously failed:

- **0 FAITHFUL** — None of the 9 V2 prompts match UAT difficulty. Every scenario introduces at least one axis of prompt-clarity enhancement.
- **7 MIXED** — The majority add output-format prescription (fenced code block, "no prose") with occasional element naming. These help the model produce the right output shape but don't fully engineer around the failure mode.
- **2 EASIER** — `async-http-retry-wrapper` and `jwt-three-endpoints` introduce all three bias types, effectively prompt-engineering around the original failure modes.

**Implication**: V2's 94.1% Laguna aggregate is not a clean measurement of whether the "system prompt was the hidden variable" — because V2's prompts are systematically clearer than UAT's. The V2 prompts tell the model what format to use, what elements to include, and (in two cases) what algorithm to follow. The UAT prompts left these decisions to the model. The fact that Laguna scored higher under V2 is at least partially attributable to V2's prompt clarity, not to the system-prompt framing change.

The two scenarios that FAILED under V2 despite prompt help (`code-review-with-confidence`, `e2e-playwright-login-test`) are notable: these are the Audit and Composite shape scenarios where Laguna may genuinely lack depth regardless of prompt clarity.

### Scenarios from UAT-PASS predecessors (6 of 15)

These regression guards serve as stability checks. All 6 passed for Laguna under V2, confirming no regression. No unexpected behavior observed. Two notes:

- `creative-particle-system`: V2 simplifies the interaction model (space-bar emission vs click-position emission, drops gravity toggle and clear-key), but since both pass this doesn't represent a bias concern.
- `k8s-manifest-complete`: V2 broadens scope (adds Service manifest, rolling update, rollback comment) and mandates a fenced code block — an output-format prescription that UAT didn't have. Since UAT passed without format prescription, this is a task-scope change rather than a rescued failure.

### Bias-axis distribution

| Axis | Fired count (of 9 UAT-FAIL) |
|---|---|
| Output-format prescription | 8 |
| Required-element naming | 5 |
| Algorithm prescription | 2 |

**Output-format prescription dominates** (8/9 scenarios). V2 consistently adds "fenced code block," "no prose," or explicit output structure requirements. This is the most consequential finding: Laguna's primary UAT failure mode was producing prose instead of code blocks. Adding "fenced code block" directly addresses this failure, and V2 does so in nearly every scenario. **If output-format prescription is responsible for most of V2's score improvement, then the "system prompt" hypothesis is not what V2 measured — what V2 measured is that Laguna produces better code when told to produce code.**

**Required-element naming fires in 5 of 9** — V2 often names specific libraries, APIs, or bugs that assertions check for. In `code-review-with-confidence`, V2 literally lists the bugs the model should find. This coupling between prompt and assertion creates a tautology: the prompt says "include X," the assertion checks for X, the model passes. This is not a capability measurement.

**Algorithm prescription is rare (2 of 9)** — Only `async-http-retry-wrapper` and `jwt-three-endpoints` prescribe approach. These two are also the only EASIER scenarios (3/3 axes). This suggests that algorithm prescription is the axis that tips MIXED scenarios into the EASIER category.

### Caveats

- **System prompt vs user prompt**: UAT tests use persona system prompts to set REPL/role context. V2 scenarios bake some of that context into the user prompt text. Where V2 says "You are a SQL terminal" and UAT relies on the sqlterminal persona's system prompt, the prompts are structurally different — but the V2 approach is more explicit. This audit scores the explicit V2 instructions against the UAT user prompt, which may overstate the bias for REPL-role scenarios (items 2, 5, 6). A more precise comparison would incorporate UAT persona system prompts.

- **Task content changes**: Several V2 scenarios introduce different task content (e.g., different SQL statements, different Python code, ClamAV in qa-test-enumeration). These content changes may independently affect difficulty. The audit focuses on prompt framing (format, element naming, algorithm) rather than task-content difficulty.

- **UAT P-B04 (e2e-debugger-root-cause) is the cleanest comparison** — it's the only FAIL-predecessor scenario where V2 does NOT add output-format prescription. V2 adds only required-element naming (explicitly listing investigation categories). This scenario passed for Laguna. It's the closest to a "FAITHFUL" comparison but the required-element naming still biases it.

- **Two FAIL cases under V2**: `code-review-with-confidence` and `e2e-playwright-login-test` both failed despite V2 prompt enhancements. These failures are the strongest evidence that Laguna genuinely struggles on Audit and Composite shape tasks, regardless of prompt clarity. They act as a partial negative control: if V2 were purely prompt-engineering, these would pass too.
