#!/usr/bin/env python3
"""Portal 5 persona coverage matrix — thin entrypoint.

Run from repo root:
    python3 tests/portal5_persona_matrix.py [--workspace auto-coding] ...

All implementation is in portal/modules/eval/persona_matrix/ (relocated
per BUILD_PROGRAM_MODULARIZATION_ALL_V1 M6 — tests/persona_matrix/ is
now a compat shim).
"""

from __future__ import annotations

import sys
from pathlib import Path

# python3 <script> puts the script's own directory on sys.path[0], not the
# repo root (unlike `python -m` or `-c`) — insert it explicitly so the
# editable-installed `portal` package resolves regardless of invocation style.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from portal.modules.eval.persona_matrix.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
