# Model disposition report (fleet closeout register)

Source: `docs/MODEL_FLEET_CLOSEOUT_20260906.tasks.json` — terminal dispositions only.
This audit does NOT regenerate a pending ledger.

| Disposition | Count |
|---|---:|
| INTEGRATED | 64 |
| RETAINED_FOR_PURPOSE | 4 |
| REMOVED_CLOSED | 113 |

## True cleanup exceptions — REMOVED_CLOSED still on disk (73)

- `baronllm:q6_k`
- `bully-ae9fa52b558fbce0:latest`
- `bully-bcb0e4b867519350:latest`
- `command-r:35b-08-2024-q4_K_M`
- `deepseek-ocr:latest`
- `devstral-small-2:latest`
- `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4`
- `gemma3:4b-it-q4_K_M`
- `gemma4:12b-it-qat`
- `gemma4:26b-a4b-it-qat`
- `gemma4:31b-it-qat`
- `gemma4:e2b-it-qat`
- `gemma4:e4b-it-q4_K_M`
- `gemma4:e4b-it-qat`
- `glm-ocr:Q8_0`
- `gpt-oss:20b`
- `granite3.2-vision:2b`
- `granite4.1:30b`
- `granite4.1:8b`
- `granite4.1:8b-q8_0`
- `granite4.1:8b-q8_0-ctx16k`
- `granite4.2:30b-q4_K_M`
- `granite4.2:30b-q8_0`
- `granite4.2:3b-q8_0`
- `granite4.2:8b-q8_0`
- `hf.co/DevQuasar/fdtn-ai.antares-1b-GGUF:Q4_K_M`
- `hf.co/HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4_K_M`
- `hf.co/Nguuma/security-slm-unsloth-1.5b:latest`
- `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF:latest`
- `hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M`
- `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M`
- `hf.co/coder543/North-Mini-Code-1.0-QAD-GGUF:NVFP4`
- `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M`
- `hf.co/ewinregirgojr/MiniCPM5-1B-Agentic-Tooluse-GGUF:Q4_K_M`
- `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M`
- `hf.co/ggml-org/dots.ocr-GGUF:Q8_0`
- `hf.co/mradermacher/Nanonets-OCR2-3B-GGUF:Q4_K_M`
- `hf.co/mradermacher/Ornith-1.5-35B-A3B-Uncensored-GGUF:Q4_K_M`
- `hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF:Q4_K_M`
- `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M`
- `hf.co/mradermacher/gemma-4-26B-A4B-it-heretic-GGUF:Q4_K_M`
- `hf.co/mradermacher/gemma-4-26B-A4B-it-heretic-GGUF:q4_k_m-ctx16k`
- `hf.co/mradermacher/gemma-4-26B-A4B-it-uncensored-heretic-GGUF:gemma-4-26B-A4B-it-uncensored-heretic.Q4_K_M.gguf`
- `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL`
- `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL`
- `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k`
- `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0`
- `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL`
- `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL-ctx64k`
- `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`
- `hf.co/unsloth/phi-4-GGUF:Q4_K_M`
- `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M`
- `huihui_ai/baronllm-abliterated:latest`
- `huihui_ai/qwen3-abliterated:14b-v2`
- `kat-coder-v2.5-dev:Q4_K_M`
- `laguna-xs.2:Q4_K_M`
- `laguna-xs.2:Q4_K_M-ctx64k`
- `lfm2.5:8b`
- `minicpm-v4.5:Q4_K_M`
- `minicpm-v:8b-2.6-q4_K_M`
- `phi4-reasoning:plus`
- `phi4-reasoning:plus-ctx32k`
- `phi4:14b`
- `phi4:14b-q4_K_M`
- `phi4:14b-q8_0`
- `portal5/cadmium:Q4_K_M`
- `portal5/omnicoder2-9b:q4_K_M-ctx256k`
- `portal5/xyz-aquila-mini:q4_k_m-ctx16k`
- `qwen3-coder-next:latest`
- `qwen3-coder:30b-a3b-q4_K_M-ctx8k`
- `qwen3-vl:2b-instruct-q4_K_M`
- `qwen36-fable-fusion-711:Q4_K_M`
- `supergemma4-26b-uncensored:Q4_K_M`

## Config drift — INTEGRATED but absent from store (0)

(none)
