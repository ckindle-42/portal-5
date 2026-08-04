---
id: unit-portal5-acceptance-execute-v9-failure-playbook
kind: what
title: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 Failure playbook"
sources:
- type: code
  path: tests/acceptance/runner.py
- type: code
  path: tests/lib/results.py
- type: code
  path: tests/acceptance/s06_security_workspaces.py
- type: code
  path: scripts/routing_regression.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.697199
updated_at: 1784946220.697199
---

The runner catches any exception a section module raises and records it as a
`{sec}-ERR` row with status FAIL; see the exception handler in `run_sections`
in `tests/acceptance/runner.py`. A NameError in such a row classifies as a
CODE-DEFECT via the error patterns in `tests/lib/results.py` and usually means
the checkout is stale — the section files were decomposed and import-clean — so
re-sync to HEAD before debugging further.

- **S6 asserts on a retired id** — you are on stale section files or a stale
  execution doc. `tests/acceptance/s06_security_workspaces.py` calls the
  `auto-security` workspace with `variant` query parameters; it does not assert
  the retired standalone security ids.
- **Routing-baseline assertion fails** — `scripts/routing_regression.py
  --assert-baseline` hard-fails on drift; that is a product routing regression
  to report, never to mask by loosening acceptance expectations.
- **A production workspace has no covering section** — a coverage gap to
  report, not an invitation to write tests into protected product code.
- **A persona is served the wrong model** — a served-model regression; report
  the persona slug, the expected pin, and the actual served model together.

## Why

Every failure mode here has a deliberate response because the suite's value is
a truthful pass/fail signal, not a green wall. Stale-checkout and stale-doc
failures are self-inflicted and cheap to rule out, while routing and
served-model failures are product regressions that loosening acceptance
expectations would hide. The classification in `tests/lib/results.py` and the
hard-fail behavior in the regression script keep the suite honest about what it
protects.
