---
id: unit-acceptance-s10_personas_ollama
kind: mixed
title: "S10 \u2014 Personas over Ollama"
sources:
- type: code
  path: tests/acceptance/s10_personas_ollama.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799771.5222862
updated_at: 1785799771.5222862
---

This is the acceptance section s10_personas_ollama. S10 — Personas over Ollama

## Why

It exercises the persona set over the Ollama backend, proving the persona routing and serving path end to end. Personas are the routing layer's user-facing surface, and a persona that routes to the wrong workspace or fails to serve is caught here rather than in a downstream section.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
