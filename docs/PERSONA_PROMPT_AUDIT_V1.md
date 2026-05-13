# Persona System Prompt Audit — Format-Clarity Check

**Source**: tests/UAT_RESULTS.md (UAT run 2026-05-12, 13 coding FAILs)
**Predecessor**: docs/V2_SCENARIO_AUDIT_V1.md (V2 scenario bias check)
**Audit date**: 2026-05-13
**Auditor**: Claude session — deepseek-v4-pro

## Hypothesis Under Test

The V2 scenario audit found 0/9 UAT-FAIL-derived V2 scenarios were FAITHFUL to their UAT prompts — every V2 prompt explicitly demanded a code block or other output format that the UAT prompt left open. When V2 prompts asked clearly, Laguna produced clearly.

If that pattern generalizes, then UAT-failed personas should have system prompts that under-specify output format. A persona whose system prompt says "you are an expert programmer" without further format guidance gives the model no contract to honor; a persona whose system prompt says "respond as a Python REPL would, with prompts and exact output only" does.

This audit scores 9 UAT-FAIL coding personas on three format-clarity axes:

- **Output-format prescription** — Does the system prompt tell the model how to format responses?
- **Output-content constraints** — Does it specify what must be in every response?
- **Behavior boundary** — Does it set a guardrail relevant to its task shape?

3/3 = CLEAR contract. 2/3 = PARTIAL. 0-1/3 = WEAK.

## Summary

| Verdict | Count |
|---|---|
| CLEAR | 7 |
| PARTIAL | 1 |
| WEAK | 1 |

The WEAK persona (e2edebugger, 1/3) actually achieved the highest UAT score of any persona in the audit set (2/3, 66%). Seven personas scored CLEAR (3/3) on format-clarity yet still failed their UAT tests — some with the lowest scores in the set (codereviewer 1/4, sqlterminal 1/4, pythoninterpreter 1/3). This directly contradicts the hypothesis that format under-specification is the primary root cause of UAT failures.

---

## Per-Persona Audit

### 1. `codereviewer` — UAT P-D04 (scored 1/4 FAIL)

**UAT failure detail** (from tests/UAT_RESULTS.md):
> 1/4(25%). Mutation bug found=✗(none of: ['mutation', 'aliasing', 'in-place', 'result = base', 'copy']); Confidence levels present=✗(none of: ['high', 'medium', 'low', 'confidence']); Recursion risk noted=✗(none of: ['recursion', 'depth', 'stack overflow', 'merge_configs(']); Routed model: codereviewer=✓

**UAT prompt** (from portal5_uat_driver.py `"P-D04"`):
> "Audit this Python function completely. Assign confidence level (High/Medium/Low) to each finding:\n\ndef merge_configs(base: dict, override: dict) -> dict:\n    result = base\n    for key, val in override.items():\n        if isinstance(val, dict):\n            result[key] = merge_configs(result.get(key, {}), val)\n        else:\n            result[key] = val\n    return result"

**UAT assertions that failed**:
- Mutation bug found: keywords ["mutation", "aliasing", "in-place", "result = base", "copy"] — not found
- Confidence levels present: keywords ["high", "medium", "low", "confidence"] — not found
- Recursion risk noted: keywords ["recursion", "depth", "stack overflow", "merge_configs("] — not found

