# Model fleet inventory — pass 2 — 2026-11-15

## Scope and evidence boundary

This is a read-only inventory of the repository config and the visible contents of `/Volumes/data01/hf-cache` and `/Volumes/data01/omlx-models`. Directory sizes are `du -sk` KiB. The task reports that the orchestrator already removed the Arete Ollama tag and six empty HF-cache stubs; those seven identities are recorded as closed below. The live Ollama list, model status, loaded processes, and the pipeline were not queried from this worker session.

“In use” follows the task definition: a production backend id, alias, fallback, workspace/variant, or configured bench workspace counts; a service loader counts by model identity even when the library downloads lazily. A model mentioned only in `config/model_inventory.snapshot`, `config/MODEL_CATALOG.md`, `config/promptfoo/*`, tests, documentation, archives, or old results does not count. A `-ctxNk` Ollama tag keeps its base weights. The `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` candidate is retained.

The Wiki fact-unit tools were not available to this worker. Discovery used the task-named config, report, service code, and Compose files. Service code proves the configured loader path, not current process residency; the latter needs orchestrator evidence.

## Unused host HF-cache snapshots

These 25 visible directories have no active model id, alias target, direct oMLX symlink, or service loader for that exact Hub identity. Their only repository hits are metadata, model-catalog/list entries, tests, documentation, or historical records. The current directory set totals about 1.25 MiB by `du`; no cleanup is proposed for that small reclaim. The unrelated active GGUF/Ollama or MLX identity with a similar model-family name does not make this HF snapshot active.

| HF-cache identity | Size | Why unused |
|---|---:|---|
| `models--Qwen--Qwen3-1.7B` | 12 KiB | No configured route, direct link, or runtime loader for `Qwen/Qwen3-1.7B`. |
| `models--Qwen--Qwen3-4B` | 12 KiB | No configured route, direct link, or runtime loader for `Qwen/Qwen3-4B`. |
| `models--Qwen--Qwen3-8B` | 20 KiB | Only base-model metadata/list references; the routed DeepSeek/Qwen3 GGUF is a different Hub identity. |
| `models--Youssofal--Ternary-Bonsai-2-27B-MTPLX-Optimized-Speed` | 4 KiB | No configured route, direct link, or runtime loader for this repo. |
| `models--ddalcu--MiMo-V2.6-Distill-Qwen-9B-MLX-Serve-4bit` | 4 KiB | No configured route, direct link, or runtime loader for this repo. |
| `models--mlx-community--Phi-4-mini-reasoning-4bit` | 4 KiB | The configured Phi reasoning seat is a separate Ollama tag; this MLX repo is not routed. |
| `models--mlx-community--Qwen2.5-0.5B-Instruct-4bit` | 4 KiB | No configured route, direct link, or runtime loader for this repo. |
| `models--nativ-community--MiMo-V2.6-Distill-Qwen-9B-MLX-4bit` | 4 KiB | No configured route, direct link, or runtime loader for this repo. |
| `models--orcarouter--OrcaCyber-Nano-1.0` | 4 KiB | Model-card/expectation metadata only; no production route or runtime loader. |
| `models--poolside--Laguna-XS.2-speculator.dflash` | 4 KiB | No configured draft-model route, direct link, or runtime loader. |
| `models--prince-canuma--Kokoro-82M` | 1,028 KiB | The host TTS loader uses `mlx-community/Kokoro-82M-bf16`, a different Hub identity. |
| `models--prism-ml--Bonsai-1.7B-unpacked` | 12 KiB | No configured route, direct link, or runtime loader for this repo. |
| `models--prism-ml--Bonsai-27B-mlx-1bit` | 4 KiB | No configured route, direct link, or runtime loader for this repo. |
| `models--prism-ml--Bonsai-4B-unpacked` | 12 KiB | No configured route, direct link, or runtime loader for this repo. |
| `models--prism-ml--Bonsai-8B-unpacked` | 8 KiB | No configured route, direct link, or runtime loader for this repo. |
| `models--prism-ml--Ternary-Bonsai-1.7B-unpacked` | 12 KiB | No configured route, direct link, or runtime loader for this repo. |
| `models--prism-ml--Ternary-Bonsai-2-27B-mlx-2bit` | 4 KiB | No configured route, direct link, or runtime loader for this repo. |
| `models--prism-ml--Ternary-Bonsai-4B-unpacked` | 12 KiB | No configured route, direct link, or runtime loader for this repo. |
| `models--prism-ml--Ternary-Bonsai-8B-mlx-2bit` | 4 KiB | No configured route, direct link, or runtime loader for this repo. |
| `models--prism-ml--Ternary-Bonsai-8B-unpacked` | 8 KiB | No configured route, direct link, or runtime loader for this repo. |
| `models--tencent--AuK` | 4 KiB | This is distinct from `AuK-Flash`; neither has a production route or service loader. |
| `models--unsloth--Qwen3-1.7B-GGUF` | 24 KiB | No Ollama backend id or service loader routes this HF-cache copy. |
| `models--unsloth--Qwen3-4B-GGUF` | 24 KiB | No Ollama backend id or service loader routes this HF-cache copy. |
| `models--unsloth--Qwen3-8B-GGUF` | 24 KiB | No Ollama backend id or service loader routes this HF-cache copy. |
| `models--unsloth--Qwen3.6-27B-GGUF` | 28 KiB | Historical WFE backfill references only; no production route or runtime loader. |

