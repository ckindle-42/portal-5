---
id: unit-claude-do-not
kind: why
title: "CLAUDE.md \u2014 Do Not"
sources:
- type: design
  path: CLAUDE.md
  section: Do Not
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1783195000.810969
updated_at: 1783195000.810969
---


- Do NOT add `OLLAMA_BASE_URL` directly to Open WebUI's env — everything must go through `portal-pipeline`
- Do NOT import `portal_pipeline` from `portal_mcp` or vice versa — they are independent
- Do NOT store conversation state in the Pipeline — Open WebUI owns that
- Do NOT add system Python packages to `Dockerfile.pipeline` — keep it lean
- Do NOT hardcode model names in Python — they come from `backends.yaml` or persona YAMLs
- Do NOT use `docker compose down -v` in scripts (nukes Ollama models) — use targeted volume removal
- Do NOT commit `.env` — it is in `.gitignore`
- Do NOT skip tests — they protect the routing logic that everything depends on

---
