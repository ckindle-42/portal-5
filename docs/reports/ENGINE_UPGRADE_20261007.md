# Engine upgrade — Ollama 0.40.0 (2026-10-07)

Ollama moved 0.35.0 → 0.40.0, the latest stable release, mainly so EmbeddingGemma 2 can run on
Ollama's MLX runner (`TASK_EMBEDDINGGEMMA2_PLATFORM_V1`). oMLX stays at 0.7.0 (current).
Installed with `scripts/engine_autoupdate.py --now` (stable `~/ollama-live` path; no data01
approval popup). The process is arm64 (`vmmap`: Code Type ARM64).

## Outcome

| Gate | 0.35.0 (HEAD baseline) | 0.40.0 |
|---|---|---|
| `engine_contract_check.py ollama` | pass | pass |
| Seat A/B, `engine_ab_ollama.yaml`, pipeline, n=3 | 35/36 | 34/36 |
| Router bench (`bench_router.py`, production router tag) | 48/73, p50 527 ms | 48/73, p50 508 ms |
| `check_model_bindings.py` | pass | pass |
| `smoke_stream.sh` | pass | pass |

Seat A/B detail (campaigns `engine_ab_ollama_035_head`, `engine_ab_ollama_040`): gemma4-e4b 9/9 → 9/9;
Nex-N2-mini 9/9 → 9/9; KAT-coder 8/9 → 8/9; omnicoder2 9/9 → 8/9. The 8/9 is one
BUDGET_EXHAUSTED `code-kv` row, which the 10-01 run also had on 0.35.0, so it is noise at n=3.
Rows that took the same trajectory ran in the same time on both versions (omnicoder2 `code-fix`
18.3/15.8/13.5 s vs 18.1/15.7/13.6 s). The slower gemma4 `code-kv` rows on 0.40.0 took more
turns (7–9 vs 4–6), not slower turns.

## What "MLX by default" means here

The new `ollama ps` RUNNER column shows every GGUF seat (all `hf.co/…` and library GGUF tags) on
**llamacpp**. Only MLX-format (safetensors) library models use the MLX runner. The fleet's
behaviour is unchanged, and oMLX remains the MLX chat engine.

## EmbeddingGemma 2 on Ollama (new)

`embeddinggemma-2:740m-mxfp8` (744M, `requires 0.36.0`, runner `mlx`, 1.3 GB resident, 8K
context). Library tags mirror the card's modality split: `270m-*-text`, `440m-*-text-vision`,
`570m-*-text-audio` and `740m-*`, each in bf16/mxfp8/nvfp4. The untagged default is nvfp4.

`POST /api/embed`, measured on this Mac:

| Check | Result |
|---|---|
| default dim / norm | 768, L2 = 1.0, all finite |
| `dimensions` 512/256/128 | truncated + renormalised (cos to the 768 prefix = 1.0) |
| text retrieval sanity (3 docs) | 3/3 top-1, with and without the card's prefixes |
| image (`{"image": b64}`) ↔ caption | matched; 0.81 / 0.84 vs 0.50 / 0.52 cross |
| text + image in one item | one 768-d vector |
| audio (`{"audio": b64}`) | embeds in 0.83 s; cos to own transcript 0.62 vs unrelated 0.55 (1 clip) |
| video | rejected: `input.video not supported` |
| throughput (64 short docs) | 57 / 59 / 83 items/s at batch 8 / 32 / 64 |
| co-residency | loaded beside the pinned router model with no eviction |

Ollama applies no task prefixes, so the client must prepend `task: … | query:` /
`title: … | text:` (`portal/platform/embedding/contract.format_text` already does).

## Fixes made during the upgrade

- **Router `think: false`** (`portal/platform/inference/router/routing.py`). With `think` unset,
  Gemma 4 sometimes ignored the JSON grammar: malformed keys like `{"auto-spl": "emotions"}` and
  length stops. Production saw 14 timeouts and 2 invalid workspaces among 36 recent routing calls.
  `bench_router.py` sent the same payload with `num_predict: 40` and scored 4/73 because thinking
  consumed the budget. Both now send `think: false`; the bench now matches production's
  `num_predict: 64`.
- **Router re-pin after an Ollama restart** (`scripts/engine_autoupdate.py`). An engine restart
  drops the router's `keep_alive: -1` pin, and the pipeline re-warms it only on the next routed
  request, so OWUI's task model (`task-router`, same tag) ran cold until then. The updater now
  reloads it pinned after every update or rollback.
- **`presence_penalty` is applied by Ollama** (since 0.35.0; both checks reported "NOW HAS
  EFFECT"). `engine_contract_check.py` now requires its delivery. The WFE runner's deliverable-key
  table and the settings auditor no longer treat it as undeliverable on Ollama, and the
  known-limitations unit is corrected. Seats that carry the 2026-09-25 `repeat_penalty: 1.05`
  substitute keep it. The auditor reports that as a card deviation, and switching a seat back is
  a per-seat A/B.

## Not done here

- Switching any seat's sampling from the `repeat_penalty` substitute back to `presence_penalty`.
- Raising `OLLAMA_MIN_VERSION` (0.32.4). The stack runs on older versions; only EG2 needs ≥ 0.36.0.
