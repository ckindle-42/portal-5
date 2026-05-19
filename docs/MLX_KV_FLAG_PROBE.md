# MLX KV-Flag Capability Probe

**Probed**: 2026-05-19T22:07:56Z
**Host**: Darwin 25.5.0 arm64
**mlx_lm**: 0.31.3
**mlx_vlm**: 0.5.0
**Probe script**: `TASK_KV_PROBE_V1.md` Phases 1-3

## Decision matrix

| Flag | mlx_lm.server | mlx_vlm.server |
|---|---|---|
| `--kv-bits` | ABSENT | PRESENT |
| `--kv-quant-scheme` | ABSENT | PRESENT |
| `--kv-cache-quantization` | ABSENT | ABSENT |
| `--kv-group-size` | ABSENT | PRESENT |
| `--max-kv-size` | ABSENT | PRESENT |
| `--draft-model` | PRESENT | PRESENT |
| `--num-draft-tokens` | PRESENT | ABSENT |
| `--draft-kind` | ABSENT | PRESENT |
| `--prefill-step-size` | PRESENT | PRESENT |

## Interpretation for TASK_KV_PROXY_V1

**mlx_lm.server (text path)**: ALL KV flags are ABSENT as of 0.31.3. This includes
`--kv-cache-quantization`, which means the existing legacy int8 fallback in the proxy
(line ~878) is already a dead code path and will not inject. Wire `MLX_LM_KV_BITS` and
`max_kv_size` support as forward-compatible infrastructure: when a future mlx_lm adds
these flags, the proxy will activate them without code changes.

**mlx_vlm.server (vision path)**: Full KV support present. `--kv-bits`, `--kv-quant-scheme`,
`--kv-group-size`, and `--max-kv-size` are all supported. The existing `MLX_VLM_KV_BITS`
env var is the proven path; per-model `kv_bits` and `max_kv_size` in backends.yaml
override it at finer granularity.

**Conditional wiring rules for TASK_KV_PROXY_V1**:
- `MLX_LM_KV_BITS` env var: wire unconditionally (infrastructure), flag injection gated by probe
- `MLX_LM_KV_QUANT_SCHEME` env var: wire unconditionally (infrastructure)
- `max_kv_size` on mlx_lm models: YAML annotation + resolver built, but `--max-kv-size` not passed (flag absent)
- `max_kv_size` on mlx_vlm models: fully enforced via `--max-kv-size` flag
- `--kv-cache-quantization int8` legacy check: remove or gate it behind probe result (flag now absent)

**Note on `--draft-kind`**: ABSENT on mlx_lm, PRESENT on mlx_vlm (dflash, mtp). P5-MTP-001
(MTP speculative decoding) is unblocked for the VLM path. Out of scope for this task series.

## Verbatim help output

### mlx_lm.server --help
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
                        Allowed origins (default: *)
  --draft-model DRAFT_MODEL
                        A model to be used for speculative decoding.
  --num-draft-tokens NUM_DRAFT_TOKENS
                        Number of tokens to draft when using speculative
                        decoding.
  --trust-remote-code   Enable trusting remote code for tokenizer
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Set the logging level (default: INFO)
  --chat-template CHAT_TEMPLATE
                        Specify a chat template for the tokenizer
  --use-default-chat-template
                        Use the default chat template
  --temp TEMP           Default sampling temperature (default: 0.0)
  --top-p TOP_P         Default nucleus sampling top-p (default: 1.0)
  --top-k TOP_K         Default top-k sampling (default: 0, disables top-k)
  --min-p MIN_P         Default min-p sampling (default: 0.0, disables min-p)
  --max-tokens MAX_TOKENS
                        Default maximum number of tokens to generate (default:
                        512)
  --chat-template-args CHAT_TEMPLATE_ARGS
                        A JSON formatted string of arguments for the
                        tokenizer's apply_chat_template, e.g.
                        '{"enable_thinking":false}'
  --decode-concurrency DECODE_CONCURRENCY
                        When a request is batchable then decode that many
                        requests in parallel
  --prompt-concurrency PROMPT_CONCURRENCY
                        When a request is batchable then process that many
                        prompts in parallel
  --prefill-step-size PREFILL_STEP_SIZE
                        Step size for prefill processing (default: 2048)
  --prompt-cache-size PROMPT_CACHE_SIZE
                        Maximum number of distinct KV caches to hold in the
                        prompt cache
  --prompt-cache-bytes PROMPT_CACHE_BYTES
                        Maximum size in bytes of the KV caches
  --pipeline            Use pipelining instead of tensor parallelism
```

### mlx_vlm.server --help
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
                        Maximum number of tokens to generate.
  --enable-thinking     Enable thinking mode by default for requests that do
                        not set enable_thinking explicitly.
  --kv-bits KV_BITS     Number of bits for KV cache quantization (e.g. 3.5 for
                        TurboQuant).
  --kv-quant-scheme {uniform,turboquant}
                        KV cache quantization backend.
  --kv-group-size KV_GROUP_SIZE
                        Group size for uniform KV cache quantization.
  --max-kv-size MAX_KV_SIZE
                        Maximum KV cache size in tokens.
  --quantized-kv-start QUANTIZED_KV_START
                        Start index for quantized KV cache.
  --draft-model DRAFT_MODEL
                        Speculative drafter path or HF id (e.g.
                        z-lab/Qwen3.5-4B-DFlash, google/gemma-4-31B-it-
                        assistant).
  --draft-kind {dflash,mtp}
                        Drafter family — 'dflash' or 'mtp' (Gemma 4). Default:
                        auto-detected from the drafter's HF model_type.
  --draft-block-size DRAFT_BLOCK_SIZE
                        Override the drafter's configured block size.
  --top-logprobs-k TOP_LOGPROBS_K
                        Server-side cap for per-token top_logprobs (0-20,
                        default 0 = disabled). Maps to the TOP_LOGPROBS_K env
                        var.
  --reload              Enable auto-reload for development.
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Set the logging level (default: INFO).
```
