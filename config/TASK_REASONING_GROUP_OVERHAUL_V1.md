# Task: Complete the reasoning-group overhaul (Tier-2 deep lane + challenger benches)

## Status of the parent effort

The adaptive UAT (2026-08-31) found the reasoning group was running dense
27–32B models at 64K context as churn defaults, which physically cannot fit
alongside other resident models on 64GB unified memory → 96–97% memory,
emergency evictions mid-generation, 5× slowdown (`tests/uat_adaptive/FINDINGS_FIXLIST.md`
§D2, `ACTION_ITEMS.md` AI-11/AI-12/AI-13).

**Already shipped (this is NOT in scope here — it's done):**
- `auto-data` repointed to `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx32k`
  (MoE, 3B active, 54.2 t/s measured, tool-call audited live). ctx32k baked tag,
  `backends.yaml` `ollama-reasoning` group entry + `MODEL_CATALOG.md` section added,
  pipeline rebuilt, lane verified live through the pipeline, routing baseline
  re-blessed.
- `auto-math` deliberately **kept** on `phi4-mini-reasoning:latest-ctx24k` (operator
  decision — an RL-trained 2.5GB math specialist is not replaced by a generalist).
- `auto-reasoning` deliberately **kept** on `DeepSeek-R1-0528-Qwen3-8B` (operator
  decision — the 5GB dense-8B lane never thrashed; kept for reasoning-group
  lineage diversity: DeepSeek vs Qwen vs Microsoft vs Aquila across the lanes).
  B3 listed it for `qwen3.6:35b-a3b` — see item 0 below.
- `granite4.1` retains its fleet homes: `auto-compliance`, `auto-documents`,
  `auto-council` evidence reviewer, blueteam `reasoning_model` (8b / 30b-ctx16k),
  plus `granite4.1:30b` stays a reachable heavy fallback in the `ollama-reasoning`
  catalog. Only `granite4.1:30b-ctx64k` (the thrash tag) lost its binding.
- Harness false-FAIL fixes: `tests/common.py` `REFUSAL_PHRASES` + adaptive
  `generate.py` boundary refusal matcher broadened; `has_code` no longer asserted
  on boundary rows; `scripts/patch_adaptive_frozen_assertions.py` reconciled the
  136 frozen boundary rows.

Reference: `config/BENCH_REWIRE_PLAN_V1.md`, `config/PROPOSED_REASONING_OVERHAUL_V3.md`.

## Objective (this task)

Everything the parent plan gates behind a bench or new code:

### 0. `auto-reasoning` primary — diversity-aware bench (B3, deferred)

B3 wants `qwen3.6:35b-a3b` here too, for consistency with `auto-data`. Deferred
because it collapses reasoning-group lineage spread to two identical Qwen3.6
lanes and DeepSeek-R1 was not a memory problem. Bench `qwen3.6:35b-a3b` vs the
incumbent `DeepSeek-R1-0528-Qwen3-8B` on the reasoning persona-matrix **with
model-diversity weighted as an explicit criterion** — only promote if the
quality delta clearly outweighs losing the DeepSeek lineage and the dedicated
thinking specialist. If it does not, record the decision and close B3 for this
slot.

### 1. Tier-2 deep lane — `qwen3.8:27b` as an explicit variant (not a router change)

`PROPOSED_REASONING_OVERHAUL_V3.md` Tier 2 wants a slow-by-design dense lane for
hard analysis / compliance deep-review / math proofs, invoked on demand, with
tier-1 weights evicted while it runs. The Layer-1 intent classifier has **no
depth/effort signal today**, so do NOT try to make the router pick it.

- Wire it as `auto-reasoning?variant=deep` (or a dedicated `auto-deep` lane),
  same mechanism as `auto-coding?variant=laguna`.
- Model: `Qwen3.8-27B-oQ4e-mtp` is **already live on oMLX** (`:8085`, 262144 ctx,
  MTP side-car, ~18 t/s vs 12.25 Ollama GGUF, tools verified — see
  `backends.yaml` `omlx-coding` comment block). Prefer the oMLX path; the Ollama
  GGUF (`hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M`) is the fallback.
- B2 in the plan ("re-bench each Ollama release, MLX fallback") is **obsolete** —
  the oMLX path exists. Just document the measured t/s in `backends.yaml` next to
  the model and record the three-part Tier-2 exception gate being satisfied.
- Confirm eviction behavior: when the deep variant loads, tier-1 (`qwen3.6:35b-a3b`)
  must be evicted first (`context_limit` for the deep lane at 32K fits once alone).

### 2. `auto-compliance` challenger bench (plan B1 / B4)

Currently `granite4.1:8b-ctx16k` — weak for multi-framework regulatory work but
not broken. Bench two challengers on the compliance persona-matrix + the 33
deferred rows (`tests/uat_adaptive/DEFERRED_COMPLIANCE_RUN.txt`):
- `qwen3.6:35b-a3b` (the new tier-1 primary — free, installed).
- `nemotron-cascade-2:30b` (~24GB download; IFBench 82.9 / ArenaHard 83.5 class
  leaders; independently confirmed on llama.cpp). **Download is operator-gated —
  do not pull without sign-off.** Budget for 30–40 t/s on this M4 Pro, not 45–60.
- Pass criteria per `BENCH_REWIRE_PLAN_V1.md` B1. Promote the winner to
  `auto-compliance` primary.

### 3. Declines + disk reclaim (plan §Declines / AI-13)

Run `scripts/model_cleanup_audit.py`, record DROPPED verdicts per
`config/PENDING_MODEL_VERDICTS.md`, then `ollama rm`. **Name exact tags before
removing** — `granite4.1:30b-ctx16k` is still live in `auto-council` (evidence
reviewer) and the blueteam `reasoning_model`; do not sweep it with the
`granite4.1:30b` decline line. `olmo-3.1:32b-think` stays a Tier-2 bench
candidate, not a decline. ~150GB reclaim.

### 4. Deferred-compliance run + A2 rerun queue (AI-12 / AI-11)

After 1–3 land: run `DEFERRED_COMPLIANCE_RUN.txt` (33 rows, 8 spaces) and the A2
memory-thrash empty captures (~26 rows, `FINDINGS_FIXLIST.md` §A2) under the new
config so acceptance measures what ships. Sequential only (memory pressure).

### 5. v9 re-baseline (AI-26)

Re-baseline the 8 compliance spaces + data-class research spaces under the new
primaries so UAT evidence and shipped config agree.

## Verification

- Per-commit: `uv run pytest tests/unit/ -q && uv run ruff check . && uv run ruff format --check .`
- `./scripts/smoke_stream.sh` + a direct pipeline call to `auto-reasoning?variant=deep`
  confirming the routed model and that tier-1 was evicted.
- Docs travel (Rule 12): `MODEL_CATALOG.md` section for any promoted model,
  `backends.yaml` catalog entry, fact-unit reconcile via `./launch.sh sync-config`
  + `python3 -m portal_wiki render --all` (review the render diff — it rewrites
  every drifted WHAT unit, not just yours; revert unrelated churn).

## Out of scope

- oMLX reasoning-pool exposure gap → `TASK_OMLX_REASONING_POOL_REPAIR_V1.md`
- `auto` router standard-vs-abliterated posture gate → `TASK_ROUTER_POSTURE_GATE_V1.md`
