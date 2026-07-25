---
id: unit-readme-unit-test-ci
kind: what
title: "README \u2014 Unit Test CI"
sources:
- type: doc
  path: README.md
  commit: 05e42ec2
  section: Unit Test CI
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6919382
updated_at: 1784946220.6919382
---

The unit test suite (`pytest tests/unit -x`) runs on every PR and push to
`main` via GitHub Actions (`.github/workflows/unit-tests.yml`). For local
pre-commit feedback, install the hooks:

```bash
pip install pre-commit && pre-commit install
```

This adds a `pytest-unit` hook that runs before each commit.

---
