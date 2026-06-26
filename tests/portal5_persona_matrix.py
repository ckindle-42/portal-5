#!/usr/bin/env python3
"""Portal 5 persona coverage matrix — thin entrypoint.

Run from repo root:
    python3 tests/portal5_persona_matrix.py [--workspace auto-coding] ...

All implementation is in tests/persona_matrix/.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from persona_matrix.cli import main

if __name__ == "__main__":
    sys.exit(main())
