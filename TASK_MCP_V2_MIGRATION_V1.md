# TASK: Migrate MCP Python SDK v1 → v2

**Task ID:** TASK-MCP-V2-MIGRATION-001
**Priority:** Low (v1.x still receives security patches upstream)
**Category:** Dependency upgrade
**Status:** Completed 2026-07-29

---

## Context

2026-07-28: `mcp` 2.0.0 was published on PyPI as a deliberate major rework (new
2026-07-28 MCP spec support + architectural fixes). It is a breaking release —
upstream's own README says `pip install mcp` now installs 2.x and instructs
projects not yet migrated to pin `<2`. CI broke (`ModuleNotFoundError: No module
named 'mcp.server.fastmcp'`) because `pyproject.toml` had an unbounded
`mcp>=1.9.0`; fixed short-term in commit 3dc92bf6 by pinning `mcp>=1.9.0,<2.0.0`
in both the `mcp` and `dev` extras. `uv.lock` already resolved to 1.27.0 so local
dev was never affected.

v1.x branch (https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)
continues to get critical bug fixes and security patches, so there's no urgency,
but v2 is where new features land going forward.

## Scope

22 files currently do `from mcp.server.fastmcp import FastMCP` (all
`portal/modules/*/tools/*_mcp.py`, `portal/platform/{mcp_host,memory}/`, plus
vendored servers in `portal_mcp/{filesystem,scrapling}/` — see Rule 3 in
CLAUDE.md for the full list of independent MCP services). v2's entry point is
renamed (`from mcp.server import MCPServer` per the v2 README snippet) — this is
not a drop-in rename, consult the real migration guide before touching code:

- What's new in v2: https://py.sdk.modelcontextprotocol.io/whats-new/
- Migration guide: https://py.sdk.modelcontextprotocol.io/migration/

## To do

- [x] Read the migration guide fully; enumerate every breaking change that
      touches how we use the SDK (tool registration decorators, transport
      setup, request/response types — whatever the guide flags).
- [x] Port all current `mcp.server.fastmcp` import sites.
- [x] Bump `pyproject.toml` pins from `<2.0.0` to the new v2 floor.
- [x] Regenerate `uv.lock` (`uv lock`) — expect this to also pick up transitive
      dependency drift unrelated to mcp itself (observed during the v1 pin fix:
      a full `uv lock` touched ~30 unrelated packages because the lock hadn't
      been refreshed recently) — review that diff for anything suspicious
      before committing, don't just accept it wholesale.
- [x] Full verification ladder: `pytest tests/unit/ -q && ruff check . && ruff
      format --check .`, then `bash scripts/ci_local.sh`.
- [x] Each MCP server is a standalone process (Rule 3) — smoke-test at least one
      of each kind (host-native FastAPI+FastMCP app, vendored server) live, not
      just via unit-test mocks.

## Definition of Done

- [x] All MCP servers running on mcp v2, `<2.0.0` pin removed / replaced with a
      v2 floor.
- [x] Full verification ladder green.
- [x] `uv.lock` diff reviewed and clean of unrelated churn (or unrelated churn
      explicitly accepted and noted why).

## Resolution

The current tree contained 21 production SDK import sites plus the smoke-test
site. The two `portal_mcp/{filesystem,scrapling}` paths named in the original
inventory do not import the Python MCP SDK, so there was nothing to port there.
All real sites now use `MCPServer`; constructor transport settings moved to
`run()` or `streamable_http_app()` as required by v2.

The v2 pin is consistent across `pyproject.toml`, Docker build paths, and the
MusicGen installer. The obsolete `portal_mcp` import shim and third-party
`fastmcp` dependency were removed. Lockfile changes are limited to the v2
dependency graph, `idna` resolution, and the declared-but-previously-unlocked
pytest-xdist development dependency.

Live v2 clients negotiated protocol `2026-07-28` and listed tools from both the
mounted Pipeline FastAPI+MCP application (11 tools) and the standalone code
sandbox server (5 tools).
