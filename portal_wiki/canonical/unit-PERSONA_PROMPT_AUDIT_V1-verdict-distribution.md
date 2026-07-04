---
id: unit-PERSONA_PROMPT_AUDIT_V1-verdict-distribution
kind: why
title: "PERSONA_PROMPT_AUDIT_V1 \u2014 Verdict distribution"
sources:
- type: design
  path: docs/PERSONA_PROMPT_AUDIT_V1.md
  section: Verdict distribution
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_PROMPT_AUDIT_V1
created_at: 1783195000.8869052
updated_at: 1783195000.8869052
---


| Verdict | Count | Personas | Avg UAT Score |
|---|---|---|---|
| CLEAR | 7 | codereviewer, ethereumdeveloper, fullstacksoftwaredeveloper, linuxterminal, pythoninterpreter, softwarequalityassurancetester, sqlterminal | 34% |
| PARTIAL | 1 | e2etestauthor | 40% |
| WEAK | 1 | e2edebugger | 66% |

The distribution is the opposite of what the hypothesis predicted. Seven of nine personas (78%) have CLEAR format contracts — explicit output format prescriptions, detailed content constraints, and behavioral guardrails — yet all seven failed their UAT tests. The two personas with weaker format contracts (e2edebugger WEAK, e2etestauthor PARTIAL) scored at or above the group average on UAT. **The hypothesis that under-specified output format causes production failures is DISPROVEN for this data.** The V2 scenario audit's finding (that format-explicit prompting improves model output) does not generalize to persona system prompts in production, because the majority of failing personas already had format-explicit system prompts.