## In-use identities and references

| Engine / identity | Referring config or service | Evidence in this checkout |
|---|---|---|
| Ollama registered tags, aliases, and fallbacks | `config/backends.yaml`; workspace and variant hints in `config/portal.yaml`; bench seats in `config/bench_workspaces.yaml` | Structured config entries count as use by task definition. This is not a claim that each tag is currently installed. Derived context tags share their base weights. |
| `glm-4.7-flash:Q4_K_M-ctx24k` | `auto-reasoning::math`; `config/backends.yaml`; Modelfile in `config/modelfiles/` | New 24K math-seat tag; WFE decision remains `wfe_math_20261018d`. |
| `glm-4.7-flash:Q4_K_M-ctx24k-agentic` | `auto-coding::glm-coder`; `config/backends.yaml`; Modelfile in `config/modelfiles/` | 24K coding-seat tag, preserving the agentic sampling arm; re-fit from 32K after the live load guard refused the 32K projection (2026-11-15). |
| `glm-4.7-flash:Q4_K_M-ctx64k[-agentic]` and base `glm-4.7-flash:Q4_K_M` | `config/backends.yaml`; catalog history and other registered uses | Retained with their base identities; 64K variants are no longer selected by the two seats. |
| `DeepSeek-R1-0528-Qwen3-8B-4bit` — 4.30 GiB | oMLX symlink `/Volumes/data01/omlx-models/DeepSeek-R1-0528-Qwen3-8B-4bit`; `config/backends.yaml` | Direct symlink into `models--mlx-community--DeepSeek-R1-0528-Qwen3-8B-4bit`. |
| `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` — 16.57 GiB | oMLX symlink; `config/engine_artifacts_20261114.yaml` | Explicitly retained as the seat candidate under measurement. |
| `Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit` — 18.19 GiB | oMLX symlink; `config/backends.yaml` | Direct symlink to the dawncr0w cache. |
| `Qwen3.8-27B-DFlash2` — 12 KiB | oMLX symlink; `config/backends.yaml`; `config/personas/qwen38coder_dflash.yaml` | Registered speculative-decoding draft helper; keep with its target model. |
| `Tongyi-DeepResearch-30B-A3B-abliterated-4bit` — 16.02 GiB | oMLX symlink; `config/backends.yaml` | Direct symlink to the jurejaklic cache. |
| `VulnLLM-R-7B-4bit` — 4.01 GiB | oMLX symlink; `config/backends.yaml` | Direct symlink to the MLX cache. |
| `gemma-4-26b-a4b-it-QAT-4bit` — 14.57 GiB | oMLX symlink; `config/backends.yaml` | Direct symlink to the MLX QAT cache. |
| `granite-4.1-30b-4bit` — 16.81 GiB | oMLX symlink; `config/backends.yaml` | Direct symlink to the MLX cache. |
| `Huihui-Qwen3.5-9B-abliterated-mlx-4bit` — 4.72 GiB | oMLX symlink; `config/backends.yaml` | Direct symlink to the huihui-ai cache. |
| `FLUX.2-klein-4B` — 14.88 GiB | MFLUX `klein` route in `portal/modules/media/tools/mflux_mcp.py` | MFLUX alias resolves to this HF-cache model family. |
| `Qwen-Image-2512` — 53.74 GiB | MFLUX `qwen-image` route | `models--Qwen--Qwen-Image-2512`. |
| `Qwen-Image-Edit-2509` — 53.74 GiB | MFLUX `qwen-image-edit` route | `models--Qwen--Qwen-Image-Edit-2509`. |
| `Z-Image-Turbo` — 30.59 GiB | MFLUX `z-image` route | `models--Tongyi-MAI--Z-Image-Turbo`. |
| `mlx-community/Kokoro-82M-bf16` — 339 MiB | Host speech service `scripts/mlx-speech.py` | Default Kokoro TTS model; maps to `models--mlx-community--Kokoro-82M-bf16`. |
| `mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit` — 2.87 GiB | Host speech service | Custom voice model path in `scripts/mlx-speech.py`. |
| `mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit` — 2.87 GiB | Host speech service | Voice-design model path in `scripts/mlx-speech.py`. |
| `mlx-community/higgs-audio-v2-3B-mlx-q8` — 5.77 GiB | Host speech service | Clone model default in `scripts/mlx-speech.py`. |
| `mlx-community/higgs-audio-v2-tokenizer` — 768 MiB | Host speech service / Higgs Audio dependency | Runtime tokenizer identity; maps to the closeout entry `models--mlx-community--higgs-audio-v2-tokenizer`. |
| `mlx-community/Qwen3-ASR-1.7B-8bit` — 2.30 GiB | Host speech service on `:8918` | `QWEN3_ASR_MODEL` in `scripts/mlx-speech.py`. |
| `mlx-community/parakeet-tdt-0.6b-v3` — 2.34 GiB | Host transcription service on `:8924` | `PARAKEET_MODEL` in `scripts/mlx-transcribe.py`. |
| `mlx-community/diar_sortformer_4spk-v1-fp32` — 471 MiB | Host transcription service on `:8924` | `DIARIZE_MODEL` in `scripts/mlx-transcribe.py`. |
| `google/embeddinggemma-2` — 80 KiB in this host cache | Host embedding service `scripts/eg2-embedding-server.py` | `MODEL_ID` default; cache path is not proven complete from this directory size. |
| `mlx-community/Qwen3-VL-Embedding-2B-mxfp8` — 2.43 GiB | Host VL retrieval service `scripts/vl-retrieval-server.py` | `EMBED_MODEL` default. |
| `mlx-community/Qwen3-VL-Reranker-2B-mxfp8` — 2.43 GiB | Host VL retrieval service | `RERANK_MODEL` default. |
| `docling-project/docling-layout-heron` — 164 MiB in host cache | Documents/RAG service `portal/modules/research/tools/rag_mcp.py` | `DocumentConverter()` lazily loads Docling layout models by library identity. |
| `docling-project/docling-models` — 342 MiB in host cache | Documents/RAG service | Model repository used by Docling's converter. |
| `mobiuslabsgmbh/faster-whisper-large-v3-turbo` — 1.51 GiB in host cache | Whisper MCP on `:8915` | `WhisperModel("large-v3-turbo")` maps to this exact repo in the installed `faster_whisper/utils.py`. |
| `BAAI/bge-reranker-v2-m3` — 20 KiB in host cache | Open WebUI RAG reranker in `deploy/portal-5/docker-compose.yml` | `RAG_RERANKING_MODEL`; model identity is configured even though this host cache directory is only metadata-sized. |
| `CIRCL/vulnerability-severity-classification-roberta-base` — 956 MiB in host cache | Security MCP on `:8919` | `AutoTokenizer` and `AutoModelForSequenceClassification` in `portal/modules/security/tools/security_mcp.py`. |
| `sentence-transformers/all-MiniLM-L6-v2` — 700 KiB in host cache | RAG chunker | Default `DOCLING_TOKENIZER` in `portal/platform/retrieval/chunking.py`. |
| Active configured oMLX identities with metadata-sized local HF snapshots | `config/backends.yaml`, aliases, and routed workspace hints | Keep identities such as the configured Laguna, Mistral, Gemma, Huihui, and Unsloth MLX models. Their matching host cache directories are only 4–28 KiB and remain on HOLD for path/completeness checks. |

