---
id: unit-HOWTO-execute-code-in-sandbox
historical: true
kind: why
title: "HOWTO \u2014 Execute code in sandbox"
sources:
- type: design
  path: docs/HOWTO.md
  section: Execute code in sandbox
confidence: high
tags:
- docs
- HOWTO

---


1. Select **Code Expert** from the model dropdown (this enables the Code tool automatically)
2. Type: `Run this code and show me the output`
3. The code executes in a Docker-in-Docker container (isolated from host)

**Verify sandbox:**
```bash
