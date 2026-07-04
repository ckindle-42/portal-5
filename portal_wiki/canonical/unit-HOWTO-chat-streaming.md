---
id: unit-HOWTO-chat-streaming
kind: why
title: "HOWTO \u2014 Chat (streaming)"
sources:
- type: design
  path: docs/HOWTO.md
  section: Chat (streaming)
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.8619268
updated_at: 1783195000.8619268
---


```bash
curl -s http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer $PIPELINE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto-reasoning",
    "messages": [{"role": "user", "content": "Explain the CAP theorem"}],
    "stream": true
  }'
