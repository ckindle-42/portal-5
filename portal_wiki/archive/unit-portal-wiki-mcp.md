---
id: unit-portal-wiki-mcp
kind: mixed
title: "Wiki MCP \u2014 agent retrieval with mandatory citations"
sources:
- type: code
  path: portal_wiki/mcp.py
  commit: dc13b2d5
last_generated_commit: 6fe71cca7b215f92e60675457af06859cfccf63f
claims: []
confidence: high
tags:
- authored-v1
- wiki
- mcp
created_at: 1785796116.926782
updated_at: 1785796116.926782
---

`portal_wiki/mcp.py` is the agent-native retrieval layer: the three tools —
`wiki_search`, `wiki_get_unit`, `wiki_explain` — that Claude Code and opencode
use to query the canonical knowledge layer. Every answer returns its
citations, which is the grounded-not-hallucinated contract.

## Why

Agents need a discovery path that starts from the spine rather than from
grep, and the flat keyword scorer here is the honest shape for that: it ranks
units by where the query words appear (title counts double, tags count 1.5,
body counts one), which is deliberately not a semantic search. The design
trade-off is explicit — a simple, deterministic scorer beats a fuzzy one for
grounding because every hit is traceable to a word match, and `wiki_explain`
compounds three top hits into a cited answer rather than letting a model
invent an answer from no source. The `preview` truncation keeps the payload
small while still showing enough context to judge relevance.

## Interfaces

`wiki_search(query, top_k)` returns ranked units with their sources and a
preview; `wiki_get_unit(unit_id)` returns one unit's full body and citations
or an error dict; `wiki_explain(query)` returns a cited composite answer. All
three read the store via `load_all`/`load_unit`.

## Gotchas

The scorer is pure keyword matching with no stemming — `streaming` and
`stream` score separately, and a query whose words never co-occur in a title
or body may surface an unrelated unit that happens to share one word.
