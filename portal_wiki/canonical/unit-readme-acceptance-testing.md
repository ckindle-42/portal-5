---
id: unit-readme-acceptance-testing
kind: what
title: "README \u2014 Acceptance Testing"
sources:
- type: doc
  path: README.md
  commit: 05e42ec2
  section: Acceptance Testing
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.691529
updated_at: 1784946220.691529
---

The full acceptance test suite (`tests/portal5_acceptance_v6.py`) runs
~300 tests across ~27 sections. Run with:

```bash
python3 tests/portal5_acceptance_v6.py        # full suite
python3 tests/portal5_acceptance_v6.py --section S70  # one section
```

Latest run summary is in [ACCEPTANCE_RESULTS.md](ACCEPTANCE_RESULTS.md).
