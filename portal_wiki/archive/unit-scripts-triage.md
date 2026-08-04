---
id: unit-scripts-triage
kind: mixed
title: "Script \u2014 triage"
sources:
- type: code
  path: scripts/triage.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799557.941393
updated_at: 1785799557.941393
---

Packages the failure context (log tail, failing command, target/model state) and asks a small triage model one bounded question: the likely cause and which corrective action from a fixed menu the supervisor should take.

## Why

The supervisor needs to decide the corrective action from a fixed menu, and the triage model is the bounded reasoning step that maps the failure context to that menu — bounded because the answer space is the menu, not free-form reasoning.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
