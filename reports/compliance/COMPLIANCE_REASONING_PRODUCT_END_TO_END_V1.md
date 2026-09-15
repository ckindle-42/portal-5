# COMPLIANCE_REASONING_PRODUCT_END_TO_END_V1 — master execution report

**Task:** `coding_task/v9_compliance/TASK_COMPLIANCE_REASONING_PRODUCT_END_TO_END_V1.md`
**Program:** `PROGRAM_COMPLIANCE_REASONING_PRODUCT_V1`
**Terminal exit (target):** `COMPLIANCE_PRODUCT_ENGINEERING_COMPLETE`

---

## 0. Execution ledger

| phase | scope | state | commit |
| --- | --- | --- | --- |
| 0 | reconcile reality, freeze ledger, this report | **DONE** | `c52edc8f` |
| 1 | product/result contract (foundation P1) | **DONE** | `626aa18d` |
| 2 | official NERC source sync (foundation P2) | **DONE** | `3ef77f88` |
| 3 | complete regulatory semantics (foundation P3) | **DONE** | `2d3ec5a8` |
 | 4 | internal revisions and source functions (foundation P4) | **DONE** | `3ff50ab1` |
| 5 | two clocks + projections (foundation P5–P6) | **DONE** | `fb473750` |
| 6 | foundation routed acceptance — `PRODUCT_FOUNDATION_READY` | pending | |
| 7 | compound R2 analysis plan (slice P1) | pending | |
| 8 | candidate closure + reading packet (slice P2–P3) | pending | |
| 9 | duty-level judgment + verification (slice §5.4/6) | pending | |
| 10 | trace/change/scenario + live slice — `CIP007_R2_PRODUCT_PROOF_COMPLETE` | pending | |
| 11 | freeze qualification harness (model/scale P1) | pending | |
| 12 | qualify reader/critic — `MODEL_ROLES_QUALIFIED` | pending | |
| 13 | shadow, activate, regress | pending | |
| 14 | cross-standard scaling — `CROSS_STANDARD_ENGINE_PROVEN` | pending | |
| 15 | twelve questions — `TWELVE_QUESTIONS_ROUTED_COMPLETE` | pending | |
| 16 | final sweep + closeout — `COMPLIANCE_PRODUCT_ENGINEERING_COMPLETE` | pending | |

## 1. Refreshed baseline (measured 2026-09-14 ~23:00 CDT)

### 1.1 Repository

- Branch `main` @ `511c3969` (2026-09-14 21:28:30 -0500). Up to date with `origin/main`.
- Worktree: two modified docs — the supersession notices that redirect the two
  2026-09-14 reading tasks to this entry point. Task-owned; committed with Phase 0.
- No other concurrent work; no active compliance campaign processes.

### 1.2 Deployed services

| surface | mechanism | identity | state |
| --- | --- | --- | --- |
| Compliance MCP (the deployed compliance route, :8937) | launchctl `com.portal5.compliance-mcp` | PID 86268, started 2026-09-14 02:41:05 CDT | **STALE vs HEAD** — predates `b1612cd2`…`511c3969` (tonight 19:59–21:28), so it cannot contain the reading-judgment product path |
| Portal pipeline (:9099) | docker `portal5-pipeline` | image built 2026-09-12 | healthy (12/12 backends); compliance is NOT served from this container |
| Ollama (:11434) | host | 78 models | council roster models + all shortlist candidates present (mistral-small3.2 Q4, Magistral Q8, gpt-oss:20b, gemma4:26b-a4b, glm-4.7-flash ctx64k) |

### 1.3 Canonical store

`portal/modules/compliance/data/compliance_store.db` (gitignored, 11 MB, WAL),
schema_version **7**, 37 tables. Selected counts:

| table | rows | note |
| --- | --- | --- |
| requirement_nodes | 254 | matches register |
| standard_revisions | 28 | 14 families, duplicated logical/import identities; **no CIP-007-7.1** |
| source_documents / document_revisions | 82 / 82 | exactly one revision per logical document |
| obligation_atoms / obligation_expressions | 310 / 254 | decomposition in store |
| relationship_assertions | 1339 | **1338 `proposed` + 1 `revoked`** — the Cartesian folder/standard materialization; none approved |
| analysis_runs / assessment_results / findings / claim_evidence | 484 / 487 / 1061 / 2559 | historical runs |
| corpus_snapshots / index_manifests / evidence_artifacts / policy_decisions | 0 | empty projections |

Temporal reality: `relationship_assertions.valid_from/valid_to` 100% NULL;
`recorded_from` 100% set, `recorded_to` NULL. `document_revisions.effective_date`
0/82 set. **The two clocks are not operational anywhere.**

### 1.4 Register and source corpus

- `data/nerc_cip_register.json`: 254 nodes (232 `part`, 22 `requirement`
  granularity), **99 with `measure_text`**, `node_type` empty on all (typed by the
  policy graph at build time), 14 pinned source PDFs in `data/cip_pdfs/`
  (gitignored), incl. `cip-007-6.pdf`. No CIP-007-7.1 material anywhere.
