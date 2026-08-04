---
id: unit-ADMIN_GUIDE-pull-additional-models
kind: what
title: "ADMIN_GUIDE \u2014 Pull Additional Models"
sources:
- type: code
  path: launch.sh
- type: code
  path: portal/platform/inference/cli/models.py
- type: code
  path: portal/platform/inference/cli/update.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1784950000.0
updated_at: 1784950000.0
---

# Pull additional models

Pull the Ollama model set for a fresh install or a re-sync of the model
registry.

```bash
./launch.sh pull-models
```

`pull-models` dispatches to `portal models pull`, which pulls every
non-retired entry in the `models:` block of `config/portal.yaml` into
Ollama. The broader default pull set — `xploiter`, `whiterabbitneo`,
`baronllm`, `tongyi`, `qwen3-coder`, `devstral`, and others — is declared
in `_DEFAULT_MODELS` in `portal/platform/inference/cli/update.py` and is
what `portal update` refreshes. A full pull takes 30-90 minutes depending
on connection speed, matching the help text in `launch.sh`.

## Why

Model acquisition is a long, interactive operation, so the CLI owns the
model list rather than this document: `config/portal.yaml` declares the
live registry that `models pull` walks, and `_DEFAULT_MODELS` in
`update.py` carries the named starter set. Grounding this unit to those
files means the documented list cannot drift from what the CLI actually
pulls — a hardcoded prose list would be stale by the next registry edit,
and an operator following it would pull a model the system no longer
serves.
