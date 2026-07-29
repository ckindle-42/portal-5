---
id: unit-known-limitations-importing-the-security-bench-module-sets-a-linux-only-prometheus-multiproc-dir-host-side
kind: what
title: "KNOWN_LIMITATIONS \u2014 Security Bench Import Mutated Host Environment (Resolved)"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: Importing the security bench module sets a Linux-only PROMETHEUS_MULTIPROC_DIR
    host-side
- type: code
  path: portal/modules/security/core/_data.py
- type: code
  path: tests/benchmarks/bench_lab_exec.py
- type: code
  path: tests/benchmarks/bench/config.py
- type: code
  path: tests/unit/test_import_environment.py
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.671319
updated_at: 1784946220.671319
---

- **ID**: P5-ENV-MULTIPROC-HOSTLEAK-001
- **Status**: RESOLVED 2026-07-29.
- **Former issue**: importing the security data module transitively loaded
  `.env` into process-global `os.environ`, including the container-only
  `PROMETHEUS_MULTIPROC_DIR=/dev/shm/portal_metrics` value.
- **Resolution**: the security data module, lab-exec benchmark, and shared
  benchmark config now parse dotenv into private mappings. Explicit process
  environment still wins, but imports do not add or alter environment keys.
- **Regression coverage**: a clean subprocess deliberately removes
  `UNIT_TEST_MODE` and `PROMETHEUS_MULTIPROC_DIR`, imports the security data
  module, and verifies that no environment key was added or changed.
