---
id: unit-scripts-execute_preflight
kind: mixed
title: "Script \u2014 execute_preflight"
sources:
- type: code
  path: scripts/execute_preflight.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799483.539776
updated_at: 1785799483.539776
---

Read-only. Prints current counts and vocabularies so an execute agent confirms reality instead of trusting doc-baked numbers, at the start of every bench/sec/acceptance session.

## Why

A session that starts from stale doc-baked numbers makes decisions on a fiction; the preflight prints the live counts and vocabularies so the agent's first act is confirming reality. Read-only is the contract — the preflight verifies, it never mutates.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
