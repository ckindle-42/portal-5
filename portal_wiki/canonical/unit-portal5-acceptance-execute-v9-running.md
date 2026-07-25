---
id: unit-portal5-acceptance-execute-v9-running
kind: what
title: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 Running"
sources:
- type: doc
  path: tests/PORTAL5_ACCEPTANCE_EXECUTE_V9.md
  commit: 05e42ec2
  section: Running
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.695101
updated_at: 1784946220.695101
---

Entry point is `tests/portal5_acceptance_v6.py` (confirm it's still the current
runner via `ls tests/portal5_acceptance_v*.py`; if a higher version exists, use
it):

```bash
python3 tests/portal5_acceptance_v6.py --section ALL          # full suite
python3 tests/portal5_acceptance_v6.py --section S3,S10,S60    # routing + personas + tools
python3 tests/portal5_acceptance_v6.py --section S0-S5         # inclusive range
python3 tests/portal5_acceptance_v6.py --section S6            # security workspaces
```

The 28 section files on disk (`tests/acceptance/s*.py`) are the authoritative
section list. Key sections for the current surface:
- **S3 (routing)** — production-workspace routing. Ties to the routing baseline
  (below).
- **S6 (security workspaces)** — `auto-security` + variant routing. Asserts
  redteam/blueteam/purpleteam/pentest *intents* route to `auto-security`; the
  retired standalone ids are gone.
- **S10 / S10c (personas)** — persona resolution; now served-model-checkable.
- **S17 (cad)**, **S21 (llm router)**, **S23 (model diversity)**.

---
