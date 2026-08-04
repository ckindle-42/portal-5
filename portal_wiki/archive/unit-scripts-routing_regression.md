---
id: unit-scripts-routing_regression
kind: mixed
title: "Script \u2014 routing_regression"
sources:
- type: code
  path: scripts/routing_regression.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799554.3093581
updated_at: 1785799554.3093581
---

Runs a fixed corpus of prompts through the auto-routing resolution path and records the resolved base/variant tuple for each, catching routing regressions.

## Why

Routing is the decision layer everything depends on, and a routing regression is invisible until a request goes to the wrong workspace. The fixed-corpus regression records the resolved tuple per prompt so any change that shifts routing is caught mechanically.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
