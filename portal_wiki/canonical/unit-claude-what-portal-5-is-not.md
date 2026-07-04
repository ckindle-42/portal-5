---
id: unit-claude-what-portal-5-is-not
kind: why
title: "CLAUDE.md \u2014 What Portal 5 Is NOT"
sources:
- type: design
  path: CLAUDE.md
  section: What Portal 5 Is NOT
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1783195000.805413
updated_at: 1783195000.805413
---


Do not add these — they are explicitly out of scope:

- A web chat interface — Open WebUI handles that
- An auth system — Open WebUI handles that  
- A RAG/knowledge base — Open WebUI handles that
- A metrics/observability stack — Open WebUI handles that
- Cloud inference (OpenRouter, Anthropic API, etc.)
- External agent frameworks (LangChain, LlamaIndex, etc.)
- Anything requiring user accounts or API keys beyond what's in `.env.example`

---
