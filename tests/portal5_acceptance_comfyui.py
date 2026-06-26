#!/usr/bin/env python3
"""Portal 5 ComfyUI / Image & Video Acceptance — thin entrypoint.

Run from repo root:
    python3 tests/portal5_acceptance_comfyui.py [--section C4] [--verbose]

All implementation is in tests/comfyui/{cli,runner,results,_common}.py.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from comfyui.cli import main

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
