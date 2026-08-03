---
id: unit-uat-browser
kind: mixed
title: "UAT browser \u2014 Playwright helpers"
sources:
- type: code
  path: tests/uat/browser.py
  commit: 85bb65bd
last_generated_commit: 85bb65bd
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat
created_at: 1785799298.675957
updated_at: 1785799298.675957
---

The Playwright helpers for the UAT driver: login, send, completion-wait, and artifact capture.

## Why

The UAT run needs a real browser to drive Open WebUI, and the browser module centralises the Playwright interaction — login, sending a message, waiting for completion, and capturing artifacts — so every section uses the same robust wait-for-completion logic instead of embedding timing loops.

## Interfaces

The Playwright login/send/completion-wait/artifact helpers.

## Gotchas

Completion-wait is the flaky point — a section that replaces the shared wait with a timing loop re-introduces the flakiness the module exists to remove.
