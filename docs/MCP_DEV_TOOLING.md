# MCP Dev Tooling — Claude Code & opencode Integration

Portal 5 ships two configuration files that wire it into AI-powered coding tools:

- **`.mcp.json`** — MCP server roster, picked up automatically by Claude Code (not opencode — see `opencode.jsonc` `mcp` block)
- **`opencode.jsonc`** — opencode provider config, points opencode at the local pipeline as its AI backend

These let Claude Code and opencode read the repo, run code, call Portal 5 tools, and (for opencode)
use fully local Portal 5 models instead of any cloud API.

---

## MCP Servers (`.mcp.json`)

Six servers activate when Claude Code or opencode opens this project:

| Server | Transport | Purpose |
|---|---|---|
| `filesystem` | npx `@modelcontextprotocol/server-filesystem` | Read/write/search repo source tree and `~/.portal5/logs` |
| `fetch` | uvx `mcp-fetch` | Read Prometheus metrics, pipeline `/health`, Ollama `/api/ps`, Grafana |
| `git` | uvx `mcp-server-git` | Commit, diff, log, blame — regression bisect and change tracking |
| `docker` | npx `@modelcontextprotocol/server-docker` | Container logs, status, exec — live MCP server debug |
| `portal-sandbox` | URL `:8914/mcp` | `execute_bash`, `execute_python`, `execute_nodejs` in isolated container |
| `portal-pipeline` | URL `:8928/mcp` | Stack introspection + FastContext repository explorer |

### Prerequisites

`npx` and `uvx` must be on PATH:

```bash
node --version && npx --version   # npx ships with Node.js ≥18
uv --version && uvx --version     # uvx ships with uv

# Install if missing:
brew install node                          # macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

`portal-sandbox` and `portal-pipeline` require the stack to be running:

```bash
./launch.sh up    # starts Docker stack + pipeline MCP (:8928) + sandbox (:8914)
```

---

## Portal Pipeline MCP (`portal-pipeline`, `:8928`)

A host-native FastMCP server started automatically by `./launch.sh up`. It gives coding
tools live introspection of the running Portal 5 stack and an AI-powered code explorer.

### Tools

| Tool | What it does |
|---|---|
| `get_pipeline_status` | Pipeline health, workspace count, version |
| `list_workspaces` | All 94 workspaces with names/descriptions; accepts optional filter string |
| `get_loaded_models` | Which Ollama models are in VRAM, their sizes, expiry times |
| `get_metrics_summary` | Request totals, tool call counts, error rates, TPS from Prometheus |
| `get_workspace_recommendation` | Given a task description, returns the best workspace ID with reasoning |
| `trigger_backend_warmup` | Pre-loads a workspace model into VRAM before a long session |
| `explore_repository` | **FastContext subagent** — finds relevant files and line ranges |

> **Two consumer paths.** These tools are reachable two ways:
> (A) **opencode / Claude Code** connect to `:8928` directly over MCP streamable-http
> (via `.mcp.json`); (B) the **in-pipeline `auto-coding-agentic` workspace** reaches them
> through the pipeline's ToolRegistry, which discovers `GET :8928/tools` and dispatches
> `POST :8928/tools/{name}`. Both paths are served by the same `_impl_*` helpers in
> `pipeline_mcp.py`, so behavior is identical. `:8928` is registered in
> `MCP_SERVERS["pipeline"]` (`MCP_PIPELINE_URL` to override).

### FastContext Repository Explorer

`explore_repository(query)` runs **FastContext-1.0-4B-SFT** (Microsoft, 2.5 GB,
[arxiv:2606.14066](https://arxiv.org/abs/2606.14066)) as a dedicated repository exploration subagent.

Instead of the main coding model burning its token budget scanning files, FastContext:
1. Receives the query (`"where is SSE streaming implemented"`)
2. Issues parallel `READ` / `GLOB` / `GREP` tool calls across the repo
3. Returns compact `{path, start_line, end_line, note}` citations

**Why it matters:** On SWE-bench benchmarks, FastContext reduces the main agent's token
consumption by 50–60% while improving resolution rates by up to 5.5 points. In practice:
Devstral reads 3 targeted file ranges instead of exploring blindly.

```json
{
  "citations": [
    {
      "path": "portal_pipeline/router/streaming.py",
      "start_line": 45, "end_line": 120,
      "note": "SSE streaming loop, tool call dispatch, preamble injection"
    },
    {
      "path": "portal_pipeline/router_pipe.py",
      "start_line": 230, "end_line": 280,
      "note": "lifespan, route registration, stream endpoint"
    }
  ],
  "turns_used": 2,
  "model": "hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M"
}
```

**Model must be pulled first:**

```bash
ollama pull hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M
```

---

## opencode Integration (`opencode.jsonc`)

[opencode](https://opencode.ai) is an open-source coding assistant. `opencode.jsonc` at the
repo root tells it to use Portal 5 as its AI backend instead of any cloud API.

### What opencode gets

- **Fully local inference** — all completions go through portal-pipeline (:9099) to Ollama
  on your hardware. No tokens leave the machine.
- **94 workspaces as models** — `opencode models` lists every Portal 5 workspace. Default:
  `portal/auto-coding-agentic` (Laguna-XS.2 33B-A3B with FastContext explore loop).
- **All 19 MCP servers** — opencode reads `.mcp.json` automatically, so it has the same
  filesystem, git, docker, sandbox, pipeline, and all 15 portal-* tool servers.
- **Cloud providers disabled** — `anthropic`, `openai`, `google`, `bedrock`, `vertex` are
  all disabled to prevent accidental cloud use.

### Quick start

```bash
# 1. Ensure stack is running
./launch.sh up

