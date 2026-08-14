# MIGRATION — Defensive Bully (current → future)

How current Portal becomes the final system. Per component: CURRENT ROLE /
CURRENT CALLERS / VALUABLE PRIMITIVES / FUTURE ROLE / DISPOSITION / NEW HOME /
MIGRATION DEPENDENCIES / COMPATIBILITY REQUIREMENTS / RETIREMENT CONDITION /
VALIDATION REQUIRED. Citations at HEAD `47d3e884`; re-verify at build HEAD.

**Bridge rule (normative):** every retirement lands only when its replacement
is live and exercised; until then the old path keeps working or reports
honest-BLOCKED. Red never sees the change: LOOP consumes the same Episode and
drives the same execution/telemetry machinery from day one.

---

## Red side — untouched

| Component | Disposition |
|---|---|
| `exec_chain.py` (SCENARIOS, `_run_chain_test`, `_prepare_scenario`) | LEAVE_ALONE. Consumed via scenario overlay (I-1). Verified direction surface suffices: scenario dicts are data; `_config.set_scenario` loads overlays; target substitution exists |
| `lab.py` / sandbox :8914 / proxmox :8927 / `Dockerfile.attack` | LEAVE_ALONE |
| `episode.py` | LEAVE_ALONE (REUSE as-is). The bully's input contract |
| `siem/` telemetry plane (`collect.py`, `hec_ship.py`, `index_wait.py`, `capture_store.py`, `network_capture.py`, `spl_backend.py`) | LEAVE_ALONE / REUSE. `query_episode` is the investigation retrieval |
| `capture_recipes.py` + `scripts/security_capture_recipes.py` | REUSE. BIN G1b engine + HND regression-test format |

## Blue/Purple — split, not demolished

### `blue.py` (2303 lines)

- CURRENT ROLE: bench driver — blue chain tests, purple tests, telemetry
  shipping, unknown-defense wiring, evasion loop.
- CURRENT CALLERS: `commands/blue_modes.py`, `cli.py` (bench flags only).
- VALUABLE PRIMITIVES: `collect_and_ship_scenario_telemetry` (`:1710-1912`);
  `_cite_or_drop` (`:831-912`); `_discriminator_contradicts` (`:915-960`);
  `_parent_collapse_precision_note`; `_build_evasion_feedback`/`_run_evasion_purple`
  (`:2185-2255+`); `load_latest_red_capture` (`:1915-1938`);
  `_VERDICT_GROUNDING_POLICY` counter-evidence discipline.
- FUTURE ROLE: telemetry/grounding utilities serve the hunt; evasion-feedback
  channel serves MUT; driver shell (run_blue_chain_tests/run_purple_tests)
  remains the **bench** path until LOOP proves parity, then bench-only.
- DISPOSITION: **SPLIT / EXTRACT.**
- NEW HOME: extraction target is minimal and mechanical — the primitives stay
  in `blue.py` and are imported by `hunt_loop.py`/`mutation_director.py`/
  `alert_bin.py` (no premature file moves; moves only if import cycles force
  them). The bench driver functions stay put and remain callable.
- MIGRATION DEPENDENCIES: LOOP1 landed and consuming Episode directly.
- COMPATIBILITY: bench CLI flags keep working throughout (regression ruler).
- RETIREMENT CONDITION: never fully — the driver shell remains as the bench
  lane; what retires is its role as the *brain*.
- VALIDATION: existing security checks (AG/AH/Z/AB/AC/AD…) stay green.

### `blue_orchestrate.py` (2904 lines)

- CURRENT ROLE: investigation orchestration (3-section / 2-section / council /
  multichain) over replayed captures; bench driver.
- CURRENT CALLERS: `commands/blue_modes.py`, corpus benches, ablation,
  validation checks (BH etc.), ~40 tests.
- VALUABLE PRIMITIVES: section runners (`run_tool_model:496`,
  `run_reasoning_model:662`, `run_expert_model:1098`, `run_mentor_model:1263`),
  `_run_three_section` loop mechanics (`:1970+`: history caps, stall handoff,
  budgets), `capture_expert_handoff`/`resume_from_handoff` (`:1779-1856`),
  `OrchestrationResult`/`SectionSpec` shapes, `run_similarity` translation
  (`:639-652`).