- Operator corpus on disk: 10 controlled PDFs under
  `coding_task/v9_compliance/LSPG-CIP/CIP-007/` (patch procedure V11, patch WI v7,
  patching validation WI v3, plus 7 other documents). Private; never committed.

### 1.5 The operator question — before-state trace

Last deployed-route receipt
(`coding_task/v9_compliance/private/reading_route/20260914T074108394845Z`,
run `f4e11d2c8471445c`, effective_on 2026-09-12, produced by the stale server):

```
CIP-007-6 R2 Part 2.1 -> UNRESOLVED
CIP-007-6 R2 Part 2.2 -> UNRESOLVED
CIP-007-6 R2 Part 2.3 -> UNRESOLVED
CIP-007-6 R2 Part 2.4 -> UNRESOLVED
```

This is the failure that started the program, still the live deployed answer
because the service predates the reading-judgment commits. At HEAD, the in-process
live family replay (`5ae8ffe1`, `reports/compliance/LDOC_FAMILY_LIVE_REPLAY.md`)
reads the L-family 12/12 with 4/4 cases carrying at 2-of-3 quorum — but that is
not the deployed route. Closing this gap is Phase 6/10 work (restart from final
commit, rerun, retain receipts).

### 1.6 Production reader identity (confirmed)

`reading.read_and_judge` resolves its model as: explicit `model` arg →
`context.report_model` → `context.seats[0].model`. In production
(`runtime_config.build_assessment_context`) the seats come from
`config/compliance/council.yaml`, so **the actual production primary reader is
`qwen38` (Qwen3.8-27B Q4_K_M ctx32k)** — not mistral. Mistral is seat 3 of the
council (cross-check role). The 2026-09-14 seat-replacement diagnosis therefore
describes a *council seat*, not the primary reader; Phase 12 must still qualify
the primary reader against the reading contract (its evidence is from the old
question too).

### 1.7 Carried code-level gaps (verified against HEAD, not assumed)

1. **Measures never reach the reader.** `GoverningBundle`
   (`core/determination.py:353`) has no `measures` field;
   `resolve_governing_bundle` (`core/assessment_source.py:94`) never populates
   one; `build_reading_packet` (`core/reading.py:189`) reads
   `getattr(governing, "measures", "")` → always `""`. 99/254 register nodes
   carry Measures text. (Phase 1–3 close this.)
2. **Technical Basis absent** from the assessment path entirely. (Phase 2–3.)
3. **Council framing stale** (`core/council.py` `_SEAT_SYSTEM` "PRE-ANALYZED"
   packet, one-sentence rationale cap, ABSENT completeness rule) and
   `core/gate.py:94-95` "pre-analyzed problem, never raw text" — now
   cross-check/diagnostic only; text still wrong. (Phase 8–9 cleanup.)
4. **Legacy alignment gates** D2–D5 remain in `core/obligation_alignment.py`
   (D1 `is_substantive` already promoted); D4's premise is invalidated by the
   resume doc §1 (malformed question no longer on the verdict path) — re-examine
   before implementing. (Phase 9.)
5. **Substring answer matching** `council.py:173`. (Phase 11+ harness hygiene.)

### 1.8 Test baseline

`uv run pytest tests/unit/ -q` @ `511c3969`: **1848 passed, 4 skipped**
(199 s). Reading suites present: 26-case acceptance manifest
(`tests/data/compliance_reading_acceptance.json`, engine
`compliance-reading/1`, effective_on 2026-09-12), reading judgment/transport/
live-runner tests (51 compliance test files total).

## 2. Lessons recurrence ledger (instantiated)

Status values: PASS (exact reference) · FAIL (blocks the named dependent phase;
closure owned by that phase) · NOT_APPLICABLE (reason). Updated per phase below.

