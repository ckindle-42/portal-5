---
id: unit-cluster-scale-stage-3-vllm-for-70b-models
kind: what
title: "CLUSTER_SCALE \u2014 Stage 3: vLLM for 70B Models"
sources:
- type: code
  path: portal/platform/inference/cluster_backends.py
- type: code
  path: config/backends.yaml
last_generated_commit: 778def71961fd1bb2f1088be9754388706facf7a
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5125499
updated_at: 1784946220.5125499
---

A vLLM node for very large models is registered with `type: openai_compatible`.
`cluster_backends.py` names vLLM as the canonical example of that type and
derives its liveness probe from the type as well: `health_url` falls back to
`/health` for any backend that is neither `ollama` nor `omlx`. After starting
`vllm serve` on the target host, append one entry to the `backends:` list of
`config/backends.yaml` carrying `type: openai_compatible`, the base `url`, a
`group`, and the served `models`. An optional `health_path:` override repoints
the probe at a proxy that fronts the vLLM process. Because the OpenAI-compatible
surface means `chat_url` appends `/v1/chat/completions` for every backend type,
the streaming and routing code is engine-agnostic.

## Why

The `type` field on `Backend` exists precisely so engine differences stay inside
config, not code. vLLM speaks the same OpenAI chat protocol as Ollama —
`chat_url` appends `/v1/chat/completions` for every type — and its only
protocol distinction is the liveness surface: `/health` instead of `/api/tags`,
which `health_url` chooses from the type. That single difference is why a
seventy-billion-parameter model server can join the fleet without touching the
request paths. `health_path:` covers the proxy-fronted deployment, keeping even
the nonstandard topology a YAML-only edit.
