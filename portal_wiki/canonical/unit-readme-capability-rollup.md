---
id: unit-readme-capability-rollup
kind: what
title: Portal 5 capability rollup
sources:
- type: code
  path: config/portal.yaml
  commit: 2704ef21dfe7
  section: workspaces
- type: code
  path: config/portal.yaml
  commit: 2704ef21dfe7
  section: mcp_fleet
- type: code
  path: config/personas/
  commit: 2704ef21dfe7
- type: code
  path: config/modules.generated.yaml
  commit: 2704ef21dfe7
claims:
- probe: modules.enabled.count
  pattern: '{value} modules enabled'
- probe: modules.total
  pattern: '{value} modules total'
- probe: workspaces.functional
  pattern: '{value} functional workspaces'
- probe: workspaces.bench
  pattern: '{value} benchmark workspaces'
- probe: workspaces.total
  pattern: '{value} workspaces total'
- probe: personas.count
  pattern: '{value} personas'
- probe: mcp.fleet.entries
  pattern: '{value} MCP tool servers'
confidence: high
tags:
- fact
- readme
- rollup
created_at: 1789063576.521034
updated_at: 1789195856.0308511
---

Portal 5 is one platform assembled from a small set of switchable
parts. The headline figures below are derived from config on every
seed, never hand-written.

| Kind | Count | Source |
|---|---|---|
| Modules | 15 enabled of 16 | `config/modules.generated.yaml` |
| Functional workspaces | 25 | `config/portal.yaml` `workspaces` |
| Benchmark workspaces | 21 | `config/portal.yaml` `workspaces` (eval module) |
| Workspaces total | 46 | `config/portal.yaml` `workspaces` |
| Personas | 122 | `config/personas/` |
| MCP tool servers | 33 | `config/portal.yaml` `mcp_fleet` |

That is 15 modules enabled of 16 modules total, 25 functional workspaces (21 benchmark workspaces, 46 workspaces total), 122 personas and 33 MCP tool servers — plus the Telegram and Slack channels, which carry no count of their own.

## Why

A first-time reader needs one number before they need eighty-one, so the README opens its capability section on a single rollup. It has to be derived rather than typed because every figure here moves between releases as modules, workspaces and personas are added or retired, and a README that quotes a stale count is the fastest way to lose a new reader's trust in the rest of the page.
