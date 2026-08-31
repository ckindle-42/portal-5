# Task: Repair the oMLX reasoning-pool exposure gap + fix the hollow-group health signal

## STATUS — mostly DONE 2026-08-31 (commits 70064738, 648c4480)

- Health-check fix shipped (`Backend.live_models`, `resolve_model` skips
  unserved targets, WARN names the gap).
- oMLX upgraded 0.6.3 → 0.6.4 (latest).
- 8 MLX builds re-pulled + symlinks re-pointed; 7/8 tool-audit clean and wired.
  omlx-{reasoning,security,general,creative,coding} hollow WARNs all clear.
- DeepSeek-R1-0528-Qwen3-8B-4bit RETIRED (no oMLX 0.6.4 tool parser for its
  format; auto-reasoning stays on the Ollama GGUF).
- ANE/GPU split tuner run on Qwen3-Coder-30B → GPU-only optimal on this M4 Pro,
  no settings change.

**Remaining:** decide whether `qwen3.6:35b-a3b` (auto-data primary) should also
get an oMLX conversion + alias for speed headroom; add a unit test asserting
every `omlx-*` alias value has a catalog entry.

## Problem (found 2026-08-31 during adaptive UAT triage)

The oMLX migration was started for the reasoning/general/security groups and
never finished. Concretely:

- `/Volumes/data01/omlx-models/` holds **15 converted models**, but the running
  oMLX server on `:8085` exposes only **5** via `/v1/models`:
  `Laguna-XS.2-4bit`, `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp`,
  `Qwen3-Coder-30B-A3B-Instruct-4bit`, `Qwen3.8-27B-oQ4e-mtp`,
  `mlx-community--gemma-3-12b-it-4bit`.
- `config/backends.yaml` `omlx-reasoning` (priority 10) aliases
  `granite4.1:30b-ctx64k → granite-4.1-30b-4bit`,
  `...DeepSeek-R1...ctx64k → DeepSeek-R1-0528-Qwen3-8B-4bit`,
  `tongyi...ctx64k → Tongyi-DeepResearch-30B-A3B-abliterated-4bit`,
  `granite4.1:8b-ctx16k → granite-4.1-8b-mxfp8` — **none of these four target
  models are in the live `/v1/models` list.** `omlx-general` is also partial
  (`gemma-4-26b-a4b-it-QAT-4bit` aliased, not exposed — only the older
  `gemma-3-12b` is). `omlx-security` (`VulnLLM-R-7B-4bit`,
  `Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit`) — neither exposed.

### Why it bites

The pipeline health check pings `:8085/v1/models` for a `200` and reports
"12/12 backends healthy" — it never verifies that the *aliased* models are in
the returned list. So `omlx-reasoning` looks healthy while being hollow: every
`auto-*` reasoning request routes to it (priority 10), oMLX 404s the unknown
model, and the pipeline falls back to Ollama **at the `ctx64k` hint**. That
64K-context dense fallback on a loaded box is the memory death-loop in
`tests/uat_adaptive/FINDINGS_FIXLIST.md` §D2 — and once Ollama memory hits 96%,
oMLX's own `hard_threshold: 0.95` guard rejects *everything*, cascading the whole
fleet onto Ollama.

## Objective

**Correct the gap (operator's call: this is a real migration to finish, not a
delete-and-move-on).**

### 1. Root cause — CONFIRMED 2026-08-31

The oMLX conversions for the reasoning/security pool **were never completed**.
`/Volumes/data01/omlx-models/` has directories for all the aliased models, but
these six are **0 bytes / empty**:
`DeepSeek-R1-0528-Qwen3-8B-4bit`, `granite-4.1-8b-mxfp8`, `granite-4.1-30b-4bit`,
`Tongyi-DeepResearch-30B-A3B-abliterated-4bit`,
`Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit`, `VulnLLM-R-7B-4bit`.
Only 5 models have real weights (Laguna-XS.2-4bit 18G, Nemotron-Lightning,
Qwen3-Coder-30B, Qwen3.8-27B-oQ4e-mtp, gemma-3-12b) — exactly the 5 oMLX
advertises. oMLX server logs show a steady stream of
`404: Model 'granite-4.1-30b-4bit' not found` etc. `omlx.server 0.6.3`.
Volume has 455GB free.

So the fix is: **complete the conversions**, not patch a registration bug.

### 2. Convert the pool

For each model, `mlx_lm.convert` (or pull an existing MLX build) into
`/Volumes/data01/omlx-models/<name>/`. Priorities:
- `DeepSeek-R1-0528-Qwen3-8B-4bit` — this is `auto-reasoning`'s current Ollama
  model; an oMLX copy gets it the shadow-shift speed path. Re-apply the
  DeepSeek-R1 tokenizer/tool-parser patches (`backends.yaml:743` — `tokenizer_config.json`
  class fix, unsloth `chat_template.jinja`, `mlx_lm/tool_parsers/deepseek_r1.py`)
  and pin them in a setup script so a `brew upgrade omlx` can't silently drop them.
- `granite-4.1-8b-mxfp8` — `auto-compliance` / `auto-documents` / blueteam.
- `Qwen3.6-35B-A3B-*-4bit` — `auto-creative` / pentest / the new `auto-data`
  primary (decide if `auto-data` should get an oMLX alias too).
- `VulnLLM-R-7B-4bit` — `auto-security`.
- `granite-4.1-30b-4bit` / `Tongyi-...` — only if still wanted; both are
  fallback-tier now.
Tool-audit each (`/v1/chat/completions` probe) before `supports_tools: true`.

Note: `auto-data` now pins `qwen3.6:35b-a3b` (Ollama GGUF, `-ctx32k`), which has
**no `omlx-reasoning` alias**, so it resolves straight to Ollama and is
unaffected by this gap. `auto-reasoning` stays on `DeepSeek-R1` (Ollama). Decide
whether either should get an oMLX conversion + alias for the speed headroom.

### 3. Health check — DONE 2026-08-31 (code shipped)

`Backend.live_models` is now populated from the oMLX `/v1/models` response on
every health probe (`cluster_backends._update_omlx_live_models`), and
`Backend.resolve_model` returns `None` when a resolved target is not in the
live set — so candidate selection skips a hollow oMLX backend **per hint** and
falls through to Ollama honestly instead of black-holing the request. A WARN
lists the aliased-but-unserved models on each change. Unit tests in
`tests/unit/test_omlx_backend.py`. Remaining: once the conversions land,
confirm the WARN clears.

### 4. Reconcile `backends.yaml`

Once the pool is real, the `omlx-reasoning` / `omlx-general` / `omlx-security`
`models:` lists and `aliases:` must match what `:8085` actually serves. Update
the comment blocks (they currently assert a state that isn't true).

## Verification

- `curl :8085/v1/models` lists every model aliased by an `omlx-*` group.
- `x-portal-route` trace on an `auto-*` reasoning request resolves to
  `omlx-reasoning`, not `ollama-reasoning` fallback (after conversions land).
- The `_update_omlx_live_models` WARN no longer fires (no gap between declared
  and served).

## Reference

`config/PROPOSED_REASONING_OVERHAUL_V3.md`, `backends.yaml` lines 654–860,
`~/.omlx/settings.json` + `model_settings.json`, `scripts/omlx-watchdog.sh`.