- FUTURE ROLE: the **investigation arm** of LOOP (per-Episode analysis over
  `query_episode`). The multichain mode remains a bench analysis mode.
- DISPOSITION: **SPLIT — REUSE the machinery, REPLACE the driver role.**
- NEW HOME: same file (imported by `hunt_loop.py`); no relocation.
- MIGRATION DEPENDENCIES: LOOP1; the arm must accept a live Episode (not only
  replay DTO) — adapter shim inside LOOP.
- COMPATIBILITY: `--blue-mode *` bench paths and validation checks BH/BE/BF/BG/
  BK/BO/BP keep passing unchanged.
- RETIREMENT CONDITION: the *driver* role retires when LOOP runs investigations
  directly; the machinery never retires.
- VALIDATION: blue_orchestration check family + hunt-loop integration tests.

### `agentic_blue_eval.py` (1226 lines)

- CURRENT ROLE: eval arms (raw/tools/harness), capture replay loader, sweep
  driver target.
- CURRENT CALLERS: own main, `_sweep_driver.py`, corpus benches.
- VALUABLE PRIMITIVES: `_call_model`, `_query_real_telemetry`,
  `_summarize_telemetry`, `score_findings_tiered`, `load_episode`
  (`:135-176`).
- FUTURE ROLE: unchanged as eval harness; `_call_model` is the model-call
  helper for bully components.
- DISPOSITION: **REUSE** (helpers) + reconcile the local `Episode` dataclass
  (`:82-91`) — rename usages to "capture replay DTO" in docs/comments; no
  behavior change.
- RETIREMENT CONDITION: n/a.

### `multichain.py` (238 lines)

- CURRENT ROLE: N-independent-chain consolidation (ESCALATE-by-default —
  verified `consolidate:110-218`).
- VALUABLE PRIMITIVES: the two-channel (known-bad vs unknown) decision model;
  ungrounded-claims quarantine.
- FUTURE ROLE: unchanged — the multichain analysis mode's triage. **Not** the
  promotion path (BIN+HEART own that).
- DISPOSITION: **LEAVE_ALONE.** (Prior design's "REPLACE clear-by-default"
  premise was stale — see REVIEW §1, drift row 1.)
- VALIDATION: BF gate stays green.

### `council_agreement.py` (199 lines)

- CURRENT ROLE: security adapter flattening SectionOutputs to votes over the
  platform primitive; called only by `_run_council` (`blue_orchestrate.py:2650`).
- VALUABLE PRIMITIVES: participation-floor and fail-safe semantics (mirror
  comments `:89-102` — already escalate-not-dismiss); the translation table.
- FUTURE ROLE: none in the bully. HEART supersedes it with the objection gate.
- DISPOSITION: **REPLACE** (its bench-council caller keeps working until
  HEART lands; then the security council mode routes through HEART).
- NEW HOME: `heart_council.py`.
- MIGRATION DEPENDENCIES: HEART built + roster config; BO/BL/BE/BP checks
  adapted to point at HEART (they assert participation/quorum semantics HEART
  preserves).
- COMPATIBILITY: `--blue-mode council` keeps working during transition via the
  old adapter; switches to HEART at HRT1 with checks updated.
- RETIREMENT CONDITION: HEART live + checks green against HEART.
- VALIDATION: BL (participation floor), BO (single quorum implementation —
  HEART keeps delegating roster math to the platform primitive), BE, BP.

### `response_loop.py` (321 lines) — RETIRE after extraction

- CURRENT ROLE: test-only deterministic gap→draft mappers.
- VALUABLE PRIMITIVES: `RESPONSE_PRIMITIVES` + `technique_responses` map
  (`:53-104`); ThreatIntake shape (`map_threat_to_gaps:213`).
- FUTURE ROLE: primitives seed HND's IR implications; threat-intake shape
  seeds external-intel ingestion (future extension).
