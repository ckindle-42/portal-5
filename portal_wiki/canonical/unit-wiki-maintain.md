---
id: unit-wiki-maintain
kind: mixed
title: "Wiki maintain \u2014 self-maintenance loop + staleness doctrine"
sources:
- type: code
  path: portal/platform/wiki/maintain.py
  commit: 649301d0f61c5bfcf00996b57c976122dd4f8e02
last_generated_commit: 649301d0f61c5bfcf00996b57c976122dd4f8e02
claims: []
confidence: high
tags:
- authored-v1
- wiki
created_at: 1785797305.434397
updated_at: 1785797305.434397
---

The maintain module is the self-maintenance loop for the wiki: it re-runs
the machine-derived seeders, updates WHAT units in place, re-cites them to the
current commit, and reports staleness. Its snapshot-diff discipline means a
no-change run produces no churn.

## Why

The maintenance loop exists because the machine-derived units (code, facts,
technique signatures) are projections of the repo and must track it, while
authored WHY units persist unless deliberately revised. `check_staleness`
encodes the doctrine that advancing HEAD alone does not make an authored unit
stale — authored units are the spine and provenance is navigation, not
reverse authority — so only the derived units are compared against their
exact would-be derivations. The snapshot hash is the churn guard: `update`
takes a hash before and after, and if nothing changed it returns an empty
list rather than rewriting files for no reason.

## Interfaces

`update_what_units` re-runs the code, signature, and fact seeders;
`check_staleness` compares stored derived bodies against fresh derivations
and returns the stale list; `wiki_status` reports total/what/why/mixed
counts, staleness, and integrity issues; `canonical_snapshot_hash` is the
churn detector.

## Gotchas

`update_what_units` is idempotent because `save_unit` overwrites by unit id —
re-seeding updates in place rather than duplicating, which the module's own
history shows was once a real failure (signature units were seeded but never
invoked, so they never landed in the store).

`python3 -m portal_wiki render --all` calls `update_what_units` as its first
step, unconditionally, before rendering any view — "no-change run produces no
churn" describes the snapshot hash, not the blast radius when the seeders
*do* disagree with what's stored. A live seeder can diverge from stored units
for reasons that have nothing to do with the task at hand (a MITRE mapping
tweak, a signature-format change, months of accumulated drift), and `--all`
will rewrite every such unit — observed rewriting title/sources/tags on 39
`unit-T*-signature` units and inventing new `unit-code-*` files in one run.
Never reach for `--all` to fix a single doc reference; `render --check` is
the read-only currency check for that. If `--all` is genuinely needed, treat
its output as its own reviewed change — diff every touched unit before
`git add`, never `git add -A` — not something to fold into an unrelated task.
