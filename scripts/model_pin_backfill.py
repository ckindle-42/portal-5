#!/usr/bin/env python3
"""Pin config/backends.yaml hf.co ids from the local Ollama blob and HF main.

Dry-run by default. ``--write`` records repo, filename and sha256, or
``unpinned`` when the local model-layer sha256 is not on HF main. No downloads.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.model_upstream import (  # noqa: E402
    backfill_lines,
    default_fetch,
    models_dir,
)

BACKENDS = REPO / "config" / "backends.yaml"


def main(argv: list[str]) -> int:
    write = "--write" in argv
    text = BACKENDS.read_text(encoding="utf-8")
    lines, updated = backfill_lines(text, models_dir(), default_fetch, write=write)
    for line in lines:
        print(line)
    if write and updated != text:
        BACKENDS.write_text(updated, encoding="utf-8")
        print(f"wrote {BACKENDS}")
    elif write:
        print("no pin changes")
    else:
        print("dry-run (pass --write to edit config/backends.yaml)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
