---
id: unit-HOWTO-melody-conditioning
kind: why
title: "HOWTO \u2014 Melody conditioning"
sources:
- type: design
  path: docs/HOWTO.md
  section: Melody conditioning
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.8460212
updated_at: 1783195000.8460212
---


Upload a reference audio clip and ask:
```
Generate music that matches the melody of this reference clip, style: jazz piano
```

**Verify:**
```bash
curl -s http://localhost:8912/health
