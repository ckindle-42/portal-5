---
id: unit-HOWTO-melody-conditioning
historical: true
kind: why
title: "HOWTO \u2014 Melody conditioning"
sources:
- type: design
  path: docs/HOWTO.md
  section: Melody conditioning
confidence: high
tags:
- docs
- HOWTO

---


Upload a reference audio clip and ask:
```
Generate music that matches the melody of this reference clip, style: jazz piano
```

**Verify:**
```bash
curl -s http://localhost:8912/health
