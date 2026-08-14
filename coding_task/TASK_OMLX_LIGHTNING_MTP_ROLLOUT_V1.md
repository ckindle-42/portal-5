# TASK: Close the Lightning MTP Gap on Dense-Model Serving (OMLX-MTP-ROLLOUT-V1)

**Task ID:** TASK-OMLX-LIGHTNING-MTP-ROLLOUT-V1
**Priority:** High — a verified, already-decided 2.2-2.5x decode speedup is sitting unused
across most of the fleet's dense-model serving.
**Category:** Inference infrastructure / performance
**Protected files:** Any workspace/backend routing change is `[GATE]` operator confirm, same
discipline as every other production-routing task in this repo.

---

## The finding (2026-08-14, side investigation off TASK-LANE-CLOSEOUT-001)

Dense-model TPS on this hardware (M4 Pro, 20-core GPU, 64GB) looked suspiciously low for a
new model intake (Qwen3.8-27B, 6.8-6.9 t/s) versus community-reported 8-15 t/s for comparable
Q4 27B models on M4 Pro. Investigation ruled out the obvious suspects and found the real cause:

- **Not `OLLAMA_NUM_PARALLEL`** — A/B tested empirically (4 vs 1), no measurable difference
  (6.8 vs 6.9 t/s). Community claims about per-request KV-cache-slot overhead didn't reproduce
  here.
- **Not GPU offload** — confirmed 66/66 layers on GPU via `ollama.log`, no silent CPU fallback.
- **Not architecture-specific to the new hybrid model** — checked this project's own historical
  `bench_tps` data across months of runs: `granite4.1:30b` (7.2-8.2 t/s) and
  `mistral-small3.2:24b` (8.8-9.5 t/s), both mature/well-optimized dense architectures, land in
  the *same* narrow band as `gemma4:31b-it-qat` (7.2 t/s) and the new `Qwen3.8-27B` (6.8 t/s).
  Four different architectures, same ceiling — systemic, not model-specific.
- **It's Ollama-on-Metal itself.** `docs/reports/OMLX_DECISION.md`'s 2026-08-02 re-evaluation
  (v3, gate-passed, "PROCEED to Phase 1") already measured this precisely: oMLX v0.5.4 decode is
  **1.32-1.46x faster than production Ollama GGUF before speculation, 2.2-2.5x with verified
  Lightning MTP.** This is not a new discovery — it's a decision this project already made and
  partially executed, then didn't finish.

## Current state (checked 2026-08-14)

- 6 of 7 `config/backends.yaml` groups have an `omlx-*` shadow-shift counterpart
  (`general`, `coding`, `security`, `reasoning`, `creative`, plus the dedicated `omlx` group).
  Only `vision` is Ollama-only.
- **No Lightning MTP flag found anywhere** — not in the live `omlx-server` process's launch
  config, not in any backend entry. The running server is plain (non-MTP) oMLX serving, i.e.
  the 1.32-1.46x tier, not the 2.2-2.5x tier the gate actually verified.
- New dense-model intakes (Qwen3.8-27B, added today) go straight to Ollama-only with **no oMLX
  counterpart staged at all** — not even the 1.32-1.46x baseline tier reaches new additions
  under the current intake process.

## Scope — what this task needs to answer and do

1. **Why isn't Lightning MTP on?** Check `docs/reports/OMLX_DECISION.md`'s "scope guards and
   watch-items" (xgrammar brew patch gap, restart-by-port, gemma livelock, dead-symlink
   cleanup, version pinning) — one of these may be the reason MTP specifically was held back
   even after the base oMLX rollout proceeded. Don't assume it's simply unfinished work;
   confirm there wasn't a deliberate reason.
2. **What does turning it on require?** oMLX's Lightning MTP/DFlash config surface — per-model
   draft-model staging, a server flag, or something else. Determine this from oMLX's own docs/
   config, not by guessing.
3. **Measure the real delta on this fleet**, not just trust the historical bake-off number —
   re-run a same-session Ollama-vs-oMLX-vs-oMLX+MTP comparison on at least one current
   production dense model to confirm the 2.2-2.5x figure still holds on the current oMLX
   version and current fleet models before rolling out further.
4. **Extend intake process**: new dense-model additions (like today's Qwen3.8-27B) should get
   an oMLX counterpart staged as a normal part of intake once this lands, not bolt-on later.
   Decide whether `vision` group should also get oMLX coverage.
5. Any actual backend/routing change from this is `[GATE]` operator confirm before it goes live.

## Non-goals

- Do not flip Lightning MTP on fleet-wide without first confirming why it wasn't already on —
  there may be a real blocker recorded in the original bake-off's watch-items.
- Do not treat "Ollama is slower" as a reason to abandon Ollama as the fallback tier — the
  existing dual-backend design (oMLX primary, Ollama fallback for GGUF-only fine-tunes,
  unprobed vision, Linux hosts) stays; this task closes the gap on the primary tier, it doesn't
  change the architecture.
