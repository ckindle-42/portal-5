# EG2 runtime measurements — 2026-10-07 (arm64, M-series, bf16 on MPS)

Arms: **A** = `scripts/eg2-embedding-server.py` (:8946, sentence-transformers 6.1.0 / transformers 5.19.0 / torch 2.14.1, bf16 MPS, own venv `~/.portal5/eg2-venv`); **O** = Ollama 0.40.0 `embeddinggemma-2:740m-mxfp8` (`mlx` runner, `/api/embed`, client-applied prefixes via `contract.format_text`). Scripts: `tests/benchmarks/eg2_runtime_measure.py`, `tests/benchmarks/eg2_runtime_parity.py`.

## Runtime
| | A (:8946) | O (Ollama) |
|---|---|---|
| Cold start → `/ready` (process start + model load + probes) | ~3.5 s (load 1.3 s, weights cached) | resident 1.3 GB, keep_alive set per request |
| Text items/s, batch 8 / 32 / 64 | 127 / 189 / 232 | 84 / 98 / 55 |
| Image (512²) single item, warm | 0.29 s | 0.22 s |
| Audio (3 s speech) single item, warm | 0.078 s | 0.072 s |
| Video (2 s, 320x240) single item, warm | 0.27 s | **rejected** (`input.video not supported`) |
| RSS | full 1264 MB, text-only 869 MB (`EG2_MODALITIES=text`) | 1.3 GB (`ollama ps`) |

Arm A text throughput is ~3.4x the Arm A (MLX Qwen3) reference of ~55 items/s @ b32 recorded in `docs/BULLY_BUILD_PROGRESS.md` SA3.2. Co-resident check: `ollama ps` shows the pinned router (5.4 GB, Forever) and EG2-on-Ollama (1.3 GB) loaded together with no eviction; the :8946 service ran beside both (free pages ≈ 1.5M x 16 KB at snapshot).

## Parity (Ollama mxfp8 vs :8946 bf16 reference)
text document / query prefixed (80 each): mean cos 0.9992, min 0.9984 / 0.9982 · top-1 retrieval agreement 20/20 · images (12): mean 0.9997, min 0.9996 · audio (5 TTS clips): mean 0.9993, min 0.9991 · MRL dims 512/256/128 (docs): mean 0.9993 / 0.9994 / 0.9996. mxfp8 does not drift, so `740m-bf16` was not needed.

## Phase 2.4 installed-source findings
* `_to_st_input` image form vs sentence-transformers' bare-PIL form: cos 0.9995 — no change to `_to_st_input`.
* `config_kwargs` encoder skipping works: text-only RSS 869 MB vs 1264 MB full.
* bf16 on MPS: `/ready` NaN-free, prefix asymmetry cos 0.9655, MRL renormalised — no fp32 fallback needed.
* Missing runtime deps found by running (not on the card): `torchvision` (processor import), `librosa` + `soundfile` (audio), `torchcodec` (video). Added to `scripts/eg2-venv-setup.sh` (`sentence-transformers[audio,video,image]`, `torchvision`, `torchcodec`).
* FINDING: the first `/ready` hang (threads blocked in `open()` on `/Volumes/data01`, ~0% CPU) was macOS TCC denying `kTCCServiceSystemPolicyAllFiles` (`authValue=0`) to the brand-new cpython-3.12.12 interpreter created by `uv venv --python 3.12` (tccd log 11:18:43 and 11:24:34 local, pid 8119). TCC keys the grant to the interpreter binary. The operator approved python3.12 on 2026-10-07; the venv stays on 3.12 and the model lives in the standard data01 cache. (Rebuilding on the granted cpython-3.13.12 was also verified to work: /ready 200, text 194 items/s @ b32.) My first workaround (a `$HOME` HF cache) was reverted.

## G-RUNTIME input
Recommendation: **split** — Ollama `/api/embed` for text/image/audio (Rule-8 tier, same vectors to 0.999, no extra service RAM beyond 1.3 GB) and keep `:8946` for video only; :8946 alone is also viable (faster on text batches, 3.4x the old reference). Ollama's throughput falls at batch 64 (55/s); :8946 does not. Decision is the operator's at Phase 4.
