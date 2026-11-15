# Unused model inventory — 2026-11-15

Scope: on-disk models across Ollama (`ollama list`, store `/Volumes/data01/ollama/models`), oMLX (`/Volumes/data01/omlx-models/*`), and orphaned HuggingFace cache snapshots (`/Volumes/data01/hf-cache/models--*` not linked by any oMLX entry).

## Method

"Referenced" = a real parse of `config/backends.yaml` (model ids, alias keys and values, fallbacks), `config/portal.yaml`, `config/bench_workspaces.yaml`, `config/personas/**`, and other `config/*.yaml`, plus a repo-wide grep of `portal/`, `scripts/` (excluding `scripts/_archive/`), `deploy/`, `launch.sh`, and `tests/` for the exact tag or directory name. Every `RETAINED_FOR_PURPOSE` and `INTEGRATED` identity in `docs/MODEL_FLEET_CLOSEOUT_20260906.tasks.json` counts as referenced. The P40 host config under `~/.claude/orchestrate` was checked read-only. Derived `-ctxNNk` tags propagate reference to their base tag (a base is never marked unused if a referenced derived tag needs it). `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` (oMLX) is kept regardless (seat candidate under measurement).

## Unused models (nothing in the repo references them)

| Engine | Tag / directory | Size | Why unused |
|---|---|---|---|
| Ollama | `hf.co/bartowski/NousResearch_Arete-27B-GGUF:Q4_K_M` | 18 GB | No config ref; grep hits = 0 across portal/, scripts/, deploy/, launch.sh, tests/, config/ |
| HF-cache (orphaned snapshot) | `models--Qwen--Qwen2.5-Omni-3B` | 4.0K | No oMLX entry links to it; no config ref; grep hits = 0 (dir name, repo id, and repo name) |
| HF-cache (orphaned snapshot) | `models--docling-project--docling-layout-heron` | 164M | No oMLX entry links to it; no config ref; grep hits = 0 (dir name, repo id, and repo name) |
| HF-cache (orphaned snapshot) | `models--docling-project--docling-models` | 342M | No oMLX entry links to it; no config ref; grep hits = 0 (dir name, repo id, and repo name) |
| HF-cache (orphaned snapshot) | `models--ibm-granite--granite-switch-4.1-3b-preview` | 4.0K | No oMLX entry links to it; no config ref; grep hits = 0 (dir name, repo id, and repo name) |
| HF-cache (orphaned snapshot) | `models--mlx-community--higgs-audio-v2-tokenizer` | 768M | No oMLX entry links to it; no config ref; grep hits = 0 (dir name, repo id, and repo name) |
| HF-cache (orphaned snapshot) | `models--mobiuslabsgmbh--faster-whisper-large-v3-turbo` | 1.5G | No oMLX entry links to it; no config ref; grep hits = 0 (dir name, repo id, and repo name) |
| HF-cache (orphaned snapshot) | `models--tencent--AuK-Flash` | 4.0K | No oMLX entry links to it; no config ref; grep hits = 0 (dir name, repo id, and repo name) |

**Total reclaimable (unused set):** ~20.9 GB (18 GB Ollama + ~2.8 GB HF-cache).

## Referenced set

### Ollama tags (97 referenced)

