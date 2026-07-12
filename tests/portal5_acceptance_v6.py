#!/usr/bin/env python3
"""Portal 5 Acceptance Test Suite v6 — thin entrypoint.

Run from repo root:
    python3 tests/portal5_acceptance_v6.py [--section S3] [--skip-passing] ...

All implementation is in tests/acceptance/{cli,runner,results,_common}.py.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# python3 <script> puts the script's own directory on sys.path[0], not the
# repo root (unlike `python -m` or `-c`) — insert both explicitly. tests/ is
# needed for the bare `acceptance._common`-style imports section modules use;
# the repo root is needed because acceptance/_common.py itself does absolute
# `from tests.memory_guard import ...` / `from portal.platform...` imports.
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

# Re-export signal dicts so unit tests that import this module still work
# (e.g. tests/unit/test_prompt_signal_overlap.py)
from acceptance._common import (  # noqa: F401
    PERSONA_PROMPTS,
    PERSONA_PROMPTS_EXCLUDED,
    WORKSPACE_PROMPTS,
)
from acceptance.cli import main

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
