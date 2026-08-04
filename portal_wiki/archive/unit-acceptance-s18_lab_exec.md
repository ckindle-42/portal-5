---
id: unit-acceptance-s18_lab_exec
kind: mixed
title: "S18 \u2014 Lab execution"
sources:
- type: code
  path: tests/acceptance/s18_lab_exec.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799797.675172
updated_at: 1785799797.675172
---

This is the acceptance section s18_lab_exec. S18 — Lab execution

## Why

It exercises the live lab-exec path, proving the security workspaces can drive the routable lab under the lab envelope. Live execution is the security tier's real-world test, and a lab-exec regression would make the workspaces unable to reach their targets.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
