---
id: unit-HOWTO-content-aware-routing-llm-based-intent-classificat
kind: why
title: "HOWTO \u2014 Content-aware routing: LLM-based intent classification (primary)\
  \ with keyword scoring fallback"
sources:
- type: design
  path: docs/HOWTO.md
  section: 'Content-aware routing: LLM-based intent classification (primary) with
    keyword scoring fallback'
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.8425448
updated_at: 1783195000.8425448
---

curl -s http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer $(grep PIPELINE_API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "exploit vulnerability payload injection"}], "stream": false}'
