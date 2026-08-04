---
id: unit-security-investigation-notebook
kind: mixed
title: "Investigation case notebook \u2014 shared per-case memory"
sources:
- type: code
  path: portal/modules/security/core/investigation/case_notebook.py
  commit: 573a2377
last_generated_commit: 573a2377
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- investigation
created_at: 1785796320.872406
updated_at: 1785796320.872406
---

`CaseNotebook` is the investigation memory for one case — one of the seven
strictly separated memory kinds the RBP design defines. It is writable and
readable by all agents working the same case, holds hypotheses, findings,
annotations, scratch, and decisions as entries, and is promotable to the
Prior-Incident library only by analyst confirmation at case close.

## Why

The seven-way memory separation exists because each memory kind has a
different trust and lifetime, and blurring them is how an agent starts
treating its own scratch as established fact. The case notebook is the
deliberate middle tier: shared across the agents in a case and writable by
all of them (unlike the immutable evidence store), but bounded to the life of
one investigation (unlike the long-lived prior-incident library). The
supersession link (`superseded_by`) is how a revised hypothesis stays in the
record as history rather than being overwritten — the notebook is mutable
unlike evidence, but the mutations are themselves recorded. The promotion
gate to Prior-Incident being analyst-confirm-only is what stops a case
conclusion from silently becoming institutional knowledge.

## Interfaces

`NotebookEntry` is the entry record with id, case id, authoring agent, entry
type, content, and supersession; `CaseNotebook` is the sqlite-backed store
providing add/read/query across the case.

## Gotchas

The notebook is strictly per-case — an agent in a different case must not
read another case's notebook, which is why every query is scoped by
`case_id` rather than being a global memory table.
