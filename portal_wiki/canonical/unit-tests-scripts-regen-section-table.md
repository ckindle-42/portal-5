---
id: unit-tests-scripts-regen-section-table
kind: mixed
title: "Section-table regenerator \u2014 marker-delimited derived table"
sources:
- type: code
  path: tests/scripts/regen_section_table.py
  commit: dc13b2d5
last_generated_commit: dc13b2d5
claims: []
confidence: high
tags:
- authored-v1
- tests
- scripts
created_at: 1785796179.317337
updated_at: 1785796179.317337
---

The section-table regenerator maintains the Section Reference table in the
V6 acceptance prompt by introspection: it reads the acceptance driver
(`tests/portal5_acceptance_v6.py`), counts the `record()` calls per section
function, and rewrites the table block between the `SECTION_TABLE_BEGIN` and
`SECTION_TABLE_END` markers in the execute doc, leaving everything outside the
markers untouched.

## Why

The section table is a count that must stay in sync with the acceptance
driver, and hand-editing it is exactly the drift this project keeps paying
for — a section gains a record call and the prompt's table silently reports
the old count. The marker-delimited rewrite is the single-write-point
discipline applied to a prompt file: the table is *derived* from the driver,
so it should be regenerated, not maintained. The `--check` mode is the CI
posture (exit non-zero if the committed table has drifted from the driver)
and `--diff` shows the change without writing, which is how an operator
reviews a regeneration before committing it.

## Interfaces

`main` introspects the acceptance module, builds the new table, and replaces
the marker-delimited block in the target doc. The three modes — write,
check, and diff — are the read/write/verify triad that keeps a generated
artifact honest.

## Gotchas

Any content between the two markers is replaced wholesale, so hand-written
notes *inside* the marked block are destroyed on regeneration — the contract
is that everything derived lives between the markers and everything authored
lives outside them.
