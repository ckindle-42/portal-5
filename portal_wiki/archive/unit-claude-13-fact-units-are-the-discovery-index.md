---
id: unit-claude-13-fact-units-are-the-discovery-index
kind: why
title: "CLAUDE.md \u2014 13 \u2014 Fact-Units Are the Discovery Index"
sources:
- type: design
  path: CLAUDE.md
  section: "13 \u2014 Fact-Units Are the Discovery Index"
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1785348301.194365
updated_at: 1785348301.194365
---


Before grepping, query the wiki: `wiki_search` / `wiki_get_unit` / `wiki_explain`. Fact-units
(`unit-fact-*`, gated by validate check AW) are the trusted index for workspaces, models, MCP fleet,
personas, tool authorizations, and the MCP tool registry. Lead discovery from them; still verify every
edit anchor `count==1` against HEAD before editing. See `unit-HOWTO-discovery-with-fact-units`.

---
