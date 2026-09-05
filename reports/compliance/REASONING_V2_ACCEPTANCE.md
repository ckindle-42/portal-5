# TASK_COMPLIANCE_REASONING_V2 — Acceptance Record (P9)

Sanitized, public-safe. No corpus text, filenames stand in as document
identity handles only (LSPG-CIP is a public/sanitized reference corpus
already committed at `coding_task/v9_compliance/LSPG-CIP/`).

## Fingerprints

| Item | Value |
| --- | --- |
| Reviewed commit | `b5b68333fa65fad4ab58602486a8917d94314efa` |
| Schema version (`compliance_store.db`) | 4 (`portal/modules/compliance/core/migrations/schema.py`) |
| Register (`nerc_cip_register.json`) | 254 nodes, sha256 `c6a9508f6264ec81cc4b950584156d6246cdc60b60369f32f25962c9214dd81` |
| Canonical store (`compliance_store.db`) | sha256 `0e1ef3fd6e97808872f8de287105d3d676f8194a23edc00c638f3cfd22ed157` (snapshot at capture time — mutates on ingest) |
| Model (auto-compliance workspace) | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` (`Qwen3.8-27B-oQ4e-mtp`) |
| Compliance MCP | `portal-compliance`, port 8937, id `compliance` in `config/portal.yaml` mcp_fleet |
| Corpus | `coding_task/v9_compliance/LSPG-CIP/` — 68 files across 14 CIP standard subdirectories |
| Held standards swept | 14 (all standards with an entry in the register) |

Exact commands used to produce the fingerprints above:

```sh
git rev-parse HEAD
python3 -c "from portal.modules.compliance.core.migrations import CURRENT_SCHEMA_VERSION; print(CURRENT_SCHEMA_VERSION)"
shasum -a 256 portal/modules/compliance/data/nerc_cip_register.json
shasum -a 256 portal/modules/compliance/data/compliance_store.db
find coding_task/v9_compliance/LSPG-CIP -type f | wc -l
curl -s http://localhost:8937/health
```

## F01–F12 disposition

All twelve named design-assessment defects were fixed at the code level and
covered by `tests/unit/test_compliance_reasoning_v2_regressions.py` (11
tests, one per defect plus one combined case). Summary:

| ID | Defect | Fix | Status |
| --- | --- | --- | --- |
| F01 | `effective_parts`/`future_effective_parts` trusted lifecycle labels, not interval math | `engine.py` `_is_enforceable_at()` — interval-based | FIXED, unit-tested |
| F02 | Unrecognized version defaulted to `EFFECTIVE` | `cip_register.py` default lifecycle → `UNKNOWN` | FIXED, unit-tested |
| F03 | `_classify` collapsed unresolved into `FULL`/`NONE` | `coverage.py` `_classify()` always returns `UNRESOLVED` with a note; added `approved_mapping_ids` | FIXED, unit-tested, **live-verified** (14-standard sweep below) |
| F04 | Locatability conflated anchor-verification with relevance | `propose.py` split into `_verify_anchor()` / `_resolve_relevance()` | FIXED, unit-tested |
| F05 | Unit/qualifier normalization silently equated different meanings | `tiers.py` `_quant_claims()` no longer converts units; qualifier normalization only distinguishes "business" | FIXED, unit-tested, **live-verified** (Q12 scenario receipt) |
| F06 | No future/effective segregation for prospective content | `compliance_prospective` tool + `scenarios.py` `prospective:true` tagging | FIXED, unit-tested, **live-verified** (Q11 receipt) |
| F07 | `register_diff` treated genuine AND/OR swaps as cosmetic | `register_diff.py` `_cosmetic_equal()` only allows same-connector trailing removal; new `"logic"` sub_type | FIXED, unit-tested |
| F08 | Mixed-version diffs silently compared apples to oranges | `diff_standard()` raises `ValueError` on mixed standard-versions per side | FIXED, unit-tested, **live-verified** (Q05/Q06 receipt) |
| F09 | Rejecting a mapping didn't revoke prior approval | `mapping_store.py` `revoke()` + `compliance_review_decide` propagation | FIXED, unit-tested, **live-verified** (isolated propose→approve→revoke demo, see SME packet) |
| F10 | KeyError on a missing mapping target was swallowed | `compliance_review_decide` surfaces `mapping_error` | FIXED, unit-tested |
| F11 | No authenticated reviewer identity — any caller string was trusted | `core/auth.py` `verify_reviewer()`, `reviewer_token` param | FIXED, unit-tested |
| F12 | No document-revision integrity/drift detection | `compliance_sources` re-hashes on read, reports `verified`/`DRIFTED` | FIXED, unit-tested |

A01–A30 (the adversarial sub-checks named per question in the design table)
are exercised through the corresponding unit-test modules listed under "Q01–
Q12 implementation" below; none were skipped. No A-check required real
network access to nerc.com except the currency checks, which correctly
report `honest-BLOCKED` rather than fabricate when unreachable (unchanged
pre-existing behavior, re-verified this task).

## The twelve operator questions — routed analysis IDs

Every question below was executed against the **real** `portal-compliance`
MCP server (port 8937) and the real ingested LSPG-CIP corpus, not a fixture.
Raw JSON receipts (private — contain reference to internal document
filenames) are at
`portal/modules/compliance/data/private/receipts_2026-09-05/`.

| Q | Tool/route exercised | Receipt file | Real-corpus result | Disposition |
| --- | --- | --- | --- | --- |
| Q01 | `nerc_cip_requirement` (also live chat-completion Q01_raw*.json, 6 attempts) | `Q01_raw6.json` | Correct verbatim CIP-007-6 R2 Part 2.2 text, correct lifecycle/effectivity, no browser/web-search fallback after the tool-registry fix | **POSITIVE_REAL_VALIDATION** |
| Q02 | `compliance_mappings` | `Q02_mappings.json` | `count: 0` — no mapping has been proposed/approved in this environment yet; correctly reports an empty, not fabricated, set | **QUALIFIED_REAL_RESULT** (honest-empty) |
| Q03 | `compliance_route` | `Q03_route.json` | Intent classified `freeform`, honest `n_nodes_in_path: 0` — no governing-set answer manufactured without a declared scope/mapping | **QUALIFIED_REAL_RESULT** |
| Q04 | `compliance_gaps` | `Q04_gaps.json` + `Q04_raw1.json` (live chat) | Real scope resolution (`impact_present`, `associated_present`), zero confirmed FULL/PARTIAL/NONE gaps for CIP-007-6 in this corpus | **POSITIVE_REAL_VALIDATION** |
| Q05/Q06 | `compliance_change_impact` | `Q05_Q06_change_impact.json` | Real CIP-003-8→9 diff: 22 rows, 6 substantive / 16 cosmetic, by real change type | **POSITIVE_REAL_VALIDATION** |
| Q07 | `compliance_draft_revisions` | `Q07_draft_revisions.json` | `mode: specification_only` — correctly refuses to author binding policy text; 0 specifications because no mapping has been approved yet (honest-empty, consistent with Q02) | **QUALIFIED_REAL_RESULT** |
| Q08 | *(none)* | — | No dedicated tool exists. `constraints.py`/`comparison.py` primitives are unit-tested but not wired to a callable operator question. `tests/acceptance/test_compliance_reasoning_v2_questions.py::test_q08_*` is `xfail(strict=True)` so this gap fails loudly if silently "fixed" by an unrelated change without updating this record. | **NOT_BUILT** |
| Q09 | *(none)* | — | Same as Q08 — no dedicated tool. `xfail(strict=True)`. | **NOT_BUILT** |
| Q10 | `compliance_trace` | `Q10_trace.json` | `n_edges: 0` — the canonical repository's typed entity tables (`systems`, `roles`, `evidence_specs`, `entity_profiles`, `internal_controls`, `activities`) are schema-complete (P2 migrations) but **zero rows populated**; only document/relationship traversal is live | **QUALIFIED_REAL_RESULT** (schema built, not populated) |
| Q11 | `compliance_prospective` | `Q11_prospective.json` | `n_future_effective: 0` — honestly reports no known future-effective content in the register (consistent with `nerc_cip_currency`'s live finding of unabsorbed newer PDFs on nerc.com) | **QUALIFIED_REAL_RESULT** |
| Q12 | `compliance_scenario` | `Q12_scenario.json` | Real before/after coverage assessment for a synthetic 21-day tightening of CIP-007-6 R2 Part 2.2, isolated to the one target node (F05's fix applied) | **POSITIVE_REAL_VALIDATION** |

All twelve questions have *some* live route reachable through the
`⚖️ Portal Compliance Analyst` workspace's tool list — this was the P8
exit criterion and it holds. Two (Q08/Q09) reach a `NOT_BUILT` tool, not a
wrong answer — the distinction matters and is preserved by the `xfail`
gate above rather than by prose alone.

## Q01–Q12 implementation and test references

| Q | Core symbol(s) | Test module |
| --- | --- | --- |
| Q01 | `engine.py::_is_enforceable_at`, `cip_register.py::Register`, `compliance_mcp.py::nerc_cip_requirement` | `test_compliance_engine.py`, `test_cip_register.py`, `test_compliance_reasoning_v2_regressions.py` |
| Q02 | `mapping_store.py::MappingStore`, `compliance_mcp.py::compliance_mappings` | `test_compliance_reasoning_v2_regressions.py` |
| Q03 | `coverage.py::_classify`, `_qualified`, `compliance_route` | `test_compliance_engine.py`, `test_compliance_reasoning_v2_regressions.py` |
| Q04 | `coverage.py::coverage_matrix`, `tiers.py::detect_conflicts` | `test_compliance_engine.py`, `test_compliance_tiers.py` |
| Q05/Q06 | `register_diff.py::diff_standard`, `compliance_mcp.py::compliance_change_impact` | `test_compliance_reasoning_v2_regressions.py` (F07, F08 cases) |
| Q07 | `scenarios.py`, `compliance_mcp.py::compliance_draft_revisions`, change_pipeline `draft_revisions`/`impact_report` | `test_compliance_draft_revisions.py` |
| Q08 | *(none — see disposition table)* | `test_compliance_reasoning_v2_questions.py::test_q08_*` (xfail) |
| Q09 | *(none — see disposition table)* | `test_compliance_reasoning_v2_questions.py::test_q09_*` (xfail) |
| Q10 | `repository.py::traverse_relationships`, `compliance_mcp.py::compliance_trace` | `test_compliance_repository.py` |
| Q11 | `compliance_mcp.py::compliance_prospective`, `currency.py` | `test_compliance_prospective.py`, `test_compliance_currency.py` |
| Q12 | `scenarios.py::evaluate_scenario`, `comparison.py`, `constraints.py`, `compliance_mcp.py::compliance_scenario` | `test_compliance_scenarios.py`, `test_compliance_comparison.py`, `test_compliance_constraints.py` |

Positive / counterexample / uncertainty variants for each defect live in
`test_compliance_reasoning_v2_regressions.py` (one test class per F0x, each
carrying at minimum the positive case and the counterexample the fix
guards against).

## False-supported / false-gap / abstention

- The planted-corpus scorer (pre-existing, unchanged by this task except
  where F03/F04 touched shared code) reports **Full-Gap recall 1.0**,
  citation resolution **1.000**, over the 11 planted control classes —
  re-run this task, unchanged.
- The **real** 14-standard, 193-obligation sweep against LSPG-CIP produced
  **zero** `FULL`, **zero** `PARTIAL`, **zero** `NONE` verdicts — every
  item that could not be positively, anchor-verified resolved reported
  `UNRESOLVED` with a note, per F03's fix. This is the safety property F03
  exists to guarantee, confirmed at full real-corpus scale, not spot
  checks. Denominator: 193 = every `EFFECTIVE` Part across the 14 held
  standards as of 2026-09-05 (`effective_parts()` count), not a
  self-derived subset.
- **No false-supported claims were possible to construct** in this sweep
  because zero mappings are approved in this environment (`compliance_mappings`
  returns `count: 0` for every requirement tried) — coverage classification
  never had an approved mapping to trust, so it could not silently promote
  one to FULL. This is an honest, not a validated-empty, result: the
  precision half of the false-supported/false-gap pair is **untested
  against real approved mappings** because none exist yet. Recall-side
  (missed gaps) was fully exercised via the planted corpus above.
- Inspected sample size for the live sweep: all 193 obligations, not a
  subsample.

## Source freshness, remaining gaps, applicability limits

- `nerc_cip_currency` (unchanged mechanism, re-verified live): reports
  newer PDFs exist on nerc.com for at least one standard family not yet
  absorbed into the register — this is disclosed, not silently ignored,
  and is exactly what `compliance_prospective`'s `n_future_effective: 0`
  is honestly *not* claiming to have accounted for (currency ≠
  future-effectivity; they are two different questions and this task
  keeps them separate per design).
- The P2 canonical store (`compliance_store.db`) has `source_documents`,
  `document_revisions` (68 rows each — the full real corpus, migrated),
  `requirement_nodes` (254), `standard_revisions` (14), and
  `effectivity_assertions` (254) populated. `relationship_assertions`,
  `obligation_atoms`, `obligation_expressions`, `claims`,
  `internal_controls`, `entity_profiles`, `systems`, `roles`,
  `evidence_specs`, `activities`, `asset_groups`, `findings`,
  `work_items`, `policy_decisions`, `authority_assertions`,
  `scope_revisions`, `corpus_snapshots`, and `index_manifests` are **all
  zero rows**. Only `compliance_sources` and `compliance_trace` read the
  canonical store live; every other operator tool (`compliance_gaps`,
  `compliance_mappings`, `compliance_route`, `compliance_scenario`,
  `compliance_draft_revisions`, `compliance_prospective`) still reads the
  pre-existing in-memory `Register`/`MappingStore` JSON path. **This is the
  single largest unresolved architectural gap**: P2 built and
  ingested-tested the bitemporal store this task specified, but P3–P7's
  operator tools were not migrated to read/write through it — they were
  built (correctly, per the design's own tool signatures) against the
  faster-to-wire legacy stores. A future task should either migrate the
  remaining tools onto `Repository`, or explicitly declare the legacy
  JSON stores the production path and demote the unused canonical tables.
- Q02/Q03/Q07/Q11's "honest-empty" results above are a direct symptom of
  this: `compliance_mappings` reports `count: 0` because no SME has
  approved a mapping in `compliance_mappings.json`/`compliance_store.db`
  in this environment — not because the corpus lacks implementing
  documents. A real SME review pass (the SME packet below) is a genuine,
  not cosmetic, prerequisite to a non-empty Q02/Q07 answer.
- Applicability: `AssetScope` is operator-declared, unchanged this task;
  the live sweep used the queue-declared scope (`impact_present: [high,
  low, medium]`, `associated_present: [bcs, eacms, pacs, pca]`) recorded
  at `queue_item_id: ef4ec02b1aa5` — a real declared scope, not a default.

## Migration / review reversal / rollback receipts

- `migrate_legacy.import_document_directory()` was run against the real
  `LSPG-CIP` corpus: 68 files → 68 `source_documents` + 68
  `document_revisions`, idempotent by content hash (re-running produces no
  duplicate rows — unit-tested in `test_compliance_migrate_legacy.py`, and
  spot-checked live by re-running the import against the same corpus and
  confirming row counts unchanged).
- F09's revoke path was exercised live end-to-end on **isolated test
  data** (never the real 625-item production queue): propose → approve →
  `approved_for()` returns the row → revoke → `approved_for()` returns
  empty. Receipt: `portal/modules/compliance/data/private/receipts_2026-09-05/review_ui_isolated_demo.json`.
- No rollback of `compliance_store.db` itself was required or exercised
  this task (`Repository.backup_to()`/`restore_from()` are unit-tested,
  not live-exercised against the real store — noted as an unresolved
  production prerequisite below).

## Unresolved production prerequisites

1. Migrate `compliance_gaps`, `compliance_mappings`, `compliance_route`,
   `compliance_scenario`, `compliance_draft_revisions`,
   `compliance_prospective` onto the P2 `Repository` (currently only
   `compliance_sources`/`compliance_trace` are wired) — or explicitly
   retire the unused canonical tables. This is the honest, load-bearing
   gap in this task's close.
2. No SME has approved any mapping in this environment — Q02/Q03/Q07/Q11's
   "empty" answers are correct-but-unhelpful until a real review pass
   happens. See `SME_REVIEW_START_HERE.md`.
3. Q08 (intentional-strictness) and Q09 (unused-flexibility) have no
   dedicated MCP tool — `xfail(strict=True)` in the acceptance suite until
   built.
4. `Repository.backup_to()`/`restore_from()` have never been exercised
   against the live `compliance_store.db` in this environment.
5. The formal `--mode live-closeout` manifest/receipts CLI harness
   described in design §L1 was not built; this task's live verification
   used direct MCP/API calls with receipts saved to
   `portal/modules/compliance/data/private/receipts_2026-09-05/` as a
   pragmatic substitute.
6. `nerc_cip_currency` disclosed at least one unabsorbed newer standard
   PDF on nerc.com not yet reflected in the register.

## Final verification commands and results

```sh
uv run pytest tests/unit/ -q                                       # PASS (see gate log)
uv run ruff check .                                                 # PASS
uv run ruff format --check .                                        # PASS
uv run pytest tests/acceptance/test_compliance_reasoning_v2_questions.py -q
                                                                      # 9 passed, 2 xfailed (Q08/Q09) — LIVE STACK REQUIRED
```

`uv run mypy portal/`, the full `bash scripts/ci_local.sh`, and
`./scripts/smoke_stream.sh` ladder rungs were run earlier in this task's
commit sequence (each commit's own gate log); they are not re-run here to
avoid re-triggering the multi-minute pre-push hook purely for this
document — re-run before the next push per CLAUDE.md Rule 10.

## Engineering terminal status

**ENGINEERING_COMPLETE_WITH_DISCLOSED_GAPS.** All F01–F12 fixed and
unit-tested. All twelve design-§9 questions reach a live, real-corpus
route (Q08/Q09 correctly reach `NOT_BUILT`, not a wrong answer). The
14-standard/193-obligation sweep proves F03's core safety property at
real scale. The disclosed gaps above — legacy-store/canonical-store
wiring split, zero approved SME mappings, Q08/Q09, no live backup/restore
exercise, no formal closeout harness — are the genuine remaining work,
not hidden behind this record. **Working entry point**: OWUI at the
configured host port, workspace `⚖️ Portal Compliance Analyst`
(`auto-compliance`), or direct MCP calls to `http://localhost:8937/tools/<name>`.
**SME start-here**: `portal/modules/compliance/data/private/SME_REVIEW_START_HERE.md`
(gitignored, local-only, no credentials).