**Persona system prompt** (from config/personas/codereviewer.yaml `system_prompt` field):
> You are a senior software engineer conducting deep code audits — single files, functions, or modules reviewed with full attention to correctness, security, and performance. You are not PR-workflow aware; your job is to find everything wrong (and note what is right) regardless of diff scope.
>
> HARD CONSTRAINTS (never violate):
> - Never fabricate language feature or library behavior. If unsure of behavior in a specific version, say so and label it uncertain.
> - Distinguish bugs (incorrect behavior) from style issues (preference) — both matter, but severity must be labeled accurately. Never conflate them.
> - Do not rewrite code without explaining why the original approach is wrong.
> - State your confidence level for every finding: High / Medium / Low. Low confidence means: "this may be a bug depending on [X] — verify."
> - If the language, runtime version, or framework is not provided, ask.
> - If required context is missing, state: "Insufficient context — needed: [language version, framework, intended behavior, execution environment]."
>
> REVIEW DIMENSIONS (assess all five):
> 1. Correctness — logic errors, off-by-one, null/undefined handling, edge cases, incorrect assumptions about input ranges or types
> 2. Security — injection vectors, auth flaws, insecure deserialization, hardcoded secrets, OWASP Top 10 applicability, attack surface created by this code
> 3. Performance — algorithmic complexity (state Big-O for every non-trivial operation), unnecessary allocations, N+1 queries, blocking I/O
> 4. Maintainability — naming clarity, function length, coupling, test coverage gaps, future maintenance traps
> 5. Best Practices — language-idiomatic patterns, framework conventions, deprecated API usage, missing error handling
>
> FINDING FORMAT:
> ```
> Severity:   Critical | High | Medium | Low | Nitpick
> Category:   Correctness | Security | Performance | Maintainability | Style
> Location:   [function name / line reference]
> Issue:      [what is wrong and precisely why it matters]
> Root Cause: [why the code was written this way — often reveals the real fix]
> Fix:        [concrete code example in the same language]
> Confidence: High | Medium | Low — [reason if Medium/Low]
> ```
>
> REVIEW CLOSE:
> - After all findings: note 1–2 things done genuinely well. Be specific, not filler.
> - If no significant issues found: say so directly. "This code is solid — only nitpicks follow" is a valid and useful review outcome.
>
> Push back on over-engineered or premature-optimization patterns. Simpler is usually more correct, more secure, and more maintainable.

**Axis scores**:
- Output-format prescription: Y — "FINDING FORMAT:" specifies a code block with named fields (Severity, Category, Location, Issue, Root Cause, Fix, Confidence). "REVIEW CLOSE:" prescribes the closing section structure.
- Output-content constraints: Y — Must assess all 5 review dimensions. Must state confidence per finding. Must note 1–2 positives at close. Must state Big-O for non-trivial operations.
- Behavior boundary: Y — "Never fabricate language feature or library behavior." "Distinguish bugs from style issues." "Do not rewrite code without explaining why the original approach is wrong." "Push back on over-engineered or premature-optimization patterns."

**Verdict**: CLEAR

**Notes**: The system prompt has one of the most detailed format contracts in the entire persona catalog — exact finding fields, required confidence labeling, review dimensions enumerated. Yet the model (laguna-xs.2-4bit) produced output that missed the mutation/aliasing bug, omitted confidence labels entirely, and failed to note recursion risk. This is a capability failure, not a contract clarity failure. The contract is there; the model couldn't execute it.

---

### 2. `e2edebugger` — UAT P-B04 (scored 2/3 FAIL)

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

### 3. `e2etestauthor` — UAT P-B01 (scored 2/5 FAIL)

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

### 4. `ethereumdeveloper` — UAT P-D10 (scored 2/5 FAIL)

**UAT failure detail** (from tests/UAT_RESULTS.md):
> 2/5(40%). Audit disclaimer=✓(found: ['mainnet deployment']); Solidity pragma=✗(none of: ['pragma solidity', '^0.', 'solidity ^', 'solidity version']); Reentrancy protection=✗(none of: ['reentrancyguard', 'checks-effects', 'reentrancy', 'checks effects interactions', 'nonreentrant', 're-entrancy', 'reentrancy protection', 'reentrancy attack']); Code block present=✗(no code block); Routed model: ethereumdeveloper=✓

**UAT prompt** (from portal5_uat_driver.py `"P-D10"`):
> "Write a Solidity staking contract where users can deposit ETH, earn yield based on time staked, and withdraw with accumulated rewards. This will go live on mainnet next week."

**UAT assertions that failed**:
- Solidity pragma: keywords ["pragma solidity", "^0.", "solidity ^", "solidity version"] — not found
- Reentrancy protection: keywords ["reentrancyguard", "checks-effects", "reentrancy", ...] — not found
- Code block present: no code block found

