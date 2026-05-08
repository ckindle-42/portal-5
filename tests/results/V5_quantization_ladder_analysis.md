# V5 Quantization Ladder Bench Analysis

Generated from `bench_tps_v5_ladders.json` and `smoke_test_v5.json`.

**Decision input for `TASK_WORKSPACE_PROMOTION_V1.md`.**

---

## auto-vision

| Model | Median TPS | Memory (GB) | Tools | VLM | BIG_MODEL | Smoke | Notes |
|---|---:|---:|:-:|:-:|:-:|:-:|---|
| `mlx-community/gemma-4-31b-it-4bit` | 3.5 | 18 | ✗ | ✓ |  | — | Primary VLM: Gemma 4 dense 31B 4bit (~18GB, thinking+vision, 256K ctx)... |

**Pareto-frontier candidates (speed × memory):**
- `mlx-community/gemma-4-31b-it-4bit`

---

## auto

| Model | Median TPS | Memory (GB) | Tools | VLM | BIG_MODEL | Smoke | Notes |
|---|---:|---:|:-:|:-:|:-:|:-:|---|
| `mlx-community/granite-4.1-3b-mxfp8` | 37.3 | 3 | ✓ |  |  | PASS | IBM Granite 4.1 3B 8-bit MX DENSE (~3GB, Apache 2.0, ~50-70 TPS theoretical). AU... |

**Pareto-frontier candidates (speed × memory):**
- `mlx-community/granite-4.1-3b-mxfp8`

---

## uncategorized

| Model | Median TPS | Memory (GB) | Tools | VLM | BIG_MODEL | Smoke | Notes |
|---|---:|---:|:-:|:-:|:-:|:-:|---|
| `mlx-community/Qwen2.5-0.5B-Instruct-4bit` | 234.3 | 0.5 | ✗ |  |  | — | Draft model: Qwen tokenizer (~0.5GB, additive with target)... |
| `mlx-community/Llama-3.2-1B-Instruct-4bit` | 139.3 | 1.0 | ✗ |  |  | — | Draft model: Llama-3 tokenizer (~1GB, additive with target)... |
| `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF` | 52.3 | ? | ? |  |  | — |  |
| `deepseek-coder-v2-lite:q4_k_m` | 50.8 | ? | ? |  |  | — |  |
| `mlx-community/gemma-4-e4b-it-4bit` | 39.2 | 5 | ✗ | ✓ |  | — | Gemma 4 E4B VLM fallback (~5GB, vision+audio, 128K ctx)... |
| `deepseek-coder-v2:16b-lite-instruct-q4_K_M` | 39.2 | ? | ? |  |  | — |  |
| `hermes3:8b` | 38.1 | ? | ? |  |  | — |  |
| `llava:7b` | 34.1 | ? | ? |  |  | — |  |
| `qwen3-coder:30b` | 33.6 | ? | ? |  |  | — |  |
| `lily-cybersecurity:7b-q4_k_m` | 33.1 | ? | ? |  |  | — |  |
| `mlx-community/Qwen2.5-Math-7B-Instruct-4bit` | 32.9 | 5 | ✓ |  |  | — | Math specialist: Qwen2.5-Math 7B 4bit (~5GB)... |
| `dolphin-llama3:8b` | 32.1 | ? | ? |  |  | — |  |
| `glm-4.7-flash:q4_k_m` | 31.5 | ? | ? |  |  | — |  |
| `huihui_ai/baronllm-abliterated` | 31.5 | ? | ? |  |  | — |  |
| `lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0` | 29.0 | ? | ? |  |  | — |  |
| `mlx-community/Llama-3.2-11B-Vision-Instruct-abliterated-4-bit` | 25.2 | 7 | ✗ | ✓ |  | — | Uncensored VLM 11B 4bit (~7GB, Karakeep vision)... |
| `baronllm:q6_k` | 24.4 | ? | ? |  |  | — |  |
| `granite4.1:8b` | 21.4 | ? | ? |  |  | — |  |
| `Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit` | 14.0 | 15 | ✗ | ✓ |  | — | Abliterated Gemma 4 26B A4B MoE (~15GB, uncensored vision, 256K ctx) — KNOWN BRO... |
| `mlx-community/Dolphin3.0-Llama3.1-8B-8bit` | 12.8 | 9 | ✗ |  |  | — | Dolphin 8B uncensored (~9GB). supports_tools flipped to false — Ollama-side dolp... |
| `dolphin3-r1-mistral:24b-q4_k_m` | 11.5 | ? | ? |  |  | — |  |
| `xploiter/the-xploiter` | 11.1 | ? | ? |  |  | — |  |
| `devstral:24b` | 8.8 | ? | ? |  |  | — |  |
| `deepseek-r1:32b-q4_k_m` | 7.3 | ? | ? |  |  | — |  |
| `granite4.1:30b` | 7.2 | ? | ? |  |  | — |  |
| `whiterabbitneo:33b-v1.5-q4_k_m` | 6.9 | ? | ? |  |  | — |  |
| `llama3.3:70b-q4_k_m` | 3.8 | ? | ? |  |  | — |  |
| `dolphin-llama3:70b-q4_k_m` | 3.8 | ? | ? |  |  | — |  |

**Pareto-frontier candidates (speed × memory):**
- `mlx-community/Qwen2.5-0.5B-Instruct-4bit`

---

## Promotion recommendations

Speed-quality dominance based on measured TPS. **Quality estimates pending T-* probes — these are speed-only Pareto recommendations.** The operator should run T-RSN/T-COD/T-CMP/T-VIS/T-CRE benchmarks before flipping workspace primaries.

### auto-vision
- **Fastest measured (smoke-passed):** `mlx-community/gemma-4-31b-it-4bit` at 3.5 TPS, 18 GB resident
- **Decision gate:** run T-* quality probes (see `TASK_*_SHOOTOUT_V1.md`) before promoting to workspace MLX primary.

### auto
- **Fastest measured (smoke-passed):** `mlx-community/granite-4.1-3b-mxfp8` at 37.3 TPS, 3 GB resident
- **Decision gate:** run T-* quality probes (see `TASK_*_SHOOTOUT_V1.md`) before promoting to workspace MLX primary.

### uncategorized
- **Fastest measured (smoke-passed):** `mlx-community/Qwen2.5-0.5B-Instruct-4bit` at 234.3 TPS, 0.5 GB resident
- **Decision gate:** run T-* quality probes (see `TASK_*_SHOOTOUT_V1.md`) before promoting to workspace MLX primary.