## HOLD

| Identity or path | Reason |
|---|---|
| Live Ollama installed tags and sizes | The worker contract assigns live inventory to the orchestrator. `config/model_inventory.snapshot` is a list, not proof of current installation. Arete is recorded as removed from the task report; no other Ollama deletion is proposed without the live inventory. |
| Host HF-cache copies for Docker-loaded identities | Compose uses `portal5-hf-cache` for Whisper/TTS and `security-hf-cache` for the CIRCL model; the Docling/RAG loader also has no host HF-cache bind shown. The model identities are in use, but those local copies are not proven to be the running containers' cache paths. |
| Metadata-sized HF directories for configured oMLX identities | A `backends.yaml` id or alias makes the model identity in use. Several local snapshots are only 4–28 KiB; do not remove or call those complete without checking the live oMLX model path and served identity. |
| `google/embeddinggemma-2`, `BAAI/bge-reranker-v2-m3`, and `sentence-transformers/all-MiniLM-L6-v2` host cache copies | Service code/config uses the identities, but the local folders (80 KiB, 20 KiB, 700 KiB) do not establish that their complete weights are present or mounted into the runtime. |
| `auto-reasoning::math` and `auto-coding::glm-coder` live fit and responses | Context sizing below is calculated from the task's supplied measurement. This worker lane lacks `router/seat_fit.py` and live seat-fit access; the actual seat-fit route and Pipeline responses remain orchestrator checks. |

