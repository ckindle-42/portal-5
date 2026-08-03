---
id: unit-security-commands-namespace
kind: mixed
title: "Security commands package \u2014 runner namespace"
sources:
- type: code
  path: portal/modules/security/core/commands/__init__.py
  commit: 5b73259d
last_generated_commit: 5b73259d
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- commands
created_at: 1785795357.189006
updated_at: 1785795357.189006
---

The commands subpackage is the extracted runner layer of the security
bench CLI: `run.py` holds the bench execution and summary printing, split out
of the argparse dispatcher so the CLI stays a thin parser. This `__init__`
is an empty namespace marker.

## Why

The extraction (documented in `run.py`'s header as M6-B2) exists so the CLI's
argument parsing does not share a module with the heavy execution logic —
separating them lets the dispatcher import cheaply while the runner pulls in
the chain, scoring, and data modules only when a bench actually runs. The
empty `__init__` marks the package boundary.

## Interfaces

No callable surface in `__init__`. The package's content is `run.py`
(`run_bench`, `_print_summary`, `_print_intake_summary`).
