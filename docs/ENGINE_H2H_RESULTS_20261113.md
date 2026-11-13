# Engine head-to-head — live results, 2026-11-13

Host: M4 Pro, 64 GB, macOS 27.2, Portal stack **up** (production conditions), no Pipeline traffic
in any cell window (checked in the Pipeline log), swap growth 0 in every reported cell.
Harness: `tests/benchmarks/bench_engine_h2h.py` + `engine_h2h.yaml`; raw rows, engine logs and
driver logs in `/Volumes/data01/portal5_data/engine_h2h_20261113/`.

Same request on every engine: identical prompt, sampling, thinking off, 400 output tokens
(all produced), 6k-token prefill file. **Decode** = single-stream median tok/s. **4-wide** =
aggregate tok/s with 4 concurrent requests. **Prefill** = tok/s on the 6k prompt.
**Mem** = resident GB (process footprint; Ollama by system free-memory drop, see notes).

Versions: Ollama 0.40.16 · oMLX 0.7.3 · mlx-serve 26.11.2 · Rapid-MLX 1.0.2 · vllm-mlx 0.6.0 ·
mlxcel 0.8.1 · vLLM Metal 0.33.0 · Splash 1.6.1 · mlx_lm 0.31.3.

## Gemma 4 26B-A4B QAT (auto-daily / hunt-reasoning seat)

| Engine | Decode | 4-wide | Prefill | Mem |
|---|---:|---:|---:|---:|
| mlx-serve | **76.3** | 79.5 | **796** | 17 |
| vllm-mlx | 70.8 | 124.7 | 619 | 18 |
| Rapid-MLX | 70.4 | 101.5 | 712 | 18 |
| Ollama (prod, 1 slot) | 69.7 | 68.5 | 654 | ~16 |
| vLLM Metal | 68.7 | **130.8** | 479 | n/m |
| mlxcel | 67.4 | 125.8 | 763 | 20 |
| mlx_lm.server | 63.7 | 127.1 | 658 | 19 |
| oMLX (prod) | 41.5 | 111.7 | 597 | 16 |

## Qwen3.8-27B dense (coding / reasoning seats)

| Engine | Mode | Decode | 4-wide | Prefill | Mem |
|---|---|---:|---:|---:|---:|
| Splash | DFlash2 | **34.2** | 39.8 | **255** | n/m |
| mlx-serve | DFlash2 | 33.8 | 33.3 | 130 | 19 |
| oMLX (prod) | MTP (oQ4e-mtp) | 27.5 | **42.0** | 124 | 19 |
| Rapid-MLX | DFlash2 | 22.6 | 21.8 | 123 | 21 |
| mlx-serve | plain | 16.0 | 46.2 | 128 | 17 |
| Rapid-MLX | plain | 15.2 | 38.8 | 120 | 20 |
| oMLX | plain | 14.1 | 36.3 | 125 | 17 |
| mlxcel | plain / DFlash2 | 14.0 / 14.0 | 36.5 | 109 | 24 |
| mlx_lm.server | plain | 13.9 | 38.9 | 120 | 20 |
| vllm-mlx | plain | 13.4 | 36.2 | 120 | 18 |
| Ollama (prod, 1 slot) | plain | 11.8 | 12.2 | 109 | ~17 |
| vLLM Metal | — | not supported (Qwen3.8 MLX checkpoint: "Unrecognized image processor") | | | |

## Nemotron 3.5 Lightning 30B-A3B (auto-daily default)

| Engine | Mode | Decode | 4-wide | Prefill | Mem |
|---|---|---:|---:|---:|---:|
| vllm-mlx | plain | **71.4** | 141.2 | 734 | 19 |
| Rapid-MLX | plain | 70.9 | 124.1 | 756 | 18 |
| mlx-serve | plain | 69.1 | 68.7 | 750 | 19 |
| mlx_lm.server | plain | 67.0 | **153.8** | 746 | 20 |
| vLLM Metal | plain | 65.5 | 133.7 | 691 | n/m |
| Ollama (prod, 1 slot) | plain | 56.6 | 56.1 | 747 | 22.9 |
| oMLX | MTP (prod setting) | 50.0 | 124.3 | 747 | 21 |
| oMLX | plain (MTP off) | 45.1 | 124.8 | 785 | 18 |
| mlxcel | — | not supported (oQ4e quant layout) | | | |
| MTP on mlx-serve / vllm-mlx / Rapid-MLX | — | no gain / refused: these engines do not read this checkpoint's MTP weights | | | |

## What the numbers say
- **oMLX is the slowest single-stream engine on Gemma and Nemotron** (41.5 and 45–50 tok/s
  against ~70 elsewhere, same weights). On Gemma it runs the checkpoint on its VLM engine (the
  config carries a vision tower). It batches well (4-wide 112–125), which is what the hunt seat uses.
- **Speculative decoding is the only big lever, and only on Qwen3.8 dense:** DFlash2 on Splash or
  mlx-serve ≈ 34 tok/s (2.9× Ollama), oMLX MTP 27.5. On the MoE seats spec decoding adds ~0–11%.
- **Ollama with `OLLAMA_NUM_PARALLEL=1` does not scale** (4-wide = single), by design; its
  single-stream numbers are competitive on the MoE seats, worst on Qwen3.8.
- **mlx-serve serialises** (4-wide ≈ single on Gemma/Nemotron; "slot serial" in its log).
- The Aug-2026 comment in `backends.yaml` (Nemotron oMLX MTP 70 tok/s vs Ollama 53) no longer
  holds on oMLX 0.7.3: oMLX MTP 50.0 vs Ollama 56.6 today, MTP acceptance 69–76%.

## Setup defects found and handled during the run (not in the numbers above)
- oMLX launchd label was stale in the registry (`homebrew.mxcl.omlx` → `com.portal5.omlx`); oMLX
  now requires its API key and the harness sent none. Both fixed.
- oMLX "plain" for Nemotron first ran **with MTP on** (production `mtp_enabled: true`; the harness
  does not disable it for plain). Re-run with MTP off; both rows reported and labelled.
- Splash "plain" passes the DFlash2 drafter (registry `splash_extra`), so Splash is reported as
  DFlash2 only; no drafter-free Splash number exists.
- MLX-dir preflight verdict REVIEW = deliberate Gemma post-tool-anchor template patch (affects only
  turns after a tool response; the speed prompts have none).
- vLLM Metal at the vendor's `--gpu-memory-utilization 0.7` pushed swap to 7.4 GB beside the stack
  (rule 3 tripped); re-run at 0.45 with `--served-model-name` (without it vLLM serves the path → 404).
- Memory: Ollama 0.40 runs a child `llama-server` whose Metal-wired weights are outside its process
  footprint and (for Gemma) outside `/api/ps` (0.69 GiB reported); Ollama memory above is the
  system free-memory drop on load. Splash / vLLM Metal "n/m": their footprint reading also misses
  child processes.
- Not measured: tool-call quality, long-context behaviour, stability over hours.
