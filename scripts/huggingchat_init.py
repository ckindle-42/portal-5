"""HuggingChat (chat-ui) initializer — generate models.yaml config.

Usage:
  python scripts/huggingchat_init.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from frontend_seeder.adapters.huggingchat import generate_models_yaml

PORTAL_ROOT = Path(__file__).resolve().parent.parent
MODELS_OUTPUT = PORTAL_ROOT / "config" / "huggingchat" / "models.yaml"


def main() -> None:
    print("[huggingchat-init] Generating config/huggingchat/models.yaml...")
    generate_models_yaml(output_path=MODELS_OUTPUT)
    print("[huggingchat-init] Done.")


if __name__ == "__main__":
    main()
