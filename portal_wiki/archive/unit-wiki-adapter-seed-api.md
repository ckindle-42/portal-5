---
id: unit-wiki-adapter-seed-api
kind: mixed
title: "Wiki seed_api adapter \u2014 AST projection for the substance check"
sources:
- type: code
  path: portal/platform/wiki/adapters/seed_api.py
  commit: 66aa9fda
last_generated_commit: 66aa9fda
claims: []
confidence: high
tags:
- authored-v1
- wiki
- adapter
created_at: 1785797578.856166
updated_at: 1785797578.856166
---

`derive_body` is the AST projection the quality gate's substance check
compares a unit against: it parses a Python file and renders its API surface —
module and function/class signatures plus docstring first lines — as plain
text.

## Why

The substance check needs a baseline of "what the AST yields for free" to
detect a unit that merely restates it. This module produces that baseline:
a shallow, deliberately mechanical projection that a lazy summary would
reproduce. If a unit's prose overlaps this projection too much, the unit is a
projection, not an explanation. The derivation is optional by contract — an
unreadable or unparsable file yields an empty string and the comparison is
skipped rather than raised.

## Interfaces

`derive_body(path, repo_root)` returns the projected API text, or an empty
string when the file cannot be read or parsed.

## Gotchas

The projection is intentionally signature-only — it carries no insight, which
is the whole point. A unit that merely echoes it is flagged; a unit that
explains *why* the signatures exist necessarily diverges from it.
