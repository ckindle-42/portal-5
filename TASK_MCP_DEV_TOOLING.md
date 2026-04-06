# TASK_MCP_DEV_TOOLING — Claude Code Dev Tooling Setup

**Task**: Add project-level MCP tooling for Claude Code / opencode to enable native repo navigation,
git history access, Docker container inspection, and SQLite DB querying during development and
debugging sessions — without requiring manual copy-paste from the terminal.

**Scope**: Configuration files and `CLAUDE.md` documentation only. No changes to any Portal 5
product code (`portal_pipeline/`, `portal_mcp/`, `config/`, `deploy/`, `scripts/`, `imports/`).

**Version**: 1.0  
**Last Updated**: 2026-04-05

---

## PROTECTED FILES — never touch these

```
portal_pipeline/**
portal_mcp/**
config/**
deploy/**
scripts/**
imports/**
Dockerfile.*
launch.sh
pyproject.toml
tests/**
```

**SAFE TO CREATE / EDIT in this task:**
- `.mcp.json`            ← new file, repo root
- `CLAUDE.md`            ← append new section only (no edits to existing content)
- `TASK_MCP_DEV_TOOLING.md`  ← this file

---

## Self-Check Before Starting

Run these before touching anything. They establish the baseline and catch pre-existing issues
this task does not own.

```bash
# Confirm you are on main and the tree is clean
git status
git log --oneline -5

# Confirm .mcp.json does NOT already exist (task is idempotent if it does)
ls -la .mcp.json 2>/dev/null && echo "EXISTS — re-read file before proceeding" || echo "NOT PRESENT — proceed"

# Confirm CLAUDE.md does NOT already contain the MCP Dev Tooling section
grep -c "## MCP Dev Tooling" CLAUDE.md && echo "SECTION EXISTS — skip Step 3" || echo "NOT PRESENT — proceed"
```

---

## Step 1 — Create `.mcp.json` at repo root

Create the file `/home/claude/portal-5/.mcp.json` (or `<repo_root>/.mcp.json` — wherever `CLAUDE.md`
lives) with exactly this content:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "${HOME}/portal-5",
        "${HOME}/portal-5/config",
        "${HOME}/portal-5/portal_pipeline",
        "${HOME}/portal-5/portal_mcp",
        "${HOME}/portal-5/portal_channels",
        "${HOME}/portal-5/tests",
        "${HOME}/.portal/logs",
        "/tmp"
      ]
    },
    "fetch": {
      "command": "uvx",
      "args": ["mcp-fetch"]
    },
    "git": {
      "command": "uvx",
      "args": ["mcp-git", "--repository", "."]
    },
    "docker": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-docker"]
    },
    "sqlite": {
      "command": "uvx",
      "args": [
        "mcp-sqlite",
        "--db-path",
        "${HOME}/.local/share/open-webui/webui.db"
      ]
    }
  }
}
```

> **Note on `sqlite` db-path**: Open WebUI writes `webui.db` inside its Docker volume
> (`open-webui-data:/app/backend/data`). The path above assumes you have that volume
> bind-mounted or exported to `~/.local/share/open-webui/` on the host. If you have a
> different host path, edit `--db-path` accordingly before committing. If `webui.db` is
> not accessible from the host at all (pure Docker volume), remove the `sqlite` entry
> entirely — it will error on connect and pollute the tool list.
>
> **To find the actual path:**
> ```bash
> docker inspect portal5-open-webui | grep -A10 '"Mounts"' | grep Source
> # Look for the mount whose Destination is /app/backend/data
> ```

---

## Step 2 — Verify `.mcp.json` is valid JSON

```bash
python3 -c "import json; json.load(open('.mcp.json')); print('JSON valid')"
```

Expected output: `JSON valid`

If it fails: fix the syntax error before proceeding.

---

## Step 3 — Append MCP Dev Tooling section to `CLAUDE.md`

Append the following block to the **end** of `CLAUDE.md`, after the existing "Known Limitations"
section. Do not modify any existing content above this insertion point.

```markdown

---

## MCP Dev Tooling (Claude Code / opencode)

The `.mcp.json` at the repo root provisions five MCP servers automatically when Claude Code or
opencode opens this project. These are **development tools only** — they have no relation to
the Portal 5 MCP Tool Servers in `portal_mcp/` that Open WebUI consumes.

### Servers

| Server | Install | Purpose |
|---|---|---|
| `filesystem` | `@modelcontextprotocol/server-filesystem` (npx) | Read/write repo source tree and `~/.portal/logs` without shell |
| `fetch` | `mcp-fetch` (uvx) | Fetch Prometheus metrics API, Open WebUI API, Grafana API, docs |
| `git` | `mcp-git` (uvx) | Walk commit history, diff, blame — critical for regression bisect |
| `docker` | `@modelcontextprotocol/server-docker` (npx) | Container logs, status, exec — debug MCP server health live |
| `sqlite` | `mcp-sqlite` (uvx) | Query `webui.db` directly — debug seeding, personas, workspace presets |

### Prerequisites

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

### Prometheus Fetch Pattern

The `fetch` MCP server can query Prometheus directly. Useful patterns:

```
# Current pipeline request rate
http://localhost:9090/api/v1/query?query=portal5_requests_total

# MCP server health over last 5 minutes
http://localhost:9090/api/v1/query_range?query=up{job="portal5"}&start=[5m ago]&end=now&step=30s

# Grafana dashboard (read-only API)
http://localhost:3000/api/dashboards/home
```

### SQLite DB Schema Reference

Key tables in `webui.db` useful for debugging seeding and routing issues:

| Table | Purpose |
|---|---|
| `model` | All model presets (workspaces + personas) — check `base_model_id IS NOT NULL` |
| `tool` | Registered MCP Tool Servers — verify all 7 portal tools appear |
| `config` | Open WebUI feature flags and connection settings |
| `user` | User accounts — verify admin seeded correctly |

