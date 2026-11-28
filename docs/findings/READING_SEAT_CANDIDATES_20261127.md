# Finding: Compliance Reading Seat — Challenger Candidate Ranking (2026-11-27)

- **Date:** 2026-11-27
- **Brief:** `coding_task/BRIEF_READING_SEAT_CANDIDATES_20261127.md`
- **Incumbent:** `auto-compliance::reading` → `gemma4:26b-a4b-it-q4_K_M-t0p0-ctx128k` / `mlx-community--gemma-4-26b-a4b-it-4bit` (oMLX; GGUF fallback same tag), window 131072, temp 0.0.
- **Voided challenger:** `auto-compliance::reading-qwen38` (`Qwen3.8-27B-oQ4e-mtp`, dense 27B, oMLX prefill 86.9 tok/s at 100k → 1,100s TTFT, exceeds 900s bar) — `docs/findings/READING_QWEN38_VOID_20261127.md`.
- **Verdict (research only):** Two candidates plausibly clear the prefill bar; top 1 staged as `auto-compliance::reading-qwen36`. Incumbent stays until the orchestrator's probes land.

> **Superseded 2026-11-28:** the staged arm was promoted. `auto-compliance::reading` now serves Qwen3.6-35B-A3B (`hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx128k` on oMLX, aliased) and the `reading-qwen36` variant is retired — see `READING_SEAT_SWAP_QWEN36` and the seat ledger in `docs/MODEL_SEAT_PROCESS.md`. Everything below is the 2026-11-27 snapshot.

## 1. Requirements (from brief, hard)

1. Prefill fast enough to finish a ~100k-token material payload + answer inside 900s on this M4 Pro 64GB host with the stack up. Dense 27B = 87 tok/s → void. Required floor: 100,000/900 = 111 tok/s before any decode; measured Gemma 4 26B-A4B (4B active) = ~420 tok/s at ~100k.
2. ≥128k usable context; reliable tool calling including `tool_choice: required` on its engine (oMLX or Ollama); non-thinking or controllable thinking.
3. Fits the memory budget co-resident with the stack (no stack-down-only models). oMLX static cap 58.88GB, prefill-safe share ~0.7 → ~41GB dynamic ceiling (`~/.omlx/logs/server.log`, 2026-11-27).
4. Verbatim extraction / long-context retrieval strength (needle/RULER/long-doc QA; quote fidelity where available).
5. Inkling explicitly: architecture, Mac-servable variant, context, tool support, and what the P40 evals showed about long-context reading.

## 2. Candidate table

Weights/active params are from vendor cards or config; prefill figures are measured on this host where noted, otherwise published/estimated. Memory figures are oMLX `Loaded model: … actual:` from `~/.omlx/logs/server.log` where available.

