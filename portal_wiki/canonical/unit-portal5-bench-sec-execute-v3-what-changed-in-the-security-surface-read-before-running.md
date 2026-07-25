---
id: unit-portal5-bench-sec-execute-v3-what-changed-in-the-security-surface-read-before-running
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 What changed in the security surface (read\
  \ before running)"
sources:
- type: doc
  path: tests/PORTAL5_BENCH_SEC_EXECUTE_V3.md
  commit: 05e42ec2
  section: What changed in the security surface (read before running)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.704969
updated_at: 1784946220.704969
---

The collapse folded 9 security workspaces into **one** `auto-security` base with
variants. The alias shim that let old ids keep working has been **removed**. So:

| Retired id (do NOT use) | Canonical form (use this) |
|---|---|
| `auto-redteam` | `auto-security::redteam` |
| `auto-redteam-deep` | `auto-security::redteam-deep` *(if defined; confirm via preflight)* |
| `auto-blueteam` | `auto-security::blueteam` |
| `auto-purpleteam` | `auto-security::purpleteam` |
| `auto-purpleteam-deep` | `auto-security::purpleteam-deep` |
| `auto-purpleteam-exec` | `auto-security::purpleteam-exec` |
| `auto-pentest` | `auto-security::pentest` |
| `auto-security-uncensored` | `auto-security::uncensored` *(guardrail variant)* |

The exact set of live `auto-security::*` variants is printed by the preflight —
**use that list, not this table**, since variants are config-driven.

`bench_security.py`'s internal vocabulary (`_data.py`
`PER_WORKSPACE_TIMEOUT`, `EXECUTION_WORKSPACES`) is already canonical
`::`-keyed as of `edcaa8b`. A bare `--workspaces auto-pentest` will now fail
(no such workspace) — use `--workspaces auto-security::pentest`.

---