Quick query to check persona seeding:
```sql
SELECT id, name, base_model_id FROM model WHERE base_model_id IS NOT NULL ORDER BY name;
```

### git MCP — Regression Bisect Pattern

For commit-range regressions (e.g., video gen bug across `dc99a4e`–`b9cd34c`):

1. Use `git` MCP tool: `git_log` to list commits in range
2. Use `git` MCP tool: `git_diff` between suspect commits on affected files
3. Correlate with `portal_mcp/generation/` and `portal_mcp/mcp_server/` changes
4. No terminal copy-paste required

### docker MCP — MCP Server Debug Pattern

When an acceptance test fails against a portal MCP server:

1. `docker_list` — confirm `portal5-mcp-<name>` container is running
2. `docker_logs` — tail last 50 lines for startup errors or import failures
3. `docker_exec` — run `curl http://localhost:<port>/health` inside container if needed
4. Avoids blind `docker logs` copy-paste cycles during test iteration

### Scope Boundaries

- `filesystem` MCP is scoped to the repo dirs and `~/.portal/logs` only. It cannot reach outside
  these paths — by design. Do not widen the scope.
- `docker` MCP uses the Docker socket. On a single-user local machine this is acceptable.
  Do not add this to any multi-user or production deployment.
- `sqlite` MCP is **read access only** to `webui.db` during debugging. Do not use it to mutate
  Open WebUI state — use `./launch.sh reseed` or the Open WebUI admin API instead.
```

---

## Step 4 — Verify `CLAUDE.md` insertion

```bash
# Confirm section was appended
grep -n "## MCP Dev Tooling" CLAUDE.md
# Expected: one matching line near the end of the file

# Confirm no existing sections were modified (line count should have grown)
wc -l CLAUDE.md
# Previous count was 544 — new count should be ~544 + ~90 = ~634

# Confirm no duplicate headers were introduced
grep -c "## What Portal 5 Is$" CLAUDE.md
# Expected: 1

grep -c "## Tech Stack" CLAUDE.md
# Expected: 1
```

---

## Step 5 — Commit

```bash
git add .mcp.json CLAUDE.md
git status
# Expected: two modified/new files — .mcp.json (new) and CLAUDE.md (modified)
# Nothing else should appear in staging

git diff --cached --stat
# Expected: 2 files changed

git commit -m "chore(tooling): add .mcp.json and CLAUDE.md section for Claude Code / opencode MCP dev tools

Adds project-level MCP server config (.mcp.json) so Claude Code and opencode
automatically provision five dev tools when the project is opened:
- filesystem: scoped read/write access to repo source tree and ~/.portal/logs
- fetch: HTTP access to Prometheus, Open WebUI, and Grafana APIs
- git: commit history, diff, blame for regression bisect without copy-paste
- docker: container log/status/exec for live MCP server health debugging
- sqlite: read-only access to webui.db for seeding and preset debugging

CLAUDE.md updated with server reference table, prerequisites, Prometheus
fetch patterns, SQLite schema reference, and git/docker debug patterns.

No product code changed."

git log --oneline -3
```

---

## Verification Checklist

Run all checks after commit. Every item must pass before this task is complete.

```bash
# 1. .mcp.json exists and is valid JSON
python3 -c "import json; d=json.load(open('.mcp.json')); print(f'OK — {len(d[\"mcpServers\"])} servers: {list(d[\"mcpServers\"].keys())}')"
# Expected: OK — 5 servers: ['filesystem', 'fetch', 'git', 'docker', 'sqlite']

# 2. CLAUDE.md section present
grep -c "## MCP Dev Tooling" CLAUDE.md
# Expected: 1

# 3. No product files touched
git diff HEAD~1 --name-only
# Expected: CLAUDE.md, .mcp.json only
# FAIL if any portal_pipeline/, portal_mcp/, config/, deploy/, scripts/ files appear

# 4. .mcp.json is in .gitignore? No — it SHOULD be committed (project-level config)
grep ".mcp.json" .gitignore 2>/dev/null && echo "WARN: .mcp.json is gitignored — remove that line" || echo "OK — not gitignored"

# 5. Unit tests still pass (no regressions from any accidental file touches)
pytest tests/unit/ -q --tb=no
# Expected: all pass

# 6. Ruff check clean
ruff check portal_pipeline/ portal_mcp/ portal_channels/
# Expected: All checks passed
```

---

## Rollback

If anything went wrong:

```bash
# Remove both files and recommit
git revert HEAD --no-edit
# OR if you want to fully undo:
git reset HEAD~1
rm -f .mcp.json
git checkout CLAUDE.md
git status  # should be clean
```

---

## Post-Task Notes

### Adjusting the `sqlite` db-path

After running the task, find the actual host path for `webui.db` and update `.mcp.json` if needed:

```bash
docker inspect portal5-open-webui --format '{{range .Mounts}}{{if eq .Destination "/app/backend/data"}}{{.Source}}{{end}}{{end}}'
```

Take the output path and update the `--db-path` arg in `.mcp.json`, then `git commit -m "chore(tooling): fix sqlite db-path for local volume"`.

### First-time npx/uvx package fetch

The first time Claude Code opens the project after this task, `npx` will download
`@modelcontextprotocol/server-filesystem` and `@modelcontextprotocol/server-docker`, and
`uvx` will fetch `mcp-fetch`, `mcp-git`, and `mcp-sqlite`. This is a one-time ~30 second
download per package. Subsequent opens use the local cache.

### opencode compatibility

opencode reads `.mcp.json` from the project root using the same format. No additional config
needed — this file serves both tools simultaneously.
