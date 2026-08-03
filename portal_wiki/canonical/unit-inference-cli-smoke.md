---
id: unit-inference-cli-smoke
kind: mixed
title: "Inference CLI smoke \u2014 live-stack end-to-end test"
sources:
- type: code
  path: portal/platform/inference/cli/smoke.py
  commit: 5fbf51f8
last_generated_commit: 5fbf51f8
claims: []
confidence: high
tags:
- authored-v1
- platform
- cli
created_at: 1785797868.820791
updated_at: 1785797868.820791
---

`portal test` runs the end-to-end smoke tests against the live Portal stack:
it exercises the pipeline, the workspace routing, and the MCP fleet through
the running services and reports pass/fail per check.

## Why

The smoke suite is the "is the stack actually up and coherent" gate that runs
against live services, distinct from the hermetic unit tests. The live
streaming smoke (`smoke_stream.sh`) exists because unit mocks cannot detect
dependency-contract mismatches — a real request through the real pipeline is
the only way to prove the streaming path works end to end. `portal test` is
the operator-facing way to run that.

## Interfaces

`cmd_test` runs the smoke scenarios against the live stack and reports
results; `register` attaches it as the top-level `test` command.

## Gotchas

This command requires the stack to be running — it is a live test by design,
and its failures mean the stack is broken, not the test.
