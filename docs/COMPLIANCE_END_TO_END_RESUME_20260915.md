# COMPLIANCE_END_TO_END_RESUME_20260915

**Task:** `coding_task/v9_compliance/TASK_COMPLIANCE_REASONING_PRODUCT_END_TO_END_V1.md`
**Session:** resumed at Phase 4 on 2026-09-15, executed Phases 4–9 to
completion, wired and verified Phase 10 through its live-run launch, then
stopped for review by operator request.
**Branch at stop:** `main` @ `10ca0406` (pushed).
**Master report:** `reports/compliance/COMPLIANCE_REASONING_PRODUCT_END_TO_END_V1.md`
**Foundation report:** `reports/compliance/PRODUCT_CONTRACT_AND_SOURCE_SYNC_V1.md`
(marker `PRODUCT_FOUNDATION_READY` is declared there)

---

## 1. What was done (phase by phase)

### Phase 4 — truthful internal revisions and source functions — `3ff50ab1`
- New `core/internal_corpus.py`: control-block metadata parser (title, document
  number/ID, stated type, NERC standard, effective date, owner/title, approver/
  approval date, version + authored date from the revision-history latest row,
  latest review date — every field page-sourced, absent stays absent, never
  guessed from a filename) and the section-function classifier over the
  controlled `SOURCE_ROLES` vocabulary (operative body, traceability appendix
  subtrees, ToC, document-control pages, definitions, commentary). Guards:
  numbering continuity (appendix table rows re-using referenced numbers like
  `3.1` stay inside the appendix), revision-history cutoff, numbered content
  items never become sections.
- Migration 10: `document_revisions.document_number/version/owner/owner_title`,
  `source_sections.title`, `relationship_assertions.derivation` (all additive;
  live store v9→v10 on a pre-v10 snapshot).
- `scripts/materialize_internal_corpus.py`: all 68 on-disk controlled documents
  hash-matched the store; 2508 revision-scoped classified sections persisted;
  the legacy whole-document section of each document typed with its role.
- Quarantine (L19): all 1342 legacy folder-derived proposals tagged
  (`folder_cartesian` 1070, `folder_placeholder_org` 272); `impact.analyze`
  computes established impact from **approved** edges only, proposals surface
  as labeled `discovery_candidates`.
- Commitment gating (L18): `extract_assertions` yields commitments only from
  operative roles — copied NERC rows can never become implementation.

### Phase 5 — two clocks and projections operational — `fb473750`
- New `core/temporal_selection.py`: governing revisions resolve from canonical
  `effectivity_assertions` under BOTH `valid_at` and `known_at`. A fact true
  but not yet recorded answers `UNKNOWN_KNOWLEDGE`; corrections replay
  before/after without mutation; `store_nodes_for_revisions` resolves verbatim
  clauses for revisions the pinned register lacks (CIP-007-7.1).
- Traversal clocks: `valid_at`/`known_at` predicates on
  `list_relationship_assertions` + `traverse_relationships`; unknown
  `valid_from` is never "always valid" (F02); `trace`/`impact` disclose a
  temporal exclusion census.
- Routed `compliance_requirement`: `revision_selection`
  (selected/future/historical/unknown_knowledge) + parts withheld as
  UNKNOWN_KNOWLEDGE when the requested `known_at` precedes their recording.
- New `core/projections.py`: deterministic canonical store fingerprint;
  `index_manifests` generations; FRESH/STALE/ABSENT verdicts (L14).
- `scripts/rebuild_compliance_projections.py`: live rebuild — retrieval 68
  files / 2636 chunks, materialization PROVEN by a live search (5 hits, L07);
  graph 292 nodes / 255 edges; both manifests FRESH @ fingerprint `2b9b6e44…`.
  Receipt: `coding_task/v9_compliance/private/projections/rebuild_20260915.json`.

### Phase 6 — foundation routed acceptance → `PRODUCT_FOUNDATION_READY` — `5c7317ac` + `0e84a88f`
- Managed restart of the deployed service (launchctl kickstart), served commit
  recorded; **all 8 P7 routed observations pass over HTTP** (current/
  historical/future selection, two-`known_at` late-recorded reproduction,
  complete R2.1–R2.4 bundles with Measures + Technical Basis + fingerprints,
  R2.3 35-day deadline + alternatives, R2.4 CIP Senior Manager exception,
  patch-procedure section functions with Appendix-1 rows as
  TRACEABILITY_ASSERTION, default trace approved-only). Receipt:
  `coding_task/v9_compliance/private/foundation_routed/20260915T183311Z/routed_observations.json`.
- New routed surfaces: `compliance_bundle` (deterministic governing bundle, no
  model calls) and `compliance_sources(include_sections)`.
- Foundation report published; 10/10 exit criteria verified there.

