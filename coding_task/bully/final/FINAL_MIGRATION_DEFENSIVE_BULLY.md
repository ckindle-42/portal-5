# FINAL MIGRATION — Defensive Bully (current → future)

How current Portal transitions into the final architecture. Per component:
CURRENT ROLE / CURRENT CALLERS / VALUABLE PRIMITIVES / FINAL DISPOSITION /
FINAL HOME / DEPENDENCIES / MIGRATION ORDER / COMPATIBILITY / RETIREMENT
CONDITION / VALIDATION. Citations at HEAD `47d3e884`; re-verify at build HEAD.

**Governing rules (normative):**
1. **Red continuity** — Red execution, lab lifecycle, and the Episode
   contract are never modified; the bully directs via scenario-overlay data
   only.
2. **Shadow-first** — every new capability lands dark behind a feature flag
   (`off | shadow | authoritative`), dual-writes/dual-runs against the legacy
   path, and cuts over per-component only after its validation gates pass.
   Dual-run **disagreements are persisted and adjudicated as migration
   evidence**, never normalized away.
3. **Bridge rule** — a component retires only when its replacement is live
   and exercised; until then the old path keeps working or reports
   honest-BLOCKED. No orphaned callers.
4. **Additive first** — no retirement before its replacement's proof; all
   existing CLI subcommands and validation checks keep working at every step.
5. **Trust-conservative backfill** — only hash-verified records import as
   VALIDATED; everything else imports as `IMPORTED_UNVERIFIED`; rollback
   disables consumption, never deletes records.
6. **Gates stay green** — `scripts/validate_system.py` (BQ/AZ/BM/BL/BN/BR/AW/
   BS + security families) passes at every step.

---

## Red side — untouched

| Component | Disposition |
|---|---|
| `exec_chain.py` (SCENARIOS:221, `_prepare_scenario:3071`, `_run_chain_test:3564`) | **LEAVE_ALONE.** Consumed via compiled scenario overlays (I-1). Verified: scenario dicts are data; `set_scenario` loads overlays; target substitution exists. |
| `lab.py` / sandbox :8914 / proxmox :8927 / `Dockerfile.attack` | **LEAVE_ALONE.** |
| `episode.py` | **LEAVE_ALONE / REUSE as-is.** The bully's input contract. |
| `siem/` telemetry plane (`collect.py`, `hec_ship.py`, `index_wait.py`, `capture_store.py`, `network_capture.py`, `spl_backend.py`) | **LEAVE_ALONE / REUSE.** `query_episode:161-205` is the investigation retrieval. |
| `capture_recipes.py` + `scripts/security_capture_recipes.py` | **REUSE.** BIN G1b engine + HND regression-test format. |
| `perception.py` (LAB_CIDR:17, assert_in_lab:46) | **REUSE.** MUT scope enforcement, unchanged. |

## Blue/Purple — split, not demolished

### `blue.py` (2303 lines)

- CURRENT ROLE: bench driver — blue chain tests, purple tests, telemetry
  shipping, unknown-defense wiring, evasion loop.
- CURRENT CALLERS: `commands/blue_modes.py`, `cli.py` (bench flags only).
- VALUABLE PRIMITIVES: `collect_and_ship_scenario_telemetry` (:1710-1912);
  `_cite_or_drop` (:831-912); `_discriminator_contradicts` (:915-960);
  `_build_evasion_feedback`/`_run_evasion_purple` (:2185-2255);
  `load_latest_red_capture` (:1915-1938).
- FINAL DISPOSITION: **SPLIT / REUSE-IN-PLACE.** The primitives stay in
  `blue.py` and are imported by the bully package (no premature file moves;
  moves only if import cycles force them). The bench driver functions
  (`run_blue_chain_tests:1342`, `run_purple_tests:1941`) remain callable as
  the bench lane.
- FINAL HOME: same file; consumers shift.
- DEPENDENCIES: LOOP landed and consuming Episodes directly.
- MIGRATION ORDER: shadow ingestion first (flagged), then LOOP parity, then
  the driver role's retirement from the hunting role.
- COMPATIBILITY: bench CLI flags keep working throughout (regression ruler).
- RETIREMENT CONDITION: never fully — the driver shell remains as the bench/
  acceptance lane; what retires is its role as the *brain*.
