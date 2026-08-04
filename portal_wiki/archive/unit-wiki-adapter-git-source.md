---
id: unit-wiki-adapter-git-source
kind: mixed
title: "Wiki git source adapter \u2014 repo walker for the spine"
sources:
- type: code
  path: portal/platform/wiki/adapters/git_source.py
  commit: 66aa9fda
last_generated_commit: 66aa9fda
claims: []
confidence: high
tags:
- authored-v1
- wiki
- adapter
created_at: 1785797561.222673
updated_at: 1785797561.222673
---

The Git source connector wires the stack-agnostic `SourceConnector` interface
to the portal-5 repository: it walks the repo for Python modules and docs and
returns them as source records the seeding adapters consume.

## Why

The wiki engine's interfaces are Portal-agnostic by design, so the *connection
to this specific repo* has to live in an adapter. This module is that
connection: it knows the repo's layout, which directories to skip (test
results, caches, hidden dirs), and how to present the files as sources. The
interface/adapter split is what lets the engine be tested without a real repo
while the real repo is walked through this connector.

## Interfaces

`GitSourceConnector.iter_sources()` returns the source-file records (Python
modules and docs) with their relative paths, used by the code seeder and the
fact derivation.

## Gotchas

The connector skips `results/` directories — the bench-output area is data,
not a knowledge source, and walking it would flood the spine with noise.
