# Memory canary findings — 2026-11 window upgrades (lane/memory-canary)

Companion to `coding_task/MEMORY_CANARY_BRIEF.md`. Runner: `scripts/memory_canary.py`
(orchestrator runs it live). Parsing tests: `tests/unit/test_memory_canary_parsing.py`.

## Method

- Window-growth census: parsed both revisions of `config/portal.yaml` (base `4a76752e7`,
  2026-11-17 — the last commit before the `--since=2026-11-18` window) with PyYAML and
  diffed every workspace + variant `(model_hint, context_limit, predict_limit)`; persona
  roster from `git diff 4a76752e7..HEAD -- config/personas/`.
- KV is computed from the **real per-layer architecture**, not a rule of thumb:
  GGUF headers parsed from the actual blobs in `/Volumes/data01/ollama/models`
  (manifests + manifests-v2 → `sha256-*` blob → metadata section), MLX `config.json`
  from `/Volumes/data01/omlx-models` (symlinks resolved into hf-cache). Per-layer
  `head_count_kv` arrays, sliding-window patterns, `*_swa` head dims and
  `full_attention_interval` are all honoured.
- Cross-check: every Ollama row was also run through the repo's own
  `load_guard._ollama_kv_bytes` on the same metadata (`lg-cross` column). Agreement
  everywhere it can run; the disagreements are finding F1.
