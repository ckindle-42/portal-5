---
id: unit-portal5-acceptance-execute-v9-new-in-v9-routing-served-model-verification
kind: what
title: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 New in V9 \u2014 routing + served-model\
  \ verification"
sources:
- type: doc
  path: tests/PORTAL5_ACCEPTANCE_EXECUTE_V9.md
  commit: 05e42ec2
  section: "New in V9 \u2014 routing + served-model verification"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.695986
updated_at: 1784946220.695986
---

The recent routing-integrity work added a versioned baseline and a served-model
regression gate. Acceptance should confirm these hold end-to-end:

**1. Routing baseline still green (before the suite):**
```bash
python3 scripts/routing_regression.py --assert-baseline    # matches tests/routing/baseline.json
```
If this fails, routing has drifted from its proven baseline — that's a product
regression; report it and do NOT mask it by adjusting acceptance expectations.

**2. Served-model correctness (during S10 persona tests):**
For any `model_pin` persona the preflight lists, confirm the acceptance run
recorded it being served its pinned model. A persona resolving to the right
workspace but served the wrong model is the exact bug class recently fixed —
S10 should catch a regression. If a persona test passes routing but the served
model ≠ its pin, that's a `{sec}-WARN`/fail worth flagging.

---
