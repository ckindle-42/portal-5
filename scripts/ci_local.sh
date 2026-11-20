#!/usr/bin/env bash
# Mirror CI's test job EXACTLY: clean env, editable install, same pytest invocation.
# Run this before every push. If it's green, CI will be green.
#
# CI (.github/workflows/unit-tests.yml) runs on actions/setup-python, which ships a bare
# `python` + stdlib pip. Local dev machines use `uv` (CLAUDE.md Rule: package manager is uv,
# NOT pip) — `uv venv` does not install a `pip` module into the venv, and this repo's dev
# machines may not have a `python` shim on PATH at all (only `python3`). Use `uv` end-to-end
# locally so the gate works without either assumption, while still exercising the identical
# ruff/pytest invocations CI runs.
set -euo pipefail

run_linux() {
  echo "== ci-local --linux: mirroring .github/workflows/unit-tests.yml in python:3.12-slim =="
  if ! command -v docker >/dev/null 2>&1; then
    echo "ci-local --linux requires 'docker' — not found on PATH" >&2
    exit 1
  fi
  local -a docker_mounts=(-v "$(pwd):/repo:ro" -v "portal5-ci-linux-cache:/root/.cache")
  local git_common_dir
  git_common_dir="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
  if [[ -n "$git_common_dir" && "$git_common_dir" != "$(pwd)/.git" ]]; then
    docker_mounts+=(-v "${git_common_dir}:${git_common_dir}:ro")
  fi
  docker run --rm "${docker_mounts[@]}" python:3.12-slim bash -c '
    set -euo pipefail
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq && apt-get install -y -qq --no-install-recommends git >/dev/null
    mkdir -p /work
    tar --exclude=.venv --exclude=.ci-local-venv --exclude=.mypy_cache --exclude=.pytest_cache --exclude=.ruff_cache --exclude=__pycache__ -C /repo -cf - . | tar -C /work -xf -
    cd /work
    python -m pip install -q --upgrade pip uv
    uv export --frozen --extra dev --no-hashes --no-emit-project > /tmp/lock-constraints.txt
    uv pip install --system -q -e ".[dev]" -c /tmp/lock-constraints.txt
    python scripts/complexity_report.py --gate
    pytest tests portal -n auto --tb=short -v
  '
  echo "== ci-local --linux: PASS — safe to push =="
}

case "${1:-}" in
  "") ;;
  --linux)
    run_linux
    exit 0
    ;;
  *)
    echo "Usage: $0 [--linux]" >&2
    exit 2
    ;;
esac

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
  # The strict type check needs optional package stubs and the locked mypy.
  uv sync --active --all-extras --frozen -q
  ruff check .
  ruff format --check .
  # Complexity ceilings (B4): exceeding one fails here and in CI.
  python3 scripts/complexity_report.py --gate
  # Compliance remains pre-service; keep its unfinished typing debt outside the
  # production gate until it is promoted. --active targets the isolated venv.
  uv run --active mypy --exclude "portal/modules/compliance/" portal/
  pytest tests portal -n auto -x --tb=short -q
' _ "$(pwd)"

rm -rf "$VENV"
echo "== ci-local: PASS — safe to push =="