| # | lesson (program §5 row) | control | status @ P0 |
| --- | --- | --- | --- |
| L01 | task/design file treated as proof architecture was right | re-derive operational question from live route (§1.5) | **FAIL → Phase 6/10** (deployed route still UNRESOLVED ×4; in-process replay correct) |
| L02 | refining pipeline before the full use case | question-to-primitive coverage ledger | FAIL → Phase 15 (twelve-question ledger) |
| L03 | HTTP 200/hermetic pass ≠ live acceptance | deployed-route receipts w/ substantive findings | FAIL → Phase 6 (P7 routed observations) |
| L04 | latest-row instead of exact run-ID | ID-scoped verifier queries + concurrent-run regression | **PASS** — `tests/unit/test_compliance_assessment_runs.py` (run-ID isolation suite); re-exercised Phase 6 |
| L05 | `nohup` reaped / failed launchctl restart | durable launcher, monitor, bootout | **PASS (operational)** — launchctl `com.portal5.compliance-mcp` managed; failed-job bootout exercised Phase 16 |
| L06 | LanceDB first-10-tables | lossless `table_names(page_token=…)` | **PASS** — `40331b57` hermeticity suite + `tests/unit/test_compliance_v3_matrices.py`; live reconciliation Phase 16 |
| L07 | KB materialization believed without proof | post-acquisition query/lookup receipt | FAIL → Phase 2 (acquisition receipts) |
| L08 | generic `UNRESOLVED` matches infra failure | exact controlled failure code + stage | **PARTIAL/PASS** — reading verifier returns controlled codes (`READING_*`); controlled failure-code vocabulary extended in Phase 1 |
| L09 | expensive rerun before stored-trace diagnosis | diagnose retained traces first | **PASS (tool)** — `scripts/replay_compliance_trace.py` byte-exact replay; discipline re-applied each phase |
| L10 | blaming model before packet/harness/transport | one-variable isolation; harness validation first | FAIL → Phase 11 (harness validation experiments) |
| L11 | different base model called a quant control | identical base/revision/template, quant only | FAIL → Phase 12 (Magistral≠Mistral-small3.2 is NOT a valid control; same-base pair required or recorded unavailable) |
| L12 | pre-analyzed council vote ≠ reading evidence | primary reader sees both sides; council = cross-check | **PASS** — `b1612cd2`/`5f5f93b8` (reading path in production); framing cleanup Phase 8 |
| L13 | omitted bundle components (Measures/TB/lead-ins) | required-component readiness + negative tests | **PASS** — `core/regulatory_bundle.py` shape-typed required components; negative test per component (`test_compliance_regulatory_bundle.py`); routed proof Phase 6 |
| L14 | stale dependent annotations after fragment repair | same-fingerprint rebuild of dependents | **PASS** — `projections.projection_status` FRESH/STALE vs canonical fingerprint (`test_manifest_records_fingerprint_and_detects_staleness`); live rebuild both FRESH @ `2b9b6e44` |
| L15 | duty identity conflated with adequacy (40d≠35d duty) | semantic correspondence before quantity compare | **PASS** — reading prompt + `constraints.compare_constraint`; minimal-pair cases re-run Phase 9 |
| L16 | spliced/token-overlap quantities | literal operand in one cited phrase | **PASS** — `reading._operand_is_in_source` + acceptance cases |
| L17 | empty top-k = absence | boundary receipt requirement | **PASS** — `reading._unprovable_absences` + case 13; corpus-boundary closure Phase 8 |
| L18 | copied regulation row = implementation | source function carried end-to-end | **PASS (store/extraction)** — P4 section-role gating (`test_copied_traceability_rows_yield_no_commitments`); packet-surface proof Phase 8 |
| L19 | Cartesian folder mappings in trace/impact | discovery-only, excluded from established trace | **PASS** — P4 `derivation` quarantine (1342 tagged) + approved-only impact (`test_cartesian_quarantine_tags_once_and_excludes_from_impact`); routed proof Phase 6 |
| L20 | approval overrides fresh comparison | approval = governance, not truth | **PASS (behavior)** — no approval prerequisite on the reading path; stale-mapping regression Phase 5 |
| L21 | `known_at` echoed, not applied | both clocks on every operation | **PASS (library+route)** — `temporal_selection` UNKNOWN_KNOWLEDGE semantics + `compliance_requirement` revision_selection/withholding (`test_late_recorded_fact_is_unknown_knowledge_before_recording`); routed receipts Phase 6 |
| L22 | running service ≠ current HEAD | record served commit; restart via managed path | **FAIL (live now)** — deployed MCP predates HEAD by 7 commits; closure Phase 6 restart-from-commit |
| L23 | reused campaign directory skips work | new immutable campaign ID/manifest per campaign | FAIL → Phase 11 (manifest-to-receipt reconciliation) |
| L24 | failures averaged / labels moved post-hoc | frozen manifest, repeats, all attempts retained | FAIL → Phase 11 freeze |
| L25 | engineering triage vs SME decisions conflated | queue classification test + packet inspection | FAIL → Phase 1 (review-queue projection of named reasons) |
| L26 | `null`/falsy/optional coercion semantics | explicit None/empty/zero/false regressions | **PASS** — `efc00c10` (store falsy), `test_the_think_key_is_never_omitted`; extended per Phase 1 |
| L27 | single standard ⇒ generality | one shape at a time + held-out family | FAIL → Phase 14 (support matrix) |

New failure shapes discovered during execution are appended here with their
regression guard in the same phase that repairs them.

### Phase 1 — product/result contract (DONE)

Implemented `core/result_contract.py` + `AssessmentResult`/schema migration:

- **§3.1 truth classes**: `truth_class_of_table()` maps all 33 canonical tables to
  `source_fact` / `derived_assertion` / `organizational_decision`; unmapped tables
  raise rather than guess.
- **§3.2 source roles**: `SOURCE_ROLES` — the full 15-role controlled vocabulary
  with load-bearing meaning text (a Measure reads as evidence context, never an
  extra duty); no numeric authority tier. `source_sections.role` column added
  (migration 8; `''` = unclassified, never guessed).
- **§3.4 separated dimensions**: `AssessmentResult` gained
  `source_readiness`/`temporal_currency`/`documentary_alignment`/
  `implementation_evidence`/`review_required`/`review_reason`, vocabulary-checked
  in `__post_init__`, computed by `dimensions_of()` at `assessment._finalize` (the
  single exit point — every path carries them), persisted as scalar columns
  (migration 8). `documentary_alignment_of()` is the one explicit
  legacy-coverage→alignment map (CONTRADICTION gap ⇒ MISALIGNED).
