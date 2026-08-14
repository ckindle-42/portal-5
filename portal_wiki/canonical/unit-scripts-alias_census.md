---
id: unit-scripts-alias_census
kind: mixed
title: "Script \u2014 alias_census"
sources:
- type: code
  path: scripts/alias_census.py
  commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799451.008158
updated_at: 1785799451.008158
---

Walks git-tracked files, excludes frozen historical artifacts and archived docs, and counts references to each of the 23 pre-collapse alias ids. It is the measurement behind the alias-removal closeout — the number that proves the shims can be removed.

## Why

A closeout is only real when it is measured. The census counts live references to the retired alias ids, excluding the frozen artifacts that legitimately keep historical mentions, so the removal decision rests on how many live callers remain. Reading from git means the census reflects the tracked tree, not the working-directory noise.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
