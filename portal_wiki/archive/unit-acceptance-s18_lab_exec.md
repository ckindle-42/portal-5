---
id: unit-acceptance-s18_lab_exec
historical: true
kind: mixed
title: "S18 \u2014 Lab execution"
sources:
- type: code
  path: tests/acceptance/s18_lab_exec.py
  commit: e75dddd2
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance

---

This is the acceptance section s18_lab_exec. S18 — Lab execution

## Why

It exercises the live lab-exec path, proving the security workspaces can drive the routable lab under the lab envelope. Live execution is the security tier's real-world test, and a lab-exec regression would make the workspaces unable to reach their targets.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
