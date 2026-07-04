---
id: unit-PERSONA_PROMPT_AUDIT_V1-next-step
kind: why
title: "PERSONA_PROMPT_AUDIT_V1 \u2014 Next Step"
sources:
- type: design
  path: docs/PERSONA_PROMPT_AUDIT_V1.md
  section: Next Step
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_PROMPT_AUDIT_V1
created_at: 1783195000.887895
updated_at: 1783195000.887895
---


This audit is INPUT to a persona-revision design conversation, NOT a recommendation to revise specific persona prompts. The auditor surfaces evidence; the operator decides which personas need revision and what shape the revisions take.

The audit's primary finding — that 7/9 failing personas already have CLEAR format contracts — shifts the investigation away from "add format instructions to system prompts" and toward:

1. **Model sizing**: Whether laguna-xs.2-4bit is too small to reliably honor multi-constraint format contracts, and whether the `suggested_model` field (pointing to qwen3-coder-next:30b) should be enforced rather than advisory for these personas.

2. **Contract simplification**: Whether the most complex CLEAR contracts (codereviewer with 5 mandatory review dimensions + 7 finding fields, ethereumdeveloper with 3 HARD CONSTRAINTS + output format + expertise taxonomy) should be simplified to fewer, more enforceable constraints for small models.

3. **UAT corpus accumulation** (TASK_UAT_CORPUS_CAPTURE_V1): If WEAK had dominated, the corpus would measure format-compliance improvement after persona revisions. Since CLEAR dominated, the corpus instead measures whether model scaling or contract simplification reduces instruction-following failures.
