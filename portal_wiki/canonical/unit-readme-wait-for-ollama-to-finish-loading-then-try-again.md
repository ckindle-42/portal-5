---
id: unit-readme-wait-for-ollama-to-finish-loading-then-try-again
kind: what
title: "README \u2014 Wait for Ollama to finish loading, then try again"
sources:
- type: doc
  path: README.md
  commit: 05e42ec2
  section: Wait for Ollama to finish loading, then try again
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.688859
updated_at: 1784946220.688859
---

```

**First run taking too long:**
FLUX.1-schnell is ~12 GB. On a 100 Mbps connection this takes ~15 minutes.
On slower connections it may take longer. The download resumes if interrupted.

**Port already in use:**
```bash
lsof -i :8080               # Find what is using port 8080
