---
id: unit-wiki-adapter-seed-intent
kind: mixed
title: "Wiki intent seeder \u2014 WHY-unit ingestion from design docs"
sources:
- type: code
  path: portal/platform/wiki/adapters/seed_intent.py
  commit: 66aa9fda
last_generated_commit: 66aa9fda
claims: []
confidence: high
tags:
- authored-v1
- wiki
- adapter
created_at: 1785797590.63635
updated_at: 1785797590.63635
---

The intent seeder ingests WHY knowledge — architecture rationale, security
decisions, design principles — from CLAUDE.md, design docs, and RFCs, as WHY
units each citing its design-doc source.

## Why

The WHY layer is what a projection can never supply: the reasons the system
is shaped the way it is. The seeder reads the authored intent documents and
turns their decisions into units, so the spine carries the rationale alongside
the machine-derived WHAT layer. The id sanitisation makes a document title
into a filesystem-safe unit id.

## Interfaces

`seed_intent(dry_run)` returns the WHY units; `_extract_sections` splits a
document into its structural sections for unit-shaped ingestion.

## Gotchas

WHY units persist across maintenance runs — the loop updates WHAT units and
leaves WHY alone unless deliberately revised, which is the authored-unit
doctrine.
