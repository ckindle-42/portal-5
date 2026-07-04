---
id: unit-MLX_KV_FLAG_PROBE-mlx-lm-server-help
kind: why
title: "MLX_KV_FLAG_PROBE \u2014 mlx_lm.server --help"
sources:
- type: design
  path: docs/MLX_KV_FLAG_PROBE.md
  section: mlx_lm.server --help
last_generated_commit: ''
confidence: high
tags:
- docs
- MLX_KV_FLAG_PROBE
created_at: 1783195000.87846
updated_at: 1783195000.87846
---

```
Calling `python -m mlx_lm.server...` directly is deprecated. Use `mlx_lm.server...` or `python -m mlx_lm server ...` instead.
usage: python3.14 -m mlx_lm.server [-h] [--model MODEL]
                                   [--adapter-path ADAPTER_PATH] [--host HOST]
                                   [--port PORT]
                                   [--allowed-origins ALLOWED_ORIGINS]
                                   [--draft-model DRAFT_MODEL]
                                   [--num-draft-tokens NUM_DRAFT_TOKENS]
                                   [--trust-remote-code]
                                   [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
                                   [--chat-template CHAT_TEMPLATE]
                                   [--use-default-chat-template] [--temp TEMP]
                                   [--top-p TOP_P] [--top-k TOP_K]
                                   [--min-p MIN_P] [--max-tokens MAX_TOKENS]
                                   [--chat-template-args CHAT_TEMPLATE_ARGS]
                                   [--decode-concurrency DECODE_CONCURRENCY]
                                   [--prompt-concurrency PROMPT_CONCURRENCY]
                                   [--prefill-step-size PREFILL_STEP_SIZE]
                                   [--prompt-cache-size PROMPT_CACHE_SIZE]
                                   [--prompt-cache-bytes PROMPT_CACHE_BYTES]
                                   [--pipeline]

MLX Http Server.

options:
  -h, --help            show this help message and exit
  --model MODEL         The path to the MLX model weights, tokenizer, and
                        config
  --adapter-path ADAPTER_PATH
                        Optional path for the trained adapter weights and
                        config.
  --host HOST           Host for the HTTP server (default: 127.0.0.1)
  --port PORT           Port for the HTTP server (default: 8080)
  --allowed-origins ALLOWED_ORIGINS
                        Allowed origins (defa
