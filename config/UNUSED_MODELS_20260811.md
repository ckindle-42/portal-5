# Unused models — TASK_MODEL_DISK_RECLAIM_V1 addendum (20260811)

Reclaimed via operator verdicts recorded inline in
`config/PENDING_MODEL_VERDICTS.md`. Verdicts and reasons quoted verbatim.

## Declined (removed from disk)

| Tag | Size | Reason |
|---|---|---|

**Total declined: 0 models, 0.0 GB.**

## Kept — active investigations (not deleted)

| Tag | Size | Reason |
|---|---|---|
| `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` | 21.7 GB | card/slot mismatch: 2 advertised capabilities untested; unique capability: MoE architecture (routes tokens to expert subsets |
| `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M` | 21.4 GB | removes Nex-N2 arch from fleet entirely; removes vendor 'sjakek' from fleet; net-new: arch family: 'Nex-N2' (not in fleet elsewhere); only exploration of this arch in the fleet |
| `hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K` | 20.6 GB | removes BugTraceAI arch from fleet entirely; removes vendor 'BugTraceAI' from fleet; net-new: arch family: 'BugTraceAI' (not in fleet elsewhere); only exploration of this arch in the fleet; post-boundary: below 20 t/s floor (avg 9.79 |
| `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:Q4_K_M` | 20.3 GB | card/slot mismatch: 1 advertised capabilities untested; unique capability: MoE architecture (routes tokens to expert subsets |
| `portal5/xyz-aquila-mini:Q4_K_M` | 19.9 GB | introduced 1d ago — still in eval window |
| `portal5/xyz-aquila-mini:q4_k_m-ctx16k` | 19.9 GB | introduced 1d ago — still in eval window |
| `muse-glimmer:30b-mlx` | 19.8 GB | removes Muse-Glimmer arch from fleet entirely; net-new: arch family: 'Muse-Glimmer' (not in fleet elsewhere); only exploration of this arch in the fleet; introduced 1d ago — still in eval window |
| `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M` | 19.7 GB | removes vendor 'Jiunsong' from fleet; net-new: vendor: 'Jiunsong' (not in fleet elsewhere |
| `hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.gguf` | 18.2 GB | card/slot mismatch: 1 advertised capabilities untested; unique capability: MTP speculative drafting (draft model bound to base); post-boundary: below 20 t/s floor (avg 9.38 |
| `gemma4:31b-it-qat-ctx8k` | 17.6 GB | card/slot mismatch: 1 advertised capabilities untested |
| `gemma4:31b-it-qat` | 17.6 GB | card/slot mismatch: 1 advertised capabilities untested |
| `gemma4:26b-a4b-it-q4_K_M` | 16.8 GB | card/slot mismatch: 2 advertised capabilities untested |
| `qwen3.6:27b-mtp-q4_K_M` | 16.5 GB | card/slot mismatch: 1 advertised capabilities untested; unique capability: MTP speculative drafting (draft model bound to base); introduced 1d ago — still in eval window; post-boundary: below 20 t/s floor (avg 10.73 |
| `hf.co/mradermacher/gemma-4-26B-A4B-it-uncensored-heretic-GGUF:gemma-4-26B-A4B-it-uncensored-heretic.Q4_K_M.gguf` | 16.4 GB | card/slot mismatch: 1 advertised capabilities untested; introduced 1d ago — still in eval window |
| `sylink/sylink:8b` | 15.3 GB | removes vendor 'sylink' from fleet; net-new: vendor: 'sylink' (not in fleet elsewhere); post-boundary: below 20 t/s floor (avg 16.5 |
| `phi4:14b-q8_0` | 14.5 GB | card/slot mismatch: 1 advertised capabilities untested; introduced 1d ago — still in eval window |
| `mistral-small3.2:24b` | 14.1 GB | card/slot mismatch: 1 advertised capabilities untested; introduced 20d ago — still in eval window; post-boundary: below 20 t/s floor (avg 9.35 |
| `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M` | 7.1 GB | card/slot mismatch: 1 advertised capabilities untested; unique capability: MTP speculative drafting (draft model bound to base); introduced 1d ago — still in eval window |
| `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M` | 6.9 GB | removes vendor 'yuxinlu1' from fleet; net-new: vendor: 'yuxinlu1' (not in fleet elsewhere); arch already 13-strong; this adds no capability |
| `gemma4:e4b-it-qat-ctx8k` | 5.7 GB | card/slot mismatch: 1 advertised capabilities untested |
| `gemma4:e4b-it-qat` | 5.7 GB | card/slot mismatch: 1 advertised capabilities untested |
| `dolphin-llama3:8b` | 4.3 GB | card/slot mismatch: 1 advertised capabilities untested; removes Llama3 arch from fleet entirely; net-new: arch family: 'Llama3' (not in fleet elsewhere); only exploration of this arch in the fleet; introduced 1d ago — still in eval window |
| `huihui_ai/gemma-4-abliterated:E2b-qat-ctx8k` | 4.1 GB | card/slot mismatch: 1 advertised capabilities untested; unique capability: Abliterated (safety-vector ablation |
| `gemma4:e2b-it-qat-ctx8k` | 4.0 GB | card/slot mismatch: 1 advertised capabilities untested |
| `gemma4:e2b-it-qat` | 4.0 GB | card/slot mismatch: 1 advertised capabilities untested |
| `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M` | 3.8 GB | unique capability: MTP speculative drafting (draft model bound to base); introduced 1d ago — still in eval window |
| `llama3.2:3b-instruct-q8_0-ctx8k` | 3.2 GB | card/slot mismatch: 1 advertised capabilities untested; introduced 1d ago — still in eval window |
| `hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M` | 2.3 GB | removes vendor 'mitkox' from fleet; net-new: vendor: 'mitkox' (not in fleet elsewhere |
| `llama3.2:3b` | 1.9 GB | card/slot mismatch: 1 advertised capabilities untested; introduced 1d ago — still in eval window |
| `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF:latest` | 1.3 GB | card/slot mismatch: 1 advertised capabilities untested; removes vendor 'QuantFactory' from fleet; net-new: vendor: 'QuantFactory' (not in fleet elsewhere); introduced 1d ago — still in eval window |
