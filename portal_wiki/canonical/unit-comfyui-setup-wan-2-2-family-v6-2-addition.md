---
id: unit-comfyui-setup-wan-2-2-family-v6-2-addition
kind: what
title: "COMFYUI_SETUP \u2014 Wan 2.2 Family (v6.2 addition)"
sources:
- type: doc
  path: docs/COMFYUI_SETUP.md
  commit: 05e42ec2
  section: Wan 2.2 Family (v6.2 addition)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.555469
updated_at: 1784946220.555469
---

Wan 2.2 video generation is shelved on this Apple Silicon host. The table is
retained only as an archival implementation inventory; none of these variants
is exposed as a supported Portal operation.

| Variant | Implementation state | Operating state |
|---|---|---|
| `wan22-t2v-a14b` | Workflow corrected; available FP8 checkpoints fail on MPS | SHELVED |
| `wan22-ti2v-5b` | Verified working in isolation | SHELVED by project decision |
| `wan22-animate-14b` | Stub only | NOT SUPPORTED |
| `wan22-s2v-14b` | FP8 checkpoint fails on MPS | SHELVED |

See `unit-known-limitations-wan22-fp8-scaled-checkpoints-crash-on-apple-silicon-mps`
for the evidence and revisit conditions.