- DISPOSITION: **EXTRACT → RETIRE.**
- NEW HOME: `handoff.py`.
- RETIREMENT CONDITION: HND1 live; its tests (test_response_loop.py) ported to
  HND equivalents.
- VALIDATION: HND package tests.

### `growth_loop.py` (362 lines) — RETIRE after extraction

- CURRENT ROLE: test-only red-miss → draft-SPL loop with placeholder-true
  proof legs (`:209,215,221`).
- VALUABLE PRIMITIVES: `DraftDetection`/`ProofResult` shapes,
  `validate_spl_syntax` (`:145-173`), `surface_for_confirm` queue shape,
  `is_promotable` confirm-only discipline, wiki writeback surface.
- FUTURE ROLE: shapes + syntax gate + queue discipline live in BIN/HND;
  placeholder proof legs are **replaced** by G1a/G1b real gates.
- DISPOSITION: **EXTRACT → RETIRE.**
- NEW HOME: `alert_bin.py` (drafts/proof), `handoff.py` (promotion surface).
- RETIREMENT CONDITION: BIN1 live; tests ported.
- VALIDATION: BIN gate tests; wiki-writeback path preserved via HND.

### `continuous_eval.py` (337 lines) — RETIRE

- CURRENT ROLE: test-only in-memory dashboard/corpus helpers.
- VALUABLE PRIMITIVES: the *intent* (regression-corpus growth, dashboard
  data) — realized properly by SUB + PLT + SCORE.
- DISPOSITION: **RETIRE** once SCORE/PLT produce the readouts. No extraction
  (in-memory stores have no content worth moving).
- RETIREMENT CONDITION: SCORE/PLT live; `test_continuous_eval.py` superseded.
- VALIDATION: SCORE/PLT readout tests.

### `unknown_defense.py` (520 lines)

- CURRENT ROLE: U1 lexical similarity (wired into purple as flags), U2
  investigation bridge, U3/U4 baseline/anomaly (dormant — no baselines), U6
  expanded outcome space.
- CURRENT CALLERS: `blue.py::_run_unknown_defense:1450-1513`,
  `blue_orchestrate.run_similarity`, tests.
- VALUABLE PRIMITIVES: grading vocabulary (EXACT/SIMILAR/NONE →
  SAME/SIMILAR/…), `SimilarityResult` shape with `overlapping_features`
  (the explanation layer), `route_to_investigation` intake shape, U6 outcome
  space, U3 `BaselineProfile` concept.
- FUTURE ROLE: BR-COUSIN owns grading (semantic composite); the
  feature-overlap layer is preserved as explanation; U3/U4 baseline concept
  is realized properly in BR-DRIFT/SUB; U6 outcome space is subsumed by the
  cousin grade space.
- DISPOSITION: **RETROFIT → MERGE** into `cousin_engine.py` (vocabulary +
  explanation) and `drift_engine.py` (baseline concept). The lexical scorer
  itself is kept as the explanation/citation compute and as the documented
  baseline the composite must beat (success criterion 1).
- COMPATIBILITY: purple flags path stays until LOOP1; then `_run_unknown_defense`
  routes to BR-COUSIN.
- RETIREMENT CONDITION: BR1 live + comparison evidence recorded.
- VALIDATION: cousin-engine calibration tests (VALIDATION doc).

### `capability_graph.py` (556 lines)

- CURRENT ROLE: ephemeral graph + gap classifier, rebuilt per invocation by
  compliance/validation/dashboards.
- VALUABLE PRIMITIVES: `classify_gap` (`:76-123`), gap axes model, coverage
  artifact renderers.
- FUTURE ROLE: gap classification over **SUB-persisted cells**; graph becomes
  a readout (rebuilt on demand from SUB), not a store.
- DISPOSITION: **RETROFIT** — add a SUB-backed loader; keep classifiers.
- RETIREMENT CONDITION: never (readout role persists).
- VALIDATION: AI check (capability graph + gap engine) stays green.

### `field_journal.py` (209 lines)

- CURRENT ROLE: in-git JSON engagement memory; keyword recall; behavior read
  only by `capability/index.py::_journal_prior_score`.
