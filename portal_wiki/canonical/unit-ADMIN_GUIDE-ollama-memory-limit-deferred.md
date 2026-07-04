---
id: unit-ADMIN_GUIDE-ollama-memory-limit-deferred
kind: why
title: "ADMIN_GUIDE \u2014 OLLAMA_MEMORY_LIMIT (deferred)"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: OLLAMA_MEMORY_LIMIT (deferred)
last_generated_commit: ''
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1783195000.817065
updated_at: 1783195000.817065
---


`OLLAMA_MEMORY_LIMIT` is currently **not set** (unlimited). On the M4 Pro 64GB, worst-case slot composition (router 5.3GB + devstral 25.7GB + granite 16.8GB) can hit ~47.8GB — well within budget. Ollama gracefully offloads to CPU before crashing, but if kernel panics or Metal OOM errors appear under heavy multi-model loads, add to the plist:

```xml
<key>OLLAMA_MEMORY_LIMIT</key>
<string>42g</string>
```

42 GB leaves ~6 GB for macOS + pipeline + Open WebUI.