| Candidate | Arch / active params | Engine + Mac variant (config) | Context | Memory (oMLX) | Prefill @ ~100k (tok/s) | Tool calling (`tool_choice: required`) | Thinking control | Long-context / verbatim retrieval | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| Gemma 4 26B-A4B (incumbent) | MoE, 4B active / 26B total | oMLX `mlx-community--gemma-4-26b-a4b-it-4bit`; GGUF `gemma4:26b-a4b-it-q4_K_M-t0p0-ctx128k` | 131072 (baked) | ~15.0 GiB | **~420 measured** (void doc §3, `stream_model_ttft=217.89s` on 98,176 tok) | Proven (incumbent seat) | `think:false` | A2 read test 4/6 identical failures to Qwen3.8/Qwen3.6; quote drift seen at temp 0.3, fixed at 0.0 | Stays incumbent until probe |
| Qwen3.8-27B (voided) | Dense 27B | oMLX `Qwen3.8-27B-oQ4e-mtp`; GGUF `…-ctx128k` | 131072 | ~16.6 GiB | **86.9 measured** (1,100s TTFT) | Proven on oMLX | `think:false` + `reasoning_effort` | A2 read test 4/6 | **Void — fails req 1** |
| **Qwen3.6-35B-A3B** | MoE, ~3B active / 35B total | oMLX `unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit` (registered `config/backends.yaml:839`); GGUF only ctx32k/ctx96k registered | 262144 native; staged at 131072 | ~21.2 GiB (`actual: 20.26–20.50GB`) | **~937 measured on this host** (14.05s TTFT on 13,168 tok, `~/.omlx/logs/server.log` 2026-11-27 06:58:40); published 1,249 tok/s at 80k on llama.cpp (Maurizio Fonte, 2026-06-16) | Tool protocol 100% (0 errors / 200 calls) at 80k; OpenAI-shaped `tool_calls` (Fonte 2026-06-16). `tool_choice: required` on oMLX **not yet probed** (flag) | `think:false` supported (Qwen3.6 card) | RULER 32k 97.08–100% (Open LLM Radar); needle reproduced verbatim at 80k on 3-bit/4-bit quants (Fonte 2026-06-16); A2 read test 4/6 tie with gemma/Qwen3.8 | **Top 1 — staged** |
| Inkling-2-Mini | Looped MoE, 3.4B active + looping = 5.4B effective / 26.4B total | oMLX `Inkling-2-Mini-oQ4e-mtp` (16.5 GiB, `config/backends.yaml:892`); Ollama fallback `inkling-2-mini:ctx256k` (registered, 262144) | 262144 served (1M trained) | ~16.5 GiB | **~549 measured on this host** (6.90s TTFT on 3,787 tok); P40 published 205 tok/s at 4k (P40_INKLING_PROPER_EVAL §3). 100k estimate 150–300 (reasoned, not measured) | Tool calls parse natively on oMLX (`inkling2_loop`); Ollama 0.40.18 tool calls verified. `tool_choice: required` on oMLX **not yet probed** (flag) | `think:false` returns no thinking on Ollama 0.40.18; `reasoning_effort` min does not disable reasoning; oMLX unknown (flag) | Long-context benchmarks improve with more passes (GraphWalks BFS, MRCR v2); knowledge-intensive does not (Inkling card). No verbatim-quote fidelity benchmark. P40 eval: bash-only tool preference, 166-iteration repetition loop at default sampling (temp 1.0) | **Top 2** |
| Nemotron 3.5 Lightning 30B-A3B | MoE, ~3B active / 30B total | Ollama `hf.co/bartowski/…-ctx32k` (registered `config/backends.yaml:54`); oMLX `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp` | 32768 registered (card max_context pending) | not measured on Mac | Not measured on Mac; active-param analogy suggests ≥400, but no 100k data (flag) | `supports_tools: true` in registry, but no live probe cited | Unknown (card unverified) | No RULER/needle citation in repo; used for `auto-daily` at 32k only | Parked — needs prefill + context + tool proof |
| LFM2.5-24B-A2B | MoE, 2B active / 24B total | Ollama/MLX published; not registered in `config/backends.yaml` | 131072 (card) | ~13.6 GiB reported | Decode 184 tok/s on M5 Max published; prefill not published (flag) | Tool calling trained; OpenAI-compatible (Liquid card) | **Reasoning-only** (always emits CoT) — weak fit for deterministic verbatim reading | Knowledge-heavy weaker than Qwen3.6 (Liquid card: GPQA 74.42 vs 83.69) | Candidate but disqualified-ish on thinking control + knowledge |
| Ternary Bonsai 2.5 27B | Qwen3.8-27B base, ternary weights, 5.9 GB | MLX (Ollama/llama.cpp published); not registered | likely 262144 (Qwen3.8 base) | 5.9 GB reported | Not published for 100k; ternary kernels likely fast, unproven | Tool calling improved vs Bonsai 2 (PrismML) | inherits Qwen3.8 `think:false` (reasoned) | No long-doc retrieval numbers; ternary compression risk to verbatim quotes (unproven) | Candidate, unproven on retrieval |
| Granite 4.1 30B | MoE (granite), no thinking mode | oMLX `granite-4.1-30b-4bit`; Ollama `granite4.1:30b-ctx96k` (96k only) | 98304 registered (<128k) | not measured | Not measured | tools verified on 8b only; 30b not probed | No thinking (good) | No long-context retrieval citation | Blocked on context (<128k registered) + retrieval proof |
| MiniMax-M2 / Ornith-1.5 122B | 10B / unknown active; 230B / 122B total | MLX published | 262k+ | >> budget | n/a | n/a | n/a | n/a | **Excluded — memory budget** |

Sources: vendor cards (Thinking Machines Inkling 2 Mini model card, 2026-11-20; Qwen/Qwen3.6-35B-A3B + Unsloth GGUF; Liquid AI LFM2.5-24B-A2B, 2026-11-15/04; PrismML Ternary Bonsai 2.5, 2026-11-24); published benchmarks (Open LLM Radar RULER; Maurizio Fonte llama.cpp teardown, 2026-06-16; P40 Inkling eval, `~/.claude/orchestrate/research/P40_INKLING_PROPER_EVAL_20261127.md`); host measurements (`~/.omlx/logs/server.log`); config (`config/backends.yaml`, `config/portal.yaml`, `config/model_card_expectations.yaml`); void doc.

## 3. Top 2 ranked

### #1 — Qwen3.6-35B-A3B (staged as `auto-compliance::reading-qwen36`)

