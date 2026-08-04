---
id: unit-portal5-acceptance-execute-v9-your-role
kind: what
title: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 Your Role"
sources:
- type: code
  path: tests/acceptance/cli.py
- type: code
  path: tests/acceptance/runner.py
- type: code
  path: tests/lib/results.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.693929
updated_at: 1784946220.693929
---

The acceptance operator acts as the execution agent for the suite: launch the
section runner against a live stack, watch the live progress log for stalls,
diagnose failures using the recorded detail and evidence, retry sections
intelligently, and produce a pass/fail report. Each check is recorded through
`record` in `tests/lib/results.py` into the in-memory `_log` with a section, id,
name, status, detail, and duration, and the CLI prints a summary plus a routing
summary via `_print_routing_summary` from the accumulated routing log when the
run finishes.

The role explicitly does not modify product code: `portal/**` is treated as
read-only during acceptance. A regression found by a section is reported with
evidence — its FAIL or WARN row, the routing tuple when applicable, and the
relevant detail — rather than fixed in the moment or hidden by editing
expectations.

## Why

The separation between execution agent and product owner is what makes the
acceptance signal trustworthy. If the same agent could edit routing or
expectation code mid-run, every red result could be quietly turned green and
the suite would measure nothing. Recording a fixed schema of status, detail,
and evidence per check, and summarizing routing intent versus actual model,
gives the owner everything needed to reproduce a failure without changing
product code.
