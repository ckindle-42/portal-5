---
id: unit-PERSONA_PROMPT_AUDIT_V1-patterns-by-task-shape
kind: why
title: "PERSONA_PROMPT_AUDIT_V1 \u2014 Patterns by task shape"
sources:
- type: design
  path: docs/PERSONA_PROMPT_AUDIT_V1.md
  section: Patterns by task shape
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_PROMPT_AUDIT_V1
created_at: 1783195000.887153
updated_at: 1783195000.887153
---


The 9 personas span four task shapes:

- **REPL** (pythoninterpreter, linuxterminal, sqlterminal): All 3 score CLEAR (3/3). These have the most explicit, restrictive format contracts in the entire catalog — "Reply ONLY with [output] inside a single code block. No explanations." Yet REPL personas average the lowest UAT scores (36%). The format contract is not the problem — simulating stateful execution faithfully is beyond the model's capability.

- **Audit** (codereviewer, softwarequalityassurancetester): Both CLEAR (3/3). Average UAT score 33%. Both have detailed finding/report formats; both failed on content completeness despite clear templates. The codereviewer's 1/4 is particularly stark given its finding-format template with explicit confidence fields.

- **Composite** (e2etestauthor, e2edebugger, fullstacksoftwaredeveloper): Mixed — one WEAK (e2edebugger), one PARTIAL (e2etestauthor), one CLEAR (fullstacksoftwaredeveloper). Average UAT score 49% — the highest group. The weakest-contract persona (e2edebugger) scored highest (66%).

- **Niche** (ethereumdeveloper): CLEAR (3/3). UAT 40%. The explicit "CODE BLOCK DELIVERED" hard constraint was violated — the model produced prose about staking mechanics without shipping a compilable contract.

No task shape clusters by verdict. All REPL and Audit personas score CLEAR; the partial/weak scores are in Composite.
