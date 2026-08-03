---
id: unit-wiki-store
kind: mixed
title: "Wiki store \u2014 git-backed canonical unit persistence"
sources:
- type: code
  path: portal/platform/wiki/store.py
  commit: 4ca84409
last_generated_commit: 4ca84409
claims: []
confidence: high
tags:
- authored-v1
- wiki
created_at: 1785797299.6082618
updated_at: 1785797299.6082618
---

The store module is the git-backed persistence layer for canonical units:
each unit is one markdown file under `portal_wiki/canonical/`, and the store
provides save, load, list, and delete over that directory. It is deliberately
portable — git-versioned, no database lock-in.

## Why

Storing units as markdown files is a design choice with two payoffs: the
units are diffable and reviewable as plain files, and the store needs no
database service to run. The canonical directory is overridable
(`set_canonical_dir`) so tests and the CLI can point the store at a different
tree without changing code — that is how the self-improving-cycle integration
test redirects writes into a `tmp_path`. `load_all` skips malformed files
rather than crashing, so one corrupt unit does not take down every consumer.

## Interfaces

`save_unit` writes a unit's markdown; `load_unit` reads one by id (None if
absent); `load_all` reads every unit sorted by filename; `list_ids` returns
the id list; `delete_unit` removes a file. `set_canonical_dir` and
`reset_canonical_dir` manage the directory override.

## Gotchas

The default canonical path is derived from the module location
(`parents[3] / portal_wiki / canonical`) so the store works from any cwd,
but any code that calls `set_canonical_dir` changes the global for the whole
process — a side effect tests must reset.
