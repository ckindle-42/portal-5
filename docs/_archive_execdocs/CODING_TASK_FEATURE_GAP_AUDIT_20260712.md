# coding_task/ Feature-Gap Audit — 2026-07-12

**Scope:** all `coding_task/*.md` files modified in the last ~2 months (since 2026-05-12), ~262 of ~280 total. `coding_task/` is a local, mostly-untracked (7/280 files tracked by git) scratch archive of task/design/build specs spanning the project's history — this is a targeted audit, not exhaustive, and most files are historical records of already-completed work, not a todo list.

**Method:** security-heavy content (`loop/`, `F1-F3/`, `EXEC_SEC*`, root `TASK_SEC_*`) audited directly in the main session (subagents reliably trip the cyber-safety classifier on this content). Everything else covered by four parallel read-only subagents. For each file: triage by title/purpose (skip pure historical bench-result/model-intake/docstring-review records), then for anything describing a real new capability, grep/search the current codebase to confirm presence or absence.

**Base commit for code verification:** `4c23473` (pre-M0-M8 state — one research worktree branched from a stale point; verified the underlying feature-presence findings still hold post-migration since M0-M8 was a pure move+path-fix, not a rewrite).

---

## 1. Confirmed unbuilt or partially-built

### Security / RBP module (directly relevant to ongoing RBP refinement work)

- **`TASK_SEC_CAPABILITY_INDEX_V1.md`** — a capability index/retrieval layer meant to make the ability library legible to a reasoning `decide` step (Stage 1 of a two-stage plan). No `capability_index`/`CapabilityIndex`/legibility-retrieval helper code anywhere in `portal/modules/security/core/`. Distinct from (not to be confused with) `self_index.py`, an already-built, different module. **Not built.**

- **`TASK_SEC_GOAL_DECIDE_V1.md`** — Stage 2: goal-driven engagement planning for the loop's `decide` step, reasoning over the capability library instead of a fixed playbook DAG. `loop.py`'s decide step is still `resolve_phases(pb, state.observations)` — a lookup over `playbooks.py`, not goal-driven reasoning. **Blocked by the missing capability index above; not built.**

- **`TASK_SEC_DRIFT_GATE_V1.md`** — a rolling-baseline regression/drift gate to catch slow metric decay under absolute thresholds. No `drift_gate`/`DriftGate`/rolling-baseline/delta-gate code anywhere in the security core. **Not built.**

- **`coding_task/loop/TASK_SEC_LOOP_NOTIFY_V1.md`** — **partially built.** Checkpoint/resume is real (`CHECKPOINT_DIR`, `_write_checkpoint`, escalation detection in `loop.py`), but the "push a notification via Portal's existing notification subsystem at escalation" half never landed — `loop.py` and `scripts/bench_supervisor.py` have zero imports of `notifications.dispatcher`/`AlertEvent`.

### Outside the security module

- **`coding_task/owui_quest/` — entire 6-file series appears unbuilt:**
  - `TASK_OWUI_FUNCTION_SEEDING_V1.md` — `scripts/openwebui_init.py` still doesn't seed OWUI Functions/Prompts.
  - `TASK_OWUI_QUICK_WINS_V1.md`, `TASK_OWUI_PROMPTS_LIBRARY_V1.md` — depend on the seeding above; not present.
  - `TASK_OWUI_EXPORT_AND_OCR_V1.md` — no OCR/export artifacts found.
  - `TASK_OWUI_MEMORY_UNIFICATION_V1.md` — MCP Memory (`:8920`) is still a separate live service; two memory stores still coexist, not unified.
  - `TASK_CRAWL4AI_DEEP_CRAWL_V1.md` — zero `crawl4ai` references anywhere in the repo.

- **`coding_task/files-RF/TASK_M3_CATALOG_UNIFY_V1.md`** — **partial.** The workspace side is unified into `config/portal.yaml` (`WorkspaceSpec`/`PersonaSpec` pydantic models). Personas were **not** migrated — still 130 separate `config/personas/*.yaml` files loaded by glob in `openwebui_init.py`, not through the config spine as the design intended (one preset schema, one loader).

