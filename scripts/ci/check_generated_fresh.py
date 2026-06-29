#!/usr/bin/env python3
"""CI guard: generated artifacts must be fresh (sync-config is idempotent).

Runs portal_pipeline.sync_config and checks git diff on the three generated
files. Fails if any file changed — meaning a human edited a generated artifact
instead of editing portal.yaml and re-running sync-config.

Does NOT run if portal.yaml or config/ has no tracked changes (fast-path skip).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
GENERATED = ["config/backends.yaml", ".mcp.json", "opencode.jsonc"]


def main() -> int:
    # Run sync-config
    result = subprocess.run(
        [sys.executable, "-m", "portal_pipeline.sync_config"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("[guard] generated-fresh: FAIL — sync-config errored")
        print(result.stderr[:500])
        return 1

    # Check for diffs in generated files
    diff = subprocess.run(
        ["git", "diff", "--name-only", "--", *GENERATED],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    changed = [f.strip() for f in diff.stdout.splitlines() if f.strip()]
    if changed:
        print("[guard] generated-fresh: FAIL — generated artifacts are stale:")
        for f in changed:
            print(f"  {f}")
        print()
        print("  Fix: edit config/portal.yaml then run ./launch.sh sync-config")
        return 1

    print("[guard] generated-fresh: OK (sync-config idempotent, no diff)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
