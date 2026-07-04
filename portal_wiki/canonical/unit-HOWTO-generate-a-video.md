---
id: unit-HOWTO-generate-a-video
kind: why
title: "HOWTO \u2014 Generate a video"
sources:
- type: design
  path: docs/HOWTO.md
  section: Generate a video
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.8453372
updated_at: 1783195000.8453372
---


```
Generate a 3-second video of ocean waves crashing on a rocky shoreline at golden hour
```

**Parameters:**
- Duration: 2-5 seconds (longer = more VRAM)
- Resolution: 480p or 720p
- FPS: 8 or 16

**Verify:**
```bash
curl -s http://localhost:8911/health
```

**Note:** Video generation is resource-intensive. On 32GB systems, close other heavy workloads first. On 64GB systems, Wan2.2 (~18GB) coexists safely with Ollama general models.

---
