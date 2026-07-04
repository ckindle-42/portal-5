---
id: unit-V2_SCENARIO_AUDIT_V1-bias-axis-distribution
kind: why
title: "V2_SCENARIO_AUDIT_V1 \u2014 Bias-axis distribution"
sources:
- type: design
  path: docs/V2_SCENARIO_AUDIT_V1.md
  section: Bias-axis distribution
last_generated_commit: ''
confidence: high
tags:
- docs
- V2_SCENARIO_AUDIT_V1
created_at: 1783195000.927304
updated_at: 1783195000.927304
---


| Axis | Fired count (of 9 UAT-FAIL) |
|---|---|
| Output-format prescription | 8 |
| Required-element naming | 5 |
| Algorithm prescription | 2 |

**Output-format prescription dominates** (8/9 scenarios). V2 consistently adds "fenced code block," "no prose," or explicit output structure requirements. This is the most consequential finding: Laguna's primary UAT failure mode was producing prose instead of code blocks. Adding "fenced code block" directly addresses this failure, and V2 does so in nearly every scenario. **If output-format prescription is responsible for most of V2's score improvement, then the "system prompt" hypothesis is not what V2 measured — what V2 measured is that Laguna produces better code when told to produce code.**

**Required-element naming fires in 5 of 9** — V2 often names specific libraries, APIs, or bugs that assertions check for. In `code-review-with-confidence`, V2 literally lists the bugs the model should find. This coupling between prompt and assertion creates a tautology: the prompt says "include X," the assertion checks for X, the model passes. This is not a capability measurement.

**Algorithm prescription is rare (2 of 9)** — Only `async-http-retry-wrapper` and `jwt-three-endpoints` prescribe approach. These two are also the only EASIER scenarios (3/3 axes). This suggests that algorithm prescription is the axis that tips MIXED scenarios into the EASIER category.