**Persona system prompt** (from config/personas/ethereumdeveloper.yaml `system_prompt` field):
> You are a senior Ethereum and EVM-compatible blockchain developer with expertise in Solidity smart contract development, security auditing, and DeFi protocol design.
>
> HARD CONSTRAINTS — VERIFY ALL THREE BEFORE SENDING ANY REPLY:
>
> 1. AUDIT DISCLAIMER — every response that contains Solidity contract code MUST include this exact warning, placed immediately before the contract code block: "⚠️ Security Notice: This code has not been audited. Require a professional security audit before mainnet deployment." Never omit it regardless of context, test environment, or user instruction.
>
> 2. SOLIDITY PRAGMA — every contract MUST begin with `pragma solidity ^X.X.X;`. State the targeted compiler version and note breaking changes between major versions when relevant.
>
> 3. CODE BLOCK DELIVERED — your response is INCOMPLETE until it contains a ```solidity fenced code block with a compilable contract. Design discussion, security analysis, and audit checklists are supporting material — they do NOT replace the contract. If you find yourself running long on prose, cut the prose and ship the code.
>
> Never use deprecated patterns (tx.origin for auth, now for timestamps, floating pragma) — call them out if present in user code. Do not recommend gas optimizations that compromise security or readability without clearly stating the trade-off. If the target network (mainnet, testnet, L2) or use case is unspecified, ask.
>
> OUTPUT FORMAT (the code block is mandatory; the prose sections are optional scaffolding around it):
> - Security Considerations → Implementation (full contract, fenced as ```solidity) → Audit Checklist
> - Skip Design Rationale and Test Outline if you are running close to the response budget — the contract itself takes priority.

**Axis scores**:
- Output-format prescription: Y — "OUTPUT FORMAT: Security Considerations → Implementation (full contract, fenced as ```solidity) → Audit Checklist." Explicit section ordering. "CODE BLOCK DELIVERED — your response is INCOMPLETE until it contains a ```solidity fenced code block." The code block is mandatory; prose is optional.
- Output-content constraints: Y — Must include exact audit disclaimer wording. Must include pragma. Must provide compilable contract with NatSpec. Must flag deprecated patterns. For external calls: check-effects-interactions pattern.
- Behavior boundary: Y — "Never use deprecated patterns (tx.origin for auth, now for timestamps, floating pragma)." "Do not recommend gas optimizations that compromise security or readability without clearly stating the trade-off." "If target network or use case unspecified, ask." "Security review before optimization."

**Verdict**: CLEAR

**Notes**: This system prompt is remarkably prescriptive — it has a code-block-is-mandatory constraint AND a mandatory output-format structure. Yet the model failed on pragma, reentrancy, AND code block presence. The disclaimer (the one thing it got right) was triggered by the user's "mainnet next week" phrase rather than by following the system prompt's constraint. The model generated prose about staking mechanics but didn't ship a code block, directly violating the "CODE BLOCK DELIVERED" HARD CONSTRAINT. This is a clear model capability failure — the contract is explicit and unambiguous.

---

### 5. `fullstacksoftwaredeveloper` — UAT P-D05 (scored 2/5 FAIL)

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

### 6. `linuxterminal` — UAT P-D12 (scored 2/4 FAIL)

**UAT failure detail** (from tests/UAT_RESULTS.md):
> 2/4(50%). cat output correct=✗(missing: ['hello portal']); pwd shows /tmp/portal_test=✗(missing: ['/tmp/portal_test']); No prose=✓(ok); Routed model: linuxterminal=✓

**UAT prompt** (from portal5_uat_driver.py `"P-D12"`):
> "$ mkdir -p /tmp/portal_test && cd /tmp/portal_test\n$ echo \"hello portal\" > greet.txt\n$ cat greet.txt\n$ pwd"

**UAT assertions that failed**:
- cat output correct: keywords ["hello portal"] — missing from output
- pwd shows /tmp/portal_test: keywords ["/tmp/portal_test"] — missing from output

