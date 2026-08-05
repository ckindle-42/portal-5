---
id: unit-portal5-bench-sec-execute-v3-what-changed-in-the-security-surface-read-before-running
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 What changed in the security surface (read\
  \ before running)"
sources:
- type: code
  path: scripts/execute_preflight.py
- type: code
  path: config/portal.yaml
- type: code
  path: portal/modules/security/core/_data.py
- type: code
  path: portal/modules/security/core/__init__.py
last_generated_commit: 65958b7ff433a91759bbe4778df434a744fa802c
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.704969
updated_at: 1784946220.704969
---

The collapse (commit a7d9dcc8) folded nine security workspaces into one
`auto-security` base with `variants:` blocks, and the alias shim that let old
ids keep working was removed. `scripts/execute_preflight.py` hard-codes the 23
retired aliases in `RETIRED_ALIASES` and its `check_no_retired_aliases` gate
fails the preflight if any leaks back into `config/portal.yaml`. The current
variant set — `redteam`, `redteam-deep`, `blueteam`, `purpleteam`,
`purpleteam-deep`, `purpleteam-exec`, `pentest`, `uncensored` — resolves to the
canonical `auto-security::<variant>` form.

The bench's internal vocabulary is already canonical: `_data.py`'s
`PER_WORKSPACE_TIMEOUT` and `EXECUTION_WORKSPACES` are keyed on the literal
`::` strings (the edcaa8b fix). Because `call_pipeline` forwards the workspace
string as the pipeline `model` field, a retired id such as `auto-pentest` is
not a registered workspace and the request fails rather than silently running;
use `auto-security::pentest`. The exact set of live variants is printed by the
preflight — use that list, not this table, since variants are config-driven.

## Why

The alias shim was removed deliberately so a stale runbook id fails loudly
instead of silently routing to a wrong workspace. Re-grounding to the
preflight's retired-alias list and to `_data.py`'s canonical keys makes the
"trust the preflight's live list" rule mechanically verifiable, because the
variant set is config-driven and the harness must never trust a table typed
from memory.

---
