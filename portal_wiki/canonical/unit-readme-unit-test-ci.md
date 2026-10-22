---
id: unit-readme-unit-test-ci
kind: what
title: "README \u2014 Unit Test CI"
sources:
- type: code
  path: .github/workflows/unit-tests.yml
- type: code
  path: .pre-commit-config.yaml
- type: code
  path: scripts/pytest_unit_with_tree_marker.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6919382
updated_at: 1792627200
---

The test suite runs on every PR and push to `main` via GitHub Actions. The
workflow `.github/workflows/unit-tests.yml` runs `pytest tests portal` (with
`-n auto -x --tb=short -v`) in a clean environment, so a change that breaks any
test blocks the merge.

For local pre-commit feedback, install the hooks once:

```bash
pip install pre-commit && pre-commit install
```

The hook config (`.pre-commit-config.yaml`) defines the per-commit gate: gitleaks
(block committed secrets), ruff lint and format, the generated-artifacts-fresh
check (sync-config idempotent), a portal config validation, and a `pytest-unit`
hook running `pytest tests/unit -n 4 -x --tb=short -q` through
`scripts/pytest_unit_with_tree_marker.py`. The cap is `2fd0da3a` (2026-10-22):
this host's `-n auto` started 14 workers, and parallel lane commits on the
machine that serves the live stack starved memory until UAT shots received
HTTP 503. Actions still uses `-n auto` on a runner that does not serve the
stack. A live measurement on this host needs a quiet machine. See
[[unit-known-limitations-host-measurement-contention]]. A heavier
`validate-system` hook (`scripts/validate_system.py --skip-pytest`) runs at push
time when the change touches `portal/`, `config/`, `portal_wiki/`, `scripts/`,
`deploy/` or `tests/`.

## Why

Unit tests must pass with no network and no live services, so the CI gate runs in
a clean environment where local state cannot mask a broken import. The
pre-commit hooks move the same checks earlier, catching style, freshness and
test failures before the commit is made, while the heavier system validation stays
at push time to keep the per-commit cost low. The local worker cap exists because
the unit suite shares unified memory with the live stack.