---

## 2. Confirmed built (~62 files verified against code)

Spans: model/CLI/config-spine refactor work (M1, M4, M5, M6, M7, M2 of `REFACTOR_MASTER_PLAN.md`), CAD render MCP, lab-exec lane, coding-uncensored lanes, RAG hybrid search + Docling + Promptfoo, research temporal-injection, pipeline metrics, RequestSlot decomposition, HF registry lift, full UAT modularization (`tests/uat/` package), stream-wait module, corpus capture, V10 workspace promotions, image/video/speech bench integrations (Qwen-Image-2512, Voxtral, Wan2.2, RAG reranker), and the full SEC "loop" build-out (`bench_integration.py`, `oast_bench.py`, `cloud_bench.py`, `cred_bench.py`, `ctf_bench.py`, `decision_engine.py`, `field_journal.py`, `lab.py`, `llm_redteam.py`, `capsules.py`, `playbooks.py`, `re_firmware.py`, `validation.py` — all present), RBP/wiki-grounding work (F1: episode_id/capability_verdict split; F2: wiki write-back adapters incl. provenance ledger; F3: unknown-defense similarity-tier + anomaly-baseline, doc-regen command), the ability-port fidelity chain (53 real oracle detectors, `register_ported_oracles()` wired), bench supervisor + Layer-2 triage, compliance report generator, Splunk blue-team integration, OpenCode↔P40 conductor wiring.

## 3. Skipped as pure historical/housekeeping record (~120 files)

Model refresh/intake/eval logs, bench methodology/audit/modularization docs, docstring passes, docs-accuracy V1-V4, CI/test-suite fix chains, MLX retirement archival, most `TASK_SEC_BENCH_*`/`*_CANDIDATE_*`/`*_SWEEP_*`/`*_MULTISEAT_*` files (candidate evaluation runs and bench-infra fix chains, not standing features), `EXEC_SEC_*` (one-shot run instructions, not specs).

## 4. Ambiguous / needs human judgment

- **`TASK_SEC_EVAL_CONTEXT_EFFICIENCY_V1.md`** — the 12000-char telemetry-truncation pattern the task set out to fix is still present verbatim in `blue.py`/`agentic_blue_eval.py`. Could be the intended capped state or an unfixed regression — needs someone who knows the intended design to judge.
- **`TASK_LIBRECHAT_UAT_MCP_ENABLEMENT_V1.md`, `TASK_UAT_LIBRECHAT_V1.md`, `TASK_UAT_LIBRECHAT_ROUTED_MODEL_FIX.md`, `TASK_UAT_V2_PHASE9_POINTER.md`** — real LibreChat frontend work was built, then deliberately reverted (`chore: remove LibreChat — OWUI is the sole supported GUI frontend`). Not a gap; significant design work exists for a feature that was intentionally dropped.
- **`coding_task/side_quest/TASK_KV_*` and `TASK_QWEN_TEMPLATE_*` (PROXY/PROMOTE/BENCH steps)** — genuinely unbuilt, but moot: they target the MLX inference proxy retired 2026-06-09.

---

## Not part of this audit

This audit covers described-but-unbuilt *features*. It does not cover, and should not be confused with:
- **Test/result freshness** (`ACCEPTANCE_RESULTS.md`, UAT corpus, bench results) — those are stale for a different reason (nobody has re-run the live suites since 2026-06-26/27, ~300+ commits ago), tracked separately.
- **Execution-harness correctness** (import paths, CLI flags in the acceptance/UAT/bench driver scripts) — audited and fixed separately, see the sibling background-agent work merged into `main` the same day (`Dockerfile.pipeline`/`pipeline-entrypoint.sh` were pointing at a deleted directory; several exec docs had stale invocation examples).
