---
id: unit-V2_SCENARIO_AUDIT_V1-15-creative-particle-system-uat-p-d20-pass-regress
kind: why
title: "V2_SCENARIO_AUDIT_V1 \u2014 15. `creative-particle-system` (UAT P-D20 \u2014\
  \ PASS regression guard)"
sources:
- type: design
  path: docs/V2_SCENARIO_AUDIT_V1.md
  section: "15. `creative-particle-system` (UAT P-D20 \u2014 PASS regression guard)"
last_generated_commit: ''
confidence: high
tags:
- docs
- V2_SCENARIO_AUDIT_V1
created_at: 1783195000.926497
updated_at: 1783195000.926497
---


**UAT P-D20 status**: PASS with Laguna
**V2 Laguna result**: PASS

**UAT prompt** (verbatim from line 3827):
> Make me a particle system visualizer. Particles should emit from wherever I click, fan outward with randomized velocity and color, fade out over their lifetime, and respect gravity. Keyboard: [Space] to toggle gravity on/off, [C] to clear all particles.

**V2 prompt** (verbatim from coding_scenarios.yaml):
> Build a self-contained HTML file with a canvas particle system:
> particles emit on space-bar, fall with gravity, fade out over 2
> seconds. Vanilla JS, no libraries. Ship it as one file, ready to
> open in a browser. Don't ask clarifying questions.

**Verdict**: NO COMPARISON

**Notes**: UAT PASS regression guard. Both are creative-coding particle system tasks. Key differences: UAT says "emit from wherever I click" with "[Space] to toggle gravity on/off, [C] to clear" — more interactive specification. V2 says "emit on space-bar, fall with gravity, fade out over 2 seconds" — simpler interaction model (emit on keypress vs click position). V2 adds "Don't ask clarifying questions" and "Ship it as one file" — both present in UAT assertions implicitly. UAT's "has_code" assertion is non-critical, recognizing creative personas may narrate. V2 simplifies the interaction model but both are PASS cases for Laguna.

---
