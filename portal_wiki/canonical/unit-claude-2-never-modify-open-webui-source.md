---
id: unit-claude-2-never-modify-open-webui-source
kind: why
title: "CLAUDE.md \u2014 2 \u2014 Never Modify Open WebUI Source"
sources:
- type: design
  path: CLAUDE.md
  section: "2 \u2014 Never Modify Open WebUI Source"
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1783195000.806443
updated_at: 1783195000.806443
---


Portal 5 extends Open WebUI through documented extension points only:
- **Pipeline server** (`portal-pipeline` at :9099) — registered as an OpenAI API connection
- **MCP Tool Servers** — registered in Admin > Settings > Tools
- **Open WebUI Functions** — installed via Workspace > Functions > Import

If something seems to require modifying Open WebUI internals, find the extension point instead.
