---
id: unit-tests-frontend-test-reasoning-display
kind: what
title: Reasoning display live-stack integration test
sources:
- type: code
  path: tests/frontend/test_reasoning_display.py
last_generated_commit: baca992c674a3cbb36a619e8f62e7e88b8fccfff
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5
updated_at: 1784946220.5
---

`test_reasoning_display.py` is a live-stack integration test for the auto-security workspace that splits into an API baseline and an Open WebUI browser check. The API half posts a `/think` prompt to the pipeline and asserts the response contains both a thinking block and a real answer after `_strip_think` removes reasoning content, treating that as the ground truth for model behaviour. The Playwright half, driven through the shared `browser_context` fixture and the `_owui_login` flow, confirms that Open WebUI buries `<think>` tokens inside collapsed `<details type="reasoning">` elements — the root cause of an earlier UAT driver failure where innerText stayed empty during streaming. Both halves skip cleanly when the required password, API key, or Playwright installation is absent.

## Why

The original UAT failure was not a pipeline bug but a frontend rendering behaviour: OWUI collapses the thinking block, so a DOM-stability check that reads visible text sees an empty bubble mid-stream and aborts early. This test pins that behaviour explicitly so future UAT drivers and model swaps know the failure mode exists, and its API baseline separates model failures from rendering failures instead of blaming the wrong layer.
