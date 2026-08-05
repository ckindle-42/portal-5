---
id: unit-portal5-bench-sec-execute-v3-full-expanded-with-live-lab-execution-needs-green-lab-ready
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 Full expanded with live lab execution\
  \ (needs green lab-ready)"
sources:
- type: code
  path: portal/modules/security/core/cli.py
- type: code
  path: portal/modules/security/core/_data.py
- type: code
  path: portal/modules/security/core/lab.py
last_generated_commit: 65958b7ff433a91759bbe4778df434a744fa802c
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.708781
updated_at: 1784946220.708781
---

```bash
python3 -m portal.modules.security.core --full-expanded --lab-exec
```

This is the heavy full-suite run. `--full-expanded` adds the expansion steps
(oracles, CTF, LLM-redteam, validation, journal) to the default
`DEFAULT_WORKSPACES` bench; it does not by itself run tool-calling chains or
blue detection. The prompt-set theory pass always runs; the tool-enabled
execution pass for the two `EXECUTION_WORKSPACES` (`auto-security::pentest`,
`auto-security::purpleteam-exec`) needs `--exec-eval`; the multi-model
attack-chain sequencing needs `--exec-chain-models`; and blue-detection
correlation needs a blue model via `--blue-defender-model` or `--purple`.
`--lab-exec` switches tool results from synthetic to real MCP sandbox execution
and, when chain models are requested, triggers the mandatory
`verify_lab_targets_reachable` gate in `cli.py`, which aborts unless the DC/SRV
targets respond unless `--force-unreachable-lab` overrides deliberately. A green
`python3 scripts/lab_ready.py` is the standing precondition. Treat the earlier
doc's blanket phrasing as aspirational: the bench is flag-composed, not one
switch.

## Why

The original doc claimed `--full-expanded` alone executes chains, execution
workspaces, and blue correlation; re-grounding shows each of those is a separate
opt-in flag. Conflating them makes an operator believe a flag-composed suite is
monolithic, which either over-runs the lab or silently skips the passes they
intended to run.