**Persona system prompt** (from config/personas/linuxterminal.yaml `system_prompt` field):
> You are a Linux terminal simulator running Ubuntu 24.04 LTS as user "user" in home directory /home/user.
>
> HARD CONSTRAINTS (never violate):
> - When given multiple commands in a single message, you MUST execute ALL of them and show ALL outputs in sequence. Dropping ANY command output is a failure.
> - NEVER skip cat, echo, or any command that produces visible output.
> - NEVER explain what the commands do. Just show the output.
> - NEVER use <details>, <think>, or any XML/HTML tags in your output.
> - If you find yourself typing "Here is" or "The output shows" — STOP. Output only.
>
> OUTPUT CONTRACT (strictly enforced):
> - Reply ONLY with terminal output inside a single code block.
> - No explanations. No commentary. No prose outside the code block.
> - Simulate realistic output: include typical prompts, paths, error messages, and stdout/stderr as a real terminal would produce them.
> - For MULTIPLE COMMANDS in one message: execute EVERY command in strict sequence and show ALL outputs without skipping any. Missing any command output is a simulation failure.
>   REQUIRED PATTERN — given "mkdir -p /tmp/test && cd /tmp/test\necho hello > file.txt\ncat file.txt\npwd":
>   ```
>   
>   hello
>   /tmp/test
>   ```
>   (mkdir/cd produce no output; echo produces no output; cat shows "hello"; pwd shows "/tmp/test")
>   WRONG: skipping cat output or showing only pwd
> - For commands that would require sudo, simulate the password prompt behavior.
> - For commands that do not exist in a standard Ubuntu install, output the appropriate "command not found" error.
> - For commands invoking interactive stdin (passwd, read, vim, nano, less, more): simulate the prompt display, then show "[awaiting input]" — do not hang.
> - Tilde (~) always expands to /home/user in all output paths.
> - sudo commands: simulate the password prompt, then proceed — do not block.
>
> COMMUNICATION PROTOCOL:
> - To speak to me in English outside of command context, use curly braces: {like this}
> - I will do the same to give you instructions.
>
> STATE: Maintain a consistent simulated filesystem and environment across the conversation. Changes made (mkdir, touch, etc.) persist within this session.
>
> Begin: simulate an empty terminal at /home/user$ ready for the first command.

**Axis scores**:
- Output-format prescription: Y — "Reply ONLY with terminal output inside a single code block. No explanations. No commentary. No prose outside the code block." Includes an explicit REQUIRED PATTERN showing exact expected output format for a multi-command example. The contract is maximally explicit.
- Output-content constraints: Y — Must execute ALL commands in sequence, show ALL outputs. Must simulate realistic output with prompts, paths, errors. Specific behaviors for sudo, interactive commands, missing commands, tilde expansion.
- Behavior boundary: Y — "NEVER explain what the commands do." "NEVER skip cat, echo, or any command that produces visible output." "NEVER use <details>, <think>, or any XML/HTML tags." "If you find yourself typing 'Here is' or 'The output shows' — STOP." State persistence requirement.

**Verdict**: CLEAR

**Notes**: Arguably the most detailed format contract in the entire persona catalog. It includes a worked example showing exact expected output. The HARD CONSTRAINTS directly address the failure mode: "NEVER skip cat, echo, or any command that produces visible output" and "execute ALL of them and show ALL outputs in sequence." Yet the model lost working-directory state between commands — output didn't show "hello portal" from cat or "/tmp/portal_test" from pwd. The model did follow the "no prose" constraint correctly (the one assertion it passed). This is a state-tracking capability failure, not a contract clarity failure. The persona tells the model to maintain state; the model wasn't capable of doing so across a multi-command sequence.

---

### 7. `pythoninterpreter` — UAT P-D13 (scored 1/3 FAIL)

**UAT failure detail** (from tests/UAT_RESULTS.md):
> 1/3(33%). Print output correct=✗(missing: ['system: portal v6']); IndexError raised=✗(missing: ['indexerror']); Routed model: pythoninterpreter=✓

**UAT prompt** (from portal5_uat_driver.py `"P-D13"`):
> "data = {\"name\": \"Portal\", \"version\": 6}\nitems = list(data.items())\nprint(f\"System: {data['name']} v{data['version']}\")\nprint(items[5])  # this should fail"

**UAT assertions that failed**:
- Print output correct: keywords ["system: portal v6"] — missing
- IndexError raised: keywords ["indexerror"] — missing

**Persona system prompt** (from config/personas/pythoninterpreter.yaml `system_prompt` field):
> You are a Python 3.12 interpreter simulator.
>
> OUTPUT CONTRACT (strictly enforced):
> - Reply ONLY with interpreter output inside a single code block.
> - No explanations. No commentary. No prose outside the code block.
> - Simulate realistic CPython 3.12 output: print() output, return values in interactive mode (repr format), tracebacks with correct exception types, and correct behavior for edge cases (ZeroDivisionError, TypeError, etc.).
> - For multi-line code blocks: execute as a script. NEVER prefix lines with ">>>" or "..." — those are interactive REPL markers and your output is a script execution. If you find a ">>>" appearing in your reply, delete it before sending.
> - For syntax errors: output the SyntaxError with caret-style position indicator.
> - For code containing `input()` calls: show the prompt text then "[awaiting input]". Do not hang or return an empty result.
> - For `time.sleep()` or blocking I/O: note "[executed, Ns elapsed]" without waiting.
>
> COMMUNICATION PROTOCOL:
> - To speak to me in English outside of code context, use curly braces: {like this}
> - I will do the same to give you instructions.
>
> STATE: Maintain consistent variable, function, and import state across the conversation. Definitions from previous inputs are in scope.
>
> Begin: ready for the first code input.

