---
id: unit-wiki-tests-migration
kind: mixed
title: "Wiki migration tests \u2014 V2 anti-gaming migration rules"
sources:
- type: code
  path: portal/platform/wiki/tests/test_migration.py
  commit: dfa74e2e
last_generated_commit: dfa74e2e
claims: []
confidence: high
tags:
- authored-v1
- wiki
- tests
created_at: 1785795467.529739
updated_at: 1785795467.529739
---

This test file guards the migration module's anti-gaming rules — the V2
definitions of what counts as a migrated doc. It pins `strip_managed_regions`
(both the reasoned V2 fence and the bare V1 fence must be stripped), the
`substantive_remainder` notion (a doc is only "migrated" when nothing
substantive survives outside managed regions), and the migration-count helpers
that drive the doc-migration coverage figures.

## Why

The migration gate's whole point is that a doc is migrated only when its
factual content lives in a unit. The anti-gaming angle is the V2 refinement:
an early migration could slap a `WIKI:HUMAN-OWNED` fence around everything and
call the doc migrated, so V2 requires a `reason` on new fences and this test
guards the strip logic that removes both fence generations. `doc_is_migrated`
must be false when substantive prose survives outside the managed regions —
that is the definition AW enforces at the doc level, and `fenced_human_lines`
plus `human_owned_reasons` give the gate the fence inventory it needs to tell
a genuine human-owned block from a gaming fence.

## Interfaces

`strip_managed_regions`, `substantive_remainder`, `doc_is_migrated`,
`generated_block_count`, `fenced_human_lines`, and `human_owned_reasons` are
the migration helpers under test. The suites exercise each against synthetic
markdown strings built with `textwrap.dedent`.

## Gotchas

`strip_managed_regions` removes generated blocks and both fence generations —
so the tests for substantive remainder rely on the strip order: a doc of only
managed regions yields an empty remainder, which is the migrated condition.
