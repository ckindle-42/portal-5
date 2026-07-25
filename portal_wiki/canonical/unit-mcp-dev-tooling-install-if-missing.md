---
id: unit-mcp-dev-tooling-install-if-missing
kind: what
title: "MCP_DEV_TOOLING \u2014 Install if missing:"
sources:
- type: doc
  path: docs/MCP_DEV_TOOLING.md
  commit: 05e42ec2
  section: 'Install if missing:'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.571248
updated_at: 1784946220.571248
---

brew install node                          # macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

`portal-sandbox` and `portal-pipeline` require the stack to be running:

```bash
./launch.sh up    # starts Docker stack + pipeline MCP (:8928) + sandbox (:8914)
```

---