- **review is an output**: `review_reason_for()` projects only genuine SME
  reasons (S04 interpretive conflict, S01 external scope fact); every
  engineering `UNRESOLVED_*` code yields `review_required=False` — triage, not
  the SME packet. Existing `review_queue.PIPELINE_KINDS`/`sme_packet()` split
  retained.
- **new controlled failure codes**: `U14_INCOMPLETE_SOURCE_BUNDLE`,
  `U15_PROJECTION_MISMATCH`, `U16_INVALID_CITATION`, `U17_INTERPRETIVE_CONFLICT`
  (each names its required payload).
- **repair**: the reading/council disagreement path emitted an unregistered code
  and would have crashed the result contract — now `U17` with both records
  retained; regression added.
- **live store**: migrated 7→8 non-destructively via `Repository()` (additive
  ALTERs only), pre-migration snapshot at
  `data/private/backups/pre-v8-20260914T232533Z.db` (11.2 MB), row counts
  identical before/after, legacy rows read with honest UNKNOWN/NOT_ASSESSED
  defaults, restore-from-backup proven (487 assessment rows recoverable).
- **validation**: `ruff check .` clean · `ruff format --check .` clean ·
  `pytest tests/unit/ -q` **1863 passed, 4 skipped** (15 new contract tests) ·
  mypy clean on touched modules · spine manifest regenerated
  (`python -m portal.platform.wiki.coverage --write-manifest`) after adding
  `result_contract.py` to `unit-compliance-engine` sources.
- Ledger rows closed/strengthened: L08 (controlled codes complete),
  L25 (review projection test), L26 (null/falsy guard on new fields).

## 3. Failure and repair history

### Phase 2 — official NERC source synchronization (DONE)

Implemented `core/nerc_source_sync.py` — fingerprinted acquisition from official
NERC sources:

- **Lifecycle registry**: NERC's One-Stop Shop workbook
  (`nerc.com/globalassets/align-reports/one-stop-shop.xlsx`,
  sha256 `0adda91e…`, retrieved 2026-09-15T10:23Z) parsed into sourced
  `LifecycleFacts` per standard revision — status, board/FERC/order/effective/
  retirement dates, docket, project page, implementation-plan/rationale links.
  The workbook hash is carried on every fact as provenance. 657 standards parse.
- **Measured lifecycle facts** (correcting the store's missing retirement
  boundary): CIP-007-6 = Mandatory Subject to Enforcement, effective
  **2016-07-01**, **inactive (retires) 2028-06-30**, docket RM15-14-000;
  CIP-007-7 = Inactive (replaced by 7.1 via errata, never effective);
  CIP-007-7.1 = Subject to Future Enforcement, effective **2028-07-01** (FERC
  order 2026-03-19, order effective 2026-05-26, docket RM24-8-000).
- **Live bundle acquisition** (all `ACQUIRED`, zero warnings, registered in the
  canonical store as immutable regulatory revisions):
  `cip-007-6.pdf` `5b7820e7…` (**byte-identical to the register's pinned copy**
  — the operator's governing source is verified current against today's
  official revision) · `cip-007-6-implementation-plan.pdf` `8ff922d2…` ·
  `cip-007-7.1.pdf` `c7014e55…` · `cip-007-7.1-implementation-plan.pdf`
  `39829090…` · `cip-007-7.1-technical-rationale.pdf` `6d1ebeb0…` · registry
  workbook. Bytes live under the private hierarchy
  (`data/private/nerc_official/`), written atomically, never mutated; identical
  re-acquisition is `UNCHANGED` (no rewrite, no new revision).
- **Guarantees tested hermetically** (9 tests, saved public fixture of the real
  registry rows at `tests/data/compliance_nerc/one_stop_shop_fixture.xlsx`):
  fingerprint-aware idempotence, failure preservation of the last verified
  snapshot with a dated currency warning, FAILED reporting when no prior
  snapshot exists, immutable-revision registration, absent-standard warning.
