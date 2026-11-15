# Superseded — root cause was our oMLX LaunchAgent (ProcessType Background)

The headline speed comparison below was invalidated by the oMLX LaunchAgent's
`ProcessType Background` setting. After that setting was corrected, live decode
speeds aligned with stock mlx_lm:

| model | oMLX before | oMLX after | stock mlx_lm |
|---|---:|---:|---:|
| Gemma-4-26B QAT (hunt), through the Pipeline | 32.5 | 73.7 | 73.4 |
| Nemotron 30B-A3B plain 4bit | 42 | 95 | 97.4 |
| Qwen3.8-27B 4bit | 13.9 | 15.2 | 15.7 |

The operator closed the engine evaluation. The original report remains below as
historical evidence; its candidate rankings are superseded by this finding.

---

# Engine grade — 2026-11-15 (from existing receipts; testing stopped by operator)

Scope: production-faithful burn-down, live through Open WebUI's Pipeline (:9099) with the oMLX incumbent measured in the same run. Each row is ONE 800-token prompt (canary valid + `engine_speed --prompts 1 --repeats 1`), receipts under `$PORTAL_DATA_ROOT/engine_eval/{canaries,speed}/<build>/`. Not run for any candidate: tool turn, 5×3 spread, Stage-3 quality, production fit (`engine_eval_runner prodfit`, merged b581aab62).

**Verdict for every seat: unproven — keep oMLX** (docs/MODEL_SEAT_PROCESS.md). The leaders below are the candidates to take through tool turn → 5×3 → Stage 3 → prodfit when this is resumed.

## coding — Qwen3.8-27B (oMLX ≈ 13.4–13.8 tok/s)
| engine / mode | decode tok/s | × oMLX | notes |
|---|---|---|---|
| **Splash 1.6.1 / DFlash2** | **37.8** | 2.8× | always-on drafter; thinking on |
| **MTPLX 2.12.3 / MTP turbo** | **32.1** | 2.3× | native MTP pack; plain 11.6 (slower) |
| rapid-mlx 1.0.3 / native MTP | 22.2 | 1.6× | DFlash arm refuses forced tool_choice (engine limit) |
| PrismML d7b2896 / MTP draft | 17.2 | 1.25× | plain 11.4 (slower) |
| vllm-metal 0.33.0 / plain | 15.0 | 1.1× | Qwen3.8 load fixed (text-only) |
| mlxcel 0.8.1 / plain, DFlash | 14.2 / 13.9 | parity | earlier WFE quality FAIL on spec |
| vllm-mlx 0.6.0 / plain | 13.5 | parity | |
| mlx-serve / mlx_lm.server | — | not graded | routing unresolved / harness picks .venv mlx-lm 0.31.3 |
Only speculative decoding moves this seat. oMLX's own MTP (oQ4e-mtp) shows no comparable gain — worth a look at the incumbent.

## daily-moe — Nemotron 3.5 Lightning 30B-A3B (oMLX ≈ 51–60 tok/s in these runs)
| engine / mode | decode | × oMLX same run |
|---|---|---|
| **rapid-mlx / plain** | **91.9** | 1.7× |
| mlxcel / plain (4-bit pack) | 81.6 | 1.4× |
| vllm-mlx / plain | 70.6 | 1.3× |
| mlx-serve / MTP | 69.5 | 1.4× (cannot co-reside per its own GPU admission) |
| brew llama-server 1.0.0 / draft-mtp, plain | 55.9 / 53.9 | parity |
MTP is inert for NemotronH on vllm-mlx 0.6.0.

## hunt — Gemma-4-26B-A4B QAT (oMLX ≈ 32–37 tok/s)
| engine / mode | decode | × |
|---|---|---|
| rapid-mlx / MTP drafter | 74.4 | 2.2× |
| mlx-serve / plain | 74.1 | 2.3× |
| rapid-mlx / plain | 73.0 | 2.0× |
| mlxcel / plain | 70.9 | 2.2× |
| vllm-mlx / plain | 70.8 | 2.1× |
| vllm-metal / plain | 69.3 | 2.0× |
Every engine is ~2× oMLX here, with no drafter needed — this points at the **oMLX hunt configuration itself** (Gemma QAT on oMLX) rather than at any one engine. Highest-value follow-up: investigate the incumbent before swapping engines.

## task-router — Gemma-4-E4B GGUF (Ollama)
brew llama-server and PrismML canaries valid; no speed comparison (router seat). Keep Ollama.

## Instrument and Pipeline fixes found by this work (live, merged)
Pipeline: streaming usage passthrough (065e3d7c1); forced tool_choice spans one turn, not the loop (52aa5b23d) — affected any strict engine in production. Eval: seat argv actually launched (8ff8d9737); vLLM memory readbacks incl. vllm-metal's driver-wired KV pool, wired-agreement gate kept (2cdddeb22, bd4e20b35); versions are minimums, installed version on every receipt; real vllm-mlx install (the earlier "vllm-mlx" rows were a rapid-mlx shim — discarded).