### Phase 7 — the compound CIP-007 R2 analysis plan — `5e47db91`
- New `core/vertical_slice.py`: ONE immutable analysis context (4 bundles
  fingerprinted, snapshot + index generation, both clocks, scope, model/prompt
  config) and a deterministic seven-operation plan (requirement_duties →
  implementing_clauses → alignment → gaps → evidence_connections →
  temporal_diff → scenario). No keyword routing can drop components. A
  defective bundle (U14) raises at plan-build time. `execute_plan` records
  every operation id and never composes answers from steps that did not run.

### Phase 8 — reading-first verdicts + source-function closure — `2a64bffe`
- `assess_part` restructured: **the reading judgment IS the verdict.** The
  pre-reading alignment gate is gone (neither an invalid alignment pass nor an
  UNKNOWN substantive link can veto the read — the old U09 path; the U12
  incomparable unresolve retired with it). Alignment now runs AFTER the
  reading as a retained diagnostic (receipt + council-packet binding
  outcomes); applicability is computed deterministically from the governing
  applicable-systems text and declared scope. The council stays a cross-check
  (ESCALATE with votes still routes S04 disputes to review).
- New `core/candidate_closure.py`: candidates entering the reader packet carry
  their classified source function, canonical revision id, `revision_current`,
  and a non-operative note; sibling/neighbor closure; exact-mapping metadata
  labeled governance-only; declared-corpus boundary receipt (complete only
  when every declared document is registered).
- Acceptance manifest cases 15/24 re-derived BEFORE any live run (documented
  in their `notes`): both stay UNRESOLVED; only the naming code changes
  (U12/U09 → U11) because those gates no longer exist. The INCOMPARABLE
  arithmetic diagnostic is still asserted.

### Phase 9 — deterministic duty-level verification — `48ec42d0`
- `verify_judgment` demotes non-operative citations
  (`READING_NON_OPERATIVE_CITED_AS_IMPLEMENTATION`) and superseded-revision
  citations (`READING_STALE_REVISION_CITED`); `verified_support` now requires
  operative + current support.
- Same-duty quantitative direction after identity: literal operands in both
  cited sides → `compare_constraint` classifies EQUIVALENT /
  MORE_RESTRICTIVE / LESS_RESTRICTIVE / INCOMPARABLE. 35→40 lands PARTIAL
  (never a different-duty escape); 30 lands STRICTER with unused flexibility
  reported.
- Separated per-duty outcomes: ALIGNED / PARTIAL / MISALIGNED / STRICTER /
  EVIDENCE_ONLY / CONFLICT + judgment-level conflict and unused-flexibility
  flags.
- Full battery green: positive, minimal counterexamples (40-day, removed
  alternative, changed approver), copied-text, ToC repeats, decoy+operative
  mix, stale revision, internal-conflict retention, boundary-absence downgrade.

### Phase 10 — live vertical slice (wired; live run NOT yet completed)
- `4a1b6694`: `core/revision_compare.py` (store-based semantic 6→7.1 delta —
  duties paired by normalized-text correspondence, obligation taxonomy,
  verbatim before/after clauses) + `core/slice_executor.py` (executes the plan
  with real primitives; persists reading-derived duty→implementation edges as
  proposed `derivation='semantic_reading'`) + `compliance_analyze`
  `analysis_plan=seven_question_cip007_r2` (routed, sync, optional
  `scenario_edits`/`scenario_part_id`).
- `1f51524f`, `c68c1c47`, `10ca0406`: runner + two live-run fixes (below).
- `cb647abd`: smallest-live-case probe.

## 2. What was observed

- **Validation progression:** unit suite 1921 → 1948 (P4) → 1963 (P5) → 1972
  (P7) → 1981 (P8) → 1990 (P10 wiring) passed, 4 skipped; ruff + format +
  complexity + spine/wiki gates green at every commit.
- **Live single-Part probe** (`scripts/probe_single_part_live.py`, receipt
  `coding_task/v9_compliance/private/seven_question/probe_2p2.json`):
  CIP-007-6 R2 Part 2.2 through the restructured path with the real
  production reader — **documentary_coverage FULL, 3 duties enumerated, all
  COVERED, 0 gaps, council SUPPORTED, reading valid** — in 2951.6 s (~49 min)
  on the local Qwen3.8-27B. This is the calibration for the full arm
  (~3.3 h for 4 Parts + scenario).
