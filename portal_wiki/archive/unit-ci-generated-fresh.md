---
id: unit-ci-generated-fresh
kind: mixed
title: "CI guard \u2014 sync-config idempotence enforces Rule 6"
sources:
- type: code
  path: scripts/ci/check_generated_fresh.py
  commit: '96146826'
last_generated_commit: '96146826'
claims: []
confidence: high
tags:
- authored-v1
- ci
- config
created_at: 1785795640.236754
updated_at: 1785795640.236754
---

The generated-fresh guard runs `sync-config` and fails if the three
generated artifacts — `config/backends.yaml`, `.mcp.json`, and
`opencode.jsonc` — differ after it, meaning a human edited a generated file
instead of editing `config/portal.yaml` and re-running sync-config. It is the
mechanical enforcement of CLAUDE.md Rule 6.

## Why

Rule 6 makes `portal.yaml` the single source of truth and declares the three
generated files derived. The failure this guard prevents is the silent drift
that results when someone hand-edits a generated file: the edit works until
the next sync-config overwrites it, and then the difference reappears as a
mystery. Because `sync-config` is idempotent, a clean tree produces no diff —
so any diff after running it is, by construction, a hand-edit that should not
have happened. The guard runs as a pre-commit hook on every commit.

## Interfaces

`main()` invokes `portal.platform.inference.sync_config` as a subprocess,
checks the git diff on the three generated paths, and returns non-zero with a
fix hint when anything changed. The `GENERATED` list is the full derived set
it guards.

## Gotchas

The guard is a fast-path skip when `config/` has no tracked changes — if the
config surface is untouched, there is nothing to regenerate and the check
would only cost a full sync-config run for no information.