- VALIDATION: existing security checks (J/P/Q/S/U/V/Z/AA–AH families) stay
  green.

### `blue_orchestrate.py` (2904 lines)

- CURRENT ROLE: investigation orchestration (3-section / 2-section / council /
  multichain) over replayed captures; bench driver.
- CURRENT CALLERS: `commands/blue_modes.py`, corpus benches, ablation,
  validation checks (BH etc.), ~40 tests.
- VALUABLE PRIMITIVES: section runners (`run_tool_model:496`,
  `run_reasoning_model:662`, `run_expert_model:1098`, `run_mentor_model:1263`),
  `_run_three_section:1970`, `capture_expert_handoff`/`resume:1779-1856`,
  `_VERDICT_GROUNDING_POLICY:91-103`, `OrchestrationResult`/`SectionSpec`.
- FINAL DISPOSITION: **SPLIT — REUSE the machinery inside LOOP's
  investigation arm; the bench-driver role retires at LOOP parity.** An
  adapter inside `bully/investigation.py` accepts a live Episode (not only
  the replay DTO).
- FINAL HOME: same file (imported by the bully package); no relocation.
- MIGRATION ORDER: adapter in shadow → hunt-loop integration tests → parity
  evidence → driver-role retirement.
- COMPATIBILITY: `--blue-mode *` bench paths and checks BH/BE/BF/BG/BK/BO/BP
  keep passing unchanged.
- RETIREMENT CONDITION: the *driver* role retires when LOOP runs
  investigations directly; the machinery never retires.
- VALIDATION: blue_orchestration check family + hunt-loop integration tests.

### `agentic_blue_eval.py` (1226 lines)

- CURRENT ROLE: eval arms (raw/tools/harness), capture replay loader, sweep
  driver target; owns the model-call helper `_call_model`.
- VALUABLE PRIMITIVES: `_call_model`, `_query_real_telemetry`,
  `score_findings_tiered`, `load_episode` (:135-176).
- FINAL DISPOSITION: **REUSE** (helpers; `_call_model` is the bully's
  model-call pattern) + comment-level reconciliation of its local `Episode`
  dataclass (:82-91) as the "capture replay DTO" — no behavior change.
- RETIREMENT CONDITION: n/a.

### `multichain.py` (238 lines) — LEFT ALONE

- CURRENT ROLE: N-independent-chain consolidation; **verified
  escalate-by-default** (`consolidate:110-218`: no-concluder → ESCALATE/
  ANOMALOUS_UNCLASSIFIED; DISMISS requires unanimous RULED_OUT ∧ zero signal).
- VALUABLE PRIMITIVES: two-channel decision model; ungrounded-claims
  quarantine.
- FINAL DISPOSITION: **LEAVE_ALONE.** It is the legacy bench lane's triage,
  not the promotion path (BIN+HEART own that). Suspect-by-default is
  implemented at the finding level in the bin; the prior design's
  "clear-by-default → replace" premise was stale.
- VALIDATION: BF gate stays green.

### `council_agreement.py` (199 lines) — LEFT ALONE on the legacy lane

- CURRENT ROLE: security adapter flattening SectionOutputs to votes over the
  platform primitive; called only by `_run_council`
  (`blue_orchestrate.py:2533,2650`).
- VALUABLE PRIMITIVES: participation-floor and fail-safe semantics
  (:89-102); detection↔review translation; disagreement→ANOMALOUS novelty
  mapping (:159-167). Verified gap: `_platform_opinions` (:44-66) never
  populates the objection fields.
- FINAL DISPOSITION: **LEAVE_ALONE for the legacy bench lane.** HEART
  (`bully/adversary.py`) is new code with its own objection-gated
  aggregation; it does not route through this adapter, and the adapter is
  not refactored — its checks (BO/BL/BE/BP) keep passing untouched. The
  translation table's *semantics* inform HEART's opinion mapping but no code
  moves.
- RETIREMENT CONDITION: none required by this program. (If a later cleanup
  retires the bench council mode, that is a separate decision with its own
  caller inventory.)
- VALIDATION: BL/BO/BE/BP stay green against the unchanged module; HEART has
  its own objection-gate tests.

### `response_loop.py` (321 lines) — KEEP-SIBLING

