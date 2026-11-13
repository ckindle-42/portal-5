# Engine eval matrix — 2026-11-13

Status: proposal. The orchestrator approves this before any Stage 3 workload runs.
Nothing here was measured live in this lane. Same-bytes means every compared engine
loads one checkpoint directory or one GGUF blob. A different quant, an oQ4e sidecar,
or a GGUF tag is a different artifact and is not a win over the other.

Incumbent for the MLX seats is oMLX. Pass, before any run: the cell is instrument-valid,
quality is not worse than the incumbent on the registered WFE task, speed is faster than
that pair's noise floor, and the candidate co-resides with the router plus the seats
without tripping the swap gate (growth 2048 MB, absolute used 4096 MB). Otherwise the
result is "Unproven — keep the incumbent." Ollama GGUF rows are failover and do not
decide the MLX engine. Template parity runs only when `same_checkpoint` is true.

## Daily MoE

Checkpoint: `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp`.
Production seat `auto-daily` hints the GGUF tag
`hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k`
(think true, context_limit 16384, predict 8192, temperature 1, top_p 0.95, top_k 64,
repeat_penalty 1.0). `workspace_routing` sends `auto-daily` to group `general`.
`omlx-general` does not alias that GGUF tag, so production serves `ollama-general`.
Pinning `portal_backend=omlx-general` on this workspace is not a production path:
the pin must refuse, because the backend does not resolve the hint. The bench
workspace `bench-engine-daily-moe` is the Stage 1/2 cell for the oQ4e directory.
It injects the production context 16384. A separate long-context cell launches
32768 and reads it back.

Same-bytes subset: engines that load that oQ4e directory. mlxcel cannot read oQ4e.
MTP on this checkpoint is an oMLX question; the 11-13 screen's other engines are not
scored as the same weights. Ollama's GGUF is a different artifact. Nemotron
oQ4e-mtp on oMLX is a candidate cell, not the Stage 0 production baseline.

Stage 0 Ollama seat id: `daily-moe`. The instrument claims the engine-reported
context, not the Pipeline cap of 16384. Ollama's tag blob stores `num_ctx` 32768
(`sha256:cca9f403c312…`, the ctx32k manifest). The 16384 cap is excluded from the
comparison. Stage 0's oMLX baseline is `hunt-reasoning`, below.

Decision: MLX engine for the resident daily MoE seat.

## Dense coding, with its speed lever

Plain checkpoint: `Qwen3.8-27B-4bit`.
MTP sidecar: `Qwen3.8-27B-oQ4e-mtp` (different bytes; upstream ships no MTP head on the plain dir).
DFlash2 drafter `/Volumes/data01/omlx-models/Qwen3.8-27B-DFlash2` is on disk (symlink
to the hf-cache incoai snapshot, restored 2026-11-12). Spec arms that name it can run.
Do not substitute another drafter.
`splash serve --help` on Splash 1.6.1 loads every model with its DFlash2 draft.
`--draft-model` only selects a different drafter. There is no draft-off switch.
The plain Splash cell is excluded. A scored plain cell that still passes
`--draft-model` stays invalid. Do not invent a flag.
vLLM Metal cannot load this MLX dir ("Unrecognized image processor" on the 11-13 screen).

Production `auto-coding` hints the GGUF ctx96k tag, context 98304, predict 32768, think true,
temperature 1, top_p 0.95, top_k 20, min_p 0, presence 0, repeat 1, with the coding tools.
`workspace_routing` tries group `coding` first. `omlx-coding` (priority 10) aliases
`hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k` to `Qwen3.8-27B-oQ4e-mtp`, so this seat
is a production oMLX path. It is not the Stage 0 baseline. A coding-seat move is proven
only by an engine that loads those bytes. Plain 4bit is a separate question and does not
by itself move the seat.

Decision: coding-seat engine.

## Task router

Workspace `task-router` hints
`hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M-ctx2k`,
context 2048, predict 128, temperature 0.2, think false, tools []. No MLX checkpoint
is named. Fair subset: GGUF loaders that serve that tag (Ollama, and a llama-server
whose alias is that tag). Do not substitute another Gemma.

Decision: the router stays resident beside a seat. "Cannot hold the router beside the
seat" is a result.

## Hunt parallel

`hunt-reasoning` hints `gemma4:26b-a4b-it-qat-ctx8k-hunt`, context 8192, temperature 0.0,
max_concurrent 8, tools [], no think field. Group `general`, and `omlx-general` (priority
10) aliases that hint to `gemma-4-26b-a4b-it-QAT-4bit`. That is the Stage 0 oMLX
production baseline. Unload that id before the run
(`POST /v1/models/gemma-4-26b-a4b-it-QAT-4bit/unload`). The checkpoint
`config.json` text `max_position_embeddings` is 262144; the instrument claims that
engine-reported context, not the Pipeline cap of 8192. Same-bytes MLX subset from the
11-13 screen: mlx-serve, vllm-mlx, rapid, vllm-metal, mlxcel, mlx_lm, oMLX. Splash
refused (not a splash family). Spec is null. Ollama's GGUF is different bytes.

This checkpoint is also `auto-council` (think false, context 16384, predict 4096,
temperature 1, top_p 0.95, top_k 64).

Decision: MLX engine for the resident Gemma QAT seats (hunt, council, the daily Gemma variant).

## Council / JSON

Production council is the Gemma QAT seat above, not a new checkpoint.
The JSON-specific seat is `compliance-council-qwen38`: GGUF ctx32k hint, context 32768,
predict 8192, temperature 0.7, top_p 0.8, top_k 20, min_p 0, repeat 1, presence 1.5,
think false, tools []. Same-bytes subset: engines that load `Qwen3.8-27B-4bit` with
those sampling values. Do not use oQ4e-mtp for this row.

Decision: council/JSON seat on that plain checkpoint.

## What is not compared

Ollama GGUF versus oMLX oQ4e, and oQ4e-mtp versus plain 4bit or DFlash2-on-4bit, are
different bytes. Template parity is skipped (`same_checkpoint: false`), not failed.
64 GB launch argv stays the argv already in `tests/benchmarks/engine_h2h.yaml`. Source
URLs are the comments in that file (mlx-serve, Rapid-MLX, mlxcel, vLLM Metal, Splash).
Those comments were not re-checked against vendor docs in this lane. oMLX and Ollama
are external services in that file and have no install URL there.
