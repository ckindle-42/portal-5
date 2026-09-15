# PRODUCT_CONTRACT_AND_SOURCE_SYNC_V1 — foundation report

**Program:** `PROGRAM_COMPLIANCE_REASONING_PRODUCT_V1`
**Task:** `TASK_COMPLIANCE_PRODUCT_CONTRACT_AND_SOURCE_SYNC_V1`
**Executed through:** `TASK_COMPLIANCE_REASONING_PRODUCT_END_TO_END_V1.md` (Phases 1–6)
**Exit marker:** `PRODUCT_FOUNDATION_READY`
**Final foundation commit:** `5c7317ac` (branch `main`)
**Deployed service:** launchctl `com.portal5.compliance-mcp`, PID 64096, started
2026-09-15 13:32:45 CDT, serving commit `5c7317ac` on :8937 (restarted through
the managed `kickstart` path; health verified before observations).

---

## 1. Before/after live inventory

| measure | before (Phase 0 baseline @ `511c3969`) | after (@ `5c7317ac`) |
| --- | --- | --- |
| schema_version | 7 | **10** (additive migrations 8/9/10, no destructive reset) |
| register nodes | 254 (99 with Measures) | 255 (CIP-008-6 R3 Parts 3.1/3.2 recovered; 255/255 fidelity-verified) |
| CIP-007-7.1 material | none anywhere | official bytes registered, 21 store duty nodes, effectivity 2028-07-01, routed future/effective resolution |
| document_revisions dates | 0/82 effective dates | 63/68 internal docs with sourced effective dates (+ owner 67, doc number 61, version 48, approval 64); absent = recorded absent |
| internal binding_effect / kind | all `unknown` | kind classification from the documents' own `Document Type:` lines (24 WI, 20 procedures, 5 plans, 4 processes, 1 policy, 5 evidence specs, 9 unknown); operative docs `internally_mandatory` |
| internal sections | 1 whole-doc section/doc, unclassified | **2508** revision-scoped classified sections (roles below) |
| relationship assertions | 1338 proposed + 1 revoked, derivation unrecorded | 1342 proposed tagged discovery-only (`folder_cartesian` 1070, `folder_placeholder_org` 272), 0 untagged; default trace/impact approved-only |
| two clocks | valid/recorded intervals effectively unused; `known_at` echoed | both clocks applied in revision selection, traversal, trace, impact, and the routed `compliance_requirement` |
| projections | corpus_snapshots / index_manifests empty | retrieval + graph generations recorded with canonical fingerprints, both FRESH @ `2b9b6e44…` |
| deployed route | stale (predated 7 commits), operator question UNRESOLVED ×4 | serving `5c7317ac`; all 8 foundation observations pass through HTTP |

## 2. Implemented file/symbol and migration map

| phase | files | substance |
| --- | --- | --- |
| P1 | `core/result_contract.py` (`truth_class_of_table`, `SOURCE_ROLES`, `AssessmentResult` dimensions, `documentary_alignment_of`, review projection), migration 8 | three truth classes; separated readiness/currency/applicability/alignment/evidence/review fields; U14–U17 codes; engineering triage split from SME queue |
| P2 | `core/nerc_source_sync.py` | fingerprinted official acquisition, lifecycle registry, failure-preserving refresh, immutable revisions |
| P3 | `core/regulatory_bundle.py`, `core/obligations.py` (rewrite), `core/duty_lineage.py`, migration 9 | complete bundle extraction with hash-verified spans; multi-atom decomposition with declared-list-only alternatives; semantic duty lineage; U14 hard gate |
| P4 | `core/internal_corpus.py`, `scripts/materialize_internal_corpus.py`, migration 10 (`document_number`/`version`/`owner`/`owner_title`, `source_sections.title`, `relationship_assertions.derivation`) | sourced control-block metadata; section-function classification; revision-scoped sections; derivation quarantine; commitment gating by section role |
| P5 | `core/temporal_selection.py`, `core/projections.py`, `scripts/rebuild_compliance_projections.py`, traversal clock predicates | two-clock selection with UNKNOWN_KNOWLEDGE semantics; canonical fingerprint + manifest generations + staleness verdicts |
| P6 | `compliance_bundle` + `compliance_sources(include_sections)` tools, `scripts/verify_foundation_routed.py` | routed acceptance surfaces; the eight observations with receipts |

