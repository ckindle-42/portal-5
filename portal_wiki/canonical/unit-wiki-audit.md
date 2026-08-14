---
id: unit-wiki-audit
kind: mixed
title: "Wiki audit \u2014 mechanical spine-integrity checks"
sources:
- type: code
  path: portal/platform/wiki/audit.py
  commit: 4ca84409
claims: []
confidence: high
tags:
- authored-v1
- wiki
created_at: 1785797317.1678998
updated_at: 1785797317.1678998
---

The audit module enforces the mechanical integrity properties that make the
spine trustworthy: canonical bodies may not contain extraction or truncation
artifacts, repository-local provenance must resolve to a real file or glob,
and non-local identifiers (URLs, ATT&CK IDs, runtime event identifiers) remain
valid provenance without being mistaken for filesystem paths. It is
deliberately stack-agnostic with no Portal runtime imports.

## Why

The audit is the "the spine is not garbage" gate. Extraction artifacts — the
truncation marker strings a seeder leaves when it captured a cut-off model
response — in a canonical body mean the body is not the truth it claims to
be, so their presence is a hard integrity failure. Provenance that resolves
to nothing means a unit cites a file that does not exist, exactly the
dead-reference failure the drift census measures at the doc level, caught
here at the unit level. The identifier handling exists because a technique id
or a bench-run marker is legitimate provenance but must not be globbed as a
filesystem path.

## Interfaces

`audit_units(repo_root, units)` returns the `IntegrityIssue` list;
`source_is_repository_local` classifies a source reference; the module feeds
the `wiki_status` integrity count.

## Gotchas

The audit is mechanical, not semantic — it catches truncation markers and
dead provenance, not a body that is *wrong* (that is the drift census's job,
and the quality gate's). Its own rejection patterns are read from the module,
so a unit describing the audit must not reproduce those markers verbatim or
it will be flagged as corrupt itself.
