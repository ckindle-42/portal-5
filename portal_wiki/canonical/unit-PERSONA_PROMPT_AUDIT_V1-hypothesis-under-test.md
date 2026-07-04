---
id: unit-PERSONA_PROMPT_AUDIT_V1-hypothesis-under-test
kind: why
title: "PERSONA_PROMPT_AUDIT_V1 \u2014 Hypothesis Under Test"
sources:
- type: design
  path: docs/PERSONA_PROMPT_AUDIT_V1.md
  section: Hypothesis Under Test
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_PROMPT_AUDIT_V1
created_at: 1783195000.883944
updated_at: 1783195000.883944
---


The V2 scenario audit found 0/9 UAT-FAIL-derived V2 scenarios were FAITHFUL to their UAT prompts — every V2 prompt explicitly demanded a code block or other output format that the UAT prompt left open. When V2 prompts asked clearly, Laguna produced clearly.

If that pattern generalizes, then UAT-failed personas should have system prompts that under-specify output format. A persona whose system prompt says "you are an expert programmer" without further format guidance gives the model no contract to honor; a persona whose system prompt says "respond as a Python REPL would, with prompts and exact output only" does.

This audit scores 9 UAT-FAIL coding personas on three format-clarity axes:

- **Output-format prescription** — Does the system prompt tell the model how to format responses?
- **Output-content constraints** — Does it specify what must be in every response?
- **Behavior boundary** — Does it set a guardrail relevant to its task shape?

3/3 = CLEAR contract. 2/3 = PARTIAL. 0-1/3 = WEAK.