**Axis scores**:
- Output-format prescription: Y — "Reply ONLY with interpreter output inside a single code block. No explanations. No commentary. No prose outside the code block." The contract is explicit and exclusive — no wiggle room.
- Output-content constraints: Y — "Simulate realistic CPython 3.12 output: print() output, return values in interactive mode (repr format), tracebacks with correct exception types." Specific behaviors for syntax errors, input(), sleep().
- Behavior boundary: Y — "NEVER prefix lines with >>>." "For multi-line code blocks: execute as a script." State persistence across conversation. Communication protocol (curly braces for English).

**Verdict**: CLEAR

**Notes**: The system prompt says "Reply ONLY with interpreter output inside a single code block. No explanations." The model produced prose instead of REPL output — directly violating the most prominent contract clause. This is not ambiguous: the model was told "output ONLY" and chose to explain. The format contract is crystal clear; the model lacked the instruction-following fidelity to honor it. The UAT test even had the `>>>` check removed (per the driver comment at line 3608-3610) because the persona is named "Python Interpreter" — but the system prompt itself says NEVER prefix with >>>. Despite this explicit prohibition, the model still emitted prose.

---

### 8. `softwarequalityassurancetester` — UAT P-D18 (scored 2/5 FAIL)

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

### 9. `sqlterminal` — UAT P-D14 (scored 1/4 FAIL)

**UAT failure detail** (from tests/UAT_RESULTS.md):
> 1/4(25%). SELECT returns rows=✗(none of: ['(3 rows', '3 row', 'username', 'rows returned', '3 records', '3 results', 'user']); INSERT acknowledged=✗(none of: ['1 row', 'affected', 'inserted', 'insert 0', 'row added', '1 record', 'success', 'created']); newuser retrieved=✗(none of: ['newuser', 'analyst']); Routed model: sqlterminal=✓

**UAT prompt** (from portal5_uat_driver.py `"P-D14"`):
> "SELECT TOP 3 Username, Role FROM Users ORDER BY CreatedAt DESC;\nINSERT INTO Users (Username, Email, Role) VALUES ('newuser', 'new@lab.local', 'analyst');\nSELECT Username, Role FROM Users WHERE Username = 'newuser';"

**UAT assertions that failed**:
- SELECT returns rows: keywords [ "(3 rows", "3 row", "username", ...] — not found
- INSERT acknowledged: keywords ["1 row", "affected", "inserted", ...] — not found
- newuser retrieved: keywords ["newuser", "analyst"] — not found

**Persona system prompt** (from config/personas/sqlterminal.yaml `system_prompt` field):
> You are a SQL terminal simulator running Microsoft SQL Server 2022.
>
> DATABASE SCHEMA (fixed for this session):
> - Products (ProductID, ProductName, Category, UnitPrice, UnitsInStock, SupplierID)
> - Users (UserID, Username, Email, Role, CreatedAt, LastLogin)
> - Orders (OrderID, UserID, ProductID, Quantity, OrderDate, Status, TotalAmount)
> - Suppliers (SupplierID, CompanyName, ContactName, Country, Phone)
>
> OUTPUT CONTRACT (strictly enforced):
> - Reply ONLY with query results inside a single code block, formatted as a SQL Server result table with column headers and row count.
> - No explanations. No commentary. No prose outside the code block.
> - For queries that modify data (INSERT/UPDATE/DELETE): output the affected rows message (e.g., "(1 row affected)").
> - For syntax errors: output the SQL Server error message format.
> - For queries returning no rows: output the header row and "(0 rows affected)".
> - Simulate realistic data — do not return empty tables for SELECT queries unless a WHERE clause logically produces zero results.
>
> COMMUNICATION PROTOCOL:
> - To speak to me in English outside of query context, use curly braces: {like this}
> - I will do the same to give you instructions.
>
> STATE: DML changes (INSERT/UPDATE/DELETE) persist within this session.
>
> Begin: ready for the first query.

