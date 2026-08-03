---
id: unit-ci-identical-sources
kind: mixed
title: "CI guard \u2014 deploy/ and portal_mcp/ must not diverge"
sources:
- type: code
  path: scripts/ci/check_no_identical_sources.py
  commit: '96146826'
last_generated_commit: '96146826'
claims: []
confidence: high
tags:
- authored-v1
- ci
- deploy
created_at: 1785795645.924342
updated_at: 1785795645.924342
---

The identical-sources guard fails if any `deploy/` Python file is
byte-identical to a `portal_mcp/` Python file. Its origin is a concrete
duplication: `deploy/playwright-mcp/browser_mcp.py` is a copy of
`portal_mcp/browser/browser_mcp.py`, and the Docker build context for
playwright-mcp is local, so the two cannot be collapsed into a symlink.

## Why

The duplicate exists because the deploy layout needs a self-contained build
context, but a *silent* duplicate is a maintenance trap: one copy gets fixed
and the other keeps the old behaviour. The guard converts the unavoidable
duplication into a managed constraint — the files must either stay identical
or the build-context arrangement must change. Failing loudly on divergence
forces a deliberate decision (manual sync or a build-context change) instead
of letting the copies drift apart until someone notices the deployed browser
behaves differently from the source one.

## Interfaces

`main()` indexes `deploy/` and `portal_mcp/` Python files by name, compares
bytes for matching names, and returns non-zero listing any that differ. Files
that share a name but already differ are reported; identical files pass.

## Gotchas

The comparison is by file *name*, not by path — two files at different
relative depths still collide if their basenames match, which is exactly the
playwright-mcp case.
