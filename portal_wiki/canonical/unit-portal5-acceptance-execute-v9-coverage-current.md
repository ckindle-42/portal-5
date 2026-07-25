---
id: unit-portal5-acceptance-execute-v9-coverage-current
kind: what
title: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 Coverage (current)"
sources:
- type: doc
  path: tests/PORTAL5_ACCEPTANCE_EXECUTE_V9.md
  commit: 05e42ec2
  section: Coverage (current)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.695499
updated_at: 1784946220.695499
---

S3 covers the production workspaces via `WORKSPACE_PROMPTS` (derived live from
`WORKSPACES` in `_common.py` — no hardcoded list to drift). S6 covers
`auto-security` and its variants. S17 covers `auto-cad`. All 21 production
workspaces should have routing coverage across S3+S6+S17 — confirm with the
preflight list against the section coverage; report any production workspace
with no covering section.

---
