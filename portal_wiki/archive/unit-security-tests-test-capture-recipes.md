---
id: unit-security-tests-test-capture-recipes
kind: what
title: Capture recipe positive/negative controls
sources:
- type: code
  path: portal/modules/security/tests/test_capture_recipes.py
last_generated_commit: baca992c674a3cbb36a619e8f62e7e88b8fccfff
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5
updated_at: 1784946220.5
---

`test_capture_recipes.py` proves that every scenario in `CAPTURE_RECIPES` can be confirmed from real telemetry and cannot be triggered by a bare request alone. For each recipe, `SAMPLE_EVIDENCE` supplies a positive control and `REQUEST_ONLY_EVIDENCE` a negative one, both routed through `validate_capture_signals` so a recipe only counts when the full exploitation trace — not just the request — is present. A second test renders every recipe, postcondition, and host command through `render_recipe_command`, `render_postcondition_command`, and `render_host_command`, asserting no `$TARGET_HOST` or `$TARGET_PORT` placeholders survive substitution and that each recipe name also exists in `SCENARIOS`. The final block pins the corrected MITRE ground truth for deserialisation and other web RCE scenarios so detection mappings cannot silently regress.

## Why

A detection corpus is only as trustworthy as its negative controls: if a bare request already trips a scenario, then every later measurement of blue-model accuracy is inflated by a false positive, and the recipe cannot distinguish a real exploit from an attempted one. Keeping a per-scenario request-only sample as a mirror of the positive evidence forces the signal contract to be discriminating by construction, and pinning the ground truth prevents a scenario author from quietly changing what a technique maps to.
