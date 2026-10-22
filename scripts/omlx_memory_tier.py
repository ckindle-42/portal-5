#!/usr/bin/env python3
"""Set oMLX's memory guard tier in ~/.omlx/settings.json; restart oMLX only on change.

Daily operation (Portal stack + Ollama up) runs `balanced`. `aggressive` (1.5GB
reserve vs 5.1GB) was added 2026-10-01 for the removed REAP-288 IDE session:
with the stack down `balanced` left a ~39.8GB prefill ceiling that rejected its
~39.97GB peak even for a one-word prompt. Nothing sets it since the removal
(2026-10-21); `./launch.sh up` always puts `balanced` back.

Usage: omlx_memory_tier.py {safe|balanced|aggressive} [--no-restart]
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SETTINGS = Path.home() / ".omlx" / "settings.json"
TIERS = ("safe", "balanced", "aggressive")


def set_tier(tier: str, path: Path = SETTINGS) -> bool:
    """Write `tier` into the settings file. Returns True when the file changed."""
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}, got {tier!r}")
    data = json.loads(path.read_text())
    memory = data.setdefault("memory", {})
    if memory.get("memory_guard_tier") == tier:
        return False
    memory["memory_guard_tier"] = tier
    path.write_text(json.dumps(data, indent=2))
    return True


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in TIERS:
        print(__doc__)
        return 2
    changed = set_tier(argv[0])
    print(f"oMLX memory guard tier: {argv[0]} ({'changed' if changed else 'already set'})")
    if changed and "--no-restart" not in argv:
        subprocess.run(["brew", "services", "restart", "jundot/omlx/omlx"], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
