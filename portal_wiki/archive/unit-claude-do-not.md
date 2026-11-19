---
id: unit-claude-do-not
historical: true
kind: why
title: "CLAUDE.md \u2014 Do Not"
sources:
- type: design
  path: CLAUDE.md
  section: Do Not
confidence: high
tags:
- claude
- architecture
- law

---


- Do NOT add `OLLAMA_BASE_URL` directly to Open WebUI's env — everything must go through `portal-pipeline`
- Do NOT import `portal.platform.inference` from an MCP module (`portal/modules/*/tools/`, `portal_mcp/`) or vice versa — they are independent
- Do NOT store conversation state in the Pipeline — Open WebUI owns that
- Do NOT add system Python packages to `Dockerfile.pipeline` — keep it lean
- Do NOT hardcode model names in Python — they come from `backends.yaml` or persona YAMLs
- Do NOT use `docker compose down -v` in scripts (nukes Ollama models) — use targeted volume removal
- Do NOT commit `.env` — it is in `.gitignore`
- Do NOT skip tests — they protect the routing logic that everything depends on

---