- CURRENT ROLE: test-only deterministic mappers — response IR playbooks
  (RESPONSE_PRIMITIVES:53-63 + technique map:81-104), reverse red-scenario
  generation (blue→red), threat intake (CVE→gaps).
- CURRENT CALLERS: tests/validation only.
- FINAL DISPOSITION: **KEEP-SIBLING.** Its three functions are distinct from
  detection generalization and outlive it: reverse-gen seeds MUT's directed
  mutations; RESPONSE_PRIMITIVES seed HND's IR-implications section; intake
  seeds the future external-cadence extension. It is not in the bully's
  authoritative path.
- RETIREMENT CONDITION: none in this program.
- VALIDATION: existing response checks stay green; HND references the
  primitives by import.

### `growth_loop.py` (362 lines) — EXTRACT → RETIRE

- CURRENT ROLE: test-only red-miss → draft-SPL loop with placeholder-true
  proof legs (:209,215,221). Verified dual nature: the legs are the
  *detection-exit* proof (fires-on-attack / quiet-on-benign / no-regression),
  not a finding bin.
- VALUABLE PRIMITIVES: `DraftDetection`/`ProofResult` shapes,
  `validate_spl_syntax` (:145-173), `surface_for_confirm` queue shape,
  `is_promotable` confirm-only discipline.
- FINAL DISPOSITION: **EXTRACT → RETIRE.** Shapes + syntax gate move into
  `bully/promotion.py`/`bully/handoff.py`; the three legs are made real
  inside HND (recipe replay / benign corpus / BQ+AZ lanes). The placeholder
  pattern is never copied.
- RETIREMENT CONDITION: HND live with real proof legs; its tests
  (test_response/growth paths) ported to HND equivalents.
- VALIDATION: BIN gate tests; HND proof-leg tests; no placeholder boolean can
  promote (a validation claim).

### `continuous_eval.py` (337 lines) — RETIRE

- CURRENT ROLE: test-only in-memory dashboard/corpus helpers.
- FINAL DISPOSITION: **RETIRE** once SCORE/PLT produce the readouts. No
  extraction (in-memory stores have no content worth moving).
- RETIREMENT CONDITION: SCORE/PLT live; its tests superseded by readout
  tests.

### `unknown_defense.py` (520 lines)

- CURRENT ROLE: U1 lexical similarity (wired into purple as flags), U2
  investigation bridge, U3/U4 baseline/anomaly (dormant — no baselines), U6
  outcome space.
- CURRENT CALLERS: `blue.py::_run_unknown_defense:1450-1513`,
  `blue_orchestrate.run_similarity`, tests.
- VALUABLE PRIMITIVES: grading vocabulary (EXACT/SIMILAR/NONE),
  `SimilarityResult` with `overlapping_features` (the explanation layer),
  route_to_investigation intake shape, U6 outcome space, U3 baseline concept.
  Its own comment documents the lexical failure (:112-128: a real variant
  scored 0.09).
- FINAL DISPOSITION: **RETROFIT → MERGE.** The vocabulary + feature-overlap
  layer become `bully/cousin_engine.py`'s explanation layer; the baseline
  concept is realized properly in BR-DRIFT/SUB; the lexical scorer is kept as
  the documented baseline the composite must beat (success criterion 1) and
  as the legacy comparator during dual-run migration. Production grading
  moves to the two-axis engine.
- MIGRATION: dual-run during shadow; disagreements adjudicated; no new result
  silently reuses the old `NONE → benign` fallback.
- RETIREMENT CONDITION: BR-COUSIN live + comparison evidence recorded +
  disagreement corpus adjudicated.
- VALIDATION: cousin-engine calibration tests (VALIDATION doc).

### `capability_graph.py` (556 lines)

- CURRENT ROLE: ephemeral graph + gap classifier, rebuilt per invocation.
- VALUABLE PRIMITIVES: `classify_gap` (:76-123), gap axes model,
  `update_graph_from_episode` (:291), coverage artifact renderers.
- FINAL DISPOSITION: **RETROFIT** — add a SUB-backed loader; keep the
  classifiers; the graph becomes a readout over SUB-persisted cells, not a
  store.
- RETIREMENT CONDITION: never (readout role persists); the
  cold-rebuild-per-run behavior retires once SUB persists cells.
