#!/usr/bin/env bash
# Mirror CI's unit-test job EXACTLY: clean env, editable install, same pytest invocation.
# Run this before every push. If it's green, CI will be green.
#
# CI (.github/workflows/unit-tests.yml) runs on actions/setup-python, which ships a bare
# `python` + stdlib pip. Local dev machines use `uv` (CLAUDE.md Rule: package manager is uv,
# NOT pip) — `uv venv` does not install a `pip` module into the venv, and this repo's dev
# machines may not have a `python` shim on PATH at all (only `python3`). Use `uv` end-to-end
# locally so the gate works without either assumption, while still exercising the identical
# ruff/pytest invocations CI runs.
set -euo pipefail

echo "== ci-local: mirroring .github/workflows/unit-tests.yml =="

if ! command -v uv >/dev/null 2>&1; then
  echo "ci-local requires 'uv' (https://docs.astral.sh/uv/) — not found on PATH" >&2
  exit 1
fi

VENV="$(pwd)/.ci-local-venv"
rm -rf "$VENV"
uv venv --python 3.12 "$VENV" -q

# clean env — drop PYTHONPATH and any local LAB_* so we test as CI does, but keep the venv on PATH
env -i HOME="$HOME" PATH="$VENV/bin:$PATH" VIRTUAL_ENV="$VENV" bash -c '
  set -euo pipefail
  cd "$1"
  uv pip install -e ".[dev]" -q
  ruff check .
  ruff format --check .
  pytest tests/unit -n auto -x --tb=short -q
' _ "$(pwd)"

rm -rf "$VENV"
echo "== ci-local: PASS — safe to push =="
