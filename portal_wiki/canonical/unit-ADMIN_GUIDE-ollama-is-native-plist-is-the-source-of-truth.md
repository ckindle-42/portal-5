---
id: unit-ADMIN_GUIDE-ollama-is-native-plist-is-the-source-of-truth
kind: why
title: "ADMIN_GUIDE \u2014 Ollama is Native \u2014 Plist Is the Source of Truth"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: "Ollama is Native \u2014 Plist Is the Source of Truth"
last_generated_commit: ''
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1783195000.816087
updated_at: 1783195000.816087
---


Ollama runs under launchd, not Docker. Docker-compose env vars pass through to the pipeline container but **do not affect Ollama itself**. The authoritative config is:

```
~/Library/LaunchAgents/homebrew.mxcl.ollama.plist
```

To change `OLLAMA_MAX_LOADED_MODELS` (or add `OLLAMA_MEMORY_LIMIT`), edit the plist and reload:

```bash
