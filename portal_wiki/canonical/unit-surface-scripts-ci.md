---
id: unit-surface-scripts-ci
kind: mixed
title: "CI guard suite \u2014 generated-fresh, no-identical-sources, no-duplicate-pins"
sources:
- type: code
  path: scripts/ci/*.py
last_generated_commit: e649d2ecdca90ba62d0eb8230060f82bc6bb01ef
claims: []
confidence: high
tags:
- authored-v1
- scripts
- ci
created_at: 1785881400.0
updated_at: 1785881400.0
---

The CI guard suite is three independent pre-commit invariants. The
generated-fresh guard runs `sync-config` and fails if `config/backends.yaml`,
`.mcp.json`, or `opencode.jsonc` differ afterwards — the mechanical
enforcement of Rule 6, where any diff after an idempotent sync is, by
construction, a hand-edit that should not have happened. The identical-sources
guard fails if any `deploy/` Python file is byte-identical to a `portal_mcp/`
Python file by basename. The pyproject guard fails if any dependency list in
`pyproject.toml` contains the same package twice, normalized.

## Why

Each guard converts a silent drift into a loud, early failure. A hand-edited
generated file works until the next sync overwrites it, and the difference
then reappears as a mystery. A silent byte-identical duplicate is a
maintenance trap — one copy gets fixed and the deployed one keeps the old
behaviour — so failing loudly on divergence forces a deliberate decision
instead. Duplicate dependency pins are ambiguous (which version wins?) and
signal a merge accident, so the normalization folds case, `-`/`_`, and version
specifiers to catch `Requests>=2.0` and `requests==2.28` as the same package
while remaining scoped per context, because one package legitimately appears
in two different extras.

## Interfaces

The generated-fresh guard invokes `portal.platform.inference.sync_config` as
a subprocess and diffs the generated paths, with a fast-path skip when
`config/` has no tracked changes. The identical-sources guard indexes
`deploy/` and `portal_mcp/` by basename and compares bytes. The pyproject
guard parses the TOML (with a `tomli` fallback for older Pythons), collects
every dependency into its context, and names offending contexts.

## Gotchas

The identical-sources comparison is by name, not path — two files at
different depths still collide if their basenames match, which is exactly the
playwright-mcp case. The pyproject normalization replaces `-` with `_`, so
two pins of the same package with different spellings or version specifiers
are caught while distinct packages that merely share a stem are not folded
together.
