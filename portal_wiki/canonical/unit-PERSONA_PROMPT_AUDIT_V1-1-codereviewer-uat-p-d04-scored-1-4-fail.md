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
created_at: 1783195000.884554
updated_at: 1783195000.884554
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
> - State your confidence level for every finding: High / Medium / Low. Low confi
