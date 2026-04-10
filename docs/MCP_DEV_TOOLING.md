# MCP Dev Tooling (Claude Code / opencode)

The `.mcp.json` at the repo root provisions four MCP servers automatically when Claude Code or
opencode opens this project. These are **development tools only** — they have no relation to
the Portal 5 MCP Tool Servers in `portal_mcp/` that Open WebUI consumes.

## Servers

| Server | Install | Purpose |
|---|---|---|
| `filesystem` | `@modelcontextprotocol/server-filesystem` (npx) | Read/write repo source tree and `~/.portal5/logs` without shell |
| `fetch` | `mcp-fetch` (uvx) | Fetch Prometheus metrics API, Open WebUI API, Grafana API, docs |
| `git` | `mcp-git` (uvx) | Walk commit history, diff, blame — critical for regression bisect |
| `docker` | `@modelcontextprotocol/server-docker` (npx) | Container logs, status, exec — debug MCP server health live |

> **sqlite server omitted**: Open WebUI's `webui.db` lives in a pure Docker volume
> (`portal-5_open-webui-data`) not bind-mounted to the host. To re-enable sqlite MCP,
> add a bind mount in `docker-compose.yml` and add the entry back to `.mcp.json`.

## Prerequisites

These servers use `npx` and `uvx` — both must be available on PATH:

```bash
# npx ships with Node.js (>=18 recommended)
node --version && npx --version

# uvx ships with uv
uv --version && uvx --version
```

If either is missing:
- Node.js: `brew install node` (Mac) or `apt install nodejs npm` (Linux)
- uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`

## Prometheus Fetch Pattern

The `fetch` MCP server can query Prometheus directly. Useful patterns:

```
# Current pipeline request rate
http://localhost:9090/api/v1/query?query=portal5_requests_total

# MCP server health over last 5 minutes
http://localhost:9090/api/v1/query_range?query=up{job="portal5"}&start=[5m ago]&end=now&step=30s

# Grafana dashboard (read-only API)
http://localhost:3000/api/dashboards/home
```

## git MCP — Regression Bisect Pattern

For commit-range regressions (e.g., video gen bug across two commits):

1. Use `git` MCP tool: `git_log` to list commits in range
2. Use `git` MCP tool: `git_diff` between suspect commits on affected files
3. Correlate with `portal_mcp/generation/` and `portal_mcp/mcp_server/` changes
4. No terminal copy-paste required

## docker MCP — MCP Server Debug Pattern

When an acceptance test fails against a portal MCP server:

1. `docker_list` — confirm `portal5-mcp-<name>` container is running
2. `docker_logs` — tail last 50 lines for startup errors or import failures
3. `docker_exec` — run `curl http://localhost:<port>/health` inside container if needed
4. Avoids blind `docker logs` copy-paste cycles during test iteration

## Scope Boundaries

- `filesystem` MCP is scoped to the repo dirs and `~/.portal5/logs` only. It cannot reach outside
  these paths — by design. Do not widen the scope.
- `docker` MCP uses the Docker socket. On a single-user local machine this is acceptable.
  Do not add this to any multi-user or production deployment.
- Do not use `fetch` MCP to POST to the Open WebUI admin API — read-only observation only.
