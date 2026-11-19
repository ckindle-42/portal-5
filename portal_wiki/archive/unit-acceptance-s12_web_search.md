---
id: unit-acceptance-s12_web_search
historical: true
kind: mixed
title: "S12 \u2014 Web search"
sources:
- type: code
  path: tests/acceptance/s12_web_search.py
  commit: e75dddd2
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance

---

This is the acceptance section s12_web_search. S12 — Web search

## Why

It proves the web-search path returns results, exercising the search service integration. A search path that returns nothing or errors is a silent failure of the grounding surface, and this section is what isolates the search service from the models that consume its results.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