| Tag | Size | First referencing file |
|---|---|---|
| `deepseek-r1:32b-q4_k_m` | 19851336215 | `config/model_inventory.snapshot` |
| `devstral-small-2:latest-ctx8k` | 15177373852 | `config/model_inventory.snapshot` |
| `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx24k` | 22067041473 | `config/MODEL_CATALOG.md` |
| `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` | 22067041472 | `config/promptfoo/daily_quality.yaml` |
| `gemma4:12b-it-qat-ctx8k` | 7151003769 | `config/promptfoo/media_quality.yaml` |
| `gemma4:26b-a4b-it-q4_K_M` | 17987581215 | `config/model_inventory.snapshot` |
| `gemma4:26b-a4b-it-q4_K_M-ctx128k` | 17987580934 | `config/MODEL_CATALOG.md` |
| `gemma4:26b-a4b-it-q4_K_M-ctx64k` | 17987580926 | `config/MODEL_CATALOG.md` |
| `gemma4:26b-a4b-it-qat-ctx128k` | 15634199591 | `config/MODEL_CATALOG.md` |
| `gemma4:26b-a4b-it-qat-ctx16k` | 15634199583 | `config/model_inventory.snapshot` |
| `gemma4:26b-a4b-it-qat-ctx32k` | 15634199590 | `config/promptfoo/document_quality.yaml` |
| `gemma4:26b-a4b-it-qat-ctx64k` | 15634199590 | `config/MODEL_CATALOG.md` |
| `gemma4:26b-a4b-it-qat-ctx8k` | 15634199961 | `config/model_inventory.snapshot` |
| `gemma4:26b-a4b-it-qat-ctx8k-hunt` | 15634199589 | `config/model_inventory.snapshot` |
| `gemma4:31b-it-qat-ctx8k` | 18851735913 | `config/model_inventory.snapshot` |
| `gemma4:e4b-it-qat` | 6146501801 | `config/model_inventory.snapshot` |
| `gemma4:e4b-it-qat-ctx8k` | 6146501444 | `config/model_inventory.snapshot` |
| `glm-4.7-flash:Q4_K_M` | 19019270897 | `config/promptfoo/reasoning_quality.yaml` |
| `glm-4.7-flash:Q4_K_M-ctx64k` | 19019270651 | `config/promptfoo/reasoning_quality.yaml` |
| `glm-4.7-flash:Q4_K_M-ctx64k-agentic` | 19019270614 | `config/MODEL_CATALOG.md` |
| `granite4.1:30b-ctx16k` | 17490259446 | `config/FOLLOWUP_REASONING_OVERHAUL_REMAINING_V1.md` |
| `granite4.1:30b-ctx64k` | 17490259446 | `config/model_inventory.snapshot` |
| `granite4.1:30b-ctx96k` | 17490259074 | `config/MODEL_CATALOG.md` |
| `granite4.1:8b-ctx16k` | 5347933109 | `config/promptfoo/document_quality.yaml` |
| `granite4.1:8b-ctx8k` | 5347933108 | `config/promptfoo/coding_quality.yaml` |
| `hermes3:8b` | 4661227243 | `config/model_inventory.snapshot` |
| `hf.co/JetBrains/Mellum2.1-12B-A2.5B-Thinking-GGUF:Q4_K_M` | 8071297424 | `config/MODEL_CATALOG.md` |
| `hf.co/JetBrains/Mellum2.1-12B-A2.5B-Thinking-GGUF:Q4_K_M-ctx32k` | 8071297092 | `config/MODEL_CATALOG.md` |
| `hf.co/bartowski/K2-Horizon-MoVA-36B-A4B-GGUF:Q4_K_M` | 22701886083 | `config/MODEL_CATALOG.md` |
| `hf.co/bartowski/K2-Horizon-MoVA-36B-A4B-GGUF:Q4_K_M-ctx64k` | 22701885809 | `config/MODEL_CATALOG.md` |
| `hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k` | 25477403910 | `config/promptfoo/daily_quality.yaml` |
| `hf.co/bartowski/THUDM_GLM-Z1-32B-0414-GGUF:Q4_K_M` | 19680023363 | `config/MODEL_CATALOG.md` |
| `hf.co/bartowski/THUDM_GLM-Z1-32B-0414-GGUF:Q4_K_M-ctx32k` | 19680022956 | `config/MODEL_CATALOG.md` |
| `hf.co/bartowski/nex-agi_Nex-N2.5-mini-GGUF:Q4_K_M` | 23217795786 | `config/MODEL_CATALOG.md` |
| `hf.co/coder543/North-Mini-Code-1.0-QAD-GGUF:NVFP4-ctx8k` | 19329884595 | `config/model_inventory.snapshot` |
| `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M-ctx64k` | 21166757955 | `config/model_inventory.snapshot` |
| `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf` | 18687057606 | `config/model_inventory.snapshot` |
| `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf-ctx8k` | 18687057621 | `config/MODEL_CATALOG.md` |
| `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0` | 8540949071 | `config/promptfoo/security_quality.yaml` |
| `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0-ctx8k` | 8540949088 | `config/MODEL_CATALOG.md` |
| `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:q4_K_M-ctx8k` | 5155565010 | `config/model_inventory.snapshot` |
| `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:Q4_K_M` | 21780953681 | `config/model_inventory.snapshot` |
| `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:q4_K_M-ctx8k` | 21780953698 | `config/MODEL_CATALOG.md` |
| `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k` | 4683076467 | `config/promptfoo/security_quality.yaml` |
| `hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M` | 5302272933 | `config/bench_engines.yaml` |
| `hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M-ctx2k` | 5302273034 | `config/bench_engines.yaml` |
| `hf.co/openbmb/MiniCPM5-1B-GGUF:Q4_K_M` | 688066719 | `config/model_inventory.snapshot` |
| `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M` | 23017033841 | `config/promptfoo/strategic_quality.yaml` |
| `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M-ctx16k` | 23017033859 | `config/MODEL_CATALOG.md` |
| `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k` | 5122748084 | `config/promptfoo/reasoning_quality.yaml` |
| `hf.co/unsloth/LFM2.5-24B-A2B-GGUF:UD-Q4_K_XL` | 14876902458 | `config/MODEL_CATALOG.md` |
| `hf.co/unsloth/LFM2.5-24B-A2B-GGUF:UD-Q4_K_XL-ctx96k` | 14876902081 | `config/MODEL_CATALOG.md` |
| `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k` | 25932839804 | `config/model_inventory.snapshot` |
| `hf.co/unsloth/NVIDIA-Nemotron-3.5-Bolt-E4B-GGUF:UD-Q4_K_XL` | 6052035863 | `config/MODEL_CATALOG.md` |
| `hf.co/unsloth/NVIDIA-Nemotron-3.5-Bolt-E4B-GGUF:UD-Q4_K_XL-ctx8k` | 6052035880 | `config/MODEL_CATALOG.md` |
| `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx32k` | 23263279036 | `config/promptfoo/reasoning_quality.yaml` |
| `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx96k` | 23263279036 | `config/MODEL_CATALOG.md` |
| `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M` | 17392047883 | `config/bench_engines.yaml` |
| `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` | 17392047901 | `config/bench_engines.yaml` |
| `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k` | 17392047901 | `config/MODEL_CATALOG.md` |
| `hf.co/unsloth/flint-GGUF:UD-Q4_K_XL` | 25054700612 | `config/MODEL_CATALOG.md` |
| `hf.co/unsloth/flint-GGUF:UD-Q4_K_XL-ctx256k` | 25054700272 | `config/MODEL_CATALOG.md` |
| `huihui_ai/Qwen3.6-abliterated:27b` | 17420432435 | `config/model_inventory.snapshot` |
| `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` | 17420432820 | `config/model_inventory.snapshot` |
| `huihui_ai/baronllm-abliterated:latest-ctx8k` | 4920748159 | `config/model_inventory.snapshot` |
| `huihui_ai/gemma-4-abliterated:E2b-qat` | 4402962478 | `config/promptfoo/security_quality.yaml` |
| `huihui_ai/qwen3.5-abliterated:9b` | 6594474385 | `config/promptfoo/daily_quality.yaml` |
| `huihui_ai/qwen3.5-abliterated:9b-ctx64k` | 6594474401 | `config/model_inventory.snapshot` |
| `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | 6594474400 | `config/model_inventory.snapshot` |
| `huihui_ai/tongyi-deepresearch-abliterated:latest-ctx64k` | 18556699858 | `config/model_inventory.snapshot` |
| `kat-coder-v2.5-dev:Q4_K_M` | 21391448657 | `config/MODEL_CATALOG.md` |
| `kat-coder-v2.5-dev:Q4_K_M-ctx32k` | 21391448675 | `config/MODEL_CATALOG.md` |
| `lfm2.5:8b-ctx8k` | 5156075540 | `config/promptfoo/media_quality.yaml` |
| `mistral-small3.2:24b` | 15177384862 | `config/model_inventory.snapshot` |
| `mistral-small3.2:24b-ctx16k` | 15177384432 | `config/MODEL_CATALOG.md` |
| `mistral-small3.2:24b-instruct-2506-q4_K_M` | 15177384862 | `config/MODEL_CATALOG.md` |
| `omnicoder2:9b-q4_k_m` | 5629109768 | `config/model_inventory.snapshot` |
| `omnicoder2:9b-q4_k_m-ctx8k` | 5629109767 | `config/model_inventory.snapshot` |
| `orcacyber-nano-1.0:ctx64k` | 16622755968 | `config/MODEL_CATALOG.md` |
| `phi4-mini-reasoning:latest-ctx24k` | 3152479483 | `config/model_inventory.snapshot` |
| `portal5/agentworld-35b:ud-q4_K_XL-ctx256k` | 22324805060 | `config/MODEL_CATALOG.md` |
| `portal5/gemma4-26b-heretic:q4_K_M-ctx256k` | 16796012079 | `config/MODEL_CATALOG.md` |
| `portal5/hauhaucs-qwen36-35b:q4_K_M-ctx256k` | 22066041284 | `config/MODEL_CATALOG.md` |
| `portal5/laguna-xs21:q4_K_M-ctx128k` | 20274302868 | `config/MODEL_CATALOG.md` |
| `portal5/omnicoder2-9b:q4_K_M-ctx256k` | 5629109769 | `config/MODEL_CATALOG.md` |
| `portal5/ornith15-35b:q4_K_M-ctx256k` | 22327659172 | `config/MODEL_CATALOG.md` |
| `portal5/spark-x2.6:q4_K_M-ctx64k` | 3543441654 | `config/MODEL_CATALOG.md` |
| `qwen3-coder:30b-a3b-q4_K_M` | 18556700761 | `config/promptfoo/coding_quality.yaml` |
| `qwen3-coder:30b-a3b-q4_K_M-ctx16k` | 18556700706 | `config/model_inventory.snapshot` |
| `qwen3-coder:30b-a3b-q4_K_M-ctx32k` | 18556700408 | `config/MODEL_CATALOG.md` |
| `qwen3-vl:32b` | 20910297800 | `config/promptfoo/media_quality.yaml` |
| `qwen3-vl:32b-ctx8k` | 20957707018 | `config/promptfoo/media_quality.yaml` |
| `qwen3-vl:4b-instruct-q4_K_M` | 3335885370 | `config/engine_contract.yaml` |
| `qwen3.6:27b-q4_K_M` | 17429272896 | `config/model_inventory.snapshot` |
| `qwen3.6:27b-q4_K_M-ctx16k` | 17420432472 | `config/MODEL_CATALOG.md` |
| `qwen3.6:27b-q4_K_M-ctx4k` | 17429272919 | `config/MODEL_CATALOG.md` |
| `supergemma4-26b-uncensored:Q4_K_M-ctx64k` | 16796015892 | `config/model_inventory.snapshot` |

### oMLX entries (20 referenced)

| Directory | First referencing file |
|---|---|
| `DeepSeek-R1-0528-Qwen3-8B-4bit` | `config/FOLLOWUP_REASONING_OVERHAUL_REMAINING_V1.md` |
| `Huihui-Qwen3.6-27B-abliterated-MLX-4bit` | `config/promptfoo/document_quality.yaml` |
| `Jiunsong--supergemma4-26b-uncensored-mlx-4bit-v2` | `config/MODEL_CATALOG.md` |
| `Laguna-XS-2.1-4bit` | `config/MODEL_CATALOG.md` |
| `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` | `config/MODEL_CATALOG.md` |
| `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp` | `config/TASK_OMLX_REASONING_POOL_REPAIR_V1.md` |
| `Qwen3-Coder-30B-A3B-Instruct-4bit` | `config/TASK_OMLX_REASONING_POOL_REPAIR_V1.md` |
| `Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit` | `config/TASK_OMLX_REASONING_POOL_REPAIR_V1.md` |
| `Qwen3.8-27B-4bit` | `config/bench_engines.yaml` |
| `Qwen3.8-27B-DFlash2` | `config/MODEL_CATALOG.md` |
| `Qwen3.8-27B-oQ4e-mtp` | `config/TASK_OMLX_REASONING_POOL_REPAIR_V1.md` |
| `Tongyi-DeepResearch-30B-A3B-abliterated-4bit` | `config/FOLLOWUP_REASONING_OVERHAUL_REMAINING_V1.md` |
| `VulnLLM-R-7B-4bit` | `config/FOLLOWUP_REASONING_OVERHAUL_REMAINING_V1.md` |
| `gemma-4-26b-a4b-it-QAT-4bit` | `config/TASK_OMLX_REASONING_POOL_REPAIR_V1.md` |
| `granite-4.1-30b-4bit` | `config/FOLLOWUP_REASONING_OVERHAUL_REMAINING_V1.md` |
| `huihui-ai--Huihui-Qwen3.5-9B-abliterated-mlx-4bit` | `config/engine_contract.yaml` |
| `mlx-community--Mistral-Small-3.2-24B-Instruct-2506-4bit` | `config/MODEL_CATALOG.md` |
| `mlx-community--gemma-4-26b-a4b-it-4bit` | `config/MODEL_CATALOG.md` |
| `unsloth--Qwen3.6-27B-UD-MLX-4bit` | `config/MODEL_CATALOG.md` |
| `unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit` | `config/MODEL_CATALOG.md` |

### HF-cache snapshots referenced (39)

| Directory | Size | First referencing file |
|---|---|---|
| `models--BAAI--bge-reranker-v2-m3` | 20K | `deploy/portal-5/docker-compose.yml` |
| `models--CIRCL--vulnerability-severity-classification-roberta-base` | 956M | `portal/modules/security/tools/security_mcp.py` |
| `models--Qwen--Qwen-Image-2512` | 54G | `tests/unit/test_check_updates.py` |
| `models--Qwen--Qwen-Image-Edit-2509` | 54G | `tests/unit/test_check_updates.py` |
| `models--Qwen--Qwen3-1.7B` | 12K | `tests/benchmarks/engine_h2h.yaml` |
| `models--Qwen--Qwen3-4B` | 12K | `tests/benchmarks/engine_h2h.yaml` |
| `models--Qwen--Qwen3-8B` | 20K | `config/model_card_expectations.yaml` |
| `models--Qwen--Qwen3.6-27B` | 28K | `config/model_card_expectations.yaml` |
| `models--Qwen--Qwen3.8-27B` | 28K | `config/MODEL_CATALOG.md` |
| `models--Tongyi-MAI--Z-Image-Turbo` | 31G | `tests/unit/test_check_updates.py` |
| `models--google--embeddinggemma-2` | 80K | `config/backends.yaml` |
| `models--mlx-community--Kokoro-82M-bf16` | 339M | `scripts/mlx-speech.py` |
| `models--mlx-community--Laguna-XS-2.1-4bit` | 4.0K | `config/backends.yaml` |
| `models--mlx-community--Phi-4-mini-reasoning-4bit` | 4.0K | `config/MODEL_CATALOG.md` |
| `models--mlx-community--Qwen2.5-0.5B-Instruct-4bit` | 4.0K | `tests/benchmarks/engine_h2h.yaml` |
| `models--mlx-community--Qwen3-ASR-1.7B-8bit` | 2.3G | `scripts/mlx-speech.py` |
| `models--mlx-community--Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit` | 2.9G | `scripts/mlx-speech.py` |
| `models--mlx-community--Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit` | 2.9G | `scripts/mlx-speech.py` |
| `models--mlx-community--Qwen3-VL-Embedding-2B-mxfp8` | 2.4G | `scripts/vl-retrieval-server.py` |
| `models--mlx-community--Qwen3-VL-Reranker-2B-mxfp8` | 2.4G | `scripts/vl-retrieval-server.py` |
| `models--mlx-community--Qwopus3.6-35B-A3B-Coder-4bit` | 4.0K | `scripts/seat_screen/kit/portal_variants.yaml` |
| `models--mlx-community--diar_sortformer_4spk-v1-fp32` | 471M | `scripts/mlx-transcribe.py` |
| `models--mlx-community--gemma-4-26b-a4b-it-4bit` | 4.0K | `scripts/seat_screen/intake_s8/queue.yaml` |
| `models--mlx-community--higgs-audio-v2-3B-mlx-q8` | 5.8G | `scripts/mlx-speech.py` |
| `models--mlx-community--parakeet-tdt-0.6b-v3` | 2.3G | `scripts/mlx-transcribe.py` |
| `models--orcarouter--OrcaCyber-Nano-1.0` | 4.0K | `config/model_card_expectations.yaml` |
| `models--poolside--Laguna-XS.2-speculator.dflash` | 4.0K | `tests/benchmarks/engine_h2h.yaml` |
| `models--prism-ml--Bonsai-1.7B-unpacked` | 12K | `tests/benchmarks/engine_h2h.yaml` |
| `models--prism-ml--Bonsai-4B-unpacked` | 12K | `tests/benchmarks/engine_h2h.yaml` |
| `models--prism-ml--Bonsai-8B-unpacked` | 8.0K | `tests/benchmarks/engine_h2h.yaml` |
| `models--prism-ml--Ternary-Bonsai-1.7B-unpacked` | 12K | `tests/benchmarks/engine_h2h.yaml` |
| `models--prism-ml--Ternary-Bonsai-2-27B-mlx-2bit` | 4.0K | `tests/benchmarks/engine_h2h.yaml` |
| `models--prism-ml--Ternary-Bonsai-4B-unpacked` | 12K | `tests/benchmarks/engine_h2h.yaml` |
| `models--prism-ml--Ternary-Bonsai-8B-unpacked` | 8.0K | `tests/benchmarks/engine_h2h.yaml` |
| `models--sentence-transformers--all-MiniLM-L6-v2` | 700K | `portal/platform/retrieval/chunking.py` |
| `models--unsloth--DeepSeek-R1-0528-Qwen3-8B` | 24K | `config/promptfoo/reasoning_quality.yaml` |
| `models--unsloth--Qwen3-1.7B-GGUF` | 24K | `tests/unit/test_bench_engine_h2h.py` |
| `models--unsloth--Qwen3-4B-GGUF` | 24K | `tests/benchmarks/engine_h2h.yaml` |
| `models--unsloth--Qwen3-8B-GGUF` | 24K | `tests/benchmarks/engine_h2h.yaml` |

## HOLD (ambiguous — not removed)

HF-cache snapshots with no direct directory/repo-id reference, but whose short model name appears somewhere in the repo (often because an oMLX entry or config shares the name). These are not removed by the script; the orchestrator decides.

| Directory | Size | Repo-name hits | Note |
|---|---|---|---|
| `models--Jiunsong--supergemma4-26b-uncensored-mlx-4bit-v2` | 4.0K | 4 | short name `supergemma4-26b-uncensored-mlx-4bit-v2` appears in repo; no direct hf-cache load by repo id found |
| `models--Youssofal--MiMo-V2.6-Qwen-9B-MTPLX-Optimized-Speed` | 4.0K | 2 | short name `MiMo-V2.6-Qwen-9B-MTPLX-Optimized-Speed` appears in repo; no direct hf-cache load by repo id found |
| `models--Youssofal--Qwen3.6-27B-MTPLX-Optimized-Speed` | 4.0K | 1 | short name `Qwen3.6-27B-MTPLX-Optimized-Speed` appears in repo; no direct hf-cache load by repo id found |
| `models--Youssofal--Ternary-Bonsai-2-27B-MTPLX-Optimized-Speed` | 4.0K | 1 | short name `Ternary-Bonsai-2-27B-MTPLX-Optimized-Speed` appears in repo; no direct hf-cache load by repo id found |
| `models--black-forest-labs--FLUX.2-klein-4B` | 15G | 1 | short name `FLUX.2-klein-4B` appears in repo; no direct hf-cache load by repo id found |
| `models--ddalcu--MiMo-V2.6-Distill-Qwen-9B-MLX-Serve-4bit` | 4.0K | 8 | short name `MiMo-V2.6-Distill-Qwen-9B-MLX-Serve-4bit` appears in repo; no direct hf-cache load by repo id found |
| `models--mlx-community--Mistral-Small-3.2-24B-Instruct-2506-4bit` | 4.0K | 4 | short name `Mistral-Small-3.2-24B-Instruct-2506-4bit` appears in repo; no direct hf-cache load by repo id found |
| `models--nabi-chan--Huihui-Qwen3.6-27B-abliterated-MLX-4bit` | 4.0K | 16 | short name `Huihui-Qwen3.6-27B-abliterated-MLX-4bit` appears in repo; no direct hf-cache load by repo id found |
| `models--nativ-community--MiMo-V2.6-Distill-Qwen-9B-MLX-4bit` | 4.0K | 5 | short name `MiMo-V2.6-Distill-Qwen-9B-MLX-4bit` appears in repo; no direct hf-cache load by repo id found |
| `models--prince-canuma--Kokoro-82M` | 1.0M | 1 | short name `Kokoro-82M` appears in repo; no direct hf-cache load by repo id found |
| `models--prism-ml--Bonsai-27B-mlx-1bit` | 4.0K | 6 | short name `Bonsai-27B-mlx-1bit` appears in repo; no direct hf-cache load by repo id found |
| `models--prism-ml--Ternary-Bonsai-8B-mlx-2bit` | 4.0K | 6 | short name `Ternary-Bonsai-8B-mlx-2bit` appears in repo; no direct hf-cache load by repo id found |
| `models--tencent--AuK` | 4.0K | 6 | short name `AuK` appears in repo; no direct hf-cache load by repo id found |
| `models--unsloth--Qwen3.6-27B-GGUF` | 28K | 22 | short name `Qwen3.6-27B-GGUF` appears in repo; no direct hf-cache load by repo id found |
| `models--unsloth--Qwen3.6-27B-UD-MLX-4bit` | 4.0K | 14 | short name `Qwen3.6-27B-UD-MLX-4bit` appears in repo; no direct hf-cache load by repo id found |
| `models--unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit` | 4.0K | 17 | short name `Qwen3.6-35B-A3B-UD-MLX-4bit` appears in repo; no direct hf-cache load by repo id found |

## Notes

- `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` (oMLX) is retained regardless of reference status (seat candidate under measurement); it is in fact referenced (config/MODEL_CATALOG.md).
- Empty 4 KB HF-cache directories (Qwen2.5-Omni-3B, granite-switch-4.1-3b-preview, AuK-Flash) are incomplete snapshots with only `refs/main` and no weights; removal reclaims no weight bytes but cleans up.
- The removal script (`scripts/remove_unused_models_20261115.sh`) re-verifies each item is still unreferenced immediately before deleting it.
