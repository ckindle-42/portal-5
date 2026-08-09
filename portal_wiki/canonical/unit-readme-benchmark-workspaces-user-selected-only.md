---
id: unit-readme-benchmark-workspaces-user-selected-only
kind: what
title: "README \u2014 Benchmark Workspaces (user-selected only)"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: config/backends.yaml
- type: code
  path: portal/platform/inference/router/workspaces.py
- type: code
  path: portal/platform/inference/config.py
last_generated_commit: 63cbca4c591d2d00f1cc9e3101ffa91f84a9a4a0
claims:
- probe: workspaces.bench
  pattern: currently {value} workspaces
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6800451
updated_at: 1784946220.6800451
---

Benchmark workspaces pin a specific model for direct, side-by-side performance
comparison. They are not intended for daily use: the user must deliberately select
one from the model dropdown. Every entry is a `bench-*` workspace in
`config/portal.yaml` whose `model_hint:` names an exact catalog model from
`config/backends.yaml`, so a bench run measures that one model and nothing else.

List the current set with:

```bash
python3 -c "from portal.platform.inference.router.workspaces import WORKSPACES; [print(k) for k in sorted(WORKSPACES) if k.startswith('bench-')]"
```

The live count is currently 66 workspaces. Verified examples from `config/portal.yaml`:

| Workspace | Pinned model (`model_hint`) |
|---|---|
| `bench-devstral` | `devstral:24b` |
| `bench-fastcontext` | FastContext-1.0-4B-SFT (repository explorer subagent) |
| `bench-gemma4-26b-qat` | `gemma4:26b-a4b-it-qat` |
| `bench-laguna` | `laguna-xs.2:Q4_K_M` |
| `bench-qwen3-coder-30b` | `qwen3-coder:30b-a3b-q4_K_M` |
| `bench-sylink` | `sylink/sylink:8b` |
| `bench-vulnllm-r-7b` | VulnLLM-R-7B GGUF Q4_K_M |

The remaining lanes cover security exec chains, LFM micro models, MTP draft pairs
and additional coding, vision and security variants; the authoritative list is
`config/portal.yaml`, not this table.

## Why

A bench lane decouples model choice from workspace behavior: the same toolset,
prompt scaffolding and routing apply, so a TPS or quality delta is attributable to
the model weights alone. Keeping the lanes behind the eval module (disabled by
default, `PORTAL_ENABLE_EVAL=1` to opt in) stops them from cluttering the daily
model dropdown while leaving a documented harness path.