- VALIDATION: AI check (capability graph + gap engine) stays green;
  coverage-persistence check (new).

### `field_journal.py` (209 lines)

- CURRENT ROLE: in-git JSON engagement memory; keyword recall; the one
  behavior-changing read is `capability/index.py::_journal_prior_score`
  (:189-199); `loop.py`'s recall feeds only `len(prior)` into reports
  (:452,471).
- FINAL DISPOSITION: **LEAVE_ALONE.** The bully treats it as a read-only
  *source* (PLAY/HARV read reusable patterns); SUB/ORG supersede its *role*
  for the bully without touching its files. It is never a Bully decision
  input.

### `investigation/` (evidence.py, case_notebook.py, agents.py, bench_investigation.py)

- CURRENT ROLE: investigation bench scaffolding; EvidenceStore in-memory
  (:111-119); CaseNotebook SQLite `:memory:` default (:53) with real
  supersede (:162); seven-memory-kinds doctrine (:1-17).
- FINAL DISPOSITION: **EXTRACT (patterns) / LEAVE_ALONE (files).** The
  EvidenceRecord schema, SourceAuthority hierarchy, SQLite+supersede pattern,
  and seven-kinds doctrine seed SUB. The bench keeps its toys; the bully does
  not depend on them. The `:memory:` default is *not* reused — SUB pins a
  durable path.

### `notify_scoreboard.py` (494 lines)

- FINAL DISPOSITION: **REUSE+EXTEND** into `bully/scoreboard.py` — preserve
  NOTIFY_VERDICTS catch set (:21), trust ordinal (:32-37), benign false-flag
  typing (BN/BQ); add the separate distance-graded discovery axis.
- VALIDATION: BN stays green against the original module (unchanged); the new
  scoreboard has its own tests.

### `recall_attribution.py` (339 lines)

- FINAL DISPOSITION: **REUSE** as HARV's eval-side honest-miss labeler. BM
  boundary preserved and extended: production bully modules never import it
  (import-scan test).

### `drift_gate.py` (370 lines)

- FINAL DISPOSITION: **REUSE (machinery) / LEAVE_ALONE (module).** Its
  rolling-window statistics pattern seeds `bully/drift_engine.py`; the gate
  itself (bench-metric drift, `drift-check`/`model-canary` CLIs, AN check) is
  untouched. Documentation distinguishes bench-metric drift from
  detection-baseline drift (the two are never substitutable — a validation
  claim).

### `siem/blue_triage.py` (129 lines)

- FINAL DISPOSITION: **REUSE** as the G3 measurement lane. A queue-load
  corpus runner wrapper is built as part of BIN (`bully/soc.py`); the lane
  itself is unchanged.

### `emergent_gaps.py` (80 lines)

- FINAL DISPOSITION: **REUSE** as MUT's off-script supply (unchanged feed;
  LOOP consumes).

### `loop.py` / `loop_cli.py` (684/74 lines)

- CURRENT ROLE: red-side engagement runner (playbook perceive/decide/act/
  verify/learn; caps; checkpoint/resume; notify).
- FINAL DISPOSITION: **LEAVE_ALONE.** It remains the red-side runner. LOOP
  mirrors its discipline (caps incl. max_lab_actions, checkpoint/resume,
  notify-with-resume-cmd via the shared dispatcher) without inheriting its
  control flow.

### Platform assets

| Asset | Disposition |
|---|---|
| `router/council.py` (556 lines) | **REUSE (mechanics), ZERO EDITS.** HEART imports `parse_opinion` + participation accounting and implements its own objection-gated aggregation; `aggregate_opinions` untouched; other council workspaces unaffected. |
| `portal/platform/agent/*` | **LEAVE_ALONE.** Evaluated as LOOP's base and **rejected** (the hunt pipeline is stage-transactional, not decide-execute-fold; `run_loop` enforces only max_iterations/wall-clock — no lab-action budget, `loop.py:52-53`). The discipline (caps, confidence floors, honest-BLOCKED) is mirrored in the orchestrator. |
| `cli/models.py` | **REUSE** (`cmd_models_import_gguf:218-259` in TRAIN). |
| `candidate_eval.py` / `intake.py` / bench harness / `execute_local_sec_bench.sh` | **REPOSITION** unchanged as the TRAIN acceptance gate. |
| `playbooks.py` + `playbooks/security/*.yaml` | **LEAVE_ALONE** (red-side static playbooks); container/validation pattern reused by PLAY. |
| wiki (`portal_wiki/`, provenance ledger, writeback) | **REUSE**: `provenance_ledger.append_entry:66` for promotions; spine stays design-facts-only. |
| notifications platform | **REUSE** (I-21). |
| MITRE MCP :8929 / detections MCP :8932 | **REUSE** read-only (ATT&CK enrichment; SPL library). |
| rag_mcp :8921 / memory :8920 | **LEAVE_ALONE** — independent services; the organ shares infrastructure (LanceDB dir, :8917/:8925), never their tables. |

