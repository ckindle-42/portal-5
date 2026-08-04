---
id: unit-wiki-schema
kind: mixed
title: "Wiki schema \u2014 KnowledgeUnit + frontmatter round-trip contract"
sources:
- type: code
  path: portal/platform/wiki/schema.py
  commit: 649301d0f61c5bfcf00996b57c976122dd4f8e02
last_generated_commit: 649301d0f61c5bfcf00996b57c976122dd4f8e02
claims: []
confidence: high
tags:
- authored-v1
- wiki
created_at: 1785797293.694478
updated_at: 1785797293.694478
---

The schema module is the data model of the entire canonical knowledge layer:
`KnowledgeUnit` is the one unit type (id, kind, title, sources, body, claims,
tags) and `SourceRef` is the provenance citation. The frontmatter round-trip
that every save/load path depends on lives here.

## Why

The schema is the contract every other wiki module compiles against, and its
frontmatter round-trip is the reason the spine can be git-backed at all: a
unit is one markdown file, and `to_markdown`/`from_markdown` must be exact
inverses or a re-save destroys data. The `claims` field is the newest part of
that contract — it must survive the round-trip or the drift-census assertions
vanish on the next seed run, which is why the field is carried through
`to_frontmatter` and `from_markdown` explicitly. The never-bloat rule (no
empty sources) is enforced in `__post_init__` so a unit without provenance
cannot be created silently.

## Interfaces

`KnowledgeUnit` carries id, kind, title, sources, body, confidence, claims,
and tags, with `to_markdown`/`to_frontmatter`/`from_markdown` for the file
round-trip and `content_hash` for change detection. `SourceRef` is the
type/path/commit provenance citation.

## Gotchas

The kind is validated to `what|why|mixed` and confidence to
`high|medium|low` at construction — a unit that violates either is rejected
before it can enter the store.
