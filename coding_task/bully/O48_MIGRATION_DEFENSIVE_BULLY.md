# MIGRATION_DEFENSIVE_BULLY

How the current RBP arm becomes the Defensive Bully without a rewrite and
without breaking Red continuity. Authoritative on *transition* (subordinate to
`DESIGN`/`ARCHITECTURE`/`INTERFACES`/`DATA_MODEL`). For each existing component:
**CURRENT ROLE · CALLERS · PRIMITIVES WORTH KEEPING · FUTURE ROLE · DISPOSITION ·
NEW HOME · DEPENDENCIES · COMPATIBILITY · RETIREMENT · VALIDATION.** Dispositions:
REUSE · RETROFIT · REPLACE · RETIRE · KEEP-SIBLING. All verified at HEAD
`47d3e884`; re-verify at the build session's HEAD.

Governing principles: Red is untouched; the Episode is the stable bridge; the
bench path is repositioned, not deleted; retirement is behind a replacement (no
orphaned callers); every migration step holds the gates green.

---

## Preserve Red continuity (non-negotiable)

- `exec_chain.py` (SCENARIOS grammar, `_run_exec_chain`, `_run_model_turn`,
  `_prepare_scenario`) and `lab.py` (dispatch, Proxmox snapshot/restore,
  stealth queries) are **KEEP / untouched**. The Bully directs Red only by
  supplying scenario dicts (as `candidate_eval` already does). No migration
  touches red execution.
- The **Episode** (`episode.py::derive_verdict`, `DetectionCorrelation`) is the
  fixed contract between the old and new worlds: whatever consumes telemetry —
  old bench or new loop — receives the same immutable Episode. This is what lets
  the arm migrate component-by-component behind a stable bridge.

---

## Per-component migration

### exec_chain / lab (Red) — **KEEP**
- CURRENT: production red executor + lab lifecycle. CALLERS: bench, loop,
  candidate_eval. PRIMITIVES: SCENARIOS grammar, snapshot/restore, dispatch.
- FUTURE: unchanged; consumes MUT-produced scenario dicts. NEW HOME: same.
- DEPS: Proxmox MCP. COMPAT: full (data-in interface already exists).
- RETIREMENT: none. VALIDATION: existing red/lab checks stay green.

### episode.py — **REUSE (reorient consumers)**
- CURRENT: deterministic purple correlation + verdict (PROVEN/FAILED/…).
  CALLERS: `blue.py`, `agentic_blue_eval.py`, corpus/benign benches.
- PRIMITIVES: FAILED = red-landed-blue-missed; synthetic-never-PROVEN (L156);
  DetectionCorrelation per technique.
- FUTURE: the finding seed — FAILED/miss becomes a suspect cousin finding.
  DISPOSITION: REUSE. NEW HOME: same; new consumers BR-COUSIN/BIN/SCORE.
- COMPAT: full. RETIREMENT: none. VALIDATION: never-PROVEN invariant preserved.

### bench harness (`run_bench`/`run_blue_chain_tests`/`run_blue_orchestration`, `BenchConfig`) — **RETROFIT → model-acceptance role**
- CURRENT: dominant BENCH_ONLY scoring path. CALLERS: `core/__main__.py`
  fallthrough `main()`.
