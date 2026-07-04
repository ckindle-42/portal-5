---
id: unit-HOWTO-end-to-end-test
kind: why
title: "HOWTO \u2014 End-to-end test"
sources:
- type: design
  path: docs/HOWTO.md
  section: End-to-end test
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.862644
updated_at: 1783195000.862644
---

curl -s http://localhost:9099/v1/chat/completions \
  -H "Authorization: Bearer $PIPELINE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "Say OK"}], "stream": false}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['choices'][0]['message']['content'])"
```

**Verify:**
```bash
./launch.sh status
