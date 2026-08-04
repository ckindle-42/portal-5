---
id: unit-uat-catalog-g_auto_docs
kind: mixed
title: "UAT catalog group \u2014 auto-documents"
sources:
- type: code
  path: tests/uat_catalog/g_auto_docs.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800128.804708
updated_at: 1785800128.804708
---

This catalog group covers the auto-documents workspace(s), exporting a `TESTS`
list of 11 UAT tests across the auto-documents section(s).

## Why

Its tests cover document generation and reading across every format: DOCX with tables, Excel trackers, PowerPoint decks, and the read-back of uploaded Word, Excel, PDF, and PowerPoint files. The format-validation tests are the contract — a document tier that returns text instead of a real file fails here.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
