---
id: unit-PERSONA_PROMPT_AUDIT_V1-falsification-check
kind: why
title: "PERSONA_PROMPT_AUDIT_V1 \u2014 Falsification check"
sources:
- type: design
  path: docs/PERSONA_PROMPT_AUDIT_V1.md
  section: Falsification check
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_PROMPT_AUDIT_V1
created_at: 1783195000.887409
updated_at: 1783195000.887409
---


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

The common thread across all seven is not format ambiguity but **model capability and instruction-following fidelity**. The model (laguna-xs.2-4bit, a quantized sub-1B-parameter model) frequently defaults to explanatory prose even when explicitly told not to, cannot reliably track multi-s