- KV cache element size: Ollama = **q8_0, 1.0625 B/element** (the live llama-server
  process was observed with `--cache-type-k q8_0 --cache-type-v q8_0 --flash-attn on`;
  matches load_guard's `OLLAMA_KV_CACHE_TYPE` default). oMLX = **bf16, 2 B/element**
  (`dtype: bfloat16` in every checkpoint config). Weights = GGUF blob size / safetensors
  dir size on this host.

## Task 1 — seats whose window grew (workspace level)

KV@baked = what the engine actually allocates for the deployed tag's baked `num_ctx`;
KV@seat = at the seat's declared `context_limit` (differs only where the tag bakes more).

| seat | model (serving engine) | old→new ctx | weights | KV@baked | KV@seat |
|---|---|---|---|---|---|
| auto-audio | gemma4:12b-it-qat-ctx16k (Ollama) | 8192→16384 | 6.50 GiB | 0.30 GiB | 0.30 GiB |
| auto-audio::music | lfm2.5:8b-ctx16k (Ollama) | 8192→16384 | 4.80 GiB | 0.10 GiB | 0.10 GiB |
| auto-compliance | Qwen3.8-27B-oQ4e-mtp (oMLX; hint Q4_K_M-ctx96k) | 32768→65536 | 15.81 GiB | 4.14 GiB | 4.14 GiB |
| auto-daily | bartowski Nemotron-3.5-Lightning-30B-A3B Q4_K_M-ctx32k (Ollama) | 16384→32768 | 23.73 GiB | 0.12 GiB | 0.12 GiB |
| auto-daily::inkling (NEW) | inkling-2-mini:ctx256k (Ollama **mlx runner**) | —→262144 | 18.80 GiB | 4.08 GiB | 4.08 GiB |
| auto-documents | gemma4:26b-a4b-it-qat-ctx32k (Ollama) | 16384→32768 | 13.45 GiB | 0.44 GiB | 0.44 GiB |
| auto-general-uncensored | Huihui-Qwen3.6-35B-A3B-abliterated q4_K_M-ctx32k (Ollama) | 8192→32768 | 19.71 GiB | 0.33 GiB | 0.33 GiB |
| auto-general-uncensored::creative | Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit (oMLX; GGUF failover Q4-ctx24k) | 8192→24576 | 18.17 GiB | 0.53 GiB | 0.53 GiB |
| auto-research | Nex-N2-mini UD-Q4_K_M-ctx32k (Ollama) | 16384→32768 | 20.60 GiB | 0.33 GiB | 0.33 GiB |
| auto-security (+blueteam-council/-orchestrated) | Inkling-2-Mini-oQ4e-mtp (oMLX) | 8192→(no limit declared; 64k assumed) | 15.69 GiB | 1.08 GiB @64k | — |
| auto-security::uncensored / ::purpleteam-deep | Inkling-2-Mini-abliterated-oQ4e-mtp (oMLX) | 8192/65536→262144 | 15.69 GiB | 2.08 GiB @131k | 4.08 GiB @262k |
| auto-security::redteam / ::purpleteam | huihui_ai/qwen3.5-abliterated:9b-ctx64k (Ollama) | 8192→32768 | 6.14 GiB | **1.06 GiB (baked 64k)** | 0.53 GiB |
| auto-security::blueteam / ::security-tool-granite41-8b / security-reviewer | granite4.1:8b-ctx16k (Ollama) | 8192→16384 | 4.98 GiB | 1.33 GiB | 1.33 GiB |
| auto-vision | qwen3-vl:32b-ctx16k (Ollama) | 8192→16384 | 19.47 GiB | 2.12 GiB | 2.12 GiB |
| auto-vision::gemma_vision | gemma4:31b-it-qat-ctx16k (Ollama) | 8192→16384 | 16.44 GiB | 1.08 GiB | 1.08 GiB |
| tools-specialist | unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit (oMLX; hint UD-Q4_K_XL-ctx96k) | 8192→32768 | 20.15 GiB | 0.68 GiB | 0.68 GiB |

Architecture notes behind the numbers: Qwen3.8-27B / Qwen3.6-27B / Qwen3.6-35B-A3B are
`qwen3_5(_moe)` **hybrid linear-attention** models — only every 4th layer keeps a growing
KV cache (16/64 or 10/40 full layers, kvh 4 or 2, head_dim 256, plus a constant fp32
linear state ≈151/63 MiB). Inkling-2-Mini keeps 4 global attention layers (kvh 8, hd 128)
and 20 sliding-window(1024) layers → KV grows only ~16 KiB/token. Nemotron-3.5-Lightning
is mostly SSM: 23.7 GiB of weights but 0.12 GiB KV at 32k. gemma4 is per-layer GQA + SWA
(head_count_kv arrays, `key_length_swa` 256 on the 1024-window layers).

### Persona roster (config/personas/, 63 preferred_models tag upgrades)

| tag change | personas | weights | KV@baked |
|---|---|---|---|
| omnicoder2:9b-q4_k_m-ctx8k → portal5/omnicoder2-9b:q4_K_M-ctx256k | 31 | 5.24 GiB | **4.25 GiB** (q8_0, 8 full layers × kvh4 × hd256) |
| huihui_ai/Qwen3.6-abliterated:27b-ctx8k → -ctx32k | 8 | 16.22 GiB | 1.06 GiB |
| qwen3-vl:32b-ctx8k → -ctx16k | 6 | 19.47 GiB | 2.12 GiB |
| huihui_ai/qwen3.5-abliterated:9b-ctx8k → 9b-ctx64k | 5 | 6.14 GiB | 1.06 GiB |
| gemma4:26b-a4b-it-qat-ctx8k → -ctx32k | 4 | 13.45 GiB | 0.44 GiB |
| HauhauCS-Aggressive Q4-ctx8k → Q4-ctx24k | 4 | 18.17 GiB (oMLX) | 0.53 GiB |
| VulnLLM-R-7B q4_K_M-ctx8k → -ctx32k | 3 | 4.36 GiB | 0.93 GiB |
| granite4.1:8b-ctx8k → -ctx16k | 2 | 4.98 GiB | 1.33 GiB |

The single biggest sleeper is **omnicoder2 at 256k**: 31 coding personas now prefer a tag
whose baked window allocates ~4.25 GiB of KV on top of 5.24 GiB weights on Ollama.

## Task 2 — heaviest realistic back-to-back co-residency pairs

Totals are weights + KV at the seat's window (what each engine must hold resident):

| pair | engine A ↔ B | total resident |
|---|---|---|
| auto-compliance @64k (19.95 GiB) × auto-daily @32k (23.85 GiB) | oMLX ↔ Ollama | **43.8 GiB** |
| auto-daily::inkling @256k (22.88 GiB) × auto-compliance @64k (19.95 GiB) | Ollama ↔ oMLX | **42.8 GiB** |
| auto-vision @16k (21.59 GiB) × tools-specialist @32k (20.83 GiB) | Ollama ↔ oMLX | **42.4 GiB** |
| auto-general-uncensored @32k (20.04 GiB) × tools-specialist @32k (20.83 GiB) | Ollama ↔ oMLX | **40.9 GiB** |
| auto-security::purpleteam-deep @131k (17.77 GiB) × auto-documents @32k (13.89 GiB) | oMLX ↔ Ollama | 31.7 GiB |

Against the 58.88 GiB oMLX cap / 64 GB host with two engines co-resident, the top four
pairs leave little room for a third admission — these are exactly the shapes that produce
mid-prefill 507s. Note: the brief said "resident oMLX daily seat"; per config auto-daily
is **Ollama** (bartowski Nemotron GGUF, no oMLX alias) — pair 1 is the same co-residency
either way. All five pairs are `DEFAULT_PAIRS` in the runner (`--list` shows them).
Inkling seats are canaried at 131k, not their declared 262k, to keep prefill time sane;
raise `Seat.context_limit` if the orchestrator wants the full-window probe.

## Findings beyond the brief's list (reported, not fixed)

- **F1 — load_guard over-counts KV 4× for scalar-kvh hybrid GGUF tags.**
  `_ollama_kv_bytes` honours per-layer `head_count_kv` arrays but not
  `full_attention_interval` when kvh is scalar: Huihui-35B-ctx32k and Nex-N2-ctx32k
  estimate 1.33 GiB vs 0.33 GiB real; omnicoder2-ctx256k 17.0 GiB vs 4.25 GiB real.
  Conservative (can only refuse/evict too eagerly), but it distorts admission for the
  newest 256k tags.
- **F2 — redteam/purpleteam bake mismatch:** seats declare `context_limit: 32768` but the
  hint is `9b-ctx64k`; llama.cpp allocates the baked 64k (1.06 GiB KV) regardless.
- **F3 — auto-security Inkling seats declare no `context_limit`** and the model's trained
  window is 1M; KV grows ~16 KiB/token on the 4 global layers (4.08 GiB at the 262k the
  uncensored/purpleteam-deep variants declare). Inkling loops layers 6–18 three passes
  (`loop_num_passes: 3`); if the serving implementation retains KV per pass, the
  core-layer share grows up to 3× — not verifiable offline; the canary's live numbers
  will show it.
- **F4 — `inkling-2-mini:ctx256k` is not GGUF:** Ollama serves it with the native `mlx`
  runner (1260 tensor-layer blobs, 18.80 GiB total), so its KV cache is bf16-like, not
  q8_0; load_guard's GGUF-geometry sizing path cannot see its architecture at all.
- **F5 — oMLX KV allocation policy unverified offline:** tables assume oMLX sizes the
  cache to the requested window (MLX grows caches dynamically). If oMLX preallocates at
  `max_position_embeddings` (262k for the Qwen3.5/3.8 family), auto-compliance's real
  footprint is ~16 GiB higher than the table shows. The canary's engine RSS deltas will
  distinguish the two.

## Task 3/4 — runner + tests

`scripts/memory_canary.py` (registered in `scripts/OPERATOR_TOOLS.md`): per pair it
snapshots Ollama `/api/ps`, oMLX `/v1/models/status`, pipeline `portal5_load_guard_*`
counters, `vm_stat`/`vm.swapusage`/engine RSS, sends a near-limit filler prompt per seat
back-to-back through OWUI `/api/chat/completions` (`base::variant` ids supported), then
re-reads everything plus `docker logs portal5-pipeline --since` load_guard lines and the
pipeline `/v1/trace` outcome. FAIL on: HTTP 507 / "would exceed" refusal, a trace outcome
other than complete, an eviction of a model that was resident before the pair and is not
one of its seats, or swap growth over `--max-swap-growth-gib` (default 1.0). One markdown
table out; `--json` for the raw snapshots. Parsing + verdict logic unit-tested offline
(16 tests).
