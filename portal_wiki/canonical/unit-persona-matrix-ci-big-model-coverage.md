---
id: unit-persona-matrix-ci-big-model-coverage
kind: what
title: "PERSONA_MATRIX_CI \u2014 Big-model coverage"
sources:
- type: code
  path: portal/modules/eval/persona_matrix/cli.py
- type: code
  path: portal/modules/eval/persona_matrix/sweep.py
- type: code
  path: portal/modules/eval/persona_matrix/loaders.py
- type: code
  path: config/backends.yaml
- type: code
  path: .github/workflows/persona_matrix_nightly.yml
last_generated_commit: 0fec84d46a8898b1b5baf0508af1e25634b099af
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5688782
updated_at: 1784946220.5688782
---

The `--include-big-models` flag and the `big_model` field still exist in the persona-matrix driver, but the policy's original claim — that specific models are flagged `big_model: true` in `config/backends.yaml` — is stale. No `big_model: true` marker exists anywhere in `backends.yaml` today, and the loader hardcodes `big_model` to `False` for every model it resolves (`models_in_group` in `loaders.py` and the explicit-models path in `sweep.py`). The pre-retirement MLX-era entries the policy named — `Qwen3-Coder-Next-4bit`, `Llama-3.3-70B-Instruct-4bit`, `Qwen3-VL-32B-Instruct-8bit` — are gone; the current catalog uses Ollama ids such as `qwen3-coder-next:latest`, and the only Qwen3-VL-32B entry is `Qwen3-VL-32B-Instruct-4bit` under the `omlx` holding group, which no workspace routing chain references.

The mechanism is retained for future use: `sweep.py` and `ollama_client.py` both filter the resolved chain with `if not args.include_big_models` before running, so a model actually flagged `big_model` today would be excluded from default sweeps and included only when an operator passes `--include-big-models`. Because the loader never sets the flag, that filter is currently inert. Operator-driven big-model coverage therefore means deliberately passing `--include-big-models`; the workflow's own chains (`auto-compliance`, `auto-coding`) run within the job's `timeout-minutes: 120` cap without any exclusion logic firing.

## Why

The original doc asserted model identities and sizes that date to the pre-retirement MLX proxy and no longer exist in the catalog, so re-grounding must state what the code actually does rather than preserve a nostalgic policy. The structural truth worth keeping is that the exclusion switch survives but is a no-op until a model is flagged — operators should read the field as a reserved capability, not a policy currently in force, and the flag's help text is the only place the intended semantics are documented.
