---
id: unit-capability-serena
kind: mixed
title: "Serena MCP \u2014 IDE-only LSP symbol navigation"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/general/tools/__init__.py
- type: code
  path: scripts/lib/util.sh
claims: []
confidence: high
tags:
- capability
- mcp
- general
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Serena MCP — IDE-only LSP symbol navigation

## What

Serena is an external language-server-backed MCP server (`oraios/serena`)
installed via `uvx --from git+https://github.com/oraios/serena` and launched
through `scripts/lib/util.sh` as a host-native launchd service. It has no port
of its own — it is an IDE-exposed tool (`expose_to_pipeline: false`,
`expose_to_ide: true`), so it appears to Claude Code and opencode, never to a
pipeline workspace persona.

## How it's used

Its tool surface is the LSP symbol model over the checked-out repo: searching
for a symbol by name, resolving a symbol to its definition, reading the AST for
a file, and finding where a symbol is referenced. These calls answer "where is
X defined and what touches it" from the language server's index rather than
from textual pattern matches.

## Why it exists

The general module deliberately keeps serena out of the pipeline for the same
reason it keeps the rest of its fleet out: an IDE-only tool is invoked by a
human operator, not by an autonomous persona. In the IDE lane it deliberately
disables the overlapping base file and shell tools so a symbol query cannot be
answered by a cruder grep fallback.

## Value

Symbol-level navigation turns "find every reference to this identifier" from a
regex gamble into a language-aware answer, which is exactly the precision a
long editing session needs. It complements the pipeline's tools instead of
duplicating them: pipeline workspaces never see serena, and the IDE gets a
cursor-grade index the pipeline tools are not asked to provide.
