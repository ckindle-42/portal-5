---
id: unit-acceptance-s17_cad_render
historical: true
kind: mixed
title: "S17 \u2014 CAD render"
sources:
- type: code
  path: tests/acceptance/s17_cad_render.py
  commit: e75dddd2
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance

---

This is the acceptance section s17_cad_render. S17 — CAD render

## Why

It proves the CAD render path produces a 3D model artifact, exercising the CAD MCP end to end. CAD is a specialised generation path, and its section verifies both the model generation and the artifact output.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
