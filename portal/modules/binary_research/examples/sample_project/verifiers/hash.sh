#!/usr/bin/env bash
set -euo pipefail
JOB_DIR="${JOB_DIR:-.}"
source "$JOB_DIR/.expected" 2>/dev/null || { echo "FAIL: .expected not found"; exit 1; }
[ -f "$JOB_DIR/03_model.md" ] || { echo "FAIL: 03_model.md missing"; exit 1; }
if grep -qF "$SHA256" "$JOB_DIR/03_model.md"; then echo "PASS: hash"; exit 0; else echo "FAIL: hash"; exit 1; fi
