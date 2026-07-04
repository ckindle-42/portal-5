---
id: unit-MCP_DEV_TOOLING-install-if-missing
kind: why
title: "MCP_DEV_TOOLING \u2014 Install if missing:"
sources:
- type: design
  path: docs/MCP_DEV_TOOLING.md
  section: 'Install if missing:'
last_generated_commit: ''
confidence: high
tags:
- docs
- MCP_DEV_TOOLING
created_at: 1783195000.870931
updated_at: 1783195000.870931
---

brew install node                          # macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

`portal-sandbox` and `portal-pipeline` require the stack to be running:

```bash
./launch.sh up    # starts Docker stack + pipeline MCP (:8928) + sandbox (:8914)
```

---