## 3. Official acquisition manifest (P2, retained)

Registered immutable revisions (sha256 prefixes; full hashes in the store and
`data/private/nerc_official/`): `cip-007-6.pdf` `5b7820e7…` (byte-identical to
the register's pinned copy), `cip-007-6-implementation-plan.pdf` `8ff922d2…`,
`cip-007-7.1.pdf` `c7014e55…`, `cip-007-7.1-implementation-plan.pdf`
`39829090…`, `cip-007-7.1-technical-rationale.pdf` `6d1ebeb0…`, One-Stop-Shop
registry workbook `0adda91e…`. Sourced lifecycle: CIP-007-6 effective
2016-07-01, retires 2028-06-30; CIP-007-7.1 effective 2028-07-01 (FERC order
docket RM24-8-000). Identical re-acquisition is UNCHANGED (fingerprint-aware).

## 4. Source-role and temporal examples (routed)

- Patch procedure revision `LSPG-ADM-CIP007SPM` v11.0: `binding_effect`
  internally_mandatory; sections 3.1/3.3/3.5/3.6 `OPERATIVE_PROCEDURE`;
  Appendix 5.1 `TRACEABILITY_ASSERTION`; REVISION HISTORY `DOCUMENT_CONTROL`
  (receipt obs7).
- Temporal: `CIP-007-6 R2 Part 2.1` SELECTED at 2026-09-14 (valid 2016-07-01→
  2028-06-30, registry-sourced); FUTURE as CIP-007-7.1 at the same date;
  SELECTED at 2028-08-01 with store-resolved verbatim clauses; withheld as
  `UNKNOWN_KNOWLEDGE` at `known_at=2026-09-01` because the effectivity was
  only recorded 2026-09-15 — the two `known_at` answers genuinely differ
  (receipt obs2/obs4).

## 5. Decomposition/readiness inspection for R2.1–R2.4 (routed)

| Part | ready | measures | TB spans | slices | revision | bundle fingerprint |
| --- | --- | --- | --- | --- | --- | --- |
| 2.1 | READY | 2 | 3 | 7 | `5b7820e7…` | `41d80d09…` |
| 2.2 | READY | 2 | 3 | 8 | `5b7820e7…` | `8992cb26…` |
| 2.3 | READY | 2 | 3 | 8 | `5b7820e7…` | `596224ac…` |
| 2.4 | READY | 2 | 3 | 8 | `5b7820e7…` | `8e8b372f…` |

R2.2 carries the 35-calendar-day cadence; R2.3 preserves "one of the
following" alternatives (declared-list-only `ANY_OF`) and the mitigation-plan
sub-duty with its 35-day deadline and Part 2.2 dependency; R2.4 preserves the
"unless … approved by the CIP Senior Manager" exception (obs6). Store-level
inspection receipt (atoms 2/1/4/1, zero decomposition defects):
`coding_task/v9_compliance/private/regulatory_bundles/20260915T115230/inspection.json`.

## 6. Projection and Cartesian-mapping disposition

- Projections rebuilt from one canonical snapshot (`2b9b6e44…`): retrieval
  68 files / 2636 chunks with a live search proof (5 hits); graph 292 nodes /
  255 edges. Generations recorded in `index_manifests`; `projection_status`
  returns FRESH for both. Receipt:
  `coding_task/v9_compliance/private/projections/rebuild_20260915.json`.
- All 1342 legacy folder-derived proposals carry machine-readable derivation
  (`folder_cartesian` 1070 IMPLEMENTS, `folder_placeholder_org` 272 org
  edges). `impact.analyze` computes established impact from approved edges
  only; proposals surface separately as labeled `discovery_candidates`.
  Default trace is approved-only (obs8: default statuses ⊆ {approved};
  proposals visible only via explicit widening).
- Internal commitments: `extract_assertions` yields commitments only from
  operative roles — the copied R2 rows in the procedure's Appendix 1 produce
  zero commitments (hermetic tests + obs7 route exposure).

## 7. Tests and routed receipts

- Per-phase minimum gate at every code phase: `uv run ruff check .` clean ·
  `uv run ruff format --check .` clean · `uv run pytest tests/unit/ -q`
  progression 1848 → 1863 (P1) → 1880 (P2) → 1921 (P3) → 1948 (P4) →
  **1963 passed, 4 skipped** (P5/P6), plus the repo's complexity gate
  (ruff C901/PLR0912/PLR0915) enforced throughout, and the spine/wiki gates
  green on the committed tree.
- Routed receipt (the required P7 evidence):
  `coding_task/v9_compliance/private/foundation_routed/20260915T183311Z/routed_observations.json`
  — 8/8 observations pass against PID 64096 serving `5c7317ac`.
- Negative-readiness proofs (one per required component), migration
  non-destructiveness (v7→v10 on populated stores), restore/rollback, and
  two-clock replay tests live in `tests/unit/` (29 P4 + 15 P5 tests).

## 8. Lessons recurrence ledger (foundation rows)

| lesson | control | result |
| --- | --- | --- |
| L03 HTTP 200/hermetic ≠ acceptance | 8 routed HTTP observations with substantive assertions | **PASS** — receipt §7 |
| L04 latest-row vs run-ID | ID-scoped queries (existing suite, re-green) | PASS |
| L07 ingestion believed without proof | live search against the rebuilt index | **PASS** — 5 hits, §6 |
| L08 generic UNRESOLVED | controlled codes U14–U17 (P1) | PASS |
| L13 omitted bundle components | routed complete bundles incl. Measures/TB | **PASS** — obs5/6 |
| L18 copied row = implementation | section-role gating + route exposure | **PASS** — obs7 |
| L19 Cartesian mappings in trace/impact | derivation quarantine + approved-only impact | **PASS** — obs8 |
| L20 approval overrides comparison | no approval prerequisite anywhere on the reading path | PASS (behavior), regression Phase 5-report |
| L21 `known_at` echoed | UNKNOWN_KNOWLEDGE semantics routed | **PASS** — obs4 |
| L22 running service ≠ HEAD | managed restart, served commit recorded | **PASS** — header |
| L25 SME queue for engineering defects | review projection test (P1) | PASS |

## 9. Exit criteria (§7) — verification

1. Result/source/time contracts implemented and migrated on the populated
   store non-destructively — migrations 8/9/10 all proven on populated
   stores with pre-migration snapshots and restore. ✔
2. Official current+future CIP-007 material reproducible from stored hashes. ✔ (§3)
3. Complete R2 bundles with Parts, applicability, Measures, TB,
   definitions disposition, roles, lifecycle — routed, READY ×4. ✔ (§5)
4. Internal current revisions and section functions source-backed; missing
   metadata explicit (empty = absent, never guessed). ✔ (§4)
5. Both clocks affect routed results correctly. ✔ (obs2/obs4)
6. Placeholder/Cartesian relationships cannot appear as established trace or
   deterministic impact. ✔ (obs8 + impact tests)
7. Every readiness assertion has a negative test. ✔ (P3 negative suite + P4/P5)
8. Routed observations retained with exact run/source IDs. ✔ (receipt §7)
9. No operator/SME approval needed to make the foundation usable. ✔
10. Lessons ledger complete for P1–P6. ✔ (§8)

## 10. Known limitations (genuinely outside this task)

- The deployed reading path (the operator's UNRESOLVED ×4 question) is
  proven at Phase 10's live vertical slice; foundation proves the routed
  governing side, not the model judgment.
- CIP-007-7.1's implementation-plan PDF is the 2024 board version; the
  2028-07-01 effective date is sourced from the fingerprinted NERC registry.
- Live LanceDB catalog reconciliation (>10 tables, lesson L06) is retained
  for the Phase 16 final sweep; hermetic pagination regressions are green.
- Evidence artifacts (completed forms) are classified but unpopulated —
  actual performance evidence is an operator act, not an engineering one.

**Marker:** `PRODUCT_FOUNDATION_READY` — continue to the CIP-007 R2 vertical
slice (Phases 7–10). This is not product completion.