- PRIMITIVES: single-slot candidate intake, slot-pinning, isolated results.
- FUTURE: the **model-acceptance harness** for TRAIN (via `candidate_eval`), not
  the hunt engine. DISPOSITION: RETROFIT (reposition, don't delete). NEW HOME:
  same; hunting moves to LOOP.
- COMPAT: preserved for CI + model validation. RETIREMENT: its role as the
  *primary* evaluation path retires as LOOP takes over hunting; the code stays
  as the acceptance gate. VALIDATION: acceptance checks stay green.

### loop.py / loop_cli.py — **RETROFIT (→ LOOP)**
- CURRENT: PRODUCTION_WIRED perceive/decide/act/verify/learn engagement loop
  hunting playbook phases. CALLERS: `core loop run` → `loop_main`.
- PRIMITIVES: checkpoint/resume, notify+resume_cmd, hard caps, field_journal
  learn, playbooks decide, oracles verify.
- FUTURE: the hunt loop — decide picks a cousin neighborhood (TGT), act directs
  MUT→RED, verify consumes Episode+BR, learn writes SUB + indexes ORG.
  DISPOSITION: RETROFIT + COMPOSE `platform.agent`. NEW HOME: same.
- COMPAT: CLI surface unchanged. RETIREMENT: the "hunt known phases" behavior is
  superseded by cousin-hunting. VALIDATION: loop caps + notify tested.

### playbooks.py — **RETROFIT (→ PLAY)**
- CURRENT: authored YAML methodology, wired to loop. PRIMITIVES: phases/scope/
  budget/stop/escalate + versioning. FUTURE: add the learning leg (refine from
  outcomes). DISPOSITION: RETROFIT. NEW HOME: same + SUB-backed versions.
- COMPAT: existing playbooks load unchanged. RETIREMENT: none. VALIDATION: new
  playbook-lifecycle check.

### drift_gate.py / drift_cli.py — **RETROFIT (→ BR-DRIFT + PLT engine)**
- CURRENT: bench-metric rolling-baseline drift + model-canary. CALLERS:
  `core drift-check`/`model-canary`. PRIMITIVES: trailing window, noise floor,
  z-score, min-baseline, INSUFFICIENT_BASELINE, model-canary.
- FUTURE: BR-DRIFT (per-detection firing baseline + 4-way cause) and PLT (rate
  baseline). DISPOSITION: RETROFIT (retarget the series; engine reused as a
  library). NEW HOME: `core/cousin/temporal.py` + `core/targeting/plateau.py`
  import the engine. COMPAT: existing drift-check/canary CLI preserved.
- RETIREMENT: none (the bench-drift use stays). VALIDATION: new drift-cause + plateau checks.

### platform/agent (decide/rank) — **REUSE (compose)**
- CURRENT: promoted platform loop; security shims `goal_decide`/`decision_engine`.
- PRIMITIVES: goal-grounded decide, tool/param rank, CapabilityProvider/Executor.
- FUTURE: composed by LOOP. DISPOSITION: REUSE. NEW HOME: same (consumed via the
  existing provider). COMPAT: full. RETIREMENT: none.

### council.py (`aggregate_opinions`) — **REUSE + add gate beside**
- CURRENT: platform council primitive (quorum, ESCALATE/ABSTAIN, code-decides).
  CALLERS: council workspaces + `council_agreement`. PRIMITIVES: roster-
  denominator quorum, isolated seats, `strongest_objection` per seat.
- FUTURE: HEART — objection gate in a **new** module beside it. DISPOSITION:
  REUSE (unchanged) + NEW `council_objection.py`. COMPAT: full — other council
  workspaces untouched (this is why the gate is beside, not inside).
- RETIREMENT: none. VALIDATION: BL participation floor stays green; new
  objection-gate check.

### council_agreement.py — **RETROFIT (refactor)**
- CURRENT: compat adapter delegating quorum to platform council; detection↔review
  translation + disagreement→ANOMALOUS. CALLERS: historical benches + opt-in CLI.
- PRIMITIVES: domain translation, disagreement-as-novelty (I8).
- FUTURE: route per-seat objections into the objection gate; keep translation +
  novelty mapping. DISPOSITION: RETROFIT. NEW HOME: same. COMPAT: preserved for
  legacy callers. RETIREMENT: the vote-only flattening behavior is superseded by
  the gate. VALIDATION: translation + ANOMALOUS mapping tested.

### unknown_defense.py — **RETROFIT (→ BR-COUSIN explanation)**
- CURRENT: EXACT/SIMILAR/NONE via token-overlap vs wiki descriptions
  (code-documented as weak — a real match scored 0.09 < 0.15). CALLERS: novelty
  path. PRIMITIVES: grade space, overlapping-features citation, matched-unit id.
- FUTURE: the *explanation* layer of BR-COUSIN; the *decision* moves to the
  5-axis composite over ORG embeddings. DISPOSITION: RETROFIT. NEW HOME:
  `core/cousin/spatial.py` (uses this for explanation). COMPAT: grade space maps
  SAME/SIMILAR/NEW. RETIREMENT: token-overlap-as-decision retires (kept as
  feature-explanation only). VALIDATION: cousin-metric check (real variant no
  longer scores ≈0).

### research/tools/rag_mcp.py — **RETROFIT (→ ORG)**
- CURRENT: doc-corpus hybrid retrieval MCP (:8921). CALLERS: research/context
  injection. PRIMITIVES: MLX embed + LanceDB + tantivy + reranker, kb_ingest/
  search, dense fallback. FUTURE: hunt-memory corpus + enforced recall/index
  (new wrapper `core/org/hunt_memory.py`). DISPOSITION: RETROFIT (new corpus +
  wrapper; retrieval internals unchanged). NEW HOME: same MCP + new wrapper.
- COMPAT: doc corpus untouched (separate corpus). RETIREMENT: none. VALIDATION:
  recall-enforced + universal-index checks.

### investigation/ (evidence + case_notebook) — **REUSE + EXTEND (→ SUB seed)**
- CURRENT: case-scoped immutable evidence + notebook; `:memory:` default.
  PRIMITIVES: append-only, SourceAuthority, supports/contradicts, supersede,
  seven-memory-kinds. FUTURE: the record engine of SUB, pinned to a durable path
  + cross-hunt tables. DISPOSITION: REUSE + EXTEND. NEW HOME: `core/substrate/`.
- COMPAT: case API unchanged; only the backing path + new tables added.
- RETIREMENT: `:memory:` default retires for the persistent path. VALIDATION:
  seven-kinds taxonomy check.

### capability_graph.py — **REUSE (schema) + EXTEND (persist)**
- CURRENT: in-memory coverage graph + gap classifier + Navigator/heatmap
  artifacts; no persist. CALLERS: emergent_gaps, response_loop, coverage report.
- PRIMITIVES: Procedure/Detection/Gap/CoverageSummary, technique-as-tag, gap
  classifier. FUTURE: coverage schema for SUB (persisted cells). DISPOSITION:
  REUSE entities + EXTEND persistence. NEW HOME: `core/substrate/coverage.py`.
- COMPAT: entities unchanged. RETIREMENT: cold-rebuild-per-run retires (state
  persists). VALIDATION: coverage-persistence check.

### growth_loop.py — **RETROFIT (→ HND proof, not the bin)**
- CURRENT: draft/prove/surface for detection exits; `prove_draft` legs are
  placeholder-True. CALLERS: emergent_gaps + response paths. PRIMITIVES: the
  three proof legs (fires-on-attack / quiet-on-benign / no-regression),
  confirm-only surface. FUTURE: the proof harness inside HND for generalized
  rules — with the legs made real. DISPOSITION: RETROFIT. NEW HOME: `core/
  handoff/detection.py` uses it. COMPAT: gap-consumption idiom preserved.
- RETIREMENT: placeholder-True legs retire (become real proofs). VALIDATION:
  each leg proven (not asserted).

### response_loop.py — **KEEP-SIBLING**
- CURRENT: response IR playbooks + reverse red-scenario generation + threat
  intake. CALLERS: response paths. PRIMITIVES: all three (reverse-gen seeds MUT;
  intake is the external-cadence seed). FUTURE: kept as-is; HND is a new sibling
  for detection generalization. DISPOSITION: KEEP-SIBLING. NEW HOME: same.
- COMPAT: full. RETIREMENT: none. VALIDATION: existing response checks stay green.

### emergent_gaps.py — **REUSE (→ MUT accidental feed)**
- CURRENT: off-script landed-but-undetected → RED_ONLY Gap; synthetic excluded.
  PRIMITIVES: trajectory-miss → gap idiom, never-synthetic. FUTURE: the
  accidental-cousin feed into MUT/BIN. DISPOSITION: REUSE. NEW HOME: same.
- COMPAT: full. RETIREMENT: none.

### recall_attribution.py — **REUSE (→ HARV labeler)**
- CURRENT: eval-only label-blind honest-miss oracle (check BM), World A/B split.
  PRIMITIVES: presence oracle, label-blind boundary. FUTURE: HARV's offline
  labeler. DISPOSITION: REUSE. NEW HOME: consumed by `core/training/harvest.py`.
- COMPAT: full; boundary preserved (labels offline only). RETIREMENT: none.

### notify_scoreboard.py / scoring.py — **REUSE + EXTEND (→ SCORE)**
- CURRENT: ordinal trustworthiness scoreboard (CONFIRMED > ANOMALOUS > SILENCE >
  WRONG) + pure scoring math. PRIMITIVES: ANOMALOUS-as-catch, deterministic math.
- FUTURE: distance-weighted value. DISPOSITION: REUSE + EXTEND. NEW HOME: same.
- COMPAT: ordinal semantics preserved. RETIREMENT: none. VALIDATION: BN
  scoreboard-semantics stays green (ANOMALOUS never below CONFIRMED).

### multichain.py — **KEEP (do not flip default)**
- CURRENT: consolidates N chains; DISMISS only when all ruled out with zero
  signal. FUTURE: unchanged. DISPOSITION: KEEP. RATIONALE: suspect-by-default
  belongs at finding-vs-red-landed, not here (flipping would spike BQ/AZ).
- VALIDATION: BQ/AZ stay green.

### siem/ (spl_detections, collect, backend) — **REUSE**
- CURRENT: detection library + telemetry adapters. FUTURE: detection state (SUB
  mirror), G3 notable creation, HND SPL change. DISPOSITION: REUSE. NEW HOME:
  consumed by BIN/HND/SUB. COMPAT: full.

### models.py (import-gguf) / candidate_eval.py — **REUSE (→ redeploy + accept)**
- CURRENT: GGUF→Modelfile→ollama create; single-slot delta-vs-incumbent isolated
  accept (confirm-only). FUTURE: TRAIN's redeploy + acceptance legs. DISPOSITION:
  REUSE. NEW HOME: consumed by `core/training/`. COMPAT: full; PROMOTE_POLICY=
  confirm preserved.

---

## Retirement order (behind replacements, gates green throughout)

1. Build SUB persistence + ORG hunt-memory wrappers (additive; nothing retired).
2. Build BR-COUSIN/BR-DRIFT and retrofit `unknown_defense`/`drift_gate` (additive;
   token-overlap-as-decision retired only once the composite metric is proven).
3. Retrofit LOOP to hunt cousins (the old "hunt phases" behavior retires as the
   new decide-step lands; CLI unchanged).
4. Build BIN gates + retrofit `growth_loop` into HND proof (placeholder-True legs
   retire as real proofs land).
5. Add HEART objection gate beside council + refactor `council_agreement`
   (vote-only flattening retires; platform primitive untouched).
6. Reposition the bench path as the model-acceptance harness (its primary-
   evaluation role retires as LOOP owns hunting; code stays).
7. Build HARV/TRAIN/PLAY/ROSTER (additive; GGUF-convert tool added).
8. `capability_graph` cold-rebuild + investigation `:memory:` default retire once
   SUB persistence is authoritative.

No step deletes a component with live callers before its replacement consumes
those callers. Every step: run `validate_system.py`; AW/BR/AZ/BL/BM/BN/BQ green.

## Compatibility guarantees

- All existing CLI subcommands keep working (loop/drift-check/model-canary/
  candidate-eval/goal/self-index/compliance-report).
- The Episode contract is stable across the migration.
- The doc spine sees new `security/core/*` files under its manifest surface at
  zero new-unit cost (check BR); no wiki explosion.
- `P5-SEC-BENIGN-CORPUS-001` stays RESOLVED (G2 reuses the benign corpus).
