---
id: unit-acceptance-s21_llm_router
kind: mixed
title: "S21 \u2014 LLM router"
sources:
- type: code
  path: tests/acceptance/s21_llm_router.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799801.407582
updated_at: 1785799801.407582
---

This is the acceptance section s21_llm_router. S21 — LLM router

## Why

It exercises the LLM router's classification, proving the Layer-1 routing path resolves correctly. The router is the decision layer everything depends on, and a router regression is invisible until a request goes to the wrong workspace, which is why its own section drives the classifier directly.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
