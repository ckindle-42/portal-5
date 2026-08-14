# IMPLEMENTATION REQUIREMENTS — Defensive Bully

What the future build-program generation and implementation must satisfy.
This is not a task list; it is the constraint set the next coding-agent
session converts into `TASK_*.md` files and a complete build.

## 1. Authoritative source documents

1. `DESIGN_DEFENSIVE_BULLY_FINAL.md` — WHAT is built (normative).
2. `ARCHITECTURE_DEFENSIVE_BULLY.md` — module/call-path boundaries.
3. `INTERFACES_DEFENSIVE_BULLY.md` — contracts (I-1 … I-20).
4. `DATA_MODEL_DEFENSIVE_BULLY.md` — state schemas.
5. `MIGRATION_DEFENSIVE_BULLY.md` — dispositions + retirement gates.
6. `VALIDATION_DEFENSIVE_BULLY.md` — proof obligations.
7. `REVIEW_DEFENSIVE_BULLY_CURRENT_STATE.md` — evidence base.
8. `HANDOFF_DEFENSIVE_BULLY_FINAL.md` — orientation.
9. Prior program (`BUILD_PROGRAM_DEFENSIVE_BULLY.md`) — superseded where this
   package differs; its phasing skeleton is retained (§14 below).

## 2. Target architecture summary

Sixteen components in four planes (DESIGN §6): knowledge plane (SUB, ORG),
brain (LOOP, BR-COUSIN, BR-DRIFT, MUT, TGT, PLT, SCORE), promotion plane
(BIN, HEART, HND), flywheel (HARV, PLAY, TRAIN, ROSTER). All new modules in
`portal/modules/security/core/` (spine-glob-covered). Red untouched; Episode
contract preserved; council mechanics reused from the platform; the bench
repositioned as the training acceptance gate.

## 3. Required components

Per DESIGN §6 table — SUB `hunt_state.py`, ORG `hunt_organ.py`, LOOP
`hunt_loop.py`, BR-COUSIN `cousin_engine.py`, BR-DRIFT `drift_engine.py`, BIN
`alert_bin.py`, HEART `heart_council.py`, MUT `mutation_director.py`, SCORE
`hunt_scoreboard.py`, TGT `target_selector.py`, PLT `plateau.py`, HND
`handoff.py`, HARV `harvest.py`, PLAY `playbook_memory.py`, TRAIN
`train_flywheel.py`, ROSTER `roster.py`, CLI `commands/hunt_modes.py`, config
`config/security/hunt.yaml` + `config/security/heart.yaml`.

## 4. Required integrations

- Red execution via existing scenario machinery (I-1/I-2) — no Red edits.
- Telemetry via `blue.py::collect_and_ship_scenario_telemetry` + `siem/*`.
- Investigation retrieval via `siem/spl_backend.py::query_episode`.
- Investigation arm via `blue_orchestrate.py` section runners.
- Council mechanics via `portal/platform/inference/router/council.py`
  (`parse_opinion`, participation accounting) — HEART owns aggregation.
- Embeddings :8917 / reranker :8925 (ORG); LanceDB under existing LANCE dir.
- Detection library `siem/spl_detections.{py,yaml}` (discriminators, siblings,
  variants) for grading explanation + HND generalization.
- Benign corpus `benign_corpus_bench.py` (G2); triage lane `siem/blue_triage.py`
  (G3); capture recipes (G1b + HND regression).
- Model redeploy via `cli/models.py` import-gguf mechanism; acceptance via
  bench harness + candidate_eval + intake floors + PENDING_MODEL_VERDICTS.
- Notifications via the platform dispatcher (loop.py pattern).
- Provenance via `portal/platform/wiki/provenance_ledger.py::append_entry`.

## 5. Existing primitives to reuse

Episode + verdict machinery; `query_episode`; telemetry plane; grounding
gates (`_cite_or_drop`, `_discriminator_contradicts`); section runners;
platform council mechanics; `analyst_verdict.SectionOutput` (similarity
carry); `notify_scoreboard` semantics; `spl_detections` discriminators;
`capture_recipes`; evasion-feedback channel; `emergent_gaps`; `drift_gate`
machinery; `blue_triage`; `recall_attribution` (eval-side only);
` EvidenceRecord` schema / `CaseNotebook` pattern; playbooks container
pattern; models.py import-gguf; candidate/intake/bench gates; notifications;
provenance ledger. (Full citations: REVIEW §11.)

## 6. Components to retrofit

- `unknown_defense.py` → vocabulary + explanation layer into `cousin_engine.py`;
  baseline concept into `drift_engine.py`.
- `capability_graph.py` → add SUB-backed loader (readout over persisted
  cells); classifiers unchanged.
