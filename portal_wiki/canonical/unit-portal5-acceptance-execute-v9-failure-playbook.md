---
id: unit-portal5-acceptance-execute-v9-failure-playbook
kind: what
title: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 Failure playbook"
sources:
- type: doc
  path: tests/PORTAL5_ACCEPTANCE_EXECUTE_V9.md
  commit: 05e42ec2
  section: Failure playbook
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.697199
updated_at: 1784946220.697199
---

- **`{sec}-ERR` NameError row** — stale checkout (missing-import defects in
  decomposed section files were fixed); re-clone at HEAD.
- **S6 asserts on a retired id** — you're on a stale section file or stale doc;
  S6 should assert `auto-security`, not `auto-redteam`. Confirm HEAD.
- **Routing baseline assertion fails** — product routing regression; report,
  don't mask.
- **A production workspace has no covering section** — coverage gap; report it
  (don't invent a test in product-protected code; note for the implementation
  agent).
- **Persona served wrong model** — served-model regression; report with the
  persona slug + expected pin + actual served model.
