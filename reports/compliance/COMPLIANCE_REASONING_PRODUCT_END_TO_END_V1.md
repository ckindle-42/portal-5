# COMPLIANCE_REASONING_PRODUCT_END_TO_END_V1 — master execution report

**Task:** `coding_task/v9_compliance/TASK_COMPLIANCE_REASONING_PRODUCT_END_TO_END_V1.md`
**Program:** `PROGRAM_COMPLIANCE_REASONING_PRODUCT_V1`
**Terminal exit (target):** `COMPLIANCE_PRODUCT_ENGINEERING_COMPLETE`

---

## 0. Execution ledger

| phase | scope | state | commit |
| --- | --- | --- | --- |
| 0 | reconcile reality, freeze ledger, this report | **DONE** | `c52edc8f` |
| 1 | product/result contract (foundation P1) | **DONE** | (this commit) |
| 2 | official NERC source sync (foundation P2) | pending | |
| 3 | complete regulatory semantics (foundation P3) | pending | |
 | 4 | internal revisions and source functions (foundation P4) | pending | |
| 5 | two clocks + projections (foundation P5–P6) | pending | |
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
| L13 | omitted bundle components (Measures/TB/lead-ins) | required-component readiness + negative tests | FAIL → Phase 3 (Measures/TB into bundle; negative readiness) |
| L14 | stale dependent annotations after fragment repair | same-fingerprint rebuild of dependents | FAIL → Phase 5 (projection invalidation tests) |
| L15 | duty identity conflated with adequacy (40d≠35d duty) | semantic correspondence before quantity compare | **PASS** — reading prompt + `constraints.compare_constraint`; minimal-pair cases re-run Phase 9 |
| L16 | spliced/token-overlap quantities | literal operand in one cited phrase | **PASS** — `reading._operand_is_in_source` + acceptance cases |
| L17 | empty top-k = absence | boundary receipt requirement | **PASS** — `reading._unprovable_absences` + case 13; corpus-boundary closure Phase 8 |
| L18 | copied regulation row = implementation | source function carried end-to-end | FAIL → Phase 4 (internal source-function classification) + Phase 8 |
| L19 | Cartesian folder mappings in trace/impact | discovery-only, excluded from established trace | FAIL → Phase 4 (quarantine 1338 proposed assertions) |
| L20 | approval overrides fresh comparison | approval = governance, not truth | **PASS (behavior)** — no approval prerequisite on the reading path; stale-mapping regression Phase 5 |
| L21 | `known_at` echoed, not applied | both clocks on every operation | FAIL → Phase 5 (two-clock operational + replay tests) |
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

| date | failure | repair | guard |
| --- | --- | --- | --- |
| (pre-baseline, retained) | L-document family UNRESOLVED ×4 via old three-gate architecture | reading judgment `b1612cd2`/`5f5f93b8` | 26-case suite + live replay `5ae8ffe1` |
| (pre-baseline, retained) | harness supplied no boundary receipt → own OMISSION rule voided correct reads (case 20) | boundary-receipt plumbing | acceptance fixtures carry receipts |
| 2026-09-14 (this phase) | deployed compliance MCP stale vs HEAD (started 02:41, HEAD 21:28) — operator question still returns UNRESOLVED ×4 from stale code | scheduled: restart from final foundation commit in Phase 6 with recorded identity | L22 row above; Phase 6 routed receipts must record served commit |
| 2026-09-14 (Phase 1) | `_reconcile_reading_and_council` emitted `U12_READING_COUNCIL_DISAGREEMENT`, which is not in `UNRESOLVED_CODES` — a genuine reading/council disagreement would have raised `DeterminationContractError` in `AssessmentResult.__post_init__` instead of producing a reviewable result | switched to the new `U17_INTERPRETIVE_CONFLICT` with both records + reading slice ids retained in `missing_fact` | `test_compliance_result_contract.py::test_reading_council_disagreement_is_a_valid_unresolved_result` |
| 2026-09-14 (Phase 1) | the migration runner splits DDL on `;`, so a `;` inside a SQL comment breaks the migration (hit while writing v8) | comment text rewritten semicolon-free; NOTE recorded in the migration file itself | `test_migration_eight_is_non_destructive`, `test_migration_from_a_populated_v7_store` |

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