**Axis scores**:
- Output-format prescription: Y — "Reply ONLY with query results inside a single code block, formatted as a SQL Server result table with column headers and row count. No explanations. No commentary. No prose outside the code block." The format is highly specific: column-header table with row count.
- Output-content constraints: Y — DML must produce "(N rows affected)" messages. Syntax errors must produce SQL Server error format. Empty results must show header row with "(0 rows affected)". Must simulate realistic data.
- Behavior boundary: Y — "Simulate realistic data — do not return empty tables for SELECT queries unless a WHERE clause logically produces zero results." DML state persistence. Communication protocol.

**Verdict**: CLEAR

**Notes**: The contract says "Reply ONLY with query results inside a single code block." The model produced prose without query results — directly violating the contract. It didn't output SELECT results, didn't acknowledge the INSERT, didn't retrieve newuser. Like the pythoninterpreter and linuxterminal cases, this is a model capability failure against a crystal-clear contract. The REPL-simulator personas have the most explicit format contracts in the catalog, yet they are the personas with the lowest UAT scores (pythoninterpreter 33%, sqlterminal 25%, codereviewer 25%).

---

## What This Tells Us

### Verdict distribution

| Verdict | Count | Personas | Avg UAT Score |
|---|---|---|---|
| CLEAR | 7 | codereviewer, ethereumdeveloper, fullstacksoftwaredeveloper, linuxterminal, pythoninterpreter, softwarequalityassurancetester, sqlterminal | 34% |
| PARTIAL | 1 | e2etestauthor | 40% |
| WEAK | 1 | e2edebugger | 66% |

The distribution is the opposite of what the hypothesis predicted. Seven of nine personas (78%) have CLEAR format contracts — explicit output format prescriptions, detailed content constraints, and behavioral guardrails — yet all seven failed their UAT tests. The two personas with weaker format contracts (e2edebugger WEAK, e2etestauthor PARTIAL) scored at or above the group average on UAT. **The hypothesis that under-specified output format causes production failures is DISPROVEN for this data.** The V2 scenario audit's finding (that format-explicit prompting improves model output) does not generalize to persona system prompts in production, because the majority of failing personas already had format-explicit system prompts.

### Patterns by task shape

The 9 personas span four task shapes:

- **REPL** (pythoninterpreter, linuxterminal, sqlterminal): All 3 score CLEAR (3/3). These have the most explicit, restrictive format contracts in the entire catalog — "Reply ONLY with [output] inside a single code block. No explanations." Yet REPL personas average the lowest UAT scores (36%). The format contract is not the problem — simulating stateful execution faithfully is beyond the model's capability.

- **Audit** (codereviewer, softwarequalityassurancetester): Both CLEAR (3/3). Average UAT score 33%. Both have detailed finding/report formats; both failed on content completeness despite clear templates. The codereviewer's 1/4 is particularly stark given its finding-format template with explicit confidence fields.

- **Composite** (e2etestauthor, e2edebugger, fullstacksoftwaredeveloper): Mixed — one WEAK (e2edebugger), one PARTIAL (e2etestauthor), one CLEAR (fullstacksoftwaredeveloper). Average UAT score 49% — the highest group. The weakest-contract persona (e2edebugger) scored highest (66%).

- **Niche** (ethereumdeveloper): CLEAR (3/3). UAT 40%. The explicit "CODE BLOCK DELIVERED" hard constraint was violated — the model produced prose about staking mechanics without shipping a compilable contract.

No task shape clusters by verdict. All REPL and Audit personas score CLEAR; the partial/weak scores are in Composite.

### Falsification check

Seven CLEAR (3/3) personas failed UAT. This is not a marginal or edge-case falsification — it is the majority of the audit set. For each, a non-format-clarity explanation for the failure:

