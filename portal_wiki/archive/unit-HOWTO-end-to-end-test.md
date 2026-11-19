---
id: unit-HOWTO-end-to-end-test
historical: true
kind: why
title: "HOWTO \u2014 End-to-end test"
sources:
- type: design
  path: docs/HOWTO.md
  section: End-to-end test
confidence: high
tags:
- docs
- HOWTO

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
