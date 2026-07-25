---
id: unit-ADMIN_GUIDE-debugging-crashes
kind: what
title: "ADMIN_GUIDE — Debugging crashes"
sources:
- type: code
  path: launch.sh
  commit: fc69762b
last_generated_commit: fc69762b
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1784950000.0
updated_at: 1784950000.0
---

```bash
# Check Ollama health and model list
curl -s http://localhost:11434/api/tags | jq .

# Check pipeline health
curl -s http://localhost:9099/health/all | jq .

# Check all services
./launch.sh status
```