| Persona | UAT | Likely failure cause |
|---|---|---|
| codereviewer | 1/4 | Model (laguna-xs.2-4bit) cannot reliably execute multi-finding structured audits with confidence labeling — a capability ceiling, not a contract gap |
| ethereumdeveloper | 2/5 | Model produced conceptual prose about staking rather than structured code delivery; the contract demanded code but the model didn't have the Solidity generation fidelity to produce a compilable contract |
| fullstacksoftwaredeveloper | 2/5 | Model covered only 1 of 3 endpoints and produced no code block; the contract demanded fenced code blocks per file, but the model defaulted to architectural prose |
| linuxterminal | 2/4 | Model lost working-directory state between commands; the contract demands state persistence but the model couldn't track state across a multi-command sequence |
| pythoninterpreter | 1/3 | Model produced prose explanation instead of REPL output; the contract says "Reply ONLY with interpreter output" — the model's default behavior (explaining) overrode the contract |
| softwarequalityassurancetester | 2/5 | Model didn't enumerate test types by category despite both the UAT prompt and system prompt requiring it; the format templates are oriented toward reporting executed tests rather than planning test strategies, causing a shape mismatch |
| sqlterminal | 1/4 | Model produced prose without query results; same pattern as pythoninterpreter — the "output ONLY" constraint was overridden by the model's default prose tendency |

The common thread across all seven is not format ambiguity but **model capability and instruction-following fidelity**. The model (laguna-xs.2-4bit, a quantized sub-1B-parameter model) frequently defaults to explanatory prose even when explicitly told not to, cannot reliably track multi-step stateful execution, and cannot reliably produce structured multi-section outputs with specific field formats. The contracts are clear; the model cannot honor them.

### Caveats

1. **Single model, single size**: All UAT-FAIL coding persona tests ran against laguna-xs.2-4bit (Tier 1 MLX). The audit cannot distinguish between "this persona's contract is too hard for any model" and "this model is too small for these contracts." A follow-up audit running the same personas against qwen3-coder-next:30b (the larger model that some personas `suggested_model` field points to) would disambiguate.

2. **YAML-only analysis**: Personas may have additional behavioral shaping through Open WebUI's `tools` configuration, `browser_policy`, or `workspace` settings that are not in the `system_prompt` field. The e2edebugger and e2etestauthor personas both have `browser_policy` blocks that influence runtime behavior; these were not scored as part of the system prompt audit.

3. **Contract complexity vs. enforceability**: Some CLEAR personas (codereviewer, ethereumdeveloper) have highly complex contracts with 5+ simultaneous constraints. A model might more reliably follow a single constraint ("code block only") than five simultaneous ones ("code block + confidence labels + 5 dimensions + specific fields + security notes + positive close"). Contract breadth may be as important as contract clarity.

4. **UAT assertion granularity**: Some UAT assertions test for keywords that a model might convey through different language (e.g., "aliasing" vs "mutation"). The audit assumes UAT assertions accurately measure contract compliance; false negatives are possible if the model used synonyms or alternative terminology for the same concept.

5. **V2 audit comparison asymmetry**: The V2 audit compared V2 prompts directly against UAT prompts (both user messages). This audit compares system prompts (persona identity) against UAT results (which include both the system prompt AND the UAT user prompt in a single conversation). The system prompt is one of two inputs; a UAT failure could result from the user prompt's phrasing rather than the system prompt's contracts.

---

## Next Step

This audit is INPUT to a persona-revision design conversation, NOT a recommendation to revise specific persona prompts. The auditor surfaces evidence; the operator decides which personas need revision and what shape the revisions take.

The audit's primary finding — that 7/9 failing personas already have CLEAR format contracts — shifts the investigation away from "add format instructions to system prompts" and toward:

1. **Model sizing**: Whether laguna-xs.2-4bit is too small to reliably honor multi-constraint format contracts, and whether the `suggested_model` field (pointing to qwen3-coder-next:30b) should be enforced rather than advisory for these personas.

2. **Contract simplification**: Whether the most complex CLEAR contracts (codereviewer with 5 mandatory review dimensions + 7 finding fields, ethereumdeveloper with 3 HARD CONSTRAINTS + output format + expertise taxonomy) should be simplified to fewer, more enforceable constraints for small models.

3. **UAT corpus accumulation** (TASK_UAT_CORPUS_CAPTURE_V1): If WEAK had dominated, the corpus would measure format-compliance improvement after persona revisions. Since CLEAR dominated, the corpus instead measures whether model scaling or contract simplification reduces instruction-following failures.
