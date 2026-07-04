---
id: unit-QWEN_TEMPLATE_PROBE-mlx-vlm-server-help
kind: why
title: "QWEN_TEMPLATE_PROBE \u2014 mlx_vlm.server --help"
sources:
- type: design
  path: docs/QWEN_TEMPLATE_PROBE.md
  section: mlx_vlm.server --help
last_generated_commit: ''
confidence: high
tags:
- docs
- QWEN_TEMPLATE_PROBE
created_at: 1783195000.889451
updated_at: 1783195000.889451
---

```
usage: python3.14 -m mlx_vlm.server [-h] [--host HOST] [--port PORT]
                                    [--trust-remote-code] [--model MODEL]
                                    [--adapter-path ADAPTER_PATH]
                                    [--vision-cache-size VISION_CACHE_SIZE]
                                    [--prefill-step-size PREFILL_STEP_SIZE]
                                    [--max-tokens MAX_TOKENS]
                                    [--enable-thinking] [--kv-bits KV_BITS]
                                    [--kv-quant-scheme {uniform,turboquant}]
                                    [--kv-group-size KV_GROUP_SIZE]
                                    [--max-kv-size MAX_KV_SIZE]
                                    [--quantized-kv-start QUANTIZED_KV_START]
                                    [--draft-model DRAFT_MODEL]
                                    [--draft-kind {dflash,mtp}]
                                    [--draft-block-size DRAFT_BLOCK_SIZE]
                                    [--top-logprobs-k TOP_LOGPROBS_K]
                                    [--reload]
                                    [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}]

MLX VLM Http Server.

options:
  -h, --help            show this help message and exit
  --host HOST           Host for the HTTP server (default:0.0.0.0)
  --port PORT           Port for the HTTP server (default: 8080)
  --trust-remote-code   Trust remote code when loading models from Hugging
                        Face Hub.
  --model MODEL         Pre-load a model at startup (e.g. mlx-
                        community/Qwen2.5-VL-3B-Instruct-4bit).
  --adapter-path ADAPTER_PATH
                        Adapter weights to load with the model.
  --vision-cache-size VISION_CACHE_SIZE
                        Max number of cached vision features (default: 20).
  --prefill-step-size PREFILL_STEP_SIZE
                        Tokens per prefill step (default: 2048).
  --max-tokens MAX_TOKENS
        
