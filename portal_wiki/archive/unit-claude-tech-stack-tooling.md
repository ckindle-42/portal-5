---
id: unit-claude-tech-stack-tooling
historical: true
kind: why
title: "CLAUDE.md \u2014 Tech Stack & Tooling"
sources:
- type: design
  path: CLAUDE.md
  section: Tech Stack & Tooling
confidence: high
tags:
- claude
- architecture
- law

---


| Tool | Command | Notes |
|---|---|---|
| **Package manager** | `uv` | NOT pip directly. Lock file: `uv.lock` |
| **Install** | `uv pip install -e ".[dev]"` | Installs all extras + dev deps |
| **Linter** | `ruff check . --fix` | Ruff handles lint AND format |
| **Formatter** | `ruff format .` | NOT Black |
| **Type check** | `mypy portal/` | strict=true currently |
| **Tests** | `pytest tests/ -v --tb=short` | Must pass before any commit |
| **Python** | 3.10+ required | pyproject.toml requires-python >= 3.10 |
| **Framework** | FastAPI + Pydantic v2 | Async throughout |
| **Launch** | `./launch.sh up` | Never `docker compose up` directly |
| **Operator CLI** | `portal config show` | Typed CLI; `portal/platform/inference/cli/`; installed via `[project.scripts]` |

---
