---
id: unit-tests-unit-test-security-corpus-contract
kind: what
title: Security corpus contract unit test
sources:
- type: code
  path: tests/unit/test_security_corpus_contract.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5
updated_at: 1784946220.5
---

`test_security_corpus_contract.py` is a single, focused contract test for the corpus definition shipped as `config/security_corpus.yaml`. It loads that YAML from the repo root and asserts the answer keys are visible only to the scorer, that the live portal source carries scenario proof while the public labeled source does not, that external scenario substitution stays disabled, and that no source may declare a theory data mode. It also pins the exact exclusion list for lab replay, requiring the cloud breach and confluence scenarios out while keeping the web-to-root scenario available for replay. The deliberately small surface makes drift obvious whenever the corpus config is edited.

## Why

The corpus contract is the promise that every downstream measurement — detection coverage, readiness gates, benchmark scoring — inherits: where the evidence came from and who may see the answers. A single test that pins the whole contract in one place forces any change to the corpus to be intentional, because weakening a provenance guarantee or exposing answer keys would fail here immediately rather than corrupt a benchmark silently.
