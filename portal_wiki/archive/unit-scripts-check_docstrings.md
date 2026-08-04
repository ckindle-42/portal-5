---
id: unit-scripts-check_docstrings
kind: mixed
title: "Script \u2014 check_docstrings"
sources:
- type: code
  path: scripts/check_docstrings.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799465.4470332
updated_at: 1785799465.4470332
---

Walks every active Python file (excluding vendored trees and the duplicated deploy/playwright-mcp copy) and reports modules, classes, and functions missing docstrings.

## Why

The docstring check is the mechanical guard for the project's documentation discipline, and the exclusions matter: vendored code and the deliberately duplicated playwright tree are not Portal's to document, and checking them would report noise. Reporting (not fixing) is the contract — the check surfaces the gaps and lets the operator decide.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
