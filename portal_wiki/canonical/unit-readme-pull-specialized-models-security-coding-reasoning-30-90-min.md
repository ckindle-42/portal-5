---
id: unit-readme-pull-specialized-models-security-coding-reasoning-30-90-min
kind: what
title: "README \u2014 Pull specialized models (security, coding, reasoning \u2014\
  \ 30\u201390 min)"
sources:
- type: code
  path: launch.sh
- type: code
  path: portal/platform/inference/cli/models.py
- type: code
  path: config/portal.yaml
last_generated_commit: ed366c7a6eb34d822a5d4aa04f8072edca8acd5d
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.681514
updated_at: 1784946220.681514
---

```bash
./launch.sh pull-models
```

`pull-models` delegates to `portal.platform.inference.cli models pull`
(`launch.sh` case block). That command loads the model registry from
`config/portal.yaml` (`models:` block), resolves pull targets via
`_select_pull_targets` (excluding `retired: true` entries and entries without an
`ollama_name`), and pulls each into Ollama — HuggingFace repos via `hf hub
download`, native registry models via `ollama pull`. It prints the estimate that
the full set takes 30–90 minutes depending on connection speed, and it skips
models already present in Ollama. Gated repositories require `HF_TOKEN` set in
`.env`; the pull reports a clear error otherwise.

## Why

The specialized catalog is large (security, coding, reasoning, vision, creative
lanes), so it is deliberately a separate, operator-initiated step after the three
core models have bootstrapped the stack. Keeping the pull set registry-driven
means a model added to `config/portal.yaml` is automatically pullable without
editing shell code, and retired entries stay documented but stop being fetched.
