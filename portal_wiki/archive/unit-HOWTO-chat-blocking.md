---
id: unit-HOWTO-chat-blocking
historical: true
kind: why
title: "HOWTO \u2014 Chat (blocking)"
sources:
- type: design
  path: docs/HOWTO.md
  section: Chat (blocking)
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
    "model": "auto-coding",
    "messages": [{"role": "user", "content": "Write a Python function to parse ISO 8601 dates"}],
    "stream": false
  }' | python3 -c "import sys,json; print(json.load(sys.stdin)['choices'][0]['message']['content'])"
```
