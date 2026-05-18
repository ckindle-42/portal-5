"""AnythingLLM initializer — seed workspaces via API.

Usage:
  python scripts/anythingllm_init.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from frontend_seeder.adapters.anythingllm import seed


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
