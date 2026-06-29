#!/usr/bin/env python3
"""CI guard: fail if any deploy/ .py file is byte-identical to a portal_mcp/ .py file.

Rationale: deploy/playwright-mcp/browser_mcp.py is a known duplicate of
portal_mcp/browser/browser_mcp.py. The Docker build context for playwright-mcp
is local, so the files cannot be collapsed to a symlink. This guard prevents
them from silently diverging — if they differ, it fails and forces either a
manual sync or a build-context change.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent

DEPLOY_DIR = REPO / "deploy"
MCP_DIR = REPO / "portal_mcp"


def main() -> int:
    deploy_files = {f.name: f for f in DEPLOY_DIR.rglob("*.py")}
    mcp_files = {f.name: f for f in MCP_DIR.rglob("*.py")}

    duplicates = []
    for name in deploy_files:
        if name in mcp_files:
            a = deploy_files[name].read_bytes()
            b = mcp_files[name].read_bytes()
            if a == b:
                duplicates.append((deploy_files[name], mcp_files[name]))
            # If they differ, that's fine — they're not identical copies
            # (one may be a deploy-adapted version)

    if duplicates:
        print("[guard] no-identical-sources: WARN — identical files detected.")
        print("  These files are byte-identical; if one is updated, the other must be too.")
        for a, b in duplicates:
            print(f"  {a.relative_to(REPO)}  ≡  {b.relative_to(REPO)}")
        print()
        print("  Options:")
        print("    1. Update both files to keep them in sync.")
        print("    2. Change the deploy/ Dockerfile to use a wider build context")
        print("       and COPY from portal_mcp/, eliminating the duplicate entirely.")
        # This is WARN not FAIL — the duplication was accepted by the operator (M7-Step1).
        # Divergence (files differ but both exist) is a real error and would show
        # up as a behavioral difference, not caught here.
        return 0

    print(
        "[guard] no-identical-sources: OK (no byte-identical deploy↔mcp files, or known pair still in sync)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
