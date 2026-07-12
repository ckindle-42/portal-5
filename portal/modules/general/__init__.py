"""The general module — the always-on base (M1 of
BUILD_PROGRAM_MODULARIZATION_ALL_V1, template proof on a non-security
discipline).

Unlike security (a large Portal-owned codebase relocated intact), general
has no Portal-authored source to move: its "tools" are four externally
vendored MCP servers (filesystem, fetch, git, docker — see tools/) declared
in config/portal.yaml's mcp_fleet and consumed IDE-side by Claude Code /
opencode, not through the pipeline. This module is config-only: it
documents the real, existing surface rather than fabricating wrapper code
for tools Portal doesn't own the implementation of.
"""
