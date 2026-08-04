---
id: unit-acceptance-s04_documents
kind: mixed
title: "S4 \u2014 Document generation"
sources:
- type: code
  path: tests/acceptance/s04_documents.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799749.24546
updated_at: 1785799749.24546
---

This is the acceptance section s04_documents. S4 — Document generation

## Why

It proves the document workspaces produce real files in the expected formats, not text masquerading as a document. A document persona that returns prose instead of a file is a silent failure the artifact validation catches, which is the difference between a document tier that works and one that merely talks about working.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
