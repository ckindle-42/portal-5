---
id: unit-tests-conftest
kind: mixed
title: "Tests conftest \u2014 deterministic environment posture"
sources:
- type: code
  path: tests/conftest.py
  commit: 4900007a
last_generated_commit: 4900007a
claims: []
confidence: high
tags:
- authored-v1
- tests
created_at: 1785798780.502145
updated_at: 1785798780.502145
---

`tests/conftest.py` configures pytest for the top-level suite: it sets the
test API key before any pipeline import, defaults the lab environment
variables for a deterministic CI posture, and adds the uv venv's
site-packages to `sys.path` when running under a bare interpreter.

## Why

The conftest is the environment contract that makes the suite run
identically everywhere. The API key is set before any pipeline import so the
module-level guard cannot `sys.exit(1)` during collection; the lab defaults
are what stop "works locally, fails CI" from absent lab variables (CI gets
dry-run behaviour, a populated local `.env` overrides via `setdefault`); and
the venv path insert lets a bare `python3 -m pytest` find the editable
install without an active virtualenv.

## Interfaces

Side effects at import time: env defaults for `PIPELINE_API_KEY` and the
`LAB_*` variables, and the conditional venv path insert.

## Gotchas

The venv probe only fires when `sys.prefix == sys.base_prefix` — inside an
active venv the install is already importable, and forcing a second
site-packages could cause version skew.
