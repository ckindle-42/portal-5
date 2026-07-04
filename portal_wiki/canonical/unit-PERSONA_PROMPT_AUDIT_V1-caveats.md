---
id: unit-PERSONA_PROMPT_AUDIT_V1-caveats
kind: why
title: "PERSONA_PROMPT_AUDIT_V1 \u2014 Caveats"
sources:
- type: design
  path: docs/PERSONA_PROMPT_AUDIT_V1.md
  section: Caveats
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_PROMPT_AUDIT_V1
created_at: 1783195000.8876579
updated_at: 1783195000.8876579
---


1. **Single model, single size**: All UAT-FAIL coding persona tests ran against laguna-xs.2-4bit (Tier 1 MLX). The audit cannot distinguish between "this persona's contract is too hard for any model" and "this model is too small for these contracts." A follow-up audit running the same personas against qwen3-coder-next:30b (the larger model that some personas `suggested_model` field points to) would disambiguate.

2. **YAML-only analysis**: Personas may have additional behavioral shaping through Open WebUI's `tools` configuration, `browser_policy`, or `workspace` settings that are not in the `system_prompt` field. The e2edebugger and e2etestauthor personas both have `browser_policy` blocks that influence runtime behavior; these were not scored as part of the system prompt audit.

3. **Contract complexity vs. enforceability**: Some CLEAR personas (codereviewer, ethereumdeveloper) have highly complex contracts with 5+ simultaneous constraints. A model might more reliably follow a single constraint ("code block only") than five simultaneous ones ("code block + confidence labels + 5 dimensions + specific fields + security notes + positive close"). Contract breadth may be as important as contract clarity.

4. **UAT assertion granularity**: Some UAT assertions test for keywords that a model might convey through different language (e.g., "aliasing" vs "mutation"). The audit assumes UAT assertions accurately measure contract compliance; false negatives are possible if the model used synonyms or alternative terminology for the same concept.

5. **V2 audit comparison asymmetry**: The V2 audit compared V2 prompts directly against UAT prompts (both user messages). This audit compares system prompts (persona identity) against UAT results (which include both the system prompt AND the UAT user prompt in a single conversation). The system prompt is one of two inputs; a UAT failure could result from the user prompt's phrasing rather than the system prompt's contracts.

---
