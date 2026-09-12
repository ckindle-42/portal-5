# Model disposition report (fleet closeout register)

Source: `docs/MODEL_FLEET_CLOSEOUT_20260906.tasks.json` — terminal dispositions only.
This audit does NOT regenerate a pending ledger.

| Disposition | Count |
|---|---:|
| INTEGRATED | 64 |
| RETAINED_FOR_PURPOSE | 14 |
| REMOVED_CLOSED | 103 |

## True cleanup exceptions — REMOVED_CLOSED still on disk (30)

- `baronllm:q6_k`
- `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4`
- `gemma4:12b-it-qat`
- `gemma4:26b-a4b-it-qat`
- `gemma4:31b-it-qat`
- `hf.co/HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4_K_M`
- `hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M`
- `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M`
- `hf.co/coder543/North-Mini-Code-1.0-QAD-GGUF:NVFP4`
- `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M`
- `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M`
- `hf.co/mradermacher/Ornith-1.5-35B-A3B-Uncensored-GGUF:Q4_K_M`
- `hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF:Q4_K_M`
- `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M`
- `hf.co/mradermacher/gemma-4-26B-A4B-it-heretic-GGUF:Q4_K_M`
- `hf.co/mradermacher/gemma-4-26B-A4B-it-heretic-GGUF:q4_k_m-ctx16k`
- `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k`
- `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL`
- `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`
- `hf.co/unsloth/phi-4-GGUF:Q4_K_M`
- `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M`
- `huihui_ai/baronllm-abliterated:latest`
- `huihui_ai/qwen3-abliterated:14b-v2`
- `laguna-xs.2:Q4_K_M`
- `lfm2.5:8b`
- `phi4:14b`
- `portal5/omnicoder2-9b:q4_K_M-ctx256k`
- `qwen3-coder-next:latest`
- `qwen3-coder:30b-a3b-q4_K_M-ctx8k`
- `supergemma4-26b-uncensored:Q4_K_M`

## Config drift — INTEGRATED but absent from store (0)

(none)