- FUTURE ROLE: unchanged for the red-side loop; the bully treats it as a
  **source** (PLAY/HARV read reusable patterns), never as the store.
- DISPOSITION: **LEAVE_ALONE** (out of scope to move/replace; SUB supersedes
  its *role* for the bully without touching its files).

### `investigation/` (evidence.py, case_notebook.py, agents.py, bench_investigation.py)

- CURRENT ROLE: investigation bench scaffolding; EvidenceStore in-memory;
  CaseNotebook SQLite with supersede; agents.py is a documented structural
  stub ("do not resurrect" — its own docstring).
- VALUABLE PRIMITIVES: `EvidenceRecord` schema (provenance, source authority,
  supports/contradicts), `CaseNotebook` SQLite+supersede pattern, the
  seven-memory-kind doctrine (`case_notebook.py:1-17` — esp. "agent long-term
  memory NOT PERMITTED at inference", "prior-incident library analyst-confirm-only").
- FUTURE ROLE: schema + pattern seed SUB; the doctrine is adopted as SUB/ORG
  memory rules.
- DISPOSITION: **EXTRACT (patterns) / LEAVE_ALONE (files).** The bench keeps
  its toys; the bully does not depend on them.

### `notify_scoreboard.py` (494 lines)

- DISPOSITION: **REUSE+EXTEND** into `hunt_scoreboard.py` — preserve
  NOTIFY_VERDICTS equality, trust ranks, benign false-flag typing (BN/BQ);
  add distance-weighted discovery axes.
- VALIDATION: BN stays green against the original module (unchanged); the new
  scoreboard has its own tests.

### `recall_attribution.py` (339 lines)

- DISPOSITION: **REUSE** as HARV's eval-side honest-miss labeler. BM boundary
  preserved: production code never imports it (BM check asserted on
  `spl_detections.py`; the same boundary discipline applies to new bully
  modules — see VALIDATION).

### `drift_gate.py`

- DISPOSITION: **REUSE/RETROFIT** — its rolling-window statistics pattern
  seeds `drift_engine.py`; the gate itself (bench-metric drift, `drift-check`
  CLI, AN check) is untouched.

### `siem/blue_triage.py`

- DISPOSITION: **REUSE** as the G3 measurement lane. May need a
  queue-load corpus runner wrapper (part of BIN build); the lane itself is
  unchanged.

### `emergent_gaps.py` (80 lines)

- DISPOSITION: **REUSE** as MUT's off-script supply (unchanged feed into the
  gap stream; LOOP consumes).

### Platform assets

| Asset | Disposition |
|---|---|
| `router/council.py` | REUSE (mechanics). No edits needed — HEART imports `parse_opinion` + participation math and implements its own aggregation |
| `portal/platform/agent/*` | LEAVE_ALONE (evaluated and rejected as LOOP's base — REVIEW §25) |
| `cli/models.py` | REUSE (`import-gguf` mechanism in TRAIN) |
| `candidate_eval.py` / `intake.py` / bench harness / `execute_local_sec_bench.sh` | REPOSITION unchanged as the TRAIN acceptance gate |
| wiki (`portal_wiki/`, provenance ledger, writeback) | REUSE: provenance ledger for promotions; spine stays design-facts-only |
| `notifications` platform | REUSE (I-20) |

## Retirement summary

| Retires | When | Replacement proven by |
|---|---|---|
| `council_agreement.py` (bully role) | HRT1 | HEART objection-gate tests + BL/BO/BE/BP green |
| `growth_loop.py` | BIN1 | BIN gate tests incl. real G1a/G1b |
| `response_loop.py` | HND1 | HND package tests |
| `continuous_eval.py` | PLT1/SC1 | SCORE/PLT readout tests |
| `unknown_defense.py` U1 scorer (grading role) | BR1 | composite-engine calibration + comparison evidence |
| blue/blue_orchestrate *driver* role | LOOP1 | hunt-loop integration tests + bench parity |
| `agentic_blue_eval.Episode` name collision | LOOP1 | comment/doc reconciliation (no behavior change) |

No current path is silently orphaned: every caller of a retiring module is
listed above, and each retirement is gated on its replacement's validation.
