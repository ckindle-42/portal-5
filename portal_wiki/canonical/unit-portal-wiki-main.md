---
id: unit-portal-wiki-main
kind: mixed
title: "Wiki CLI \u2014 render/status/propose/drift maintenance surface"
sources:
- type: code
  path: portal_wiki/__main__.py
  commit: dc13b2d5
last_generated_commit: dc13b2d5
claims: []
confidence: high
tags:
- authored-v1
- wiki
- cli
created_at: 1785796111.272097
updated_at: 1785796111.272097
---

The wiki CLI is the one-command maintenance surface for the canonical layer:
`render` regenerates the derived views, `status` reports wiki state, `propose`
lists proposed units, and `drift` runs the code-to-doc drift census that `BS`
uses as its data source. It wires the store's canonical directory to the repo
path so every subcommand sees the same tree.

## Why

The CLI exists to make the wiki operations re-runnable by an operator or an
agent without threading the store setup through each script. `cmd_render`
registers the view renderers in one place so adding a view is one line; the
`--check` mode renders to a temp dir and diffs against the committed output,
which is the drift gate that proves the generated docs are current. The
`drift` subcommand is the standing instrument for the drift census — it exits
non-zero on a claim violation or unbaselined drift and can re-pin the
baseline with `--pin-baseline`.

## Interfaces

`cmd_render` handles `render --all` / `--check` / `--dry-run`;
`cmd_status` reports wiki status; `cmd_drift` runs the census or pins the
baseline; `cmd_propose` lists proposed units. `_hash_dir` backs the
change-detection used by the drift-gate comparison.

## Gotchas

The CLI derives the repo root from `__file__`, so it works from any cwd as
long as the package is importable — but it always targets this repository's
canonical directory, never a configured alternative.