- `playbooks.py` pattern → PLAY's learned-memory container (new module; the
  static engagement playbooks stay).

## 7. Components to replace

- `council_agreement.py` (bully role) → HEART objection gate (at HRT1).
- The bench-driver *role* of `blue.py`/`blue_orchestrate.py` → LOOP (at
  LOOP1); the files remain (bench lane + reused machinery).

## 8. Components to retire

- `growth_loop.py` (at BIN1 — after extracting DraftDetection/ProofResult/
  `validate_spl_syntax`/queue shape).
- `response_loop.py` (at HND1 — after extracting RESPONSE_PRIMITIVES + map).
- `continuous_eval.py` (at SC1/PLT1 — superseded by readouts).
Each retirement: callers migrated, tests ported, checks green (MIGRATION doc).

## 9. Components to create

All NEW modules of §3, plus: `config/security/hunt.yaml`,
`config/security/heart.yaml`, the cousin-judgment bench set (built from SUB
history once hunts exist), and the queue-load corpus for G3 (wrapper around
the triage lane).

## 10. Required data contracts

Per DATA_MODEL doc: SUB tables (hunts, iterations, cousin_records, candidates,
council_records/opinions, known_state, detection_baselines, drift_flags,
decision_events, cost_ledger, plateaus, promotion_queue, playbooks,
dataset_versions, trained_models, roster_weights); ORG `hunt_memory` record
schema; transient MutationSpec/Candidate/CouncilRecord/HandoffPackage shapes;
HARV JSONL example + dataset manifest schema.

## 11. Required persistence

`PORTAL5_HUNT_DIR` (default `/Volumes/data01/portal5_hunt/`): `hunt_state.db`
(SQLite WAL), `corpus/`, `playbooks/`, `artifacts/`. Outside the git tree
(the in-git `field_journal/` write-through pattern is explicitly NOT
repeated). Integrity/backup: file copy + `hunt doctor` command.

## 12. Required configuration

`config/security/hunt.yaml` keys per DESIGN §35 (organ, distance
weights/taus, mutation budget, budgets, plateau, costs, triage SLA,
`promote_policy: confirm`, roster_ref). `config/security/heart.yaml` roster
(seats, families, floors, materiality version). Model ids resolve via the
backends registry — no hardcoded model names. Derived files regenerate only
via `./launch.sh sync-config` if portal.yaml is touched (prefer not to).

## 13. Required model/runtime + training dependencies

Runtime: existing fleet only (Ollama + :8917/:8925). Training (TRAIN phase
owns install + verification): `mlx-lm` (LoRA train/fuse) and `llama.cpp`
(GGUF convert) host-native on Apple Silicon; no new Docker services; no
`torch`/`transformers` in `portal/platform/inference/` (Rule 8); training
deps are host tooling, documented in the phase, with a verification command.

## 14. Dependency graph + mandatory ordering

Phase skeleton retained from the prior program, corrected per review:

```text
P1 SUB1 (schema+store) → SUB2 (decision log) → ORG1 (organ) → BR1 (cousin
   engine) → LOOP1 (hunt loop + investigation arm)         [HARD GATE]
P2 BIN1 (G0,G1a,G1b,G2) → HRT1 (HEART objection gate) → BIN2 (G3 lane +
   suspect-default completion + promotion queue)
P3 MUT1 (mutation director + budget; needs BR1) → BRDRIFT1 (needs SUB+LOOP1)
P4 SC1 (needs BR1) → TGT1 (needs SUB+BR1) → PLT1 (needs BR1+SUB)
P5 HND1 (needs BIN1+HRT1)
P6 HARV1 (needs SUB2+HRT1+BR1) → PLAY1 (needs LOOP1) → TRAIN1 (needs HARV1
   + toolchain) → TRAIN2 (fuse/GGUF/create/bench-gate wiring) → ROSTER1
   (needs SUB2+HRT1)
```

- Nothing lands before LOOP1; the repo stays operational at every step
  (bench CLI + all checks green per commit).
- Replacement ordering per MIGRATION doc: extractions before retirements;
  HEART before council_agreement retirement; BIN before growth_loop
  retirement; HND before response_loop retirement.
- Migration ordering: two-Episode reconciliation (comment-level) rides LOOP1.
- Integration gates: P1 exit = first graded live cousin; P2 exit = full gate
  pipeline + council block/pass demonstrated; P6 exit = trained specialist
  serving on confirm + measured cousin-bench gain.

## 15. Migration constraints

Per MIGRATION doc: bridge rule (retire only when replacement is live),
honest-BLOCKED for un-replaced retired paths, bench flags keep working until
their replacement phases land, validation families stay green, spine globs
absorb new modules (zero new units; ≤1 authored design unit per phase;
two-commit re-pin sequence when BS requires).

