---
id: unit-security-tests-test-corpus-coverage
kind: what
title: Combined red-corpus coverage contract tests
sources:
- type: code
  path: portal/modules/security/tests/test_corpus_coverage.py
last_generated_commit: baca992c674a3cbb36a619e8f62e7e88b8fccfff
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5
updated_at: 1784946220.5
---

`test_corpus_coverage.py` holds the combined red-corpus coverage report to its provenance and mode contracts. Using `tmp_path` fixtures and a monkeypatched `list_captures`, it verifies that external techniques never substitute for live scenario proof, that a merely declared inventory cannot pass the live-probe readiness gate, and that an empty external probe fails that gate as well. A dedicated test proves a hollow, newer capture never masks an older valid one when the agentic blue loader chooses the episode, because freshness must not override validity. The source contract is asserted directly through `load_source_contract`, and the report must label the catalog as lab-exercise rather than theory, with unbacked scenarios kept out of the lab replay denominator.

## Why

Readiness gates exist to stop a benchmark from being run against evidence that was never actually observed. If external, publicly-labeled techniques could stand in for a live capture, or a hollow newest file could shadow a valid older one, the coverage report would say "ready" for detection design while the underlying proof is missing. These tests make the gate's honesty conditions explicit so the report cannot silently overstate what the corpus proves.
