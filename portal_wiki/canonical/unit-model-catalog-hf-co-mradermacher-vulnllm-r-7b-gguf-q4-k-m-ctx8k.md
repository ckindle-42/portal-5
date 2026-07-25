---
id: unit-model-catalog-hf-co-mradermacher-vulnllm-r-7b-gguf-q4-k-m-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.649809
updated_at: 1784946220.649809
---

Context-capped derived tag of `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M` (`PARAMETER num_ctx 8192` baked in via `portal models apply-params`, TASK-SEC-LIVE-EXEC / Ollama 0.31 num_ctx-default fix). Ollama's `/v1/chat/completions` ignores request-time `options.num_ctx`, so capping context per-workspace requires a derived model tag rather than a request option. See base model's own catalog entry for full model detail; this entry exists only to satisfy backends.yaml/MODEL_CATALOG.md parity (test_model_catalog_parity.py).

Tag note (P5-SECURITY-ARM-RECONCILE-001, 2026-07-16): `ollama create` lowercases the quantization
segment of derived tags it mints (`Q4_K_M` → `q4_K_M`) even when the source `Modelfile`/CLI arg used
uppercase — this catalog entry (and `backends.yaml`/`portal.yaml`) previously declared the tag with
the uppercase `Q` that was never actually pullable/creatable, causing a silent routing gap. Verified
against the live Ollama instance during the security-arm reconciliation run.