## 16. Validation gates

Per VALIDATION doc: component proofs (V-*), integration proofs, live
behavioral proofs, the six-feed compounding series, the training arms
comparison, SOC-context G3 measurement, regression floor (BQ/AZ/BM/BL/BN/BR/
AW/BS/AL + security families), and the final end-to-end proof (§14 there).
Each build phase closes with its mapped validation items; the final proof is
the program's exit gate.

## 17. Operator-confirmation points

Machine-enforced (`promote_policy: confirm` + queue actor checks): finding
promotion, detection-library change (via normal commit + validation), model
serving, playbook activation, roster activation. Also operator-only: hunt
start/stop, budget/threshold config, organ external-intel ingestion, dataset
builds, train runs.

## 18. Failure/blocking semantics

Per DESIGN §30 + INTERFACES error sections: honest-BLOCKED on infra failure;
INDETERMINATE never scored as miss/pass; sub-floor council → operator
escalation; gate failure → KILLED with rationale; unindexed emission →
failed iteration; no-recall → no direction; below-floor corpus → documented
non-build; degraded organ → blocked grading, never silent lexical fallback.

## 19. Compatibility requirements

- Existing bench CLI (`--purple`, `--blue-mode *`, candidate-eval, loop,
  goal, drift-check) keeps working until its phase's retirement gate.
- Existing validation checks keep passing; checks pointed at replaced
  components (BL/BO/BE/BP at HRT1) are updated in the same change with their
  semantics preserved (participation floors, single quorum implementation,
  cite-or-drop, council bench semantics).
- `config/security_corpus.yaml` contracts unchanged; BM label-blind boundary
  extends to all new production modules (import-scan test).
- The two-Episode reconciliation is comment/doc-level only — no behavior
  change to replay benches.

## 20. Repository-operability requirements

- `./launch.sh up` unaffected; no new services; no new ports.
- `pytest tests/unit -q`, `ruff check .`, `ruff format --check .` green per
  commit; `bash scripts/ci_local.sh` green per phase; pre-push validation
  suite green (74 checks at review HEAD).
- No `.env` changes required for the core build; lab/live hunts use existing
  env (SANDBOX_LAB_EXEC, LAB_SPLUNK_*, etc.).
- `git checkout -- portal/modules/security/core/field_journal/_index.json`
  discipline after module-tree test runs (existing rule).

## 21. Definition of complete implementation

All sixteen components built, integrated, and validated per §16; the six
feeds demonstrably change later hunts; the flywheel has run at least once
through operator-confirmed serve (or a documented, evidence-backed non-serve
when the trained arm shows no gain); the final end-to-end proof
(VALIDATION §14) is recorded with artifacts; every retirement in MIGRATION
is either complete or explicitly retained with its replacement-live evidence;
all success criteria in DESIGN §38 hold.

## 22. Final proof requirements

The recorded hunt series of VALIDATION §14 with cited artifacts, plus: the
compounding series report (six feed instruments), the acceptance-gate bench
report (five arms), the operator decision log excerpts, and the green
validation-suite output at the final HEAD.

## 23. What the coding agent must re-verify at its own HEAD

1. Every existing-code anchor cited in this package (file::symbol), starting
   with: `episode.py::derive_verdict`, `blue.py::collect_and_ship_scenario_telemetry`/
   `_cite_or_drop`/`_build_evasion_feedback`, `blue_orchestrate.py` section
   runners + `_run_council`, `council.py::parse_opinion`/`aggregate_opinions`,
   `spl_backend.py::query_episode`, `rag_mcp.py` tool semantics,
   `cli/models.py::cmd_models_import_gguf`, `drift_gate.py`,
   `siem/blue_triage.py`, `capture_recipes.py`, `emergent_gaps.py`,
   `benign_corpus_bench.py`, `recall_attribution.py`, `notify_scoreboard.py`,
   `multichain.py::consolidate`, `growth_loop.py`, `response_loop.py`,
   `investigation/{evidence,case_notebook}.py`.
2. Validation check letters and their implementations (registry evolves;
   74 checks at review HEAD).
3. `config/spine_surfaces.yaml` globs still cover new-module locations.
4. Fleet roster model ids in `config/portal.yaml` / `backends.yaml` (fleet
   churn is continuous — resolve by family, not by id).
5. Lab reachability + Splunk HEC + attack-image presence before live proofs.
6. Training toolchain availability (TRAIN phase owns install; verify
   `mlx_lm` LoRA + GGUF convert on the host at that phase, not earlier).
7. Any drift between this package's claims and HEAD is a finding: record it
   in the build program's grounding section and adjust the *implementation*,
   never the invariants, without operator review.
