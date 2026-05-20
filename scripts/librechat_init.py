"""LibreChat initializer — generate config and seed presets.

Usage:
  python scripts/librechat_init.py [--config-only] [--seed-only]

Default: generate config/librechat/librechat.yaml, then seed presets via API.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Make the scripts/ dir importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from frontend_seeder.adapters.librechat import generate_librechat_yaml, seed

PORTAL_ROOT = Path(__file__).resolve().parent.parent
CONFIG_OUTPUT = PORTAL_ROOT / "config" / "librechat" / "librechat.yaml"


def main() -> None:
    parser = argparse.ArgumentParser(description="LibreChat config generator + seeder")
    parser.add_argument("--config-only", action="store_true", help="Only generate librechat.yaml, skip API seeding")
    parser.add_argument("--seed-only", action="store_true", help="Only seed via API, skip config generation")
    args = parser.parse_args()

    if not args.seed_only:
        print("[librechat-init] Generating config/librechat/librechat.yaml...")
        generate_librechat_yaml(output_path=CONFIG_OUTPUT)

    if not args.config_only:
        asyncio.run(seed())


if __name__ == "__main__":
    main()
