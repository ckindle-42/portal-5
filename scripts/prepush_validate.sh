#!/usr/bin/env bash
# Pre-push: validate exactly what is being pushed. Uncommitted edits to tracked files would be
# validated but not pushed (a fix in the tree let failing commits through, 2026-10-20).
set -euo pipefail
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "pre-push: tracked files have uncommitted changes; commit or stash them first" >&2
    git status --short --untracked-files=no >&2
    exit 1
fi
exec env PORTAL5_VALIDATE_CHANGED_ONLY=1 uv run python3 scripts/validate_system.py --skip-pytest