- **Failures found and repaired this session** (all with guards):
  1. Migration-10 comment contained a semicolon — the runner splits on `;`
     (`near "empty"`); the exact migration-8 trap. Rewritten semicolon-free.
  2. `InternalSection.section_id` omitted the revision id — 68 documents
     sharing heading paths collided; only 1037 of 2531 sections survived with
     cross-revision references. Fixed (id hashes revision|path|page|role) and
     the store re-materialized (2508 sections, 0 shared ids).
     Regression: `test_section_ids_are_scoped_to_the_revision`.
  3. First routed live launch died in 6 s (`'R' object has no attribute
     'snapshot'`) — the packet-building request in `implementing_clauses`
     lacked a snapshot attribute. Fixed (`1f51524f`).
  4. **The arm reaped its own run 34 s in** — `assessment_runs.init_store()`
     runs at import time and sweeps RUNNING runs whose `worker_owner` is not
     provably alive; `run_seven_question` created its run row without one.
     Fixed (`10ca0406`): run rows now record the serving process identity.
     This stall was diagnosed by refusing to wait blind: process sampling
     showed no model generation, then the smallest live case isolated the
     machinery before any further expensive attempt.
- **Model throughput measured:** ~49 min/Part (reading + council + alignment
  diagnostic on local Ollama). Full arm ≈ 3.3 h; keep the scenario as a
  separate routed call to stay under the 4 h HTTP client timeout.
- **Two live runs were abandoned and retained as INTERRUPTED** (rows
  `f0abae2a…`, `5bb632f2…`, `eac51749…`) — evidence of the pre-fix state; the
  fixes above are why relaunching is now expected to complete.

## 3. Where to resume

**Phase 10 remains: run the live arm, inspect everything, write the slice
report, and declare `CIP007_R2_PRODUCT_PROOF_COMPLETE`.** Concretely:

1. (Service is deployed at `10ca0406` — kickstart + health check, record PID
   and served commit.)
2. Launch the routed arm WITHOUT the scenario (≈3.3 h):
   `nohup uv run python scripts/run_seven_question_routed.py > /tmp/sq.log 2>&1 &`
   — monitors: `analysis_runs` row stays RUNNING (worker_owner now recorded),
   `assessment_results` rows appear per Part (~49 min cadence), receipt lands
   under `coding_task/v9_compliance/private/seven_question/<stamp>/`.
3. Then run the scenario separately (≈50–70 min):
   same script with `--scenario` (isolated ADD to the patch WI; before/after
   coverage in the receipt).
4. Inspect every R2.1–R2.4 duty, finding, citation, trace path, diff row,
   impact and the scenario before/after against exact sources (slice §9.10 —
   inspect, not sample).
5. Prove reverse traversal from an internal node to the governing duties
   (the run persists `semantic_reading` proposed edges; `compliance_trace`
   with `include_proposed=true`).
6. Write `reports/compliance/CIP007_R2_VERTICAL_SLICE_V1.md` per slice §10
   (source/snapshot inventory, executed plan, per-duty rows with anchors,
   retrieval/source-function inspection, counterexample matrix, trace/diff/
   impact/scenario examples, call counts + latency, receipts, defects, the
   explicit not-ready-for-cross-standard statement, lessons ledger).
7. Record `CIP007_R2_PRODUCT_PROOF_COMPLETE` in the master report ledger and
   continue to Phases 11–16 (`TASK_COMPLIANCE_MODEL_QUALIFICATION_AND_SCALE_V1`):
   11 freeze qualification harness → 12 qualify reader/critic
   (`MODEL_ROLES_QUALIFIED`) → 13 shadow/activate/regress → 14 scale one
   standard at a time (`CROSS_STANDARD_ENGINE_PROVEN`) → 15 twelve questions
   (`TWELVE_QUESTIONS_ROUTED_COMPLETE`) → 16 final sweep + closeout
   (`COMPLIANCE_PRODUCT_ENGINEERING_COMPLETE`).

**Standing notes for the resuming session:**
- The production primary reader is `qwen38` (council.yaml seat 1); seat swaps
  on 32 GB hardware dominate latency — keep monitoring via
  `GET http://127.0.0.1:11434/api/ps` `eval_count` (idle None between calls
  is normal; persistent None across minutes with a loaded model means the
  pipeline is between stages, not stuck — compare against the per-Part cadence).
- Never `git add -A`: `data/private/` (store backups, official bytes) and
  `coding_task/v9_compliance/private/` (receipts) stay out of Git.
- Pre-commit's wiki regeneration may rewrite `portal_wiki/canonical/*.md`
  (tool counts) and the spine manifest resets new-file surfaces to
  `unit-code-missing` until the new module is cited in
  `portal_wiki/canonical/unit-compliance-engine.md` AND the file is tracked —
  cite first, then `--write-manifest`, then commit.

## 4. State at stop

- Branch `main` @ `10ca0406`; working tree clean of phase-owned paths.
- Deployed service: launchctl `com.portal5.compliance-mcp`, serving `10ca0406`.
- Live arm: stopped mid-Part-2.1 (~20 min of ~49); run row
  `eac517497ad34421` explicitly marked INTERRUPTED with the other two
  abandoned rows retained. Nothing in-flight survives the stop.
- Test baseline at stop: 1990 passed / 4 skipped; ruff clean; format clean.
