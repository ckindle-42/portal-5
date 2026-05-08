# V5 Quantization Ladder Bench Analysis

Generated from `bench_tps_v5_ladders.json` and `smoke_test_v5.json`.

**Decision input for `TASK_WORKSPACE_PROMOTION_V1.md`.**

---

## auto-vision

| Model | Median TPS | Memory (GB) | Tools | VLM | BIG_MODEL | Smoke | Notes |
|---|---:|---:|:-:|:-:|:-:|:-:|---|
| `mlx-community/gemma-4-26b-a4b-it-4bit` | 23.4 | 13 | ✓ | ✓ |  | PASS | Gemma 4 26B-A4B 4-bit MoE (~13GB, Apache 2.0, multimodal). V5 vision ladder — fa... |
| `mlx-community/gemma-4-26b-a4b-it-6bit` | 20.0 | 19 | ✓ | ✓ |  | PASS | Gemma 4 26B-A4B 6-bit MoE (~19GB). V5 ladder middle-ground.... |
| `mlx-community/gemma-4-31b-8bit` | 4.5 | 31 | ✓ | ✓ |  | PASS | Gemma 4 31B 8-bit DENSE (~31GB, Apache 2.0). V5 vision dense comparator vs 26B-A... |
| `mlx-community/gemma-4-26b-a4b-it-8bit` | 4.0 | 26 | ✓ | ✓ |  | PASS | Gemma 4 26B-A4B 8-bit MoE (~26GB, multimodal). V5 vision PRIMARY candidate. Repl... |
| `mlx-community/Qwen3-VL-32B-Instruct-8bit` | 3.9 | 36 | ✗ | ✓ | ✓ | — | Heavy VLM: Qwen3-VL 32B 8bit (~36GB, BIG_MODEL)... |
| `mlx-community/gemma-4-31b-it-4bit` | 3.5 | 18 | ✗ | ✓ |  | — | Primary VLM: Gemma 4 dense 31B 4bit (~18GB, thinking+vision, 256K ctx)... |

**Pareto-frontier candidates (speed × memory):**
- `mlx-community/gemma-4-26b-a4b-it-4bit`

---

## auto-reasoning

| Model | Median TPS | Memory (GB) | Tools | VLM | BIG_MODEL | Smoke | Notes |
|---|---:|---:|:-:|:-:|:-:|:-:|---|
| `mlx-community/Olmo-3-1125-32B-4bit` | 8.6 | 17 | ✗ |  |  | PASS | Allen AI Olmo 3 32B 4-bit DENSE (~17GB, Apache 2.0, NOT Qwen). bench-only — auto... |
| `mlx-community/Olmo-3-1125-32B-6bit` | 5.2 | 24 | ✗ |  |  | PASS | Allen AI Olmo 3 32B 6-bit DENSE (~24GB). V5 ladder middle-ground variant.... |
| `mlx-community/Olmo-3-1125-32B-8bit` | 4.4 | 34 | ✗ |  | ✓ | PASS | Allen AI Olmo 3 32B 8-bit DENSE (~34GB). V5 ladder high-quality variant. BIG_MOD... |

**Pareto-frontier candidates (speed × memory):**
- `mlx-community/Olmo-3-1125-32B-4bit`

---

## auto-compliance