## Retirement summary

| Retires | When | Replacement proven by |
|---|---|---|
| `growth_loop.py` | HND live | BIN/HND gate + proof-leg tests |
| `continuous_eval.py` | SCORE/PLT live | readout tests |
| `unknown_defense.py` U1 scorer (production grading role only) | BR-COUSIN live + dual-run adjudicated | cousin-engine calibration + comparison evidence |
| blue/blue_orchestrate *driver* role (hunting brain) | LOOP parity | hunt-loop integration tests + bench parity |
| `capability_graph` cold-rebuild behavior | SUB persistence authoritative | coverage-persistence check |
| investigation `:memory:` default (bully role) | SUB live | SUB restart/recovery tests |

**Never retired in this program:** Red execution, Episode, telemetry plane,
capture recipes, multichain, council_agreement, response_loop, field_journal,
playbooks.py, loop.py, platform agent/council, bench harness (repositioned),
drift_gate module, blue_triage, rag_mcp/memory_mcp, wiki spine.

## Migration phases (ordering; each phase ends gates-green)

```text
M0 contracts/config/store/events/outbox foundation + spine surface entry
M1 Episode shadow ingestion (dual-write, feature-flagged) + evidence manifests
M2 ORG projection + outbox worker + recall receipts (shadow recall)
M3 signatures + cousin engine + drift engine (shadow dual-run vs U1/flags)
M4 mutation validation/compilation + orchestrator (bounded, admission control)
M5 promotion machine + SOC adapter + HEART (objection lifecycle)
M6 six-feed shadow → DecisionImpact evidence → authoritative cutovers
M7 HND + PLAY lifecycles
M8 HARV datasets + TRAIN lifecycle (toolchain install owned here)
M9 component cutovers + legacy retirements (this doc's conditions)
M10 final end-to-end proof
```

Each cutover requires: caller inventory; compatibility adapter; shadow data
over the configured minimum window; disagreement analysis; fault/restart/
idempotency proof; resource proof; operator approval; rollback drill; docs/
config/spine updates in the same increment. Final retirement requires: no
unresolved callers, retained historical access, successor semantic coverage,
all regression/e2e gates passing, and an approved retirement record.

## Data backfill policy

1. Inventory candidate legacy Episodes, captures, journals, graphs, corpora,
   results — without mutation.
2. Import only by idempotent manifest (source path/id, content hash, importer
   version, inferred fields, omissions).
3. Preserve existing synthetic/truth labels. Never upgrade a legacy claim
   based on filename or old model prose.
4. Verified-hash records may become VALIDATED only after the corresponding
   new validator runs; otherwise IMPORTED_UNVERIFIED or SUSPECT.
5. Imported examples are excluded from training test sets until leakage/group
   provenance is established.
6. Rollback disables consumption but keeps imports and audit receipts.

## Compatibility guarantees

- All existing CLI subcommands keep working (bench flags, `--blue-mode *`,
  loop, goal, drift-check, model-canary, candidate-eval, self-index,
  stage2-propose, compliance-report, capability).
- The Episode contract is stable across the migration.
- Legacy purple results and wiki provenance remain byte/semantically
  compatible with the feature flag off.
- The doc spine sees one new surface entry; no unit explosion (BR green).
- `P5-SEC-BENIGN-CORPUS-001` stays RESOLVED (G2 is its concept-native home).
- Synthetic-never-PROVEN and telemetry-indeterminate semantics remain.
- Public import/startup never requires training extras.