## GLM seat sizing

The task's live report gives 17.71 GiB weights, a 1.25 multiplier, and 31.21 GiB q8_0 KV at 65,536 context against a supplied 40–42 GiB empty-host budget. The 2026-11-15 22:0xZ live refusal measured the effective budget lower: 37.6 GiB (oMLX headroom 39.6 + idle Ollama 0.0 − margin 2). Re-running load_guard's sizing (`_estimate_ollama_need`, the `seat_fit()` per-seat path) on the real on-disk GGUF geometry (47 layers, 20 KV heads, 256-dim keys/values, q8_0) reproduces the refusal (32K → 37.75 GiB) and gives:

| Seat | Context | Estimated weight + KV | Margin to 37.6 GiB live headroom | Config |
|---|---:|---:|---:|---|
| `auto-reasoning::math` | 24,576 | 22.14 + 11.70 = 33.85 GiB | +3.75 GiB | `glm-4.7-flash:Q4_K_M-ctx24k`, 12,288 output tokens |
| `auto-coding::glm-coder` | 24,576 | 22.14 + 11.70 = 33.85 GiB | +3.75 GiB | `glm-4.7-flash:Q4_K_M-ctx24k-agentic`, 16,384 output tokens |

Math keeps its established 24,576 context window. Coding re-fits to the same window after the 32K tag was refused live: it keeps the dedicated agentic arm and drops the output cap 24,576 → 16,384 so prompt + output fit with the designed 8K prompt room; 64K no longer fits the budget. The re-fit row is computed with the guard's own sizing function against the real weights blob, not fresh live `seat_fit()` output — the live seat fit remains an orchestrator check.

## Closed removals and removal script

The closeout register marks the orchestrator-reported removals `REMOVED_CLOSED`: Arete plus the six empty HF stubs `models--Qwen--Qwen2.5-Omni-3B`, `models--ibm-granite--granite-switch-4.1-3b-preview`, `models--tencent--AuK-Flash`, `models--Jiunsong--supergemma4-26b-uncensored-mlx-4bit-v2`, `models--Youssofal--MiMo-V2.6-Qwen-9B-MTPLX-Optimized-Speed`, and `models--Youssofal--Qwen3.6-27B-MTPLX-Optimized-Speed`. The four service identities wrongly listed as removable in pass 1 are restored to `INTEGRATED`.

`scripts/remove_unused_models_20261115.sh` is dry-run by default and rechecks each of those seven prior targets immediately before any action. It does not target the 25 metadata-sized unused snapshots above; their combined `du` size is only 1.25 MiB. No model was deleted by this worker.
