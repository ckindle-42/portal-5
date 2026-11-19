---
id: unit-HOWTO-chat-streaming
historical: true
kind: why
title: "HOWTO \u2014 Chat (streaming)"
sources:
- type: design
  path: docs/HOWTO.md
  section: Chat (streaming)
confidence: high
tags:
- docs
- HOWTO

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
