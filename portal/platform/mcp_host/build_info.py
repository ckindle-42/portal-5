"""What build a service process runs (root-fix Part 2c).

Docker images carry PORTAL_BUILD_SHA from `./launch.sh` build args; host-native services get it
from scripts/native-mcp-service.sh, with PORTAL_BUILD_DIRTY counting uncommitted changes under
portal/ at launch. MCP health routes report both, so WFE preflight can prove which code served.
"""

from __future__ import annotations

import os


def build_info() -> dict[str, str | int]:
    dirty = os.environ.get("PORTAL_BUILD_DIRTY", "")
    return {
        "build_sha": os.environ.get("PORTAL_BUILD_SHA") or "unknown",
        "build_dirty": int(dirty) if dirty.isdigit() else -1,
    }
