# Unused Ollama models — confirmed safe to delete (2026-07-21)

Generated during a project-wide disk-usage review (see `P5-FUT-DISK-CLEANUP-001` in
`P5_ROADMAP.md`). Cross-referenced against every workspace `model_hint`/`secondary_model`/
`tertiary_model`/`preferred_models` in `config/portal.yaml`, every `backends.yaml` group `id`,
every persona `model_pin`, a full-repo text grep for live code references, and
`scripts/reconcile_security_arm.py`'s 2026-07-16 reconciliation report
(`docs/reconciliation/SECURITY_ARM_RECONCILE_20260716T022931Z.md`), which already flagged these
as unwired 5 days before this list was built — this is known, deferred cleanup debt from past
V10/V11/V13 candidate-intake rounds, not a mystery.

**41 models, 637.4 GB total.**

Excluded from this list (confirmed still needed, do not delete):
- `hf.co/ewinregirgojr/MiniCPM5-1B-Agentic-Tooluse-GGUF:Q4_K_M` and
  `hf.co/openbmb/MiniCPM5-1B-GGUF:Q4_K_M` — actively imported by
  `portal/platform/inference/tool_preselect/{cli_probe,config}.py` (the dormant-but-preserved
  `P5-FUT-TOOL-PRESELECT` feature — roadmap: "the built Phase 1+2 code is reusable as-is").
- `nomic-embed-text:latest` — real RAG-embedding fallback, referenced by
  `portal/platform/inference/cli/update.py`'s pull list; wired through the embedding subsystem
  (docker-compose/RAG), not the workspace `model_hint` system this review's primary scan covered.

Already deleted in this pass (documented DROPPED in `MODEL_CATALOG.md`, 30GB reclaimed 2026-07-21):
- `hf.co/TeichAI/GLM-4.7-Flash-Claude-Opus-4.5-High-Reasoning-Distill-GGUF:Q4_K_M`
- `hf.co/deepreinforce-ai/Ornith-1.0-9B-GGUF:Q4_K_M`
- `hf.co/empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF:Q4_K_M`

## Confirmed safe to delete

| Model | Size |
|---|---|
| `cogito:32b` | 19 GB |
| `davidau-qwen36-40b-neocode:latest` | 24 GB |
| `deephat-v1-7b-ctx16k:latest` | 4.7 GB |
| `devstral-small-2-ctx16k:latest` | 15 GB |
| `gemma4-12b-uncensored-ctx16k:latest` | 7.4 GB |
| `gemma4-26b-a4b-uncensored-ctx16k:latest` | 16 GB |
| `gemma4-31b-uncensored-ctx16k:latest` | 18 GB |
| `gemma4:e2b-it-q4_K_M` | 7.2 GB |
| `gemma4:e4b-mlx` | 8.8 GB |
| `granite4.1:30b-ctx32k` | 17 GB |
| `hauhaucs-gemma4-12b-ctx16k:latest` | 7.6 GB |
| `hf.co/Abiray/ThinkingCap-Qwen3.6-27B-Q4_K_M-GGUF:ThinkingCap-Qwen3.6-27B-Q4_K_M.gguf` | 16 GB |
| `hf.co/HauhauCS/Gemma4-12B-QAT-Uncensored-HauhauCS-Balanced:Gemma4-12B-QAT-Uncensored-HauhauCS-Balanced-Q4_K_M.gguf` | 7.6 GB |
| `hf.co/HeYujie/Qwen3.5-27B-abliterated-GGUF:Q4_K_M` | 16 GB |
| `hf.co/MaralGPT/MaralGPT-Mythos-9B-2606-GGUF:MaralGPT-Mythos-9B-2606-Q4_K_M.gguf` | 5.6 GB |
| `hf.co/TrevorJS/gemma-4-12B-it-uncensored-GGUF:gemma-4-12B-it-uncensored-Q4_K_M.gguf` | 7.4 GB |
| `hf.co/TrevorJS/gemma-4-26B-A4B-it-uncensored-GGUF:gemma-4-26B-A4B-it-uncensored-Q4_K_M.gguf` | 16 GB |
| `hf.co/TrevorJS/gemma-4-31B-it-uncensored-GGUF:gemma-4-31B-it-uncensored-Q4_K_M.gguf` | 18 GB |
| `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf-ctx32k` | 20 GB |
| `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M-ctx32k` | 48 GB |
| `hf.co/bartowski/nvidia_Nemotron-3-Nano-30B-A3B-GGUF:Q4_K_M` | 24 GB |
| `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M-ctx32k` | 21 GB |
| `hf.co/huihui-ai/Huihui-Ornith-1.0-9B-abliterated-MTP-GGUF:ornith-9b-mtp-kl-Q4_K_M.gguf` | 6.9 GB |
| `hf.co/migtissera/Tess-4-27B-GGUF:Tess-4-27B-Q4_K_M.gguf` | 17 GB |
| `hf.co/mradermacher/DeepHat-V1-7B-GGUF:Q4_K_M` | 4.7 GB |
| `hf.co/mradermacher/Devstral-Small-2-24B-Instruct-abliterated-GGUF:Q4_K_M` | 14 GB |
| `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx32k` | 5.1 GB |
| `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx32k` | 14 GB |
| `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx8k` | 25 GB |
| `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL-ctx32k` | 22 GB |
| `huihui_ai/qwen3.5-abliterated:9b-ctx32k` | 6.6 GB |
| `huihui_ai/tongyi-deepresearch-abliterated:latest-ctx32k` | 18 GB |
| `laguna-xs.2:Q4_K_M-ctx32k` | 23 GB |
| `maralgpt-9b-ctx16k:latest` | 5.6 GB |
| `phi4-mini-reasoning:latest-ctx8k` | 3.2 GB |
| `phi4-reasoning:plus-ctx16k` | 11 GB |
| `qwen3-coder-next:latest-ctx32k` | 51 GB |
| `qwen36-abliterated-27b-ctx16k:latest` | 17 GB |
| `supergemma4-26b-uncensored:Q4_K_M-ctx32k` | 16 GB |
| `tess-4-27b-ctx16k:latest` | 17 GB |
| `thinkingcap-27b-ctx16k:latest` | 16 GB |

To delete: `ollama rm <model>` for each row above. Re-verify none are loaded
(`curl -s http://localhost:11434/api/ps`) and none overlap any in-progress bench/ablation run
before deleting.
