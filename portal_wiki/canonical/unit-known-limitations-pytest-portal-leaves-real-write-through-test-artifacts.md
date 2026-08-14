---
id: unit-known-limitations-pytest-portal-leaves-real-write-through-test-artifacts
kind: what
title: "KNOWN_LIMITATIONS \u2014 `pytest portal` Write-Through Artifacts (Resolved)"
sources:
- type: code
  path: portal/modules/security/tests/conftest.py
- type: code
  path: portal/modules/security/tests/test_write_isolation.py
- type: code
  path: portal/modules/security/core/field_journal.py
- type: code
  path: portal/modules/security/core/loop.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.664905
updated_at: 1784946220.664905
---

- **Status**: RESOLVED 2026-07-29.
- **Former issue**: Security module tests could write journals and checkpoints into the real runtime tree, leaving dated entries in the committed `field_journal/` history and stray checkpoint files.
- **Resolution**: The autouse fixture `isolated_security_writes` in `portal/modules/security/tests/conftest.py` monkeypatches `field_journal.JOURNAL_DIR`, `loop.RESULTS_DIR`, and `loop.CHECKPOINT_DIR` into each test's `tmp_path`. The production modules also stopped creating those directories merely by being imported; the write functions (`field_journal.write_entry`, `loop._write_checkpoint`) create their destination lazily at write time.
- **Regression coverage**: `portal/modules/security/tests/test_write_isolation.py` writes both artifact types and asserts that their parents are the fixture sandbox.

## Why

Write-through test artifacts are dangerous because they look like real committed history and can ride along with an unrelated commit — the field journal is tracked, so a test-side entry becomes an untraceable line in the repo. Routing the write destinations through a fixture-injected `tmp_path` makes the sandbox the only possible target, and asserting the parent path in the regression test proves the isolation mechanically rather than by inspection.