| Model | Median TPS | Memory (GB) | Tools | VLM | BIG_MODEL | Smoke | Notes |
|---|---:|---:|:-:|:-:|:-:|:-:|---|
| `mlx-community/granite-4.1-30b-mxfp4` | 7.8 | 15 | ✓ |  |  | PASS | IBM Granite 4.1 30B mxfp4 DENSE (~15GB, Apache 2.0). PRIMARY auto-compliance can... |
| `mlx-community/granite-4.1-30b-nvfp4` | 6.8 | 15 | ✓ |  |  | PASS | IBM Granite 4.1 30B nvfp4 DENSE (~15GB, Apache 2.0). Alternative 4-bit format (N... |
| `mlx-community/granite-4.1-30b-mxfp8` | 4.2 | 30 | ✓ |  |  | PASS | IBM Granite 4.1 30B mxfp8 DENSE (~30GB, Apache 2.0). FALLBACK auto-compliance ca... |

**Pareto-frontier candidates (speed × memory):**
- `mlx-community/granite-4.1-30b-mxfp4`

---

## auto-coding

| Model | Median TPS | Memory (GB) | Tools | VLM | BIG_MODEL | Smoke | Notes |
|---|---:|---:|:-:|:-:|:-:|:-:|---|
| `mlx-community/Laguna-XS.2-4bit` | 40.3 | 19 | ✓ |  |  | — | Laguna XS.2 33B-A3B MoE 4bit (~18.8GB) — Poolside AI lineage (first non-Alibaba/... |
| `mlx-community/Devstral-Small-2505-4bit` | 10.7 | 13 | ✓ |  |  | PASS | Mistral Devstral Small 2505 4-bit DENSE 24B (~13GB, Apache 2.0). V5 coding ladde... |
| `mlx-community/Devstral-Small-2505-4bit-DWQ` | 9.0 | 13 | ✓ |  |  | PASS | Mistral Devstral Small 2505 4-bit DWQ DENSE 24B (~13GB, Apache 2.0). Apple Silic... |
| `mlx-community/Devstral-Small-2505-6bit` | 6.9 | 19 | ✓ |  |  | PASS | Mistral Devstral Small 2505 6-bit DENSE 24B (~19GB). V5 ladder middle-ground.... |
| `mlx-community/Devstral-Small-2505-8bit` | 5.6 | 26 | ✓ |  |  | PASS | Mistral Devstral Small 2505 8-bit DENSE 24B (~26GB). V5 ladder high-quality vari... |

**Pareto-frontier candidates (speed × memory):**
- `mlx-community/Laguna-XS.2-4bit`
- `mlx-community/Devstral-Small-2505-4bit`

---

## auto-security/redteam

| Model | Median TPS | Memory (GB) | Tools | VLM | BIG_MODEL | Smoke | Notes |
|---|---:|---:|:-:|:-:|:-:|:-:|---|
| `mlx-community/Qwen3.6-27B-AEON-Ultimate-Uncensored-BF16-mlx-4Bit` | 7.9 | 14 | ✓ |  |  | PASS | Qwen3.6 27B AEON-Ultimate-Uncensored 4-bit DENSE (~14GB, Apache 2.0). V5 securit... |
| `mlx-community/Qwen3.6-27B-AEON-Ultimate-Uncensored-BF16-mlx-6Bit` | 6.0 | 22 | ✓ |  |  | PASS | Qwen3.6 27B AEON 6-bit DENSE (~22GB). V5 ladder middle-ground.... |
| `mlx-community/Qwen3.6-27B-AEON-Ultimate-Uncensored-BF16-mlx-8Bit` | 4.7 | 29 | ✓ |  |  | PASS | Qwen3.6 27B AEON 8-bit DENSE (~29GB). V5 ladder high-quality variant.... |

**Pareto-frontier candidates (speed × memory):**
- `mlx-community/Qwen3.6-27B-AEON-Ultimate-Uncensored-BF16-mlx-4Bit`

---

## auto

| Model | Median TPS | Memory (GB) | Tools | VLM | BIG_MODEL | Smoke | Notes |
|---|---:|---:|:-:|:-:|:-:|:-:|---|
| `mlx-community/granite-4.1-3b-mxfp8` | 37.3 | 3 | ✓ |  |  | PASS | IBM Granite 4.1 3B 8-bit MX DENSE (~3GB, Apache 2.0, ~50-70 TPS theoretical). AU... |
| `mlx-community/Llama-3.2-3B-Instruct-8bit` | 30.7 | 3 | ✓ |  |  | — | Ultra-fast routing model (~3GB)... |

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
- **Fastest measured (smoke-passed):** `mlx-community/gemma-4-26b-a4b-it-4bit` at 23.4 TPS, 13 GB resident
- **Decision gate:** run T-* quality probes (see `TASK_*_SHOOTOUT_V1.md`) before promoting to workspace MLX primary.

### auto-reasoning
- **Fastest measured (smoke-passed):** `mlx-community/Olmo-3-1125-32B-4bit` at 8.6 TPS, 17 GB resident
- **Decision gate:** run T-* quality probes (see `TASK_*_SHOOTOUT_V1.md`) before promoting to workspace MLX primary.

### auto-compliance
- **Fastest measured (smoke-passed):** `mlx-community/granite-4.1-30b-mxfp4` at 7.8 TPS, 15 GB resident
- **Decision gate:** run T-* quality probes (see `TASK_*_SHOOTOUT_V1.md`) before promoting to workspace MLX primary.

### auto-coding
- **Fastest measured (smoke-passed):** `mlx-community/Laguna-XS.2-4bit` at 40.3 TPS, 19 GB resident
- **Decision gate:** run T-* quality probes (see `TASK_*_SHOOTOUT_V1.md`) before promoting to workspace MLX primary.

### auto-security/redteam
- **Fastest measured (smoke-passed):** `mlx-community/Qwen3.6-27B-AEON-Ultimate-Uncensored-BF16-mlx-4Bit` at 7.9 TPS, 14 GB resident
- **Decision gate:** run T-* quality probes (see `TASK_*_SHOOTOUT_V1.md`) before promoting to workspace MLX primary.

### auto
- **Fastest measured (smoke-passed):** `mlx-community/granite-4.1-3b-mxfp8` at 37.3 TPS, 3 GB resident
- **Decision gate:** run T-* quality probes (see `TASK_*_SHOOTOUT_V1.md`) before promoting to workspace MLX primary.

### uncategorized
- **Fastest measured (smoke-passed):** `mlx-community/Qwen2.5-0.5B-Instruct-4bit` at 234.3 TPS, 0.5 GB resident
- **Decision gate:** run T-* quality probes (see `TASK_*_SHOOTOUT_V1.md`) before promoting to workspace MLX primary.
