---
id: unit-known-limitations-pytest-portal-leaves-real-write-through-test-artifacts
kind: what
title: "KNOWN_LIMITATIONS \u2014 `pytest portal` Write-Through Artifacts (Resolved)"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: '`pytest portal` Leaves Real Write-Through Test Artifacts'
- type: code
  path: portal/modules/security/tests/conftest.py
- type: code
  path: portal/modules/security/tests/test_write_isolation.py
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.664905
updated_at: 1784946220.664905
---

- **Status**: RESOLVED 2026-07-29.
- **Former issue**: Security module tests could write journals and checkpoints
  into the real runtime tree.
- **Resolution**: An autouse fixture redirects `JOURNAL_DIR`, `RESULTS_DIR`, and
  `CHECKPOINT_DIR` into each test's `tmp_path`. The production modules also
  stopped creating those directories merely by being imported; write
  functions create their destination lazily.
- **Regression coverage**: `test_write_isolation.py` writes both artifact types
  and asserts that their parents are the fixture sandbox.
