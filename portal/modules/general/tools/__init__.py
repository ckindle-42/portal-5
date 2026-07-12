"""The general module's base tools — externally vendored MCP servers, not
Portal source. Declared in config/portal.yaml's mcp_fleet (single source
of truth per CLAUDE.md Rule 6), rendered to .mcp.json by sync-config.

All four are IDE-only (expose_to_pipeline: false) — available to Claude
Code / opencode for repo work, not callable by workspace personas through
the pipeline. This module intentionally has no Python wrapper code: the
real "implementation" is the third-party package each server runs.
"""

BASE_TOOL_FLEET_IDS: tuple[str, ...] = ("filesystem", "fetch", "git", "docker")