- **Why:** Only candidate with measured Mac prefill comfortably above the floor (~937 tok/s at 13k, published 1,249 tok/s at 80k) **and** a published long-context retrieval result (RULER 32k 97–100%, needle verbatim at 80k on aggressive 3-bit quants). 3B active → prefill cost ~3.5× cheaper per token than dense 27B. Thinking off supported. Tool protocol 100% at 80k. Memory 21.2 GiB fits the prefill-safe ceiling.
- **Risks to probe:** `tool_choice: required` on oMLX not yet proven for this id (Qwen3.8 proved it; same family, but must be shown); quote fidelity at 100k on the compliance payload is unmeasured (Fonte's needle is a single token, not verbatim multi-span quoting); A2 read test tied 4/6 with the incumbent, so the probe must show a *quality* win, not just speed.
- **Serving config:**
  - Engine: oMLX (`omlx-general`), id `unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit` (`config/backends.yaml:839`, `supports_tools: true`).
  - Fallback: none registered at ≥128k (GGUF tags are ctx32k/ctx96k only). Probe assumes oMLX up; if a GGUF fallback is wanted, an `ollama create` ctx128k tag is needed (orchestrator-only, not staged here).
  - Window: 131072 staged (`context_limit`), card native 262144.
  - Sampling (Qwen3.6 instruct row, `config/model_card_expectations.yaml` `qwen3.6`): temperature 0.7, top_p 0.8, top_k 20, min_p 0.0, presence_penalty 1.5, repeat_penalty 1.0.
  - `think: false`, `emits_reasoning: false`, `tool_choice: required`.
- **Probe command (orchestrator runs):**
  ```
  uv run python scripts/compliance_acceptance.py --seat auto-compliance::reading-qwen36 --case parent --case choice --case interval --case read_check --runs 1 --adapter workspace
  ```
  Success signal: all four cases finish inside 900s with non-empty answers and a `Quoted sources:` list; `prompt_tokens_high_water` ≈ 98k–105k with `headroom > 0`; no `adaptive_prefill_throttle` / `client_disconnect`. Failure signal: any case aborts at 900s in prefill, empty answer, or quote drift vs the incumbent's rows.

### #2 — Inkling-2-Mini

- **Why:** 26.4B/5.4B-effective-active looped MoE with a published long-context *improvement* story (GraphWalks BFS, MRCR v2 gain with more passes), strong tool use (MCP Atlas 82.7%), and a 262144 served window with an existing Ollama fallback (`inkling-2-mini:ctx256k`). Memory 16.5 GiB — smallest of the plausible candidates. Mac-servable today on both engines.
- **Risks to probe:** Measured Mac prefill is only ~549 tok/s on short prompts; at 100k the looped 48 layer-applications may land near the 111 tok/s floor (reasoned, not measured). `tool_choice: required` on oMLX unproven. `think:false` is proven only on Ollama 0.40.18, not oMLX. No verbatim-quote benchmark; P40 eval found a bash-only tool preference and a 166-iteration repetition loop at default sampling (temp 1.0). Knowledge-intensive tasks do not improve with looping (card).
- **Serving config (if staged later as `reading-inkling`):**
  - Engine: oMLX id `Inkling-2-Mini-oQ4e-mtp` (`config/backends.yaml:892`, `supports_tools: true`, `keep_reason`); Ollama fallback `inkling-2-mini:ctx256k` (registered `config/backends.yaml:93`, 262144 baked).
  - Window: 262144 (or 131072 to match the seat's budget).
  - Sampling (Inkling card, `config/model_card_expectations.yaml` `inkling-2-mini`): temperature 1.0, top_p 0.95 (oMLX global default; not a vendor value). Note: compliance lane ceiling is 0.3 — a 1.0 seat would need a `sampling_override` reason or a tuned tag; the P40 `-seat` tag (top_p 1.0/top_k 0) is the closest existing tuned variant.
  - Thinking: `reasoning_effort` knob (default 0.9 = high; minimum does not silence reasoning) or `think: false` on Ollama 0.40.18+. For deterministic reading, prefer `think: false` if oMLX honors it (unproven — flag).
- **Probe command (assumes a future `reading-inkling` variant is staged):**
  ```
  uv run python scripts/compliance_acceptance.py --seat auto-compliance::reading-inkling --case parent --case choice --case interval --case read_check --runs 1 --adapter workspace
  ```

## 4. Staging done

- Added `auto-compliance::reading-qwen36` variant to `config/portal.yaml` (mirrors `reading-qwen38`: same prompt v2.10, tool list, `tool_choice: required`, 24576 predict, on Qwen3.6-35B-A3B with its card sampling). Non-production; `auto-compliance::reading` untouched.
- No derived files hand-edited. `tests/unit/test_variant_hints_resolve_in_routing.py` passes.

## 5. Stop condition check

A plausible candidate (Qwen3.6-35B-A3B) clears the prefill floor by ~8× on published numbers and ~8× on the one Mac measurement we have, with a published RULER/needle result. Inkling plausibly clears it but is unmeasured at 100k. The stop condition ("no catalog or new model plausibly meets prefill + tool_choice") is **not** triggered — two candidates are ranked. The incumbent still stays pending the orchestrator's probes; "unproven — keep the incumbent" remains a valid final outcome per `MODEL_SEAT_PROCESS.md` §9.