- **Known honesty note**: the 7.1 implementation-plan PDF is the 2024 board
  version (`clean_04032024`) and predates FERC's 2026 order, so the plan text
  does not carry the final effective date; **2028-07-01 is sourced from the
  fingerprinted registry** (NERC's own post-order lifecycle record). Both
  artifacts retained with explicit provenance.
- **validation**: `ruff check .` / `format --check .` clean ·
  `pytest tests/unit/ -q` **1880 passed, 4 skipped** · spine manifest
  regenerated · wiki unit updated.
- Ledger rows: L07 (KB/ingestion proof → acquisition receipts + parse-through)
  PASS at module level, routed proof at Phase 6; L22 unchanged (Phase 6).

### Phase 3 — complete regulatory semantics (DONE)

Implemented `core/regulatory_bundle.py` + decomposer rewrite + duty lineage —
the governing side now extracts completely, models its own logic, and refuses
to run on a defective bundle.

- **Bundle extraction** (`core/regulatory_bundle.py`): one module extracts the
  whole semantic content of an official revision — requirement Parts with
  lead-ins and applicable-system columns, per-Part Measures + `M<n>` measure
  statements, the Guidelines and Technical Basis section (per-requirement
  spans, per-Part sub-spans, NERC rationale boxes as separate spans), and the
  definitions disposition. Every span is hash-anchored
  (`RegulatorySpan.verify` re-derives text+sha256 from the revision bytes).
  Marker-based GTB parsing handles the three observed header shapes
  ("Requirement R2:", "Rationale for Requirement R2:", "Rationale for R2:")
  and refuses markers outside a real GTB section (CIP-013-2's duty prose
  contains a "Requirement R2:" phrase that would otherwise fabricate a span).
  CIP-007-7.1's 2024 edition has **no GTB section** — recorded as a revision
  shape fact (`technical_basis_section: absent`), never silently tolerated.
- **Decomposition rewrite** (`core/obligations.py`): multi-atom with verbatim
  clause text + offsets per atom, declared-list-only `ANY_OF`
  ("one of the following" — an incidental "or" can no longer manufacture
  alternatives), explicit/inherited/absent modality (`modality_basis`),
  conditions, exceptions, deadlines, and `Part X.Y` dependencies. Expression
  kinds: `ALL_OF`/`ANY_OF` (≥2 children only), `SINGLE`, `EMPTY` — the
  one-child false-complete container is now structurally impossible.
  `decomposition_defects()` names every way an expression can fail to
  represent the text and feeds readiness.
- **CIP-007-6 R2 verified shapes**: R2.1 `ALL_OF[2]` (process + tracking
  source), R2.2 `SINGLE` with the 35-day cadence + dependency on Part 2.1
  (the old `ANY_OF` from "source or sources" is dead), R2.3
  `ALL_OF[ANY_OF[3 alternatives], mitigation-plan subduty]` with the 35-day
  deadline and the Part 2.2 dependency, R2.4 `SINGLE` with the
  `unless…approved by the CIP Senior Manager` exception.
- **Duty identity + lineage** (`core/duty_lineage.py`): concepts are computed
  from duty-text correspondence (terminology-fold normalizer — "cyber
  security patches"→"security patches", "Applicable Systems"→"applicable
  Cyber Assets", "BCS"→"BES Cyber Systems"; difflib autojunk off — it
  distorted long duties to ~0.47), threshold 0.75, derivation string
  recorded on every concept. CIP-007-6↔7.1: **19 duties pair (0.83–1.00)**;
  genuinely new/changed duties stay unpaired (7.1's new R1 Part 1.3 VCA
  duty; both rewritten R1 Part 1.1s). Concepts root at the oldest member, so
  a future revision joins instead of forking. Part numbers are carried for
  inspection, never used as a matching feature.
- **GoverningBundle + packet** (`core/determination.py`,
  `core/assessment_source.py`, `core/reading.py`): the bundle carries
  `measures`, `technical_basis`, `applicable_systems`, `revision_id`,
  `definitions_disposition`, and a component `readiness` verdict; the dead
  `getattr(governing, "measures", "")` placeholder is gone — Measures and
  Technical Basis reach the reader as labelled context blocks
  ("not an additional duty" / "not binding text"), excluded from
  `selectable_slice_ids`. The reading verifier demotes a context-slice
  citation with `READING_CONTEXT_CITED_AS_DUTY` and strips it from covered
  governing anchors. Definitions: CIP-007 defers to the NERC Glossary —
  recorded as `external_glossary`; the three fabricated
  "Canonical NERC defined term" rows are deleted and never re-created.
- **U14 hard gate**: `build_assessment_request` raises
  `SourceBundleIncompleteError` (U14, per-component payload) on a non-ready
  bundle — an engineering stop, not an SME item. Census after fixes: **all
  255 register nodes READY**.
- **Migration 9** (additive; live store 8→9 after a full backup at
  `data/private/backups/pre-v9-20260915T114116Z.db`, 11.26 MB):
  `obligation_atoms.clause_text`, `obligation_dependencies`,
  `obligation_concepts`. `source_sections.role` now written by the
  materializers (live: 33 `REGULATORY_REQUIREMENT`, 51 `MEASURE`,
  24 `TECHNICAL_BASIS`).
- **Store re-derivation** (same immutable revisions, `L14`): live atoms
  310→378, expressions 254→277 (multi-atom + CIP-007-7.1 duty rows + the two
  new CIP-008-6 R3 parts), 22 dependency rows, 22 concepts. Zero one-child
  containers remain. The stale `CIP-008-6 R3` register-orphan node (and its
  legacy `valid_to=NULL` effectivity rows) removed with its derived rows.
  `materialize_regulatory_bundles.py` registered both official CIP-007
  revisions with role-typed sections + hash-verified spans, asserted
  registry-sourced effectivity (6: 2016-07-01→2028-06-30; 7.1: 2028-07-01,
  replacing the unverified `legacy:` rows), and wrote the R2.1–R2.4
  inspection receipt at
  `coding_task/v9_compliance/private/regulatory_bundles/20260915T115230/inspection.json`
  (all four READY; atoms 2/1/4/1; decomposition defects none).
- **Register regenerated** (`255` nodes, 255/255 fidelity-verified, 0
  completeness holes): the `_table_parts` header-row fix (content-located, so
  7.1-style layouts with empty leading rows parse) exposed that CIP-008-6 R3
  actually has Parts 3.1/3.2 that the register build had missed (that is why
  an R-level placeholder node existed). `nerc_cip_register.json` +
  `nerc_cip_map.json` regenerated through the canonical build CLI.
- **validation**: `ruff check .` clean · `ruff format --check .` clean ·
  `pytest tests/unit/ -q` **1921 passed, 4 skipped** (73 new tests:
  decomposition 13, bundle extraction/readiness negatives 23, lineage 9,
  packet/context-citation 4, plus updated migration/policy-graph pins) ·
  spine manifest regenerated after adding the two new modules to
  `unit-compliance-engine`.
- Ledger rows closed: **L13** (required components by source shape + one
  negative test per component: lead-in, part text, applicable systems,
  measures missing/truncated, TB truncated, TB fact unrecorded, definitions
  disposition, span offsets, revision pin, decomposition defects, mixed
  fingerprint) PASS. **L20/L14 strengthened** (register supersession cleanup;
  same-revision re-derivation replaces derived rows) PASS. L13's routed
  proof remains Phase 6; L18/L19 unchanged (Phase 4).

| date | failure | repair | guard |
| --- | --- | --- | --- |
| (pre-baseline, retained) | L-document family UNRESOLVED ×4 via old three-gate architecture | reading judgment `b1612cd2`/`5f5f93b8` | 26-case suite + live replay `5ae8ffe1` |
| (pre-baseline, retained) | harness supplied no boundary receipt → own OMISSION rule voided correct reads (case 20) | boundary-receipt plumbing | acceptance fixtures carry receipts |
| 2026-09-14 (this phase) | deployed compliance MCP stale vs HEAD (started 02:41, HEAD 21:28) — operator question still returns UNRESOLVED ×4 from stale code | scheduled: restart from final foundation commit in Phase 6 with recorded identity | L22 row above; Phase 6 routed receipts must record served commit |
| 2026-09-14 (Phase 1) | `_reconcile_reading_and_council` emitted `U12_READING_COUNCIL_DISAGREEMENT`, which is not in `UNRESOLVED_CODES` — a genuine reading/council disagreement would have raised `DeterminationContractError` in `AssessmentResult.__post_init__` instead of producing a reviewable result | switched to the new `U17_INTERPRETIVE_CONFLICT` with both records + reading slice ids retained in `missing_fact` | `test_compliance_result_contract.py::test_reading_council_disagreement_is_a_valid_unresolved_result` |
| 2026-09-14 (Phase 1) | the migration runner splits DDL on `;`, so a `;` inside a SQL comment breaks the migration (hit while writing v8) | comment text rewritten semicolon-free; NOTE recorded in the migration file itself | `test_migration_eight_is_non_destructive`, `test_migration_from_a_populated_v7_store` |
| 2026-09-15 (Phase 3) | the census exposed that `resolve_governing_bundle` crashed for attachment-shaped parts (CIP-002/003) — a latent defect at the Phase-0 baseline: lead-in recovery ran `_pdf_parent_requirement` for `requirement="Attachment 1"`, which cannot resolve | lead-in resolution restricted to numbered requirements; attachment shape requires only its own components | readiness census 255/255 READY + `test_attachment_shape_requires_only_its_own_components` |
| 2026-09-15 (Phase 3) | register staleness discovered against its own pinned sources: CIP-008-6 R3 has Parts 3.1/3.2 that the register build missed (empty-leading-row table layout defeated the fixed header-row index), leaving a bogus R-level node | `_table_parts` locates the header row by content; register regenerated via the canonical CLI (255 nodes, 0 holes); superseded store node removed with its derived rows by the materializer | extraction-vs-register diff run over all 14 standards (only CIP-008-6 changed); `test_migration_from_a_populated_v7_store` extended to migration 9 |
| 2026-09-15 (Phase 3) | difflib's default `autojunk` distorted long-duty similarity (true pair CIP-007-6↔7.1 R2.1 scored 0.47, below any sane threshold) | similarity computed with `autojunk=False`; threshold 0.75 pinned by same-duty/different-duty tests | `test_compliance_duty_lineage.py` (same-duty ≥0.75, different-duty <0.5, swapped-number pairing) |
| 2026-09-15 (Phase 3) | CIP-013-2 carries no Guidelines and Technical Basis section, but its duty prose contains "Requirement R2:" — the marker scan fabricated a Technical Basis span from requirement text with the wrong role | markers only count inside a real GTB section (heading-scoped); section-absent is a recorded shape fact | `test_absent_technical_basis_section_is_a_recorded_shape_fact` + census (0 fabricated spans) |

### Phase 4 — internal revisions and source functions (DONE)

Implemented `core/internal_corpus.py` + migration 10 + the discovery-only
quarantine — the internal side of the corpus now resolves to exact revisions
and classified sections.

- **Control-block metadata** (`parse_document_control`): title, document
  number (`Document Number:` and the `Document ID:` variant), stated type,
  NERC standard, effective date, owner/owner-title, approver/approval date,
  version + authored date from the REVISION HISTORY latest row, and the
  latest review-row date. Every field carries page provenance; a field the
  document does not state stays `None`/empty — a filename never invents a
  value. Corpus census: 63/68 effective dates, 61 document numbers, 48
  versions, 67 owners, 64 approval dates sourced; the rest recorded as
  absent (mostly forms).
- **Kind classification** (`classify_kind`): the document's own
  `Document Type:` line wins, filename fallback recorded as such, no signal
  → `unknown`/unknown binding — never a plausible guess. Kinds: 24 work
  instructions, 20 procedures, 5 plans, 4 processes, 1 policy, 5 evidence
  specifications, 9 unknown.
- **Section functions** (`sectionize`): heading-driven sections with full
  dotted paths, page ranges, and hash-verified span anchors, classified into
  the controlled vocabulary — operative body (doc-kind role), copied
  regulation rows under a Requirements Traceability appendix subtree
  (`TRACEABILITY_ASSERTION`), ToC pages (`TABLE_OF_CONTENTS`), owner/
  approvals/revision-history (`DOCUMENT_CONTROL`), definitions, commentary.
  Guards proven on the real corpus: numbering continuity keeps appendix
  table rows that re-use referenced numbers (`3.1`, `3.3`) inside the
  appendix; a revision-history cutoff stops date/author rows re-using
  section numbers; numbered content items never become sections. New roles
  `TABLE_OF_CONTENTS`/`DOCUMENT_CONTROL` added to `SOURCE_ROLES` (vocabulary
  is "at minimum" per contract §3.2).
- **Migration 10** (additive; live store 9→10 after a full backup at
  `data/private/backups/pre-v10-*.db`): `document_revisions`
  .document_number/.version/.owner/.owner_title, `source_sections.title`,
  `relationship_assertions.derivation`. Sourced values fill honest
  placeholders only — a re-run can never clobber a real value.
- **Materialization** (`scripts/materialize_internal_corpus.py`): all 68
  on-disk controlled documents hash-matched their store revisions (zero
  unmatched, zero missing-from-disk); 2508 revision-scoped sections + spans
  persisted; the legacy whole-document section of each document typed with
  its document-level role. Receipt:
  `coding_task/v9_compliance/private/internal_corpus/20260915T171637Z/inventory.json`
  (+ the pre-fix run at `…/20260915T171511Z/`).
- **The quarantine (L19)**: `impact.analyze` computes established impact
  from **approved** edges only — proposed edges return as labeled
  `discovery_candidates` (`derivation`, "discovery-only" note), never in
  direct/transitive. All 1342 legacy folder-derived proposals tagged:
  1070 `folder_cartesian` (IMPLEMENTS node×document per standard folder) +
  272 `folder_placeholder_org`; 0 untagged proposed rows remain, and a
  re-run re-tags nothing (idempotent). `trace()` already defaulted to
  approved-only.
- **Commitment gating (L18)**: `extract_assertions(section_role=…)` — only
  operative roles can yield commitments; the patch procedure's Appendix 1
  copied R2 rows produce zero commitments while its §3.1–3.8 sections
  resolve operative.
- **Exit-condition inspection (store-level)**: patch procedure revision =
  `LSPG-ADM-CIP007SPM` v11.0, effective 2026-07-31, approved 2026-07-24,
  owner Ryan Borg, binding `internally_mandatory`; sections 3.1/3.3/3.5/3.6
  `OPERATIVE_PROCEDURE`, 5.1 `TRACEABILITY_ASSERTION`. The routed proof of
  these classifications is Phase 6 (P7 observations 7–8).
- **validation**: `ruff check .` clean · `ruff format --check .` clean ·
  `pytest tests/unit/ -q` **1948 passed, 4 skipped** (29 new tests) · spine
  manifest regenerated after mapping `internal_corpus.py` (+`impact.py`)
  into `unit-compliance-engine`.

| date | failure | repair | guard |
| --- | --- | --- | --- |
| 2026-09-15 (Phase 4) | migration 10's comment text contained a semicolon ("impact; empty") — the runner splits statements on `;` and executed a comment fragment (`near "empty"`), the exact migration-8 trap | comment rewritten semicolon-free | migration tests (v10 fresh + populated-v9 upgrade); the schema file's own NOTE |
| 2026-09-15 (Phase 4) | `InternalSection.section_id` omitted the revision id — 68 documents sharing heading paths (`1.0` page 1) collided, and only 1037 of 2531 sections survived insertion with cross-revision references | id now hashes `{revision_id}|path|page_start|role`; live store re-materialized and verified (2508 sections, 0 shared ids across revisions) | `test_section_ids_are_scoped_to_the_revision` |


### Phase 5 — two clocks and projections operational (DONE)

Implemented `core/temporal_selection.py` + `core/projections.py` +
`scripts/rebuild_compliance_projections.py` — both clocks now select truth,
and projections carry checkable freshness.

- **Two-clock revision selection** (`select_revision_effectivity`): governing
  revisions resolve from the canonical `effectivity_assertions` (never from
  filenames or the static register snapshot). At `valid_at`:
  SELECTED / FUTURE / SUPERSEDED_OR_RETIRED; under `known_at`, a fact true
  but not yet recorded answers **UNKNOWN_KNOWLEDGE** with its recording time
  named — the late-recorded shape (L21). Correction replay: a correction
  closes the prior row's `recorded_to`, so `known_at` before the correction
  selects the old fact and after selects the correction, no mutation.
- **Routed application** (`compliance_requirement`): responses carry
  `revision_selection` (selected/future/historical/unknown_knowledge); parts
  whose revision's effectivity postdates the requested `known_at` are
  **withheld** (`withheld_as_unknown_knowledge`), so "what applied then given
  what we knew then" genuinely differs from "what we know now". Future
  revisions the pinned register lacks (CIP-007-7.1) resolve from the store's
  own verbatim decomposition clauses. Live checks: `CIP-007-6 R2 Part 2.1`
  SELECTED @ 2026-09-14; withheld (UNKNOWN_KNOWLEDGE) at
  `known_at=2026-09-01`; served at `known_at=2026-09-16`; `CIP-007-7.1 R2`
  FUTURE today and SELECTED with verbatim clauses at 2028-08-01.
- **Both clocks on traversal** (L19/L21): `list_relationship_assertions` and
  `traverse_relationships` accept `valid_at`/`known_at`; an unknown
  `valid_from` is excluded from temporal reads, never treated as "always
  valid" (F02); `trace()`/`impact.analyze()` disclose a
  `temporal` exclusion census so an empty temporal trace is explained, not
  silent.
- **Projection fingerprints** (`core/projections.py`): one deterministic
  `canonical_fingerprint` over the ten truth tables; every projection
  generation records the fingerprint it was built from in `index_manifests`;
  `projection_status` returns FRESH/STALE/ABSENT — a stale dependent
  projection is detectable, never silently consumed (L14).
- **Live projection rebuild** (`rebuild_compliance_projections.py`, receipt
  `coding_task/v9_compliance/private/projections/rebuild_20260915.json`):
  retrieval projection rebuilt over the 68-document operator corpus (2636
  chunks) and **proved materialized** with a live search returning 5 hits
  (L07 — an ingestion count is not proof); graph projection rebuilt (292
  nodes / 255 edges); both generations recorded FRESH against canonical
  fingerprint `2b9b6e44…`. The first ten tables catalog lesson (L06) keeps
  its hermetic regression (`test_compliance_v3_matrices.py`); live catalog
  reconciliation is the Phase 16 final-sweep item.
- **validation**: `ruff check .` clean · `ruff format --check .` clean ·
  `pytest tests/unit/ -q` **1963 passed, 4 skipped** (15 new two-clock and
  projection tests) · spine manifest regenerated.

| date | failure | repair | guard |
| --- | --- | --- | --- |
| 2026-09-15 (Phase 5) | the first `select_revision_effectivity` joined `standard_revisions → document_revisions → requirement_nodes` on hashes, but the store's live linkage runs node-id → `standard_revision_id` text ids (e.g. `CIP-007-6`), so every selection came back empty | selection re-based on the canonical node-level effectivity (the assertion itself), with `standard_revisions` only as display metadata | routed checks above (obs 1/2/4 non-empty) |
| 2026-09-15 (Phase 5) | `effective_now` was evaluated over ALL recorded intervals, so at a post-correction `known_at` the superseded pre-correction interval still selected the revision | interval visibility now requires the requested knowledge time to fall inside the row's recording interval (`recorded_from <= known_at < recorded_to`), defaulting to latest believed rows | `test_corrected_effectivity_replays_before_and_after` |

## 4. Commands and receipts (Phase 0)

```
git status / git log                      # §1.1
curl :8937/health, :9099/health, :11434/api/tags   # §1.2
sqlite3 …compliance_store.db (read-only URI)        # §1.3 counts
python3 (register census)                 # §1.4
uv run pytest tests/unit/ -q              # 1848 passed, 4 skipped, 199 s
```

Retained receipts relied on for baseline:
`coding_task/v9_compliance/private/reading_route/20260914T074108394845Z/`
(the stale-server route result), `reports/compliance/LDOC_FAMILY_LIVE_REPLAY.{md,json}`.

## 5. Premise reconciliation against subordinate tasks

Every stale premise in the three subordinate specs is recorded here and will be
re-measured in its phase, per task rule 5. Confirmed-now (2026-09-14 23:00):
254 nodes / 99 Measures ✓ · no definition nodes ✓ · no CIP-007-7.1 ✓ · single
revision per internal document ✓ · valid/recorded intervals empty ✓ ·
`GoverningBundle.measures` absent in production ✓ · 1338 proposed Cartesian
relationships ✓ · deployed route UNRESOLVED on the operator question ✓ ·
production reader = `qwen38` (new fact, refines the seat-replacement task's
"incumbent" framing).

---

*Phase states, commits, and per-phase validation results are appended below as
each phase completes.*
