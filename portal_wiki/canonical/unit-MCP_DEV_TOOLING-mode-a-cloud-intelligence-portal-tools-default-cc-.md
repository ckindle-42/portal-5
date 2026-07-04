---
id: unit-MCP_DEV_TOOLING-mode-a-cloud-intelligence-portal-tools-default-cc-
kind: why
title: "MCP_DEV_TOOLING \u2014 Mode A \u2014 Cloud intelligence + Portal tools (default,\
  \ `cc-portal.sh`)"
sources:
- type: design
  path: docs/MCP_DEV_TOOLING.md
  section: "Mode A \u2014 Cloud intelligence + Portal tools (default, `cc-portal.sh`)"
last_generated_commit: ''
confidence: high
tags:
- docs
- MCP_DEV_TOOLING
created_at: 1783195000.872891
updated_at: 1783195000.872891
---


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
