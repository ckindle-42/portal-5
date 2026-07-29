---
id: unit-PERSONA_PROMPT_AUDIT_V1-1-codereviewer-uat-p-d04-scored-1-4-fail
kind: why
title: "PERSONA_PROMPT_AUDIT_V1 \u2014 1. `codereviewer` \u2014 UAT P-D04 (scored\
  \ 1/4 FAIL)"
sources:
- type: design
  path: docs/PERSONA_PROMPT_AUDIT_V1.md
  section: "1. `codereviewer` \u2014 UAT P-D04 (scored 1/4 FAIL)"
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_PROMPT_AUDIT_V1
created_at: 1785348275.818845
updated_at: 1785348275.818845
---


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
