---
id: unit-portal5-bench-sec-execute-v3-failure-playbook
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 Failure playbook"
sources:
- type: doc
  path: tests/PORTAL5_BENCH_SEC_EXECUTE_V3.md
  commit: 05e42ec2
  section: Failure playbook
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.710026
updated_at: 1784946220.710026
---

- **`--workspaces auto-pentest` → "unknown workspace"** — you used a retired
  alias; switch to `auto-security::pentest`.
- **Variant resolves to base with no variant behavior** — confirm
  `auto-security.variants.<v>` exists in `portal.yaml`; the `::` unpacking needs
  a defined variant.
- **Lab RED** — resolve per `LAB_SETUP.md` before benching; don't bench a cold
  lab.
- **Chain times out** — check `_data.py` `PER_WORKSPACE_TIMEOUT` has an entry
  for the canonical `::` key; a folded variant that lost its cap gets the
  default and may be killed mid-chain (this was fixed in `edcaa8b` — verify it
  held).
