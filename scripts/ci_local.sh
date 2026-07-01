#!/usr/bin/env bash
# Mirror CI's unit-test job EXACTLY: clean env, editable install, same pytest invocation.
# Run this before every push. If it's green, CI will be green.
set -euo pipefail

echo "== ci-local: mirroring .github/workflows/unit-tests.yml =="

# clean env — drop PYTHONPATH and any local LAB_* so we test as CI does
env -i HOME="$HOME" PATH="$PATH" bash -c '
  set -euo pipefail
  cd "$1"
  python -m pip install -e ".[dev]" -q
  ruff check .
  ruff format --check .
  pytest tests/unit -x --tb=short -q
' _ "$(pwd)"

echo "== ci-local: PASS — safe to push =="