# 2. Export the pipeline API key into the environment
export $(grep PIPELINE_API_KEY .env | xargs)

# 3. Launch opencode (reads opencode.jsonc + .mcp.json automatically)
opencode .
```

### Workspace selection

```bash
opencode .                                          # default: portal/auto-coding-agentic (Laguna-XS.2 33B)
opencode . --model portal/auto-agentic              # heavy 80B MoE for complex multi-file refactors
opencode . --model portal/auto-agentic-lite         # AgentWorld 35B direct (lighter load, 45 t/s)
opencode . --model portal/auto-agentic-ornith       # Ornith-1.0-35B direct — agentic option, not a replacement
opencode . --model portal/auto-coding               # one-shot code generation (Qwen3-Coder 30B)
opencode . --model portal/auto-coding-northmini     # North-Mini-Code 30B-A3B — coding diversity option
opencode . --model portal/auto-reasoning            # deep reasoning for architectural decisions
opencode . --model portal/auto-security             # defensive security code review
opencode . --model portal/auto-pentest              # authorized penetration testing assistance
opencode . --model portal/auto-purpleteam-exec      # tool-calling security with live lab access
opencode . --model portal/auto-data                 # data science, SQL, analysis
opencode . --model portal/auto-research             # web-augmented research and summarization
```

Run `opencode models` to list all 94 available workspaces.

### Dual mode: Portal vs stock (no file renaming)

Portal is the in-repo default — bare `opencode .` auto-discovers `opencode.jsonc`. To run
**stock** opencode (your normal cloud providers) while inside the repo, use the wrapper,
which points `OPENCODE_CONFIG` at your global config:

```bash
scripts/oc-portal.sh            # Portal: local pipeline backend (default)
scripts/oc-stock.sh             # stock: your global/cloud opencode config
scripts/oc-stock.sh --model anthropic/claude-sonnet-4-6   # extra args pass through
```

opencode has no `--strict` MCP bypass and merges configs by cwd, so if `oc-stock.sh` still
shows Portal models, run opencode from outside the repo (`cd ~ && opencode`) or set
`OC_GLOBAL_CONFIG=/path/to/your/opencode.json`. Neither mode renames or edits
`opencode.jsonc`.

---

## Claude Code Integration

Claude Code has **two modes** with Portal 5:

### Mode A — Cloud intelligence + Portal tools (default, `cc-portal.sh`)

Anthropic cloud provides the AI. Portal 5 provides tools. The `.mcp.json` gives Claude Code
access to Portal 5's full tool set alongside Anthropic's intelligence.

```bash
scripts/cc-portal.sh            # cloud Anthropic + Portal MCP tools (default)
claude .                        # equivalent — auto-discovers .mcp.json + CLAUDE.md
```

Available tools after opening this project:

| Tool namespace | Key tools |
|---|---|
| `filesystem/*` | read_file, write_file, search_files, directory_tree |
| `git/*` | git_status, git_diff, git_add, git_commit, git_log, git_branch |
| `docker/*` | list_containers, container_logs, exec_command, start/stop_container |
| `fetch/*` | fetch (HTTP GET) — pipeline health, models, Prometheus, Grafana |
| `portal-sandbox/*` | execute_bash, execute_python, execute_nodejs, sandbox_status |
| `portal-pipeline/*` | explore_repository, list_workspaces, get_loaded_models, get_metrics_summary |

### Mode B — Local model intelligence + Portal tools (`cc-local.sh`)

Portal 5's local models provide the AI via the pipeline's `/v1/messages` Anthropic
compatibility endpoint. All tokens stay on your hardware. Same tool set as Mode A.

```bash
scripts/cc-local.sh                              # default: auto-agentic workspace
scripts/cc-local.sh --model auto-coding-agentic  # Laguna-XS.2 33B (agentic loop)
scripts/cc-local.sh --model auto-agentic         # Qwen3-Coder-Next 80B / AgentWorld 35B fallback
scripts/cc-local.sh --model auto-agentic-lite    # AgentWorld 35B direct (lighter, 45 t/s)
scripts/cc-local.sh --model auto-agentic-ornith  # Ornith-1.0-35B direct — agentic option, not a replacement
scripts/cc-local.sh --model auto-coding          # Qwen3-Coder 30B (one-shot)
scripts/cc-local.sh --model auto-coding-northmini # North-Mini-Code 30B-A3B — coding diversity option
scripts/cc-local.sh --model auto-reasoning       # DeepSeek-R1-0528 8B (reasoning)
scripts/cc-local.sh --model auto-security        # VulnLLM-R-7B (security)
```

**How it works:** `cc-local.sh` sets `ANTHROPIC_BASE_URL=http://localhost:9099` and
`ANTHROPIC_API_KEY=$PIPELINE_API_KEY`, then launches `claude`. The claude CLI sends all
`/v1/messages` requests to portal-pipeline instead of Anthropic's servers.
Portal-pipeline's `/v1/messages` endpoint translates to OpenAI format, routes through
the workspace stack (LLM router → backend selection → streaming), and returns Anthropic
SSE format. No change to `.mcp.json` — all Portal tools still available.

**AgentWorld for IDE use:** AgentWorld (Qwen-AgentWorld-35B-A3B, 45 t/s) is
particularly well-matched — its pretraining covers MCP tool-calling, Terminal execution,
SWE workflows, and web/OS environment simulation. These are exactly the trajectories
Claude Code exercises. It runs as the `auto-agentic` fallback when the primary 80B isn't warm.
(2026-06-30: a re-validation bench scored noticeably below what this training profile would
predict — production status is unchanged while that gap is investigated, see
`config/MODEL_CATALOG.md`.)

**Ornith-1.0-35B for IDE use:** Ornith (DeepReinforce, `auto-agentic-ornith`) is a second,
architecturally distinct agentic option — self-improving RL jointly optimizes solution
rollout and scaffold rather than env-simulation pretraining. Promoted 2026-06-30 on strong
tool-chain and SWE-handoff probe scores. Not a replacement for AgentWorld or the 80B
primary — pick it when you want a different agentic lineage to compare against, or when
the others aren't warm.

**Environment variable shortcut** (without the script):
```bash
export ANTHROPIC_BASE_URL=http://localhost:9099
export ANTHROPIC_API_KEY=$(grep PIPELINE_API_KEY .env | cut -d= -f2)
claude --model auto-agentic
```

### Mode C — Stock cloud (zero Portal MCP, `cc-stock.sh`)

```bash
scripts/cc-stock.sh             # stock: claude --strict-mcp-config --mcp-config '{}' (zero MCP)
CC_STOCK_KEEP_GENERIC=1 scripts/cc-stock.sh   # stock intelligence, keep filesystem/git/fetch/docker
CC_STOCK_IGNORE_SETTINGS=1 scripts/cc-stock.sh  # also ignore project/local settings
```

`--strict-mcp-config` makes Claude Code use only command-line MCP servers and ignore all
file-based ones, so `.mcp.json` stays in place untouched.

---

## `auto-coding-agentic` Workspace

Built specifically for Portal 5 self-improvement work. Available in Open WebUI and via opencode.

| Property | Value |
|---|---|
| **Model** | `laguna-xs.2:Q4_K_M` — Poolside AI 33B-A3B MoE, 68.2% SWE-bench Verified (~19 GB) |
| **Keep alive** | 15 min |
| **First tool** | `explore_repository` — FastContext finds exact files/lines before any edit |
| **Other tools** | `execute_bash`, `execute_python`, `execute_nodejs`, `sandbox_status`, file readers, memory |

**Agentic loop baked into system prompt:**

1. `explore_repository` — FastContext locates the relevant files and line ranges
2. `execute_bash cat -n` — read only the targeted ranges
3. State the minimal change needed and which files are affected
4. Make precise, targeted edits
5. `execute_bash pytest tests/unit/ -q` — verify before reporting done
6. Report what changed, what passed, what remains

---

## Workflow Examples

### Fixing a bug (Claude Code)

```
You: "Workspace routing is sending some requests to the wrong model"

Claude Code:
  portal-pipeline/explore_repository("workspace routing, model_hint resolution")
  → citations: router/routing.py:380-430, router/workspaces.py:205-250
  filesystem/read_file router/routing.py (lines 380-430)
  [diagnoses the keyword scoring threshold]
  filesystem/edit_file router/routing.py
  portal-sandbox/execute_bash "pytest tests/unit/test_pipeline.py -q"
  git/git_diff
  git/git_commit
```

### Adding a feature (opencode with local Laguna)

```
You: "Add a new auto-lab-report workspace for generating pentest reports"

opencode (Laguna-XS.2 33B-A3B via portal/auto-coding-agentic):
  explore_repository("how workspaces are defined, backends.yaml routing pattern")
  → citations: router/workspaces.py, config/backends.yaml, router/routing.py
  execute_bash "sed -n '205,250p' portal_pipeline/router/workspaces.py"
  [writes workspace definition matching the pattern]
  execute_bash "pytest tests/unit/ -q && python3 -c 'workspace consistency check'"
  [reports complete with passing tests]
```

### Debugging a failing MCP server (Claude Code)

```
You: "portal-sandbox is returning errors on execute_bash"

Claude Code:
  docker/list_containers → confirms portal5-mcp-sandbox is Up
  docker/container_logs portal5-mcp-sandbox → finds the traceback
  fetch/fetch http://localhost:8914/health → reads health state
  portal-sandbox/execute_bash "ls /workspace" → tests the tool directly
```

### Checking what's in VRAM before a long task

```
You: "Is devstral loaded? I don't want to wait for a cold start"

Claude Code:
  portal-pipeline/get_loaded_models
  → [{"name": "laguna-xs.2:Q4_K_M", "size_gb": 19.0, "expires_at": "2026-06-17T23:45:00"}]
  → Yes, warm for 33 more minutes
```

---

## Prometheus Fetch Patterns

```
http://localhost:9090/api/v1/query?query=portal5_requests_total
http://localhost:9090/api/v1/query?query=portal5_tool_calls_total
http://localhost:9090/api/v1/query?query=portal5_tps
http://localhost:9090/api/v1/query?query=up
http://localhost:3000/api/dashboards/home   (Grafana read-only API)
```

---

## Security Boundaries

- `filesystem` is scoped to the repo dirs and `~/.portal5/logs` only — cannot reach outside.
- `docker` uses the Docker socket. Acceptable on a local single-user machine only.
- `fetch` is read-only HTTP GET. Do not use it to POST to the Open WebUI admin API.
- `portal-sandbox` runs commands in an isolated container. `SANDBOX_LAB_EXEC=true` expands
  capabilities for lab pentest workflows — see `docs/LAB_SETUP.md`.
- `portal-pipeline` is localhost-only. Reads `PIPELINE_API_KEY` from the environment to
  authenticate calls to the pipeline.

> **sqlite server omitted:** Open WebUI's `webui.db` lives in a Docker volume not bind-mounted
> to the host. To enable sqlite MCP, add a bind mount in `docker-compose.yml` and add the
> entry back to `.mcp.json`.
