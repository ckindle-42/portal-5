---
id: unit-tool-preselect-test-preselector
kind: mixed
title: "Preselector tests \u2014 every fallback branch, no live backend"
sources:
- type: code
  path: portal/platform/inference/tool_preselect/tests/test_preselector.py
  commit: 50d41b55
last_generated_commit: 50d41b55
claims: []
confidence: high
tags:
- authored-v1
- platform
- tool-preselect
- tests
created_at: 1785796860.508613
updated_at: 1785796860.508613
---

This test file covers `preselect()` end to end with every Ollama call mocked:
each fallback branch in the §1.9 failure-mode table (not opted in, disabled
flag, too few tools, ranker timeout, low confidence, parse failure), plus the
happy path that narrows the tool set.

## Why

The preselector's most important property is that it *never raises* and
always falls back to the full tool set — a failure in any branch must degrade
to "return everything", never crash the request. Testing every fallback with
the backend mocked is how that totality is proven without a live Ollama. The
`bypass_low_tools` case matters because it is the easy-to-break short-circuit:
narrowing five tools saves nothing, and a change that removes the guard would
add latency to small workspaces for zero gain.

## Interfaces

The suite constructs synthetic tool sets and mock responses and asserts both
the returned subset (full set on fallback, narrowed on success) and the
`PreselectOutcome.reason` label for each path.

## Gotchas

The tests mock the HTTP client via `patch`/`AsyncMock`, so they pin the
fallback *behaviour*, not the wire format — a change to the Ollama request
shape that still returns the same response will not be caught here.
